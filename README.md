# Rating UI

Local web app for reviewing model prediction images on Windows. Reviewers mark images where the model predicted incorrectly, and the app exports the selected images as a `.zip` package with both `manifest.json` and `manifest.csv` for the training team.

## Multi-user mode (v2)

The app now supports a task-based, role-based workflow:

- **L1 (Reviewer / Assigner)** — creates tasks, assigns them to L2 annotators, runs QC, returns or approves submissions, and exports approved task ZIPs. L1 also manages users at `/admin/users`.
- **L2 (Annotator)** — sees tasks assigned to them on the dashboard, opens one to review images, submits for QC when finished, and fixes any returned tasks.

Task lifecycle: `draft → assigned → in_progress → submitted → in_qc ↔ returned → approved → exported`.

### First-time setup

```powershell
# 1. create the SQLite DB
python -m app.cli init-db

# 2. create the first L1 admin (prompts for password)
python -m app.cli create-user --username admin --role L1 --display-name "Admin"

# 3. (optional) seed an L2 annotator
python -m app.cli create-user --username alice --role L2 --display-name "Alice"
```

Then run the app and sign in at `/login`:

```powershell
python -m uvicorn app.main:app --reload
```

Subsequent users can be created from the L1 admin page at `/admin/users` (the **⚙ Users** link in the top nav).

### Setting the session secret

For production / shared deployments, set a stable cookie-signing key so sessions survive restarts:

```powershell
$env:RATING_UI_SECRET_KEY = "<long random string>"
```

If the env var is missing, the app warns at startup and uses an insecure dev key.



## Stack

- Backend: `FastAPI`
- UI: server-rendered HTML with local Bootstrap styling and small vanilla JavaScript for a responsive review workflow
- State persistence: JSON autosave per folder under `%LOCALAPPDATA%\\RatingUI\\states`

## Features

- Native Windows folder picker for selecting the image folder
- Browser-side folder import so users can choose a folder directly from their PC in the web page
- Resume per-folder review state automatically
- Review states: `unreviewed`, `correct`, `wrong`
- Filter views: `all`, `reviewed`, `unreviewed`, `selected`
- Progress tracking with reviewed and selected counters
- Autosave of both review decisions and last UI position/filter
- Export selected images only as a zip bundle
- Export selected filenames only as a plain text list
- Manifest output in both JSON and CSV
- Export manifest includes target/original image mapping for Label Studio style follow-up workflows
- Keyboard shortcuts for faster review

## Supported image formats

`jpg`, `jpeg`, `png`, `bmp`, `webp`, `gif`, `tif`, `tiff`

## Quick Start on Windows

### 1. Create a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If `py` is not available on that machine, use:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Run the app

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`

## Run on Central PC for LAN Users

If this project is hosted on the central Windows PC with IP `192.168.120.231`, run it on port `8081` so other users in the same LAN can use the same URL.

### Option 1. Use the provided launcher

```powershell
.\run_lan.ps1
```

Or double-click [run_lan.bat](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/run_lan.bat)

### Option 2. Run manually

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8081
```

Users in the LAN should then open:

`http://192.168.120.231:8081`

### Windows Firewall

If other users cannot connect, allow inbound TCP port `8081` on the central PC:

```powershell
New-NetFirewallRule -DisplayName "Rating UI 8081" -Direction Inbound -Protocol TCP -LocalPort 8081 -Action Allow
```

### Important Behavior in LAN Mode

- `Choose Folder` opens a folder dialog on the central PC only, not on each user's PC.
- `Load Path` reads a path on the central PC only.
- For users on other PCs, the correct option is `Import Folder From PC` because it uploads the selected folder from their browser to the central server.
- Export still downloads the generated zip back to the user's browser as usual.

### Internal Hostname Instead of Raw IP

If you want users to open a friendly internal URL such as `http://rating-ui.infra.local` instead of `http://192.168.120.231:8081`, use a reverse proxy in front of the FastAPI app.

Recommended on this Windows central PC:

- `IIS` reverse proxy to `http://127.0.0.1:8081`

Included files:

