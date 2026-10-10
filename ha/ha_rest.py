#!/usr/bin/env python3
"""Minimal Home Assistant REST helper: ha_rest.py METHOD /api/path ['<json body>']"""
import json, os, pathlib, sys, urllib.request

HA = os.environ.get("HASS_URL", "http://10.0.1.174:8123").rstrip("/")
TOKEN = pathlib.Path(os.environ.get("HASS_TOKEN_FILE", "~/.hass_token")).expanduser().read_text().strip()

method, path = sys.argv[1], sys.argv[2]
body = sys.argv[3].encode() if len(sys.argv) > 3 else None
req = urllib.request.Request(HA + path, data=body, method=method,
                             headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print(json.dumps({"http_error": e.code, "body": e.read().decode()[:2000]}))
    sys.exit(1)
