#!/usr/bin/env python3
"""Tiny Home Assistant WebSocket client for dashboard work.

Reads the long-lived token from ~/.hass_token (override with HASS_TOKEN_FILE) and
talks to HASS_URL (default http://10.0.1.174:8123). Usage:

  ha_ws.py call '<json message without id>'      # one WS command, prints the result as JSON
  ha_ws.py save-dashboard <url_path> <file.yaml> # replace a dashboard's config from YAML
"""
import asyncio, json, os, pathlib, sys

import websockets
import yaml

HA = os.environ.get("HASS_URL", "http://10.0.1.174:8123").rstrip("/")
TOKEN_FILE = pathlib.Path(os.environ.get("HASS_TOKEN_FILE", "~/.hass_token")).expanduser()


async def call(messages):
    url = HA.replace("http", "ws", 1) + "/api/websocket"
    async with websockets.connect(url, max_size=64 * 1024 * 1024) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN_FILE.read_text().strip()}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("Home Assistant rejected the token")
        out = []
        for i, msg in enumerate(messages, 1):
            await ws.send(json.dumps({**msg, "id": i}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == i and r.get("type") == "result":
                    break
            if not r.get("success"):
                sys.exit(f"{msg.get('type')}: {r.get('error')}")
            out.append(r.get("result"))
        return out


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "call":
        print(json.dumps(asyncio.run(call([json.loads(sys.argv[2])]))[0], indent=1))
    elif len(sys.argv) == 4 and sys.argv[1] == "save-dashboard":
        config = yaml.safe_load(pathlib.Path(sys.argv[3]).read_text())
        asyncio.run(call([{"type": "lovelace/config/save", "url_path": sys.argv[2], "config": config}]))
        print(f"saved {sys.argv[2]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
