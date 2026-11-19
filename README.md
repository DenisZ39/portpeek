# portpeek

A clean, cross platform CLI to inspect active listening ports and stop processes safely.

## features 

- List listening ports with process name, PID, protocol, address, and mem usage ('portpeek ls')
- Filter by ('--port') or process name ('--name'), or export machine readable output ('--json')
- Inspect and stop processes on a port with confirmation, '--dry-run', '--force' and '--yes' ('portpeek kill <port>')

## demo
![portpeek ls output](assets.demo_ls.png)
![portpeek ls by port](assets.demo_ls_by_port.png)
![portpeek kill by port](assets.demo_kill_by_port.png)


## install 

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1  # or: source .venv/bin/activate
pip install -e .
