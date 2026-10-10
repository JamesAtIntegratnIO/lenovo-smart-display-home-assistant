#!/usr/bin/env python3
"""Run text through a voice pipeline exactly as if it had been spoken at the display.

  ask.py "what's the first football game tomorrow"
"""
import asyncio, json, pathlib, sys, time, websockets
TOKEN = pathlib.Path("~/.hass_token").expanduser().read_text().strip()
PIPELINE = "01hmmxp6jjc996mawjb5xzepfg"   # Home Assistant Cloud
DEVICE = "549c40def793d18c19283c0859c88c68"  # Den display

async def ask(text):
    async with websockets.connect("ws://10.0.1.174:8123/api/websocket", max_size=None) as ws:
        await ws.recv(); await ws.send(json.dumps({"type": "auth", "access_token": TOKEN})); await ws.recv()
        t = time.time()
        await ws.send(json.dumps({"id": 1, "type": "assist_pipeline/run", "start_stage": "intent", "end_stage": "intent",
                                  "input": {"text": text}, "pipeline": PIPELINE, "device_id": DEVICE}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 90))
            if m.get("type") != "event": continue
            e = m["event"]
            if e["type"] == "intent-end":
                o = e["data"]["intent_output"]
                speech = " ".join((o["response"]["speech"].get("plain", {}).get("speech") or "").split())
                where = "local" if e["data"].get("processed_locally") else "AI"
                print(f"[{where}, {time.time()-t:.1f}s] {text}\n   -> {speech}")
            if e["type"] in ("run-end", "error"):
                if e["type"] == "error": print("ERROR", e["data"])
                break

for q in sys.argv[1:]:
    asyncio.run(ask(q))
