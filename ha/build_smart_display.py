#!/usr/bin/env python3
"""Build the Smart Display dashboard (1024x600 touch screen) from the main Overview.

Reads an Overview config dump (JSON) and writes ha/smart-display.yaml. Cards whose
actions already exist on the Overview (quick actions, roof themes, back yard looks)
are copied from it by name so the two never drift apart in behaviour.

  build_smart_display.py work/ha/overview.json ha/smart-display.yaml
"""
import copy, json, sys
import yaml

overview = json.load(open(sys.argv[1]))


def section_cards(view_path, heading):
    view = next(v for v in overview["views"] if v.get("path") == view_path)
    for s in view.get("sections", []):
        cards = s.get("cards", [])
        if any(c.get("type") == "heading" and c.get("heading") == heading for c in cards):
            return [copy.deepcopy(c) for c in cards if c.get("type") not in ("heading", "markdown")]
    raise SystemExit(f"section {heading!r} not found in view {view_path!r}")


def heading(text, icon=None):
    h = {"type": "heading", "heading": text, "heading_style": "title"}
    if icon:
        h["icon"] = icon
    return h


def tile(entity, name=None, icon=None, features=None, toggle=False, cols=6, rows=1, **extra):
    c = {"type": "tile", "entity": entity, "grid_options": {"columns": cols, "rows": rows}}
    if name:
        c["name"] = name
    if icon:
        c["icon"] = icon
    if features:
        c["features"] = features
    if toggle:
        c["tap_action"] = {"action": "toggle"}
        c["icon_tap_action"] = {"action": "toggle"}
    c.update(extra)
    return c


def big(cards, cols=6, rows=2):
    """Make copied buttons/tiles finger sized."""
    for c in cards:
        c["grid_options"] = {"columns": cols, "rows": rows}
    return cards


def section(title, cards, icon=None, span=1):
    s = {"type": "grid", "cards": [heading(title, icon)] + cards}
    if span > 1:
        s["column_span"] = span
    return s


NAV = [  # (view path, icon)
    ("home", "mdi:home"), ("lights", "mdi:lightbulb-group"), ("cameras", "mdi:cctv"),
    ("outside", "mdi:home-roof"), ("music", "mdi:music"), ("media", "mdi:television-play"),
    ("sports", "mdi:football"),
]


def nav_strip(current):
    """One slim row of icon buttons across the top of a view, replacing the hidden HA top bar."""
    cards = []
    for path, icon in NAV:
        card = {"type": "button", "icon": icon, "show_name": False, "show_state": False,
                "tap_action": {"action": "navigate", "navigation_path": f"/smart-display/{path}"},
                "grid_options": {"columns": 3, "rows": 1}}
        if path == current:
            card["card_mod"] = {"style": "ha-card { background: var(--primary-color); --state-inactive-color: white; --state-icon-color: white; }"}
        cards.append(card)
    return {"type": "grid", "column_span": 2, "cards": cards}


def camera(entity, name):
    # Snapshot that refreshes on the card; tap opens the live stream full size.
    return {"type": "picture-entity", "entity": entity, "name": name, "camera_view": "auto",
            "show_state": False, "tap_action": {"action": "more-info"},
            "grid_options": {"columns": 12, "rows": 4}}


light = lambda e, n: tile(e, n, toggle=True)
fan = lambda e, n="Fan": tile(e, n, toggle=True)

# ---------------------------------------------------------------- Home
TIMERS_MD = """{% set timers = state_attr('sensor.den_display', 'timers') or [] %}
{% if timers | length == 0 %}
<ha-icon icon="mdi:timer-off-outline"></ha-icon> No timers or alarms
{% else %}
{% for t in timers %}
{% set mins = ((as_timestamp(t.expires) - as_timestamp(now())) / 60) | round(0, 'ceil') | int %}
## <ha-icon icon="mdi:{{ 'alarm' if t.timer_class == 'alarm' else 'timer-outline' }}"></ha-icon> {{ t.name or t.timer_class | title }} · {{ mins }} min · {{ t.expiry.time }}
{% endfor %}
{% endif %}"""

