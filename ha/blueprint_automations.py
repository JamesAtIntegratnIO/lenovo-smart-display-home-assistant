#!/usr/bin/env python3
"""Recreate the automations that are instances of View Assist blueprints, plus the
Seahawks default-team automation.

These were first created by hand on 2026-10-09; this file records exactly what was sent
so they can be rebuilt. It has not been re-run since (the automations already exist), so
treat it as a record first and a script second.
"""
import json, subprocess, sys

MA_ENTRY = "01M4HGGHSCR4A11QKH597KY6KP"   # Music Assistant config entry id


def post(automation_id, config):
    out = subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                          f"/api/config/automation/config/{automation_id}", json.dumps(config)],
                         capture_output=True, text=True).stdout.strip()
    print(automation_id, out)


def blueprint(alias, description, path, inputs):
    return {"alias": alias, "description": description, "use_blueprint": {"path": path, "input": inputs}}


post("view_assist_alarms_reminders_timers", blueprint(
    "View Assist - Alarms Reminders Timers",
    "Voice timers, alarms and reminders shown on View Assist displays",
    "dinki/blueprint-alarmsreminderstimers.yaml", {"use_vaca_onboard_sound": True}))

post("view_assist_get_sports_scores", blueprint(
    "View Assist - Get Sports Scores",
    "Voice sports scores shown on View Assist displays",
    "dinki/blueprint-getsportsscores.yaml",
    {"team_tracker": "sensor.team_tracker", "trigger_phrases": [
        "how did [the] {team} do",
        "(what is | what's) the score of the {team} (game | match)",
        "how (is | are) [the] {team} doing",
        "how (is | are) [the] {team} (game | match) [going]",
        # added: the ways people actually ask
        "(get | show [me] | tell me | what is | what's) [the] {team} score[s]",
        "(get | show [me] | tell me | what is | what's) [the] score[s] (of | for) [the] {team} [(game | match)]",
        "did [the] {team} win",
        "(is | are) [the] {team} winning",
        "when (do | does) [the] {team} play [next]",
        "when is the [next] {team} (game | match)",
        "who (do | does) [the] {team} play [next]",
    ]}))

post("view_assist_play_music", blueprint(
    "View Assist - Play Music with Music Assistant",
    "Voice music requests played through Music Assistant on View Assist displays",
    "dinki/blueprint-playmusicwithmusicassistant.yaml",
    {"ma_instance": MA_ENTRY, "view_path": "/smart-display/music",
     # The default also has "play some {artist} [music]", which treats every "play some X" as an
     # artist ("play some oldies" played an artist called "Oldies Playing"). Without it those
     # go to the AI, which picks artist or genre and calls the script in ha/music_tool.py.
     "play_artist_command": "(play the artist {artist} | play [some] (music | songs) by {artist})"}))

# The sports blueprint repoints one shared tracker at whichever team was asked about. Put it
# back on the Seahawks afterwards so requests with no team named ("get sports scores") report on them.
post("smart_display_sports_default_team", {
    "alias": "Smart Display - Sports default team (Seahawks)",
    "description": "After a voice question about another team, point the shared tracker back at the Seahawks",
    "triggers": [{"trigger": "template",
                  "value_template": "{{ state_attr(\"sensor.team_tracker\",\"team_abbr\") not in [\"SEA\", none] }}",
                  "for": "00:01:30"}],
    "actions": [{"action": "teamtracker.call_api", "target": {"entity_id": "sensor.team_tracker"},
                 "data": {"sport_path": "football", "league_path": "nfl", "team_id": "SEA"}}],
    "mode": "single"})
