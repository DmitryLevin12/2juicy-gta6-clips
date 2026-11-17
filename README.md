# 2JUICY GTA VI clip pipeline

Manual-test mode initially. The workflow searches YouTube for GTA VI videos (Shorts first), checks Dropbox OAuth, creates a dated destination folder, and uploads a `manifest.json` discovery report.

## Test
Open **Actions → GTA VI discovery and Dropbox test → Run workflow**. The four repository secrets must be set: `YOUTUBE_API_KEY`, `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`.

## Video exports
`sources.json` begins empty. To enable MP4 export, supply an approved direct HTTPS MP4 URL and explicit permission evidence:
```json
{"sources":[{"id":"sample","source_url":"https://your-authorized-host.example/video.mp4","approved_hosts":["your-authorized-host.example"],"rights_cleared":true,"permission_note":"Owned footage or documented license","start_seconds":0,"duration_seconds":12}]}
```
Each clip is trimmed to 8–20 seconds, rendered vertical, muted and uploaded to `/2JUICY💦/01_Video/GTA 6 Clips/YYYY-MM-DD`.

This is **not yet** automatic video downloading from YouTube, AI highlight detection, or 10 clips guaranteed daily. YouTube discovery results are metadata only. No daily schedule is enabled until the manual test passes.