home = {
    "title": "Home", "path": "home", "icon": "mdi:home", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "badges": [
        {"type": "entity", "entity": "weather.forecast_home"},
        {"type": "entity", "entity": "lock.front_door_2", "name": "Front"},
        {"type": "entity", "entity": "lock.back_door", "name": "Back"},
        {"type": "entity", "entity": "binary_sensor.g4_doorbell_pro_poe_doorbell", "name": "Doorbell"},
        {"type": "entity", "entity": "sensor.my_ecobee_humidity", "name": "Humidity"},
    ],
    "sections": [
        section("Now", [
            {"type": "clock", "clock_size": "large", "show_seconds": False,
             "grid_options": {"columns": 12, "rows": 2}},
            tile("climate.my_ecobee", "Thermostat", features=[{"type": "target-temperature"}],
                 cols=12, rows=2, tap_action={"action": "more-info"}),
            # View Assist keeps voice timers and alarms on its sensor; list them here.
            {"type": "markdown", "grid_options": {"columns": 12},
             "content": TIMERS_MD},
        ], "mdi:clock-outline"),
        section("Quick actions", big(section_cards("home", "Quick actions")) + [
            tile("lock.front_door_2", "Front door", features=[{"type": "lock-commands"}], rows=2),
            tile("lock.back_door", "Back door", features=[{"type": "lock-commands"}], rows=2),
        ], "mdi:gesture-tap"),
    ],
}

# ---------------------------------------------------------------- Lights
lights = {
    "title": "Lights", "path": "lights", "icon": "mdi:lightbulb-group", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "sections": [
        section("Living areas", [
            light("light.living_room_light_1", "Living room"), fan("fan.living_room_fan", "Living fan"),
            light("light.kitchen_light", "Kitchen"), light("light.pantry_lights", "Pantry"),
            light("light.dining_room_light", "Dining"), light("light.hallway_light_1", "Hallway"),
            light("light.front_hall_light", "Front hall"), light("light.front_entry_light", "Front entry"),
            light("light.laundry_room_light", "Laundry"), light("light.garage_light", "Garage"),
        ], "mdi:sofa"),
        section("Master suite", [
            light("light.master_bed_light", "Bedroom"), fan("fan.master_bed_fan", "Bedroom fan"),
            light("light.master_bath_light", "Bath"), fan("fan.master_bath_fan", "Bath fan"),
            light("light.master_shower_light", "Shower"), light("light.master_tub_light", "Tub"),
            light("light.master_toilet_light", "Toilet"), fan("fan.master_toilet_fan", "Toilet fan"),
            light("light.master_closet_light", "Closet"), light("light.master_office", "Office"),
        ], "mdi:bed-king"),
        section("Kids", [
            light("light.kids_bedroom_1_light_1", "Kid 1"), fan("fan.kids_bedroom_1_fan", "Kid 1 fan"),
            light("light.kids_bedroom_2_light_1", "Kid 2"),
            light("light.front_bathroom_light_1", "Bath 1"), light("light.front_bathroom_light_2", "Bath 2"),
            fan("fan.front_bathroom_fan", "Bath fan"),
        ], "mdi:teddy-bear"),
    ],
}

# ---------------------------------------------------------------- Cameras
# Medium resolution channels: this display decodes at most 1920x1088 H.264.
cameras = {
    "title": "Cameras", "path": "cameras", "icon": "mdi:cctv", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "sections": [
        # One full-width 2x2 grid so each picture stays wide instead of a tall crop.
        {"type": "grid", "column_span": 2, "cards": [
            camera("camera.front_doorbell_medium_resolution_channel", "Doorbell"),
            camera("camera.front_driveway_medium_resolution_channel", "Driveway"),
            camera("camera.front_landscape_medium_resolution_channel", "Landscape"),
            camera("camera.back_yard_medium_resolution_channel", "Back yard"),
        ]},
    ],
}

