from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import socket
from typing import Optional

import psutil
from rich.console import Console
from rich.table import Table
import typer

app = typer.Typer(
    name= "portpeek",
    help= "inspect active listening ports and kill processes cleanly",
    no_args_is_help=True,
)
console = Console()

@dataclass
class PortEntry:
    port: int 
    protocol: str
    pid: int 
    process: int 
    memory_mb: float
    address: str
    
def _format_proto(family: socket.AddressFamily, sock_type: int) -> str:
    proto = "tcp" if sock_type == socket.SOCK_STREAM else "udp"
    if family == socket.AF_INET6:
        return f"{proto}6"
    return proto

def collect_listening_ports(
    port_filter: Optional[int] = None,
    name_filter: Optional[str] = None,
) -> tuple[list[PortEntry], int]:
    entries: list[PortEntry] = []
    seen: set[tuple[int, int, str]] = set()
    skipped_restricted = 0
    proc_cache: dict[int, tuple[str, float]] = {}
    
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN or not conn.laddr or conn.pid is None:
            continue
        
        port = conn.laddr.port
        if port_filter is not None and port != port_filter:
            continue
        
        proto = _format_proto(conn.family, conn.type)
        key = (port, conn.pid, proto)
        if key in seen:
            continue
        
        if conn.pid not in proc_cache:
            try:
                proc = psutil.Process(conn.pid)
                proc_name = proc.name()
                mem_mb = proc.memory_info().rss / (1024 * 1024)
                proc_cache[conn.pid] = (proc_name, round(mem_mb, 1))
            except psutil.AccessDenied:
                skipped_restricted += 1
                continue
            except psutil.NoSuchProcess:
                continue
            
        proc_name, mem_mb = proc_cache[conn.pid]
        if name_filter is not None and name_filter.lower() not in proc_name.lower():
            continue
        
        seen.add(key)
        entries.append(
            PortEntry(
                port=port,
                protocol=proto,
                pid=conn.pid,
                process=proc_name,
                memory_mb=mem_mb,
                address=conn.laddr.ip or "*",
            )
        )
    
    entries.sort(key=lambda item: (item.port, item.pid))
    return entries, skipped_restricted

@app.command("ls")
def list_ports(
    port: Optional[int] = typer.Option(None, "--port", "-p", help="filter by port number"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="filter by process name"),
    as_json: bool = typer.Option(False, "--json", help="output as json"),
) -> None:
    """Show processes listening on local ports"""
    entries, skipped = collect_listening_ports(port_filter=port, name_filter=name)
    
    if as_json:
        payload = {
            "ports": [asdict(e) for e in entries],
            "skipped_restricted": skipped,
        }
        print(json.dumps(payload, indent=2))
        return
    
    if not entries:
        console.print("[yellow]no matching listening ports found[/yellow]")
        if skipped:
            console.print(f"[dim]({skipped} restricted system process(es) skipped without admin rights)[/dim]")
        raise typer.Exit(code=0)
    
    table = Table(title="listeninig ports")
    table.add_column("port", style="bold cyan", justify="right")
    table.add_column("proto", style="dim")
    table.add_column("pid", style="magenta", justify="right")
    table.add_column("process", style="bold")
    table.add_column("RAM (mb)", justify="right")
    table.add_column("Bind", style="dim")
    
    for item in entries:
        table.add_row(
            str(item.port),
            item.protocol,
            str(item.pid),
            item.process,
            f"{item.memory_mb:.1f}",
            item.address,
        )
        
    console.print(table)
    if skipped:
        console.print(f"[dim]note: {skipped} restricted process(es) skipped due to permissions[/dim]")
        
@app.command("kill")
def kill_port(
    port: int = typer.Argument(..., help="port number whose listening process should be stopped"),
    force: bool = typer.Option(False, "--force", "-f", help="force kill the process immediately"),
    dry_run: bool = typer.Option(False, "--dry-run", help="show what would be killed without stopping anything"),
    yes: bool = typer.Option(False, "--yes", "-Y", help="skip confirmation prompt"),
) -> None:
    """stop the process listening oa a given local port"""
    entries, _ = collect_listening_ports(port_filter=port)
    
    if not entries:
        console.print(f"[yellow]No listening process found on port {port}[/yellow]")
        raise typer.Exit(code=1)
    
    target = entries[0]
    console.print(
        f"port [bold cyan]{target.port}[/bold cyan] ({target.protocol}) is used by "
        f"[bold]{target.process}[/bold] (PID [magenta]{target.pid})[/magenta], {target.memory_mb:.1f} mb"
    )
    
    if dry_run:
        action = "force-kill" if force else "terminate"
        console.print(f"[dim][dry-run] would {action} PID {target.pid} ({target.process})[/dim]")
        raise typer.Exit(code=0)
    
    if not yes:
        confirmed = typer.confirm (f"stop {target.process} (PID {target.pid})?")
        if not confirmed:
            console.print("[dim]cancelled[/dim]")
            raise typer.Exit(code=0)
        
    try:
        proc = psutil.Process(target.pid)
        if force:
            proc.kill()
        else:
            proc.terminate()
        proc.wait(timeout=3)
        console.print(f"[green]stopped {target.process} (PID {target.pid})[/green]")
    except psutil.NoSuchProcess:
        console.print(f"[yellow]process {target.pid} already existed[/yellow]")
    except psutil.AccessDenied:
        console.print(
            f"[red]permission denied[/red] when stopping PID {target.pid} "
            "try running the terminal as admin if u use windows"
        )
        raise typer.Exit(code=1)
    except psutil.TimeoutExpired:
        console.print(
            f"[yellow]process {target.pid} did not exit within 3s.[/yellow] Try again with [bold]--force[/bold]"
        )
        raise typer.Exit(code=1)