# 12 — Developer Guide (extend the system)

Code map (every file has one job):

```text
src/data/psx_client.py    download + cache PSX data
src/data/news.py          RSS headlines
src/data/investify.py     Investify.pk news + PSX announcements (free, no key)
src/data/sentiment.py     word-mood scorer + reddit
src/analysis/indicators.py   all maths (RSI, MACD, SMAs…)
src/analysis/researcher.py   bull/bear/debate/verdict
src/analysis/strategy.py     votes + trader + proposal
src/analysis/risk.py         sizing + safety checks
src/backtest/engine.py       strategies + time-machine runner
src/screener/engine.py       filters + presets
src/paper/ledger.py          SQLite diary
src/app/server.py            API + dashboard hosting
src/app/static/              dashboard (html/css/js, no frameworks)
```

## Add a new indicator

1. Write a function in `src/analysis/indicators.py`:
```python
def my_ratio(close: pd.Series, n: int = 10) -> pd.Series:
    return close / close.rolling(n).mean()
```
2. Add one line in `compute_all()`: `df["my_ratio"] = my_ratio(c)`.
3. Add it to `snapshot()` so API/research can see it.
4. Use it in `researcher.py` or `strategy.py`.

## Add a new backtest strategy

1. In `src/backtest/engine.py`, write a signal function:
```python
def sig_golden(df, **k):
    t = ind.compute_all(df)
    return t["sma50"] > t["sma200"]   # True = invested
```
2. Register it in `STRATEGIES`:
```python
"golden": {"fn": sig_golden, "name": "Golden Trend",
           "desc": "Long while 50DMA is above 200DMA.", "params": {}},
```
3. It appears automatically in the dashboard dropdown + `/api/backtest/strategies`.
4. Test:
```bash
python3 -c "from src.backtest import engine as bt; print(bt.run('OGDC','golden')['metrics'])"
```

## Add a screener filter

- **Snapshot filter** (fast, no history): add a `(key, column, op)` row to
  `apply_fundamental()` in `src/screener/engine.py`.
- **Technical filter**: compute it in `enrich_technical()` via `indicators`,
  then filter it in `apply_technical()`.
- Add the input box to `FDEFS`/`FSEL`/`FCHK` in `src/app/static/app.js`
  (function `readFilters` picks it up automatically).

## Add a preset screen

In `src/screener/engine.py`, add to `PRESETS`:
```python
"my-screen": {"label": "My Screen", "desc": "What it hunts",
              "filters": {"min_yield": 5, "above_sma50": True, "limit": 30}},
```
It appears on Home + Screener automatically.

## Add an API endpoint

In `src/app/server.py`:
```python
@app.get("/api/my-thing")
def my_thing():
    return {"hello": "psx"}
```
Docs at `/docs` update automatically. Restart the server to load changes.

## Rules to keep the system healthy

- Never add a paid API or key-based service — free/offline only.
- Wrap every internet call in try/except with a graceful fallback.
- Reuse `indicators.compute_all()` — don't recompute maths in two places.
- Cache anything downloaded (see `psx_client._json_put` / CSV pattern).
