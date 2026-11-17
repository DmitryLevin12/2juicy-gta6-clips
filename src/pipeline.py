"""Discover GTA VI YouTube metadata and export explicitly approved direct MP4 sources."""
import datetime as dt
import json
import os
import pathlib
import subprocess
import tempfile
from urllib.parse import urlparse

import dropbox
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = "/2JUICY💦/01_Video/GTA 6 Clips"

def iso_seconds(value):
    """Parse the ISO 8601 durations returned by YouTube videos.list."""
    import re
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    return sum(int(x or 0) * factor for x, factor in zip(m.groups(), (3600, 60, 1))) if m else 0

def discover():
    """Shorts-first metadata discovery. Duration is not proof of vertical aspect ratio."""
    key = os.environ["YOUTUBE_API_KEY"]
    found = {}
    for query, priority in (("GTA 6 gameplay shorts", 2), ("GTA VI gameplay", 1)):
        response = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "key": key, "part": "snippet", "q": query, "type": "video",
            "order": "date", "maxResults": 25,
            "videoDuration": "short" if priority == 2 else "any"
        }, timeout=30)
        response.raise_for_status()
        for item in response.json().get("items", []):
            vid = item["id"]["videoId"]
            title = item["snippet"]["title"]
            title_lower = title.lower()
            if not any(term in title_lower for term in ("gta 6", "gta vi", "grand theft auto vi", "grand theft auto 6")):
                continue
            if any(term in title_lower for term in ("gta 5", "gta v ", "gta online", "gta 4")):
                continue
            if vid not in found:
                found[vid] = {"id": vid, "title": title, "url": "https://youtube.com/watch?v=" + vid,
                              "published_at": item["snippet"].get("publishedAt"), "shorts_query": priority == 2}
            else:
                found[vid]["shorts_query"] |= priority == 2
    ids = list(found)
    for i in range(0, len(ids), 50):
        response = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
            "key": key, "part": "contentDetails,status", "id": ",".join(ids[i:i+50])
        }, timeout=30)
        response.raise_for_status()
        for item in response.json().get("items", []):
            v = found[item["id"]]
            v["duration_seconds"] = iso_seconds(item["contentDetails"].get("duration"))
            v["embeddable"] = item.get("status", {}).get("embeddable", False)
            v["short_candidate"] = 0 < v["duration_seconds"] <= 180
            v["score"] = (30 if v["short_candidate"] else 0) + (20 if v["shorts_query"] else 0)
            v["vertical_verified"] = False
            v["rights_verified"] = False
    return sorted((v for v in found.values() if "duration_seconds" in v),
                  key=lambda v: (v["score"], v["published_at"] or ""), reverse=True)

def read_seen(dbx):
    try:
        _, response = dbx.files_download(DEST + "/discovery_state.json")
        return set(json.loads(response.content).get("seen_ids", []))
    except dropbox.exceptions.ApiError as exc:
        if exc.error.is_path() and exc.error.get_path().is_not_found():
            return set()
        raise

def save_seen(dbx, ids):
    content = json.dumps({"seen_ids": sorted(ids)}, indent=2).encode()
    dbx.files_upload(content, DEST + "/discovery_state.json",
                     mode=dropbox.files.WriteMode.overwrite)

def approved(s):
    url = urlparse(s.get("source_url", ""))
    return (s.get("rights_cleared") is True and bool(s.get("permission_note"))
            and url.scheme == "https" and url.hostname in s.get("approved_hosts", []))

def ensure_folder(dbx, path):
    cur = ""
    for part in path.strip("/").split("/"):
        cur += "/" + part
        try:
            dbx.files_create_folder_v2(cur)
        except dropbox.exceptions.ApiError as e:
            if not (e.error.is_path() and e.error.get_path().is_conflict()):
                raise

def upload(dbx, local, path):
    with open(local, "rb") as f:
        dbx.files_upload(f.read(), path, mode=dropbox.files.WriteMode.overwrite)

def main():
    candidates = discover()
    print("YouTube discovery:", len(candidates), "candidates; metadata only")
    sources = [s for s in json.loads((ROOT / "sources.json").read_text()).get("sources", []) if approved(s)]
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=os.environ["DROPBOX_REFRESH_TOKEN"],
        app_key=os.environ["DROPBOX_APP_KEY"],
        app_secret=os.environ["DROPBOX_APP_SECRET"])
    print("Dropbox account:", dbx.users_get_current_account().name.display_name)\n    seen = read_seen(dbx)\n    fresh = [v for v in candidates if v["id"] not in seen]\n    print("New candidates:", len(fresh), "Previously seen:", len(candidates) - len(fresh))
    folder = DEST + "/" + dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    ensure_folder(dbx, folder)
    uploaded = []
    with tempfile.TemporaryDirectory() as d:
        work = pathlib.Path(d)
        for index, s in enumerate(sources[:10], 1):
            try:
                src = work / "source.mp4"
                out = work / "clip.mp4"
                response = requests.get(s["source_url"], timeout=60, allow_redirects=False)
                response.raise_for_status()
                if len(response.content) > 200_000_000:
                    raise ValueError("Source too large")
                src.write_bytes(response.content)
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(max(0, float(s.get("start_seconds", 0)))),
                    "-i", str(src), "-t", str(min(20, max(8, float(s.get("duration_seconds", 12))))),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
                name = f"{index:02d}_{s.get('id','clip')}.mp4"
                upload(dbx, out, folder + "/" + name)
                uploaded.append({"file": name, "source": s["source_url"], "permission": s["permission_note"]})
            except Exception as exc:
                print("Source skipped:", s.get("id"), type(exc).__name__, str(exc)[:120])
        manifest = work / "manifest.json"
        manifest.write_text(json.dumps({"candidates": fresh[:25], "uploaded": uploaded, "note": "Short candidates are not verified vertical or rights-cleared"}, indent=2))
        upload(dbx, manifest, folder + "/manifest.json")\n        save_seen(dbx, seen | {v["id"] for v in fresh})
    print("Uploaded clips:", len(uploaded))

if __name__ == "__main__":
    main()
