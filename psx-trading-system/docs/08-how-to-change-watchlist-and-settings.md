# 08 — Settings Tab (change anything, no coding)

**You never need to touch code.** Open the dashboard → **⚙ Settings** tab.
Everything is in plain English with explanations. Press **Save** — changes work
**immediately** (no restart).

## ⭐ Watchlist — my stocks

- **Edit:** change any box directly (symbol, company name, sector, reason).
- **Delete:** press ✕ on a row. (At least 1 stock must remain.)
- **Add:** fill the 4 boxes under the table → **+ Add stock**.
- Press **Save watchlist**. The Home page updates at once.
- Rules: symbols must be CAPITAL letters/numbers exactly as PSX writes them
  (e.g. `SYS`, not `Sys`). Max 30 stocks.
- Note: around dividends/bonuses PSX temporarily renames stocks (`BOP` →
  `BOPXD`). The system detects this automatically — keep the normal symbol;
  data keeps flowing and flips back by itself.

## 💰 Trading defaults (used by proposals, backtests & paper reset)

| Setting | Simple meaning | Safe value |
|---|---|---|
| Starting paper cash | Fake money for practice + trade-plan math | 1,000,000 |
| Risk per trade % | How much of your money one idea may risk | 1.0 (careful) |
| Circuit breaker % | PSX daily price limit | 7.5 (don't change) |
| Commission per side % | Broker + taxes cost per buy/sell | check broker (~0.15) |
| Slippage per side % | Extra cost as price moves while ordering | 0.10 |
| Proposal valid days | After this, a trade plan is old | 5 |
| Screener depth 20–120 | Stocks fully checked per screen (higher = slower) | 80 |

## 🤖 Local AI notes (Ollama) — optional

1. First follow guide 09 (install Ollama + download a model).
2. Here: switch **On**, check address/model, **Save AI settings**.
3. Press **Test connection** — ✅ means working; ❌ explains what's wrong.

## 🔄 Auto-refresh & display

- **Auto-refresh:** ON = data + signals update by themselves every X seconds
  (you'll see the ⟳ button pulse and `auto ⟳ in Ns` count down). OFF = manual only.
- **Seconds:** 30–600. **60 is the recommended default.**
- **Default stock:** which stock pre-loads first (e.g. OGDC).

## 🧹 Maintenance

- **Saved data info:** how many files + MB the cache uses.
- **Clear saved data:** deletes downloads → everything re-downloads fresh once.
  Use it if numbers ever look stuck or strange.
- **Reset paper money:** wipes practice trades, restores your chosen cash amount.

## ✏️ Advanced: edit the file by hand (optional)

Everything above writes to one file: `config/watchlist.yaml`.
You can also edit it in Notepad — **no restart needed** either way:

```bash
python3 -c "import yaml; print(yaml.safe_load(open('config/watchlist.yaml'))['watchlist'])"
```

If this prints your stocks with no error, the file is correct.
