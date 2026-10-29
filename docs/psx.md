# PSX guide — symbols, data, units and limits

The research desk covers **only** Pakistan Stock Exchange listings. This page documents what that
means in practice: how symbols are read, where fundamentals come from, how units are handled, how
the scoring model is calibrated, and what the desk deliberately will not do.

## Symbols

Any of these spellings resolve to the same company:

| You type | Normalised |
|---|---|
| `OGDC` | `OGDC` |
| `ogdc` | `OGDC` |
| `PSX:OGDC` | `OGDC` |
| `OGDC.KA` | `OGDC` |
| `OGDC-KA` | `OGDC` |

The canonical symbol is the PSX ticker. Yahoo Finance's Karachi listing code is derived as
`<SYMBOL>.KA`, which the optional `yfinance` *fundamentals* provider uses (never the price path).

## Where the fundamentals come from

The PSX Data Portal publishes prices, indices and announcements, and companies publish audited
accounts as PDFs. There is **no stable, documented, machine-readable API for PSX financial
statements**, so the desk does not pretend to have one. Instead:

| Provider | Source | Used when |
|---|---|---|
| `psx` | **Your own statements as JSON** in `STRATA_RESEARCH_PSX_DIR` | You want defensible, audited numbers (recommended) |
| `yfinance` | Yahoo Finance `<SYMBOL>.KA` annual statements | You want a quick first pass and have network access |
| `demo` | Fictional PSX-style companies built into the repo | Offline demos, tests, screenshots |

In `auto` mode the desk tries `psx` → `yfinance` → `demo` and records which one answered in
`profile.data_source`. Every report states its `data_quality`: `reported`, `mixed` or `synthetic`.

> Scope note: `yfinance` and `demo` exist **for the analyst desk only**. The mirror database
> ([psx-database.md](psx-database.md)) is built from the PSX Data Portal exclusively — nothing from
> Yahoo or the demo universe ever enters `data/psx.db`.

### Filling `STRATA_RESEARCH_PSX_DIR`

```bash
mkdir -p data/psx
cp examples/psx/DMQSR.json data/psx/LUCK.json   # then replace the figures
export STRATA_RESEARCH_PSX_DIR="$PWD/data/psx"
python -m strata_research analyze LUCK
```

One file per symbol (`LUCK.json`) or a single `companies.json` with `{"companies": [...]}`. Fields
are the standardized statement lines; anything you leave out becomes `n/a` and simply reduces
coverage instead of scoring zero.

### Units — the one thing that breaks PSX models

Pakistani annual reports are usually published in **PKR thousands**; some use millions, and
commentary uses crore/lakh. Declare it once per file:

```json
{ "units": "thousands", "fiscal_years": [ ... ] }
```

Accepted: `thousands` (`'000`), `millions`, `billions`, `crore`, `lakh`, `units` (rupees).
Everything is converted to **millions of PKR** internally. Per-share fields (`eps`,
`dividend_per_share`, `price`) are never scaled — a company reporting in thousands still quotes EPS
in rupees. A silent 1,000x error is the classic PSX analysis bug, so this conversion is explicit and
tested.

## Live prices

Prices come from the **PSX Data Portal only** (`https://dps.psx.com.pk`), in this order:

1. **The local mirror** — `data/psx.db`, the SQLite database described in
   [psx-database.md](psx-database.md). When it exists it is authoritative: an exact, offline close
   plus the trade date the portal itself reported, with no network call at all.
2. **`/company/{SYMBOL}`** — when there is no mirror, the desk reads the company page: `Close` (or
   `Current Price` when the market is open) and `LDCP`, and derives the change from the two.
3. **Nothing.** A missing quote is never fatal: `profile.price` from your statement file is used and
   the report records what happened (`data_quality: mixed`).

Notes that matter:

- The old `POST /historical` month table this client used **no longer returns rows** — the deployment
  serves the date picker and nothing else. That route is gone from the code, not merely
  error-suppressed.
- This is an **unofficial, undocumented endpoint**. Markup can change; the parser degrades to
  "no quote" rather than crashing, and `scripts/psx_probe.py` shows the current shape.
