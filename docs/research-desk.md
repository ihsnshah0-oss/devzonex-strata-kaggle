# PSX Research Desk

A team of LLM research agents on a Python backend, scoped to the **Pakistan Stock Exchange**.
**Agent 1 — the Fundamental Analyst** is implemented end to end; agents 2–6 are declared with their
contracts so the roadmap is explicit rather than implied.

The desk talks to **any OpenAI-compatible chat endpoint**, including the Strata server the Kaggle
launcher in this repository starts.

```
strata_research/
├── api.py            FastAPI app (/api/v1 + /ui)
├── psx.py            PSX symbols, sector lens, macro lens, units, quote client
├── orchestrator.py   ResearchTeam: agents, history, briefs, PSX context
├── agents/
│   ├── base.py       AgentCard, JSON extraction from model output
│   ├── fundamental.py  Agent 1 pipeline (fetch → compute → draft → LLM → ground)
│   └── __init__.py   registry: available + planned agents
├── compute.py        deterministic PKR ratio engine
├── scoring.py        PSX-calibrated quality score + red flags
├── grounding.py      numeric hallucination check
├── heuristics.py     deterministic draft / offline LLM / fallback
├── tools.py          6 read-only tools (incl. PSX context) + audited runner
├── prompts.py        evidence pack + PSX lens + JSON contract
├── llm.py            httpx transport, retries, offline client
├── data/             psx statements, yfinance (.KA), demo, generic JSON
├── render.py         Markdown/console output
├── cli.py            `strata-research` commands
└── ui/index.html     single-file UI (no CDN, no build step)
```

Market specifics (symbols, units, sectors, macro checklist, quotes) live in `psx.py`, and the
guidance on sourcing data is in **[psx.md](psx.md)**.

## Why two layers

Financial text is easy to generate and hard to trust. So the desk splits the work:

| Layer | Owner | Guarantee |
|---|---|---|
| Numbers | Python (`compute.py`, `scoring.py`) | Reproducible, unit-tested, PKR-correct |
| Narrative | LLM | Judgement and synthesis — but every figure it writes is checked |

The LLM never invents a ratio: the evidence pack is rendered *from* the computed models, and
`grounding.py` re-reads the finished narrative and flags any number that is not in that evidence set
(it accepts display rounding, percent forms, and PKR bn/crore renderings). If the check fails, the
agent asks the model to rewrite; if it still fails, the offending bullet is removed and the report
carries a warning.

## Quickstart (offline, no keys)

```bash
python -m pip install -e ".[api,dev]"
python -m strata_research --offline psx            # universe, sectors, macro lens
python -m strata_research --offline status
python -m strata_research --offline analyze DMEPL  # demo universe
python -m strata_research --offline analyze DMPWR --save reports/dmpwr.md
python -m strata_research serve --port 8000        # UI at http://localhost:8000/ui/
```

Offline mode still walks the whole pipeline — prompt building, JSON validation, grounding, scoring —
with a deterministic "LLM" that returns the rule-based draft. That is how CI runs without
credentials.

The offline universe is **fictional** and labelled as such everywhere:

| Ticker | Sector | Archetype | Expected behaviour |
|---|---|---|---|
| `DMEPL` | Oil & Gas Exploration | Net cash, high margin, low multiple | BUY, ~85/100 |
| `DMFRT` | Fertilizer | High margin dividend payer | BUY, ~84/100 |
| `DMCMT` | Cement | Cyclical, leveraged, margin squeeze | SELL, ~37/100 |
| `DMPWR` | Power Generation | IPP, circular debt, thin cover | SELL, ~28/100 |

## Analysing real PSX symbols

Two routes (details in [psx.md](psx.md)):

```bash
# 1) Statements you control (recommended) + live PSX quotes
export STRATA_RESEARCH_PSX_DIR="$PWD/data/psx"
export STRATA_RESEARCH_PSX_QUOTES=true
python -m strata_research analyze OGDC

# 2) Quick pass from Yahoo Finance (<SYMBOL>.KA)
python -m pip install -e ".[live]"
python -m strata_research analyze OGDC
```

## Connect a real LLM

The desk reads the same variables the Kaggle launcher uses:

```bash
export STRATA_BASE_URL="https://<your-tunnel>.trycloudflare.com/v1"   # or http://127.0.0.1:8000/v1
export STRATA_API_KEY="$(cat ~/.config/opencode/strata-key.txt)"
export STRATA_MODEL="qwen3.8-flash-next-gyro-gyro-s"
python -m strata_research analyze DMFRT
```

