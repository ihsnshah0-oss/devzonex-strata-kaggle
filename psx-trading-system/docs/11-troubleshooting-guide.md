# 11 — Troubleshooting Guide (fix common problems)

## Dashboard looks broken (no clock, dead buttons, Settings won't load)

Do these 3 checks in order — they fix 95% of cases:

**1. Are you on the right address?**
You must open `http://localhost:8111` (server running). If you double-clicked
`index.html` directly, the page cannot work — a red warning banner will tell you.
Start the server first (guide 01, Step 4), then use the `http://` address.

**2. Hard-refresh your browser (clears old saved files).**
After any update, your browser may show yesterday's page with today's brain
(or the reverse) and buttons die silently. Press:
- Windows: `Ctrl + Shift + R` · Mac: `Cmd + Shift + R` · Phone: close the tab fully, reopen.
- The page footer of the code is versioned (`?v=1.1.0`) so this gets rarer over time.

**3. Run the built-in health check.**
Open ⚙ Settings → scroll to **🩺 Health check** → **Run health check**.
- `Server API: OK` + times shown → system is fine; tell us which exact button fails.
- `Server API: FAILED` → the server stopped. Restart it (guide 01, Step 4).
- Any red `⚠️ Error:` popup → copy its exact words when asking for help.

## 'uvicorn' is not recognized (Windows error)

**What it means:** Windows cannot find the `uvicorn` program. One of 3 causes:

1. Libraries were never installed (the `pip install` step was skipped).
2. Installed, but Python's Scripts folder is not on PATH ("Add python.exe to
   PATH" was unticked during Python install — the #1 Windows mistake).
3. More than one Python on the PC — `pip` put packages in a different Python
   than the one running your command.

**Fix (pick one):**

- **Easiest:** double-click **`RUN.BAT`** in the project folder. It installs
  the packages and uses `python -m uvicorn`, which bypasses PATH completely.
- **Manual:** run these 2 commands inside the project folder:
  ```powershell
  python -m pip install -r requirements.txt
  python -m uvicorn src.app.server:app --host 0.0.0.0 --port 8111
  ```
  (`python -m ...` always works; bare `uvicorn` needs PATH luck.)
- **Permanent:** reinstall Python and tick **"Add python.exe to PATH"** on the
  first install screen.

## Server won't start

**`No module named 'fastapi'` (or pandas/psxdata/…)**
→ You skipped installing. Run inside the project folder:
```bash
pip install -r requirements.txt
```

**`Address already in use` / port 8111 busy**
→ Something already uses port 8111. Either stop it, or use another port:
```bash
uvicorn src.app.server:app --host 0.0.0.0 --port 8001
```
Then open `http://localhost:8001`.

**`python` not recognized (Windows)**
→ Reinstall Python and tick **"Add python.exe to PATH"**.

## Dashboard problems

**Page loads but shows "Loading…" forever**
→ The server terminal shows the real error. Common cause: no internet for the
first data download. Connect to the internet and refresh.

**A stock shows "Failed to load"**
→ Wrong symbol (check spelling on the Home → market tables), or DPS is down.
Try again in a few minutes. You can also clear cache (below).

**Chart is empty**
→ Stock may be newly listed (<60 days history). Indicators need history.

**Research says HOLD with low confidence**
→ Not a bug — it means bull and bear evidence are balanced. That *is* the answer.

## Data problems

**Numbers look old**
→ Cache may be serving saved data. Force refresh:
```bash
python3 -c "from src.data import psx_client as psx; psx.clear_cache()"
```
Then refresh the page. (Next load will be slower — it re-downloads.)

**News tab is empty**
→ RSS feeds may be temporarily blocking. Wait 30 minutes (cache expiry) and retry.
Check your internet can open `https://www.dawn.com` in a browser.

**Screener is slow the first time**
→ Normal — it downloads each symbol's history once. Pre-warm it:
```bash
python3 scripts/warm_cache.py 150
```
Later runs take seconds.

**Reddit mentions empty**
→ Normal — Reddit often blocks automated requests. News sentiment still works.

## Phone problems

**Phone can't open the page**
→ Check: (1) same Wi-Fi as laptop, (2) server running, (3) correct IP
(re-run `ipconfig` / `hostname -I` — IPs change), (4) include `:8111`,
(5) laptop firewall allows Python (Windows asks on first run — click Allow).

## Paper trading

**"Insufficient paper cash/holdings"**
→ Fake account limits, working as designed. Reduce qty, or Reset to Rs 1,000,000.

**Want to move diary to a new laptop?**
→ Copy the file `data/psx.db` to the new computer's `data/` folder.

## Still stuck?

1. Copy the **last 20 lines** of the server terminal (the error).
2. Note what you clicked and which stock.
3. Check `FAQ.md`, then ask with those details.
