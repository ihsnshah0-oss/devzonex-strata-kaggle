# 17 — Data Sources & Reference Links (the full PSX link list)

Every link you shared with the system, triaged into three groups:

1. **Integrated** — the system fetches live data from these automatically.
2. **Reviewed but not integrated** — checked on 2026-10-03; explained why not.
3. **Learning & reference** — educational content, worth browsing; no machine data.

All integrated sources are **free, keyless, and public** (no paid API anywhere).

---

## ✅ 1. Integrated — used for live data fetching

| Source | Link | What the system takes from it |
|---|---|---|
| **PSX DPS portal** | https://dps.psx.com.pk/ | Quotes, ~8.5 yrs daily EOD history, market snapshot, KSE-100/ALLSHR constituents, index levels (via the open-source `psxdata` library). |
| **PSX Market Summary** | https://www.psx.com.pk/market-summary/ | **Official market internals** (added 2026-10-03): advance/decline counts, volume, traded value, trade count, session status + 8 official index levels (incl. BKTI, OGTI, KMI-AllShare, Dividend-20). Shown on Home under the indices. |
| **PSX Financial Reports portal** | https://financials.psx.com.pk/ | **Official filings** (added 2026-10-03): every company's annual/quarterly report history with direct PSX PDF links → Stock page **📄 Filings** tab; market-wide latest-filings feed → News view **📄 Company Reports** tab. |
| **Investify.pk** | https://investify.pk/ , /announcements, /news | PSX announcements (board meetings, payouts, results, insider trades) + Urdu/English market news, with PDF links. Powers News view + per-stock news. |
| **SCS Trade** | http://www.scstrade.com/stockscreening/SS_StockIndiceQuote.aspx | Field-reference for the PSX screener snapshot (covered via `psxdata`). |
| **RSS news feeds** | Dawn, Tribune, The News, ARY, Dunya | Business news for the News view + sentiment scoring. |
| **Yahoo Finance (fallback only)** | https://finance.yahoo.com/ | Backup index level (^KSE100) if DPS is down; optional ratios (P/B, ROE…) on Fundamentals tab. |

APIs for these three new endpoints (see also `docs/10-api-guide.md`):

```
GET /api/market/overview            # official breadth/turnover/status/indices
GET /api/stock/{SYMBOL}/filings     # official annual/quarterly reports + PDFs
GET /api/filings/recent?limit=40    # latest filings across all of PSX
```

## ⏭️ 2. Reviewed, not integrated (and why)

| Link | Reason |
|---|---|
| https://dps.psx.com.pk/screener , /trading-panel, /analysis-reports, /monthly-reports, /downloads | JS-only portal pages; same data we already get via DPS/`psxdata`; PSX data-licensing notice discourages scraping beyond casual use. |
| https://www.psx.com.pk/analysis-report/ | Broker research PDFs behind a JS portal; same licensing note. |
| https://pkfinance.info/kse/stock/PSX | **Paywalled** — all figures show "[hidden]" without a paid login. |
| https://stockanalysis.com/quote/psx/PSX/ , https://www.investing.com/ , https://chartmill.com , https://psxstocksanalyzer.com | Third-party mirrors of the same DPS/Yahoo data we already pull at the source. Redundant. |
| https://psxtechnicalanalysis.com/ | Chart content for humans, no machine-readable feed. |
| https://www.psx.com.pk/shareholder-info/ | Shareholder services (CDC links etc.) — reference for humans. |

## 📚 3. Learning & reference (bookmark these)

| Link | What it's good for |
|---|---|
| https://knowledgecenter.psx.com.pk/ | **PSX official free courses** — start here if you're newer to PSX. |
| https://knowledgecenter.psx.com.pk/courses/introduction-to-fundamental-analysis | Free course: reading financial statements & ratios (pairs with our Fundamentals tab). |
| https://www.psxinvest.com/features | Official PSX investor features/how-tos. |
| https://www.psxinvest.com/compare | PSX's own side-by-side company comparison (compare results with our Compare tab). |
| https://www.kasb.com/ | Kasb Securities research & market commentary. |
| https://chasesecurities.com/how-to-read-a-stock-chart-psx/ | Beginner guide to reading candlestick charts. |
| https://ksestocks.com/blog/ | Long-running PSX blog, market commentary. |
| https://azeetrade.com/how-to-invest-in-pakistan-stock-exchange/ and /screener/ | Azeem Chaudhry's free PSX guides + his public screener (compare results with our Screener tab). |
| https://www.azeetrade.com/beginners-guide-to-fundamental-analysis.php | Beginner walkthrough of fundamental analysis for PSX. |
| https://sarmaaya.pk/webinars | Free investing webinars (Sarmaaya). |
| https://www.tickeranalysts.com/ | Analyst dashboard style reference (our UI layout was modeled on it). |
| https://pakstockexchange.com/tools | Assorted free PSX calculators/tools. |
| https://psxterminal.com/research | Free research articles. |
| https://www.scstrade.com/Default.aspx and https://scstrade.com/Default.aspx | SCS Trade portal home (fields from its screener already feed our data via `psxdata`). |
| https://www.investing.com/equities/pakistan-stock-exchange | Third-party PSX overview page (reference only — same data we fetch at source). |
| https://stockanalysis.com/ | Third-party quotes/financials viewer (reference only). |

---

### Rules the system follows for all sources
- Free & keyless only; nothing paid, no stored third-party API keys.
- Every fetch is cached on disk (5 min – 24 h TTL) so the sites are never hammered.
- If a source is down, the system falls back to its last cache or an alternate source — the dashboard never breaks.
- `GET /api/refresh` (button: ⟳ Refresh) clears the short-lived caches and pulls everything fresh.
