#!/usr/bin/env python3
"""Install (or remove) the temporary HLS guard as a Home Assistant dashboard resource.

See ha/frontend/hls_guard.js for what it does and why. It is only needed on Home Assistant
2026.10.0 (core issue 184775, fixed in 2026.10.1). After updating, run:  hls_guard.py remove

The script is registered as a `data:` URL so nothing has to be copied into Home Assistant's
config folder. It loads in every browser but only acts on the display (it checks the user agent).

  $AVB_PYTHON ha/hls_guard.py install | remove | status
"""
import asyncio, base64, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ha_ws import call

MARK = "data:text/javascript;base64,"
src = pathlib.Path(__file__).parent / "frontend" / "hls_guard.js"


def ours(res):
    if not res["url"].startswith(MARK):
        return False
    try:
        return b"__hlsGuard" in base64.b64decode(res["url"][len(MARK):])
    except Exception:
        return False


async def main(action):
    resources = (await call([{"type": "lovelace/resources"}]))[0]
    mine = [r for r in resources if ours(r)]
    if action == "status":
        print("installed" if mine else "not installed")
        return
    for r in mine:  # remove any earlier copy first, so install is repeatable
        await call([{"type": "lovelace/resources/delete", "resource_id": r["id"]}])
    if action == "install":
        url = MARK + base64.b64encode(src.read_bytes()).decode()
        await call([{"type": "lovelace/resources/create", "res_type": "module", "url": url}])
        print("installed")
    else:
        print("removed" if mine else "nothing to remove")

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "status"))