- A live close overrides a `price` you typed in `data/psx`, and the report says so.
- `STRATA_RESEARCH_PSX_QUOTES=false` forces fully offline runs; `PsxQuoteClient(mirror_path=...)`
  points at a different database.

## Sector lens

Each sector carries a short, specific lens that goes into the prompt and the UI:

| Sector group | What the desk insists on discussing |
|---|---|
| Cement | Despatches, coal/power cost per tonne, retention prices, utilisation, leverage |
| Oil & Gas Exploration | Crude/gas price formula, PKR/USD, circular debt on gas receivables, concessions |
| Oil & Gas Marketing | Regulated OMC margins, inventory gains/losses, power-sector receivables |
| Fertilizer | Gas tariff and allocation, urea/DAP pricing, whether payout is cash-funded |
| Power Generation | Capacity payments, circular debt and receivable ageing, covenant headroom |
| Commercial Banks | Flagged as out of scope for the industrial ratio engine (NIM, provisioning, ADR, CAR needed) |
| Technology & Communication | USD-linked revenue, PKR depreciation, client concentration |

## Macro lens

Every prompt carries the Pakistan macro checklist, and the offline draft turns the relevant items
into watch-list entries:

1. **Policy rate** — interest cost, bank margins, discount rate.
2. **PKR/USD** — USD-linked revenue vs imported inputs.
3. **Inflation** — nominal growth can flatter real growth; working capital absorbs cash.
4. **Circular debt** — power/gas chain receivables.
5. **Regulation & tariffs** — administered prices, duties, gas allocation.
6. **Liquidity & free float** — thin floats make the market price a weak fair-value signal.
7. **IMF programme & FX reserves** — external account stress moves the whole market's discount rate.

## Scoring anchors

PSX multiples are structurally lower than developed markets, so a global anchor set would call
almost every Pakistani company cheap. The `PSX` profile is used by default; `GLOBAL` exists only for
non-PSX statements.

| Metric | Unattractive | Attractive | Global profile |
|---|---|---:|---|
| P/E | 18x | 4x | 45x → 12x |
| EV/EBITDA | 12x | 3.5x | 25x → 8x |
| P/S | 4.0x | 0.5x | 12x → 1.5x |
| Dividend yield | 0% | 10% | 0% → 4% |
| FCF yield | 2% | 15% | 0% → 8% |
| ROIC | 2% | 25% | 0% → 20% |
| Net debt/EBITDA | 3.0x | 0x | 4.0x → 0x |
| Interest coverage | 1.0x | 8.0x | 1.5x → 10x |

Dividend yield is a scored component on PSX (weight 0.20 inside the valuation pillar) because income
is a real part of the local investment case. A 12.7x P/E that would look cheap globally scores
mid-range here — that is the intended calibration.

## What the desk will not do

- **Banks, insurers and NBFCs**: the industrial ratio engine (gross margin, EBITDA, inventory) does
  not map onto financial statements. The report emits an explicit red flag instead of a confident
  verdict. A bank model is a separate agent, not a tweak.
- **Price targets**: the model may only use `compute_scenario`, which returns arithmetic from
  explicit growth/margin/multiple assumptions and is labelled as such.
- **PDF extraction**: no scraping of annual-report PDFs. Numbers must arrive in a structured,
  auditable form.
- **Unverifiable claims**: any figure in the narrative that is not in the computed evidence set is
  rewritten or removed, and the report is flagged.
- **Investment advice**: output is research for educational use. Verify against filings.

## Data hygiene for PSX specifically

- Use the **audited annual accounts**, not press summaries; restated figures happen.
- Watch for **period mismatches** (June year-end vs December), and keep `fiscal_year` consistent.
- Check whether revenue is **gross or net** of sales tax and commissions (common in cement/OMC).
- For power and E&P, receivables are the story — the statements here don't carry them, so the red
  flags and watch items call them out explicitly.
- Free float and board (Main vs GEM) are not modelled; note them manually when they matter.
