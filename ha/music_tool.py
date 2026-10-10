#!/usr/bin/env python3
"""Give the AI conversation agent a real way to play music, and tell it what is real.

Fixed phrases ("play some X", "start the X playlist") are handled locally by View Assist's
blueprint. Anything looser ("play Stone Temple Pilots", "play something relaxing") falls
through to the AI, which had no music tool and so apologised and even retracted the local
replies. This creates a script the AI can call, exposes it and the display's player to
voice, and updates the agent's prompt.
"""
import json, pathlib, subprocess, sys

PLAYER = "media_player.vaca_ha0000xx_media_player_2"


def rest(method, path, body=None):
    args = [sys.executable, "ha/ha_rest.py", method, path] + ([json.dumps(body)] if body is not None else [])
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def play(extra):
    return {"action": "music_assistant.play_media", "target": {"entity_id": PLAYER},
            "data": {"media_id": "{{ query }}", "enqueue": "replace",
                     "radio_mode": "{{ radio_mode | default(false) }}", **extra}}


script = {
    "alias": "Play music on the den display",
    "description": ("Search Spotify and the music library through Music Assistant and start playing the best "
                    "match on the den display's speaker. Use this for any request to play music: an artist, a "
                    "song, an album, a playlist, or a mood or genre. This is the only way to start music."),
    "icon": "mdi:music",
    "mode": "restart",
    "fields": {
        "query": {"name": "Query", "required": True,
                  "description": "What to play, for example 'Stone Temple Pilots', 'Plush by Stone Temple Pilots', or 'relaxing jazz'.",
                  "selector": {"text": {}}},
        "media_type": {"name": "Media type", "required": False,
                       "description": "Set when the request is clearly one of these; leave empty to let the search decide.",
                       "selector": {"select": {"options": ["artist", "album", "track", "playlist", "radio"]}}},
        "radio_mode": {"name": "Keep playing similar music", "required": False,
                       "description": "True to continue with similar music after the match finishes. Use for moods and genres.",
                       "selector": {"boolean": {}}},
    },
    "sequence": [
        {"choose": [{"conditions": [{"condition": "template",
                                     "value_template": "{{ media_type is defined and media_type | length > 0 }}"}],
                     "sequence": [play({"media_type": "{{ media_type }}"})]}],
         "default": [play({})]},
        # Show the dashboard's music view on the display (instead of View Assist's own music screen)
        {"action": "view_assist.navigate", "data": {"device": "sensor.den_display", "path": "/smart-display/music"}},
    ],
}
print("script:", rest("POST", "/api/config/script/config/den_display_play_music", script))

prompt = """You are the voice assistant for this home, speaking through a smart display in the den.
Answer in one or two short spoken sentences in plain text. No markdown, lists or emoji.
Use the available tools to control or check devices, and never say a device changed unless the tool call succeeded.
For anything current (sports schedules and scores, weather beyond the home sensors, news), look it up rather than guessing, and say so briefly if you could not find it.

Some requests are handled before they reach you by automations in this home: timers and alarms, showing cameras, sports scores, switching screens, and fixed music phrases such as "play some ...". Their replies appear earlier in this conversation as assistant messages without any tool call. Those actions really happened. Never retract, correct or apologise for them.

Music: to play anything, call the "Play music on the den display" script with what was asked for. It searches Spotify. Music plays on the den display itself, whose player is named "Den display"; use that player to pause, resume, skip or stop. Do not use the Spotify or TV media players for music requests unless asked by name.

The household's NFL team is the Seattle Seahawks.
The current time is {{ now().strftime('%A, %B %-d %Y, %-I:%M %p') }}.
"""
pathlib.Path("work/claude_prompt.txt").write_text(prompt)
ENTRY, SUB = "01M4HGNSMY8B0C54JP827YY0FJ", "01M4HGNSMYM66CB3PQENA3K3ZZ"
flow = json.loads(rest("POST", "/api/config/config_entries/subentries/flow", {"handler": [ENTRY, "conversation"], "subentry_id": SUB}))
fid = flow["flow_id"]
step = json.loads(rest("POST", f"/api/config/config_entries/subentries/flow/{fid}",
                       {"prompt": prompt, "llm_hass_api": ["assist"], "recommended": False}))
step = json.loads(rest("POST", f"/api/config/config_entries/subentries/flow/{fid}",
                       {"chat_model": "claude-haiku-5-5", "prompt_caching": "prompt"}))
step = json.loads(rest("POST", f"/api/config/config_entries/subentries/flow/{fid}",
                       {"max_tokens": 1024, "thinking_effort": "low", "code_execution": False, "web_search": True,
                        "web_search_max_uses": 2, "user_location": True, "web_fetch": False, "web_fetch_max_uses": 1}))
print("agent:", step.get("type"), step.get("reason"))
