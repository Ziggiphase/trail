# Trail

**Small daily decisions, made visible.** Trail runs quietly in your system tray,
counts the time you spend in the apps you choose (VS Code, terminals, Docker,
Jupyter…), and turns it into a GitHub-style trail of green squares, with a daily
goal, streaks and per-app breakdowns. Your history is saved to a free cloud
Postgres database (Neon recommended).

## Install on Windows

**Build the installer once on your PC (about 3 minutes):**
1. Double-click **`BUILD-INSTALLER.bat`**. It finds your Python (python.org or
   Anaconda), bundles Trail, installs the free Inno Setup tool via winget if
   needed, and opens the `dist` folder.
2. Double-click **`dist\Trail-Setup.exe`**. No admin rights needed. You get a
   Start Menu entry, start-at-sign-in, an optional desktop shortcut, and a
   normal uninstaller in Settings → Apps.

`Trail-Setup.exe` can be copied to any other Windows PC; Python isn't needed there.

**Or let GitHub build it:** push this folder to a GitHub repository. The workflow
in `.github/workflows` builds the installer on every push; download it from the
*Actions* tab, or from *Releases* if you push a tag such as `v1.0.0`.

## Using Trail

| Page | What it's for |
|---|---|
| **Dashboard** | Today vs your goal, this week, streak, last 30 days, last 7 days chart, today by app, and your year trail |
| **Activity** | Whole-year graph; click any day to see which apps you worked in; monthly totals; best streak |
| **Tracked apps** | Switch apps on/off, **Add apps** (open now, used recently, type a name, or browse for an `.exe`), edit, remove; one-click add for apps you used recently |
| **Settings** | Daily goal, streak minimum, idle timeout, start at sign-in, notifications, cloud database, export to CSV |

- **Pause** (top right or tray menu): 30 min, 1 h, 2 h, until tomorrow, or until you resume.
- **Browser rules:** edit an app and set *"Only count when the window title contains"*,
  e.g. Chrome with `JupyterLab, Colab`, so only notebook time counts.
- **Notifications:** one when you reach your daily goal, and an evening reminder
  (time is up to you) if your streak is at risk.
- Closing the window keeps Trail running in the tray (bottom-right; click ^ if
  hidden). Right-click the tray icon to quit.

## Connect the free database

1. Sign up at neon.tech → create a project → **Connect** → copy the connection string.
2. In Trail: **Settings → Cloud sync**, paste it, click **Test**, then **Save & connect**.

Until you connect, Trail keeps your time on this PC and uploads it once connected.
Use the same link on other computers and give each one its own name; totals are combined.

## Built in, so you don't have to think about it

- **Idle detection:** time stops counting after 2 minutes (configurable) without
  keyboard or mouse input; sleep and hibernate are never counted.
- **Nothing gets lost:** unsynced minutes are saved to a small file every minute and
  uploaded later, so a crash, power cut or offline day doesn't lose time.
- **No double counting:** only one copy of Trail can run at a time.
- **Privacy:** only app names and durations per day are stored. Window titles are
  read only to check your rules and never saved; no keystrokes or screenshots.
- **Your data is yours:** export everything to CSV from Settings.

Files on your PC: settings in the registry (`HKCU\Software\Trail`); log and the
unsynced buffer in `%LOCALAPPDATA%\Trail`.

## Run from source

```bash
pip install -r requirements.txt
python run_trail.py
```

## Project layout

```
trail/
  app.py        main window, tray, pause, sync, notifications
  pages.py      Dashboard, Activity, Tracked apps, Settings
  dialogs.py    Add apps / Edit app
  widgets.py    cards, toggle switch, goal ring, charts
  heatmap.py    year graph
  tracker.py    what counts (pure logic, tested)
  activity.py   foreground window, idle time, open apps (Windows/macOS/Linux)
  storage.py    Postgres sync      outbox.py  crash-safe buffer
  stats.py      streaks, totals    settings.py  saved settings, start at sign-in
  theme.py, icons.py   look and feel
packaging/      icon + Inno Setup script
build.ps1, BUILD-INSTALLER.bat
```