# ---------------------------------------------------------------- Outside
outside = {
    "title": "Outside", "path": "outside", "icon": "mdi:home-roof", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "sections": [
        section("Lights", [
            tile("light.exterior_lights", "All exterior", "mdi:outdoor-lamp", toggle=True, cols=12),
            light("light.front_porch_light", "Front porch"), light("light.driveway_light", "Driveway"),
            light("light.back_porch_light", "Back porch"), light("light.pergola", "Pergola"),
            tile("light.roof", "Roof", toggle=True, cols=12),
        ], "mdi:outdoor-lamp"),
        section("Roof themes", big(section_cards("outside", "Roof themes"), cols=3, rows=2),
                "mdi:palette", span=2),
        section("Back yard looks", big(section_cards("outside", "Back yard looks"), cols=4, rows=2),
                "mdi:grass"),
    ],
}

# ---------------------------------------------------------------- Media
media = {
    "title": "Media", "path": "media", "icon": "mdi:television-play", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "sections": [
        section("Living room TV", [
            {"type": "media-control", "entity": "media_player.living_room_tv",
             "grid_options": {"columns": 12}},
        ], "mdi:television"),
        section("Vacuum", [
            tile("vacuum.x40_ultra", "X40 Ultra", cols=12, rows=2,
                 features=[{"type": "vacuum-commands",
                            "commands": ["start_pause", "stop", "return_home", "locate"]}]),
        ], "mdi:robot-vacuum"),
    ],
}

# ---------------------------------------------------------------- Sports
sports = {
    "title": "Sports", "path": "sports", "icon": "mdi:football", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "sections": [
        {"type": "grid", "column_span": 2, "cards": [
            {"type": "custom:teamtracker-card", "entity": "sensor.seahawks",
             "show_league": True, "show_rank": True, "outline": False,
             "grid_options": {"columns": "full"}},
        ]},
    ],
}

# ---------------------------------------------------------------- Music
# Shown by voice music requests in place of View Assist's own music screen.
MUSIC_PLAYER = "media_player.vaca_ha0000xx_media_player_2"
music = {
    "title": "Music", "path": "music", "icon": "mdi:music", "type": "sections",
    "max_columns": 2, "dense_section_placement": True,
    "sections": [
        {"type": "grid", "column_span": 2, "cards": [
            {"type": "media-control", "entity": MUSIC_PLAYER, "grid_options": {"columns": "full", "rows": 5}},
            # System-wide volume, the same level the physical rocker moves
            tile("number.vaca_ha0000xx_music_volume", "Volume", "mdi:volume-high",
                 features=[{"type": "numeric-input", "style": "slider"}], cols=24, rows=2),
        ]},
    ],
}

# ---------------------------------------------------------------- Screen saver
# Full-screen photo slideshow with a clock (a dim clock alone when the room is dark). Not in the navigation row: the "Smart Display - Screen saver"
# automation (ha/screen_saver.py) opens it when nobody is there. The card is ha/frontend/kitchen_saver.js.
saver = {
    "title": "Screen saver", "path": "saver", "icon": "mdi:image-multiple", "type": "panel",
    "cards": [{"type": "custom:kitchen-saver-card", "interval": 20, "fade": 2, "device": "sensor.den_display",
               # room dark: a dim clock on black instead of the pictures
               "dark_entity": "input_boolean.kitchen_display_dark"}],
}

views = [home, lights, cameras, outside, music, media, sports]
for v in views:
    v["sections"].insert(0, nav_strip(v["path"]))
config = {"views": views + [saver]}
yaml.safe_dump(config, open(sys.argv[2], "w"), sort_keys=False, allow_unicode=True, width=120)
print("views:", ", ".join(v["path"] for v in config["views"]))
