#!/usr/bin/env python3
"""Keep a local copy of a shared Google Photos album for the display's screen saver.

Runs inside Home Assistant (installed to /config/kitchen_display/ by ha/photo_album.py and
called by a command_line sensor). Standard library only.

  album_sync.py "<shared album link>"     # empty link -> placeholder photos

Google's Photos API no longer lists albums an app did not create, so this reads the public
share page instead: it carries every picture's base address and size. Each picture is
downloaded once at screen size into /config/www/kitchen_display/, which Home Assistant
serves at /local/kitchen_display/ (no login needed on the local network, so the display
needs no internet access to show them). Pictures removed from the album are deleted here.

Prints one line of JSON for the sensor: {"count", "source", "updated", "error"}.
If the album cannot be read, the pictures already here are kept.
"""
import datetime, hashlib, json, os, pathlib, re, sys, urllib.parse, urllib.request

OUT = pathlib.Path(os.environ.get("ALBUM_OUT", "/config/www/kitchen_display"))
WEB = "/local/kitchen_display"
MAX_PHOTOS = 300
SIZE = "=w1024-h1024"       # longest side 1024: enough for a 1024x600 screen
MIN_SIDE = 400              # skips avatars and icons that share the page
PLACEHOLDERS = 12
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/138.0 Safari/537.36")
ALLOWED = {"photos.app.goo.gl", "photos.google.com"}
PHOTO = re.compile(r'\["(https://lh3\.googleusercontent\.com/pw/[A-Za-z0-9_\-]+)",(\d+),(\d+)')


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def album(url):
    """[(base address, width, height)] for every picture on the share page."""
    if urllib.parse.urlparse(url).hostname not in ALLOWED or not url.startswith("https://"):
        raise ValueError("not a Google Photos share link")
    html = fetch(url).decode("utf-8", "replace")
    seen, out = set(), []
    for base, w, h in PHOTO.findall(html):
        w, h = int(w), int(h)
        if base in seen or min(w, h) < MIN_SIDE:
            continue
        seen.add(base)
        out.append((base + SIZE, w, h))
    if not out:
        raise ValueError("no pictures found on the share page (is link sharing on?)")
    return out[:MAX_PHOTOS]


def placeholders():
    return [(f"https://picsum.photos/seed/kitchen{i}/1024/600", 1024, 600) for i in range(PLACEHOLDERS)]


def main():
    url = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if url in ("unknown", "unavailable", "None"):
        url = ""
    OUT.mkdir(parents=True, exist_ok=True)
    index = OUT / "photos.json"
    old = json.loads(index.read_text()) if index.exists() else {"photos": [], "source": "none"}
    source, error = ("album" if url else "placeholder"), ""
    try:
        wanted = album(url) if url else placeholders()
    except Exception as e:  # keep what is already here
        print(json.dumps({"count": len(old["photos"]), "source": old.get("source", "none"),
                          "updated": old.get("updated", ""), "error": f"{type(e).__name__}: {e}"[:200]}))
        return
    photos, keep = [], {"photos.json"}
    for src, w, h in wanted:
        name = ("ph-" if not url else "") + hashlib.sha1(src.encode()).hexdigest()[:16] + ".jpg"
        dest = OUT / name
        try:
            if not dest.exists() or dest.stat().st_size == 0:
                tmp = dest.with_suffix(".part")
                tmp.write_bytes(fetch(src))
                tmp.rename(dest)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"[:200]
            continue
        keep.add(name)
        photos.append({"src": f"{WEB}/{name}", "w": w, "h": h})
    if not photos:
        print(json.dumps({"count": len(old["photos"]), "source": old.get("source", "none"),
                          "updated": old.get("updated", ""), "error": error or "nothing downloaded"}))
        return
    updated = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    tmp = index.with_suffix(".part")
    tmp.write_text(json.dumps({"updated": updated, "source": source, "photos": photos}))
    tmp.rename(index)
    for f in OUT.iterdir():
        if f.name not in keep:
            f.unlink()
    print(json.dumps({"count": len(photos), "source": source, "updated": updated, "error": error}))


main()