- [deployment/iis/enable_iis_prereqs.ps1](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/deployment/iis/enable_iis_prereqs.ps1)
- [deployment/iis/setup_iis_proxy.ps1](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/deployment/iis/setup_iis_proxy.ps1)
- [deployment/iis/add_hosts_entry.ps1](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/deployment/iis/add_hosts_entry.ps1)
- [deployment/iis/web.config](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/deployment/iis/web.config)
- [deployment/nginx/rating-ui.conf](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/deployment/nginx/rating-ui.conf)
- [deployment/README.md](C:/Users/infra/OneDrive%20-%20Infra%20Plus%20Co%20Ltd/Learning/RS26/rating_UI/deployment/README.md)

Typical IIS setup:

1. Keep the app running on the central PC:

```powershell
.\run_lan.ps1
```

2. Configure IIS reverse proxy:

```powershell
.\deployment\iis\enable_iis_prereqs.ps1
.\deployment\iis\setup_iis_proxy.ps1 -HostName "rating-ui.infra.local" -FrontendPort 80 -ServerIp "192.168.120.231"
```

Important:

- Restart Windows after `enable_iis_prereqs.ps1` if it says `RestartNeeded : True`
- Prefer running the IIS scripts from Windows PowerShell as Administrator; the scripts now try to relaunch there automatically if started from PowerShell 7

3. Point `rating-ui.infra.local` to `192.168.120.231` in internal DNS.

If you do not have internal DNS yet, add a temporary `hosts` entry on each client:

```text
192.168.120.231 rating-ui.infra.local
```

You can also use the helper PowerShell script on any Windows machine:

```powershell
.\deployment\iis\add_hosts_entry.ps1 -HostName "rating-ui.infra.local" -ServerIp "192.168.120.231"
```

After that, LAN users can open:

`http://rating-ui.infra.local`

## How to Use

1. Load images in one of three ways:
   - Click `Choose Folder` to open a Windows folder dialog on the local machine
   - Click `Import Folder From PC` to choose a folder directly from the browser
   - Paste a folder path and click `Load Path`
2. Set `Target image path` before zip export:
   - Click `Choose Target Folder`
   - Or paste the path directly and click `Save Target Path`
3. The app scans the folder recursively for supported images.
4. Review each image:
   - `Mark Correct`: image is reviewed and not exported
   - `Mark Wrong / Export`: image is reviewed and added to the export set
   - `Clear`: reset the image back to `unreviewed`
5. Use filters on the left to focus on `reviewed`, `unreviewed`, or `selected` images.
6. Export one of two ways:
   - `Export Selected Zip`: prediction images + JSON/CSV manifest + target mapping
   - `Export Selected TXT`: only selected prediction filenames, one filename per line

## Keyboard Shortcuts

- `A` or `Left Arrow`: previous image
- `D` or `Right Arrow`: next image
- `C`: mark correct
- `W`: mark wrong
- `U`: clear review state

## Export Format

The exported zip contains:

- `manifest.json`
- `manifest.csv`
- `images/...` containing only the images marked `wrong`

Manifest fields:

- `index`
- `filename`
- `relative_path`
- `source_path`
- `target_filename`
- `target_relative_path`
- `target_source_path`
- `decision`
- `reviewed_at`

## TXT Export Format

- Exports only the selected prediction filenames
- One filename per line
- Example:

```text
tst1.jpg
test2.jpg
```

## Target Image Mapping

- The `Target image path` should point to the original image folder that will be used downstream for retraining or Label Studio import.
- Export uses the same `relative path` under both folders to map files.
- Example:
  - prediction image: `predictions/camera_a/frame001.jpg`
  - target image path: `D:\dataset\images`
  - mapped target image: `D:\dataset\images\camera_a\frame001.jpg`
- Export is blocked if any selected image does not have a matching target image under the target path.

## Autosave Behavior

- Review decisions are saved immediately after every change.
- The current filter and current image are also saved, so reopening the same folder resumes close to the previous working position.

## Notes

- The app is designed for local use on the same Windows machine as the image files.
- Image scanning is recursive, so nested subfolders are included.
- If a previously reviewed image is removed from disk, the app ignores it on the next load.
- Browser-imported folders are copied into `%LOCALAPPDATA%\\RatingUI\\imports` so the review session and export flow work the same as normal local folders.