Any OpenAI-compatible server works: llama.cpp, Ollama (`http://localhost:11434/v1`), vLLM,
LM Studio, or a hosted provider. With no key the desk uses the offline client, and `status` tells you
which mode is active.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `STRATA_BASE_URL` / `OPENAI_BASE_URL` | `http://127.0.0.1:8000/v1` | Chat-completions base URL |
| `STRATA_MODEL` / `OPENAI_MODEL` | `qwen3.8-flash-next-gyro-gyro-s` | Model id |
| `STRATA_API_KEY` / `OPENAI_API_KEY` | — | Bearer token (never logged) |
| `STRATA_API_KEY_FILE` | — | Read the key from a file instead |
| `STRATA_RESEARCH_LLM` | `auto` | `auto`, `openai`, `template` |
| `STRATA_RESEARCH_PROVIDER` | `auto` | `auto`, `psx`, `yfinance`, `demo`, `json` |
| `STRATA_RESEARCH_PSX_DIR` | `./data/psx` if it exists | Folder of PSX statement JSON files |
| `STRATA_RESEARCH_PSX_QUOTES` | `true` | Fetch latest close from the PSX Data Portal |
| `STRATA_RESEARCH_PSX_BASE_URL` | `https://dps.psx.com.pk` | Quote endpoint (override for a mirror) |
| `STRATA_RESEARCH_PSX_TIMEOUT` | `12` | Quote timeout in seconds |
| `STRATA_RESEARCH_DATA_DIR` | — | Generic JSON statements (non-PSX fallback) |
| `STRATA_RESEARCH_TEMPERATURE` | `0.2` | Sampling temperature |
| `STRATA_RESEARCH_MAX_TOKENS` | `1600` | Response budget |
| `STRATA_RESEARCH_TIMEOUT` | `180` | Per-request LLM timeout (seconds) |
| `STRATA_RESEARCH_RETRIES` | `2` | Retries on 429/5xx/timeout |
| `STRATA_RESEARCH_REPAIR_ATTEMPTS` | `1` | Schema and grounding repair attempts |
| `STRATA_RESEARCH_ALLOW_FALLBACK` | `true` | Return the deterministic note if the endpoint fails |
| `STRATA_RESEARCH_TOOLS` | `true` | Offer tool calling (set `false` if the endpoint rejects `tools`) |
| `STRATA_RESEARCH_REPORT_HISTORY` | `50` | Reports kept in memory per process |

## What happens on `analyze`

1. **Normalise** — `PSX:ogdc`, `OGDC.KA`, `ogdc` → `OGDC`; anything that is not a PSX symbol is
   rejected before any work starts.
2. **Fetch** — provider chain `psx` → `yfinance` (`.KA`) → `demo`, with provenance recorded and the
   latest close from the PSX Data Portal applied when quotes are enabled.
3. **Compute** — ~30 PKR ratios plus explicit margin-change metrics; `scoring.py` maps 20 of them
   onto PSX anchors, aggregates five pillars and runs the red-flag rules (including policy-rate
   sensitivity and IPP circular-debt exposure).
4. **Draft** — `heuristics.py` writes a full deterministic note (verdict, conviction, scenario
   maths, PSX watch items). This becomes the prompt prior, the offline answer and the failure
   fallback.
5. **Ask** — the model receives the evidence pack (statements, ratios, score, PSX sector and macro
   lens) plus six read-only tools. Tool calls are executed server-side and audited.
6. **Validate** — JSON is parsed out of prose/fences, validated against the pydantic contract, and
   repaired once if malformed.
7. **Ground** — every checkable number must match the evidence set. Unverified figures trigger one
   rewrite, then removal with a warning.
8. **Package** — a `FundamentalReport` with ratios, scores, grounding, tool audit, token usage,
   warnings and duration.

### Tools available to the agent

| Tool | Purpose |
|---|---|
| `get_financials` | Annual statements as JSON |
| `get_ratios` | Deterministic ratios, optionally filtered |
| `get_score_breakdown` | Pillars, components, red flags |
| `compute_scenario` | Implied price from growth/margin/multiple assumptions |
| `get_company_profile` | Identity, provenance, peers |
| `get_psx_context` | Sector group and lens, Pakistan macro checklist, `.KA` code |

`compute_scenario` exists so the model has a sanctioned way to talk about price: it must state
assumptions and gets arithmetic back, labelled as assumptions, instead of inventing a target.

## API

