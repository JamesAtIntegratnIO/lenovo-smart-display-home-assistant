#!/usr/bin/env python3
"""Give the AI conversation agent a way to put a web page on the owner's phone.

A recipe or a how-to is no use read aloud in two sentences. The agent's prompt (in
music_tool.py) tells it to web search for general requests, name the site it picked, and then
call this script with that page's URL, so the full page is one tap away on the phone.
"""
import json, subprocess, sys

NOTIFY = "notify.mobile_app_your_phone"   # the owner's phone, the only mobile app registered
SCRIPT = "send_link_to_phone"


def rest(method, path, body=None):
    args = [sys.executable, "ha/ha_rest.py", method, path] + ([json.dumps(body)] if body is not None else [])
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


script = {
    "alias": "Send a link to the owner's phone",
    "description": ("Send a web page to the owner's phone as a notification that opens the page when tapped. Use it "
                    "after a web search for a recipe, a how-to, a product or anything else worth reading in "
                    "full. The url must be the exact address of that page from the search results. It returns "
                    "whether the link was sent."),
    "icon": "mdi:cellphone-link",
    "mode": "queued",
    "fields": {
        "url": {"name": "URL", "required": True,
                "description": ("The full https address of the specific page, copied exactly from the web search "
                                "results. Never a site's home page and never an address you composed yourself."),
                "selector": {"text": {}}},
        "title": {"name": "Title", "required": True,
                  "description": "The page's name and the site it is on, for example 'Southern Peach Cobbler - Allrecipes'.",
                  "selector": {"text": {}}},
        "summary": {"name": "Summary", "required": False,
                    "description": "One short sentence on what the page is.",
                    "selector": {"text": {}}},
    },
    "sequence": [
        {"variables": {"link": "{{ url | default('') | trim }}"}},
        {"if": [{"condition": "template", "value_template": "{{ not (link.startswith('https://') or link.startswith('http://')) }}"}],
         "then": [{"variables": {"result": {"sent": False, "error": "url must be a full http or https address"}}},
                  {"stop": "bad url", "response_variable": "result"}]},
        {"action": NOTIFY,
         "data": {"title": "{{ title }}",
                  "message": "{{ summary | default('', true) or link }}",
                  "data": {"clickAction": "{{ link }}", "channel": "Kitchen display links",
                           "actions": [{"action": "URI", "title": "Open", "uri": "{{ link }}"}]}}},
        {"variables": {"result": {"sent": True, "to": "the owner's phone"}}},
        {"stop": "sent", "response_variable": "result"},
    ],
}
print("script:", rest("POST", f"/api/config/script/config/{SCRIPT}", script))
expose = {"type": "homeassistant/expose_entity", "assistants": ["conversation"],
          "entity_ids": [f"script.{SCRIPT}"], "should_expose": True}
print("expose:", subprocess.run([sys.executable, "ha/ha_ws.py", "call", json.dumps(expose)],
                                capture_output=True, text=True).stdout.strip())
