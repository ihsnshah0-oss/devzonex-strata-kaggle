# 10 — API Guide (use the system from code)

Base address: `http://localhost:8111`
Interactive docs (try everything in browser): `http://localhost:8111/docs`

> Windows PowerShell: replace `curl` examples with the same `curl` command —
> Windows 10/11 includes curl. For POST examples, save JSON into a file and use
> `--data @file.json` if quoting gets messy.

## Read market

```bash
curl localhost:8111/api/health
curl localhost:8111/api/pulse
curl localhost:8111/api/watchlist
curl localhost:8111/api/universe | head -c 500
```

## Clock, signal timestamps & refresh

```bash
# server PKT time + market OPEN/CLOSED + when signals were last generated
curl localhost:8111/api/signals/status

# quick refresh: latest quotes/snapshot/indices/news + recompute signals
curl -X POST localhost:8111/api/refresh \
  -H "Content-Type: application/json" -d '{"full": false}'

# deep refresh: also re-downloads ALL price history (slow, minutes)
curl -X POST localhost:8111/api/refresh \
  -H "Content-Type: application/json" -d '{"full": true}'
```

## Research one stock

```bash
curl localhost:8111/api/stock/OGDC
curl localhost:8111/api/stock/OGDC/history
curl localhost:8111/api/stock/OGDC/research
curl "localhost:8111/api/stock/OGDC/proposal?capital=500000&risk=1.5"
curl localhost:8111/api/stock/OGDC/report
curl -o OGDC_report.pdf localhost:8111/api/stock/OGDC/report.pdf
curl localhost:8111/api/stock/OGDC/news
curl "localhost:8111/api/news?limit=10"
curl "localhost:8111/api/announcements?limit=10"
curl "localhost:8111/api/announcements?watchlist_only=true"
curl "localhost:8111/api/announcements?symbol=OGDC"
```

## Run the screener

```bash
curl -X POST localhost:8111/api/screener/run \
  -H "Content-Type: application/json" \
  -d '{"filters": {"min_yield": 7, "exclude_zero_pe": true, "limit": 10}}'

curl localhost:8111/api/screener/presets
```

Useful filter keys: `min_price`, `max_price`, `min_mcap`, `min_pe`, `max_pe`,
`min_yield`, `min_avgvol`, `min_day_chg`, `max_day_chg`, `min_1y_chg`,
`kse100_only`, `exclude_zero_pe`, `rsi_min`, `rsi_max`, `above_sma50`,
`above_sma200`, `macd_bull`, `golden_cross`, `breakout_20d`, `breakdown_20d`,
`min_vol_ratio`, `near_52w_high_pct`, `sort`, `ascending`, `limit`.

## Run a backtest

```bash
curl localhost:8111/api/backtest/strategies

curl -X POST localhost:8111/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbol": "HBL", "strategy": "breakout", "start": "2022-01-01",
       "capital": 1000000, "atr_mult": 2.0}'
```

## Paper trading + risk

```bash
curl localhost:8111/api/paper/account
curl localhost:8111/api/paper/history

curl -X POST localhost:8111/api/paper/order \
  -H "Content-Type: application/json" \
  -d '{"symbol": "OGDC", "side": "buy", "qty": 10}'

curl -X POST "localhost:8111/api/paper/reset?cash=1000000"

curl -X POST localhost:8111/api/risk/check \
  -H "Content-Type: application/json" \
  -d '{"symbol": "OGDC", "entry": 320, "stop": 305, "target": 345,
       "qty": 100, "capital": 1000000}'
```

## Settings + maintenance

```bash
# read everything (watchlist, trading defaults, AI, display)
curl localhost:8111/api/settings

# save: partial updates allowed, validated, instant (no restart)
curl -X PUT localhost:8111/api/settings \
  -H "Content-Type: application/json" \
  -d '{"settings": {"default_risk_pct": 1.5}, "ui": {"auto_refresh_sec": 90}}'

# test the local AI connection
curl -X POST localhost:8111/api/settings/test-ollama

# cache info + clear
curl localhost:8111/api/cache/info
curl -X POST localhost:8111/api/cache/clear

# official PSX website feeds (psx.com.pk + financials.psx.com.pk)
curl localhost:8111/api/market/overview              # breadth, turnover, status, indices
curl localhost:8111/api/stock/OGDC/filings           # official report history + PDF links
curl "localhost:8111/api/filings/recent?limit=40"    # latest filings across PSX

# compare up to 5 stocks A-to-Z (price, perf, valuation, technicals, filings)
curl "localhost:8111/api/compare?symbols=OGDC,PPL,FFC,MCB,HUBC"

# A-to-Z executive report: JSON preview + downloadable PDF
curl localhost:8111/api/stock/OGDC/report
curl -OJ localhost:8111/api/stock/OGDC/report.pdf
```

## Tiny Python client (no extra install)

```python
import json, urllib.request
def api(path, data=None):
    req = urllib.request.Request(
        "http://localhost:8111" + path,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET")
    return json.load(urllib.request.urlopen(req))

print(api("/api/pulse")["breadth"])
print(api("/api/screener/run", {"filters": {"rsi_max": 32, "limit": 3}})["count"])
```

# Strategy Fit Guide (which strategy fits which stock)
curl localhost:8111/api/fit-guide            # status + PDF size
curl -X POST localhost:8111/api/fit-guide/run   # regenerate (background, ~1 min)
curl localhost:8111/api/fit-guide/download -o strategy_fit_guide.pdf

# Money Management (plan, sizing, journal)
curl localhost:8111/api/money                                   # full state
curl -X POST localhost:8111/api/money/plan -d '{"capital":500000}' -H 'Content-Type: application/json'
curl -X POST localhost:8111/api/money/size -d '{"symbol":"OGDC","entry":200,"stop":190,"target":225}' -H 'Content-Type: application/json'
curl -X POST localhost:8111/api/money/trade -d '{"symbol":"OGDC","qty":500,"entry":200,"exit":210}' -H 'Content-Type: application/json'
curl -X DELETE localhost:8111/api/money/trade/{id}
curl -o trade_plan_OGDC.pdf localhost:8111/api/money/trade-plan/OGDC   # research + best strategy + sized plan

# Broker statement upload (PDF -> positions preview -> apply)
curl -F "file=@statement.pdf" localhost:8111/api/broker/statement/parse
curl -X POST localhost:8111/api/broker/statement/apply -d '{"rows":[{"symbol":"OGDC","qty":2500,"rate":185.5}],"date":"2026-10-06"}' -H 'Content-Type: application/json'