```bash
curl -s localhost:8000/health | jq '{market, currency, llm}'
curl -s localhost:8000/api/v1/psx/symbols | jq '.demo[].ticker'
curl -s localhost:8000/api/v1/psx/context/DMPWR | jq '.sector_group, .yahoo_symbol'
curl -s localhost:8000/api/v1/psx/yahoo/luck | jq .yahoo_symbol
curl -s localhost:8000/api/v1/companies/DMEPL/preview | jq '.ratios.pe'      # no LLM call
curl -s -X POST localhost:8000/api/v1/agents/fundamental/analyze \
     -H 'Content-Type: application/json' \
     -d '{"ticker":"DMCMT","focus":"policy-rate sensitivity"}' | jq .analysis.verdict
curl -s -X POST localhost:8000/api/v1/team/brief \
     -H 'Content-Type: application/json' -d '{"ticker":"DMFRT"}' | jq .headline
```

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness, active LLM mode, market/currency |
| GET | `/api/v1/status` | Settings (secrets masked), agents, providers, demo universe |
| GET | `/api/v1/agents` | Roster: available and planned, tool catalogue |
| GET | `/api/v1/providers` | Provider readiness |
| GET | `/api/v1/psx/symbols` | Demo universe, local statements, optional live directory (`?live=true`) |
| GET | `/api/v1/psx/context/{ticker}` | Sector lens, macro checklist, peers, `.KA` code |
| GET | `/api/v1/psx/yahoo/{ticker}` | Yahoo listing code |
| POST | `/api/v1/agents/fundamental/analyze` | Full report |
| POST | `/api/v1/team/brief` | All available agents + roadmap |
| GET | `/api/v1/reports` | Session history |
| GET | `/api/v1/reports/{id}` | One report |
| GET | `/api/v1/companies/{ticker}/preview` | Deterministic snapshot, no tokens |
| GET | `/ui/` | Single-file dashboard |
| GET | `/docs` | OpenAPI docs |

Errors are typed: `404`/`data_provider_error` for unknown PSX symbols, `502`/`llm_error` for model
failures (with `retryable`), `422` for invalid requests. Key material is redacted from every error
string before it leaves the process.

## Extending the team

Each planned agent has a card in `agents/__init__.py`. To promote one:

1. Implement `MyAgent(BaseAgent)` with a `run(request) -> ReportModel`.
2. Give it tools in `tools.py` (pure functions over already-fetched data).
3. Add a factory to `FACTORIES` and flip `status` to `"available"`.
4. Call it from `ResearchTeam.brief` and add its section to the `TeamBrief` coverage.

For PSX specifically, the obvious next two are a **bank model** (NIM, provisioning, ADR, CAR) — the
current engine explicitly refuses to score financials — and a **circular-debt/announcements agent**
using PSX disclosures.

## Security and operating limits

- The browser only ever talks to this backend; LLM keys never reach the client.
- `Settings.public_dict()` masks the key; error strings are scrubbed of `sk-…` patterns and the
  configured key.
- Tools are read-only and cannot fetch network data, so a tool loop cannot exfiltrate or mutate.
- The agent loop is bounded (3 tool rounds, 1 repair) and every run has a request timeout.
- Reports are stored in process memory only. Nothing is written to disk unless you pass `--save`.
- Output is research, not advice. Synthetic demo data is labelled everywhere it appears.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `404 data_provider_error` | Symbol not in the active provider. Demo only has DMEPL/DMFRT/DMCMT/DMPWR; real symbols need `STRATA_RESEARCH_PSX_DIR` or the `.KA` provider. |
| `mode: template_llm` | No API key found. Set `STRATA_API_KEY` or pass `--offline` deliberately. |
| `502 llm_error` | Endpoint unreachable or rejected the key. Check `status`, then the tunnel URL. |
| Numbers look 1,000x too big | The file's `units` says millions but the source was thousands. Fix `units`, then rerun. |
| Multiples are `n/a` | No price and/or share count. Set `profile.price` and `shares_outstanding`, or enable quotes. |
| `No PSX quote for X` note | The portal is unreachable or the markup changed; the file price was used instead. |
| `INSUFFICIENT_DATA` | Coverage below 35% or no valuation inputs, so no defensible verdict. |
| Bank/insurer report looks odd | Expected: the industrial engine flags financials rather than scoring them. |
| `Grounding check could not verify…` | The model invented numbers and the rewrite failed; unsupported bullets were removed. Lower temperature or use a stronger model. |

## Tests

```bash
python -m pip install -e ".[api,dev]"
python -m pytest -q tests/test_research_desk.py
```

Covers PSX symbol normalisation, unit conversion (thousands → millions with EPS untouched), the
quote-table parser and quote client (MockTransport), the statements provider, PSX vs global scoring
anchors, red flags for an IPP and a cement name, grounding forms (percent, bn, crore, sign), tool
round-trips, repair and fallback paths, httpx retry and key redaction, every API route, and the CLI.
