#!/usr/bin/env python3
"""Give the AI conversation agent a real way to play music, and tell it what is real.

Fixed phrases ("play music by X", "start the X playlist") are handled locally by View Assist's
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


MA_ENTRY = "01M4HGGHSCR4A11QKH597KY6KP"   # Music Assistant config entry id

# A genre, era or mood is not a thing Spotify can play, and a free search for one lands on
# whatever happens to be named after it ("oldies" found a stock-music artist called "Oldies
# Playing"). So for those, search playlists only and rank them: Spotify's own editorial
# playlists (ids 37i9dQZF1D...) first, then its genre mixes (37i9dQZF1E..., but not the
# per-song "... Radio" ones, 37i9dQZF1E8), then everything else. Within a tier, a name that
# contains every word asked for wins, then Spotify's own search order.
PICK = """{% set words = (query | lower | regex_replace('[^a-z0-9 ]', ' ')).split() %}
{% set ns = namespace(rows=[]) %}
{% for p in found.playlists | default([]) %}
  {% set id = p.uri.split('/') | last %}
  {% set name = p.name | lower %}
  {% set named = words | select('in', name) | list | length == words | length %}
  {% set tier = 0 if id.startswith('37i9dQZF1D') else 1 if id.startswith('37i9dQZF1E') and not id.startswith('37i9dQZF1E8') else 2 %}
  {% set ns.rows = ns.rows + [[tier, 0 if named else 1, loop.index, p]] %}
{% endfor %}
{{ (ns.rows | sort | first | default([0, 0, 0, none]))[3] }}"""

# Anything else goes to Music Assistant as asked; it picks the best match of that type.
DIRECT = """{% set d = {'media_id': query, 'enqueue': 'replace', 'radio_mode': radio_mode | default(false) | bool} %}
{% set d = dict(d, media_type=media_type) if media_type | default('') not in ['', 'genre'] else d %}
{{ dict(d, artist=artist) if artist | default('') | length > 0 else d }}"""


def player(action, data):
    return {"action": action, "target": {"entity_id": PLAYER}, "data": data}


script = {
    "alias": "Play music on the den display",
    "description": ("Search Spotify through Music Assistant and start playing on the den display's speaker. Use this "
                    "for any request to play music: an artist, a song, an album, a named playlist, or a genre, era "
                    "or mood. This is the only way to start music. It returns what it started; say that."),
    "icon": "mdi:music",
    "mode": "restart",
    "fields": {
        "query": {"name": "Query", "required": True,
                  "description": ("What to play. An artist, album, song or playlist name on its own, without the "
                                  "words 'music', 'songs' or 'playlist'. For a genre, era or mood, the plain name "
                                  "a radio station would use: 'oldies', 'classic rock', '90s hip hop', 'jazz', "
                                  "'relaxing piano'."),
                  "selector": {"text": {}}},
        "media_type": {"name": "Media type", "required": True,
                       "description": ("'genre' for any genre, style, era, decade, mood or activity (oldies, country, "
                                       "80s, dinner music, something relaxing), even when the word could also be "
                                       "an artist name. 'artist', 'album', 'track' or 'playlist' when that is what "
                                       "was named. 'radio' only for a broadcast radio station."),
                       "selector": {"select": {"options": ["genre", "artist", "album", "track", "playlist", "radio"]}}},
        "artist": {"name": "Artist", "required": False,
                   "description": "For a track or album, the artist if one was named. Leave empty otherwise.",
                   "selector": {"text": {}}},
        "radio_mode": {"name": "Keep playing similar music", "required": False,
                       "description": "True to continue with similar music after an artist, album or track finishes.",
                       "selector": {"boolean": {}}},
    },
    "sequence": [
        {"variables": {"pick": None, "result": None}},
        {"if": [{"condition": "template", "value_template": "{{ media_type | default('') == 'genre' }}"}],
         "then": [{"action": "music_assistant.search", "response_variable": "found",
                   "data": {"config_entry_id": MA_ENTRY, "name": "{{ query }}", "media_type": ["playlist"], "limit": 20}},
                  {"variables": {"pick": PICK}}]},
        {"if": [{"condition": "template", "value_template": "{{ pick is mapping }}"}],
         "then": [player("media_player.shuffle_set", {"shuffle": True}),
                  player("music_assistant.play_media", {"media_id": "{{ pick.uri }}", "media_type": "playlist", "enqueue": "replace"}),
                  {"variables": {"result": {"started": "{{ pick.name }}", "kind": "Spotify playlist, shuffled"}}}],
         # Shuffle an artist or playlist so it does not open on the same song every time; an album or
         # a single track plays as asked.
         "else": [player("media_player.shuffle_set", {"shuffle": "{{ media_type | default('') in ['artist', 'playlist'] }}"}),
                  player("music_assistant.play_media", DIRECT),
                  {"variables": {"result": {"started": "the best match for {{ query }}"}}}]},
        # Show the dashboard's music view on the display (instead of View Assist's own music screen)
        {"action": "view_assist.navigate", "data": {"device": "sensor.den_display", "path": "/smart-display/music"}},
        {"stop": "started", "response_variable": "result"},
    ],
}
print("script:", rest("POST", "/api/config/script/config/den_display_play_music", script))

# The local phrases ("play music by X", "start the X playlist") are View Assist's blueprint, which
# never touches shuffle, so the queue keeps whatever the last request left. Turn shuffle on as
# soon as that automation fires; it searches before it plays, so this lands first.
print("shuffle:", rest("POST", "/api/config/automation/config/smart_display_shuffle_local_music", {
    "alias": "Smart Display - Shuffle local music requests",
    "description": "Turn shuffle on when View Assist's music blueprint handles a request, so artists and playlists do not always start on the same song",
    "triggers": [{"trigger": "state", "entity_id": "automation.view_assist_play_music_with_music_assistant",
                  "attribute": "last_triggered"}],
    "actions": [player("media_player.shuffle_set", {"shuffle": True})],
    "mode": "single"}))

prompt = """You are the voice assistant for this home, speaking through a smart display in the den.
Answer in one or two short spoken sentences in plain text. No markdown, lists or emoji.
Use the available tools to control or check devices, and never say a device changed unless the tool call succeeded.
For anything current (sports schedules and scores, weather beyond the home sensors, news), look it up rather than guessing, and say so briefly if you could not find it.

Some requests are handled before they reach you by automations in this home: timers and alarms, showing cameras, sports scores, switching screens, and fixed music phrases such as "play music by ...". Their replies appear earlier in this conversation as assistant messages without any tool call. Those actions really happened. Never retract, correct or apologise for them.

Music: to play anything, call the "Play music on the den display" script. It searches Spotify. Always set its media type. When what was asked for is a genre, style, era, decade, mood or activity (oldies, country, 80s rock, jazz, something relaxing, dinner music), use the media type "genre" with the plain genre name as the query, and never guess an artist or playlist for it yourself. Use "artist", "album", "track" or "playlist" only when that is what was named. Then say what the script reports it started. Music plays on the den display itself, whose player is named "Den display"; use that player to pause, resume, skip or stop. Do not use the Spotify or TV media players for music requests unless asked by name.

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
