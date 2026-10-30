# 01 — Installation Guide (Windows, Mac, Linux)

Follow only the part for your computer. Total time: about 10 minutes.

---

## Step 1 — Install Python 3.11 or newer

**Windows:**
1. Go to `https://www.python.org/downloads/` and download Python 3.11+ (3.12 or 3.13 is fine).
2. During install, **tick the box "Add python.exe to PATH"**. This is the #1 mistake — do not skip it.
3. Open **PowerShell** and check:
```powershell
python --version
```
You should see `Python 3.12.x` or similar.

**Mac:**
```bash
# install Homebrew first (from https://brew.sh), then:
brew install python@3.12
python3 --version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install -y python3 python3-pip
python3 --version
```

---

## Step 2 — Copy the project folder

Copy the whole `psx-trading-system` folder to your computer, e.g. `Documents/`.
Then open a terminal **inside** that folder:

**Windows (PowerShell):**
```powershell
cd "$HOME\Documents\psx-trading-system"
```

**Mac/Linux:**
```bash
cd ~/Documents/psx-trading-system
```

---

## Step 3 — Install the free libraries (one time)

```bash
pip install -r requirements.txt
```
(On Mac/Linux you may need `pip3 install -r requirements.txt`.)

This installs: `psxdata` (PSX data), `fastapi` + `uvicorn` (server),
`pandas`, `yfinance`, `feedparser`, and friends. All free and open-source.

---

## Step 4 — Start the system

**Mac/Linux:**
```bash
./run.sh
```
**Windows (easiest):** double-click **`INSTALL.BAT`** once (checks/installs
Python + all packages), then double-click **`RUN.BAT`** whenever you want
the dashboard — it starts the server and opens the browser by itself.
**`STOP.BAT`** stops it. Want it on every boot? Run **`AUTORUN-ON.BAT`** once
(and **`AUTORUN-OFF.BAT`** to undo).

**Windows (manual):**
```powershell
python -m uvicorn src.app.server:app --host 0.0.0.0 --port 8111
```

Open your browser at: **http://localhost:8111** 🎉

Keep this terminal window open while you use the system. To stop it, press `Ctrl + C`.

---

## Step 5 — Warm the cache (one time, recommended)

This pre-downloads data so screens and charts feel instant. Takes a few minutes:

```bash
python3 scripts/warm_cache.py 150
```
(Windows: `python scripts/warm_cache.py 150`)

---

## How to check everything works

1. Home page shows KSE-100 value and 25 watchlist stocks → data OK.
2. Click OGDC → chart loads → history OK.
3. Click "Research Desk" → verdict appears → brains OK.
4. Open `http://localhost:8111/docs` → you see the API list → server OK.

If something fails, see `11-troubleshooting-guide.md`.
