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

def discover():
    key = os.environ["YOUTUBE_API_KEY"]
    videos = []
    for query in ("GTA 6 gameplay shorts", "GTA VI gameplay"):
        data = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "key": key, "part": "snippet", "q": query, "type": "video",
            "order": "date", "maxResults": 25,
            "videoDuration": "short" if "shorts" in query else "any"
        }, timeout=30)
        data.raise_for_status()
        for item in data.json().get("items", []):
            videos.append({"id": item["id"]["videoId"], "title": item["snippet"]["title"],
                           "url": "https://youtube.com/watch?v=" + item["id"]["videoId"]})
    return list({v["id"]: v for v in videos}.values())

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
    print("Dropbox account:", dbx.users_get_current_account().name.display_name)
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
        manifest.write_text(json.dumps({"candidates": candidates, "uploaded": uploaded}, indent=2))
        upload(dbx, manifest, folder + "/manifest.json")
    print("Uploaded clips:", len(uploaded))

if __name__ == "__main__":
    main()
