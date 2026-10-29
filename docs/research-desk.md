# Strata Research Desk

A team of LLM research agents on a Python backend. **Agent 1 — the Fundamental Analyst** is
implemented and production-shaped; agents 2–6 are declared with their contracts so the
roadmap is explicit rather than implied.

The desk runs against **any OpenAI-compatible chat endpoint**, including the Strata server the
Kaggle launcher in this repository starts.

```
strata_research/
├── api.py            FastAPI app (/api/v1 + /ui)
├── orchestrator.py   ResearchTeam: agents, history, briefs
├── agents/
│   ├── base.py       AgentCard, JSON extraction from model output
│   ├── fundamental.py  Agent 1 pipeline (fetch → compute → draft → LLM → ground)
│   └── __init__.py   registry: available + planned agents
├── compute.py        deterministic ratio engine
├── scoring.py        rule-based quality score + red flags
├── grounding.py      numeric hallucination check
├── heuristics.py     deterministic draft / offline LLM / fallback
├── tools.py          5 read-only tools + audited runner
├── prompts.py        evidence pack + JSON contract
├── llm.py            httpx transport, retries, offline client
├── data/             demo, JSON and yfinance providers
├── render.py         Markdown/console output
├── cli.py            `strata-research` commands
└── ui/index.html     single-file UI (no CDN, no build step)
```

## Why two layers

Financial text is easy to generate and hard to trust. So the desk splits the work:

| Layer | Owner | Guarantee |
|---|---|---|
| Numbers | Python (`compute.py`, `scoring.py`) | Reproducible, unit-tested, no network |
| Narrative | LLM | Judgement, framing, synthesis — but every figure it writes is checked |

The LLM never invents a ratio: the evidence pack is rendered *from* the computed models, and
`grounding.py` re-reads the finished narrative and flags any number that is not in that evidence
set. If the check fails, the agent asks the model to rewrite; if it still fails, the offending
bullet is removed and the report carries a warning.

## Quickstart (offline, no keys)

```bash
python -m pip install -e ".[api,dev]"
python -m strata_research --offline status
python -m strata_research --offline agents
python -m strata_research --offline analyze NOVA
python -m strata_research --offline analyze ARCL --save reports/arcl.md
python -m strata_research serve --port 8000     # UI at http://localhost:8000/ui/
```

Offline mode still walks the entire pipeline — prompt building, JSON validation, grounding,
scoring — with a deterministic "LLM" that returns the rule-based draft. It is how the tests run
in CI without credentials.

The offline universe is **fictional**:

| Ticker | Archetype | Expected behaviour |
|---|---|---|
| `NOVA` | Industrial automation compounder | High score, rich multiple, no red flags |
| `HELX` | Defensive pharma cash generator | Highest score, fair multiple, strong FCF |
| `ARCL` | Leveraged mall retailer | Weak score, seven red flags, SELL |

## Connect a real LLM

The desk reads the same variables the Kaggle launcher uses:

```bash
export STRATA_BASE_URL="https://<your-tunnel>.trycloudflare.com/v1"   # or http://127.0.0.1:8000/v1
export STRATA_API_KEY="$(cat ~/.config/opencode/strata-key.txt)"
export STRATA_MODEL="qwen3.8-flash-next-gyro-gyro-s"
python -m strata_research analyze NOVA
```

Any OpenAI-compatible server works: llama.cpp, Ollama (`http://localhost:11434/v1`), vLLM,
LM Studio, or a hosted provider. If no key is found the desk silently uses the offline client, so
nothing breaks — but the log line and `status` output tell you which mode you are in.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `STRATA_BASE_URL` / `OPENAI_BASE_URL` | `http://127.0.0.1:8000/v1` | Chat-completions base URL |
| `STRATA_MODEL` / `OPENAI_MODEL` | `qwen3.8-flash-next-gyro-gyro-s` | Model id |
| `STRATA_API_KEY` / `OPENAI_API_KEY` | — | Bearer token (never logged) |
| `STRATA_API_KEY_FILE` | — | Read the key from a file instead |
| `STRATA_RESEARCH_LLM` | `auto` | `auto`, `openai`, `template` |
| `STRATA_RESEARCH_PROVIDER` | `auto` | `auto`, `demo`, `json`, `yfinance` |
| `STRATA_RESEARCH_DATA_DIR` | — | Folder with `<TICKER>.json` or `companies.json` |
| `STRATA_RESEARCH_TEMPERATURE` | `0.2` | Sampling temperature |
| `STRATA_RESEARCH_MAX_TOKENS` | `1600` | Response budget |
| `STRATA_RESEARCH_TIMEOUT` | `180` | Per-request timeout (seconds) |
| `STRATA_RESEARCH_RETRIES` | `2` | Retries on 429/5xx/timeout |
| `STRATA_RESEARCH_REPAIR_ATTEMPTS` | `1` | Schema and grounding repair attempts |
| `STRATA_RESEARCH_ALLOW_FALLBACK` | `true` | Return the deterministic note if the endpoint fails |
| `STRATA_RESEARCH_REPORT_HISTORY` | `50` | Reports kept in memory per process |
| `STRATA_RESEARCH_TOOLS` | `true` | Offer tool calling to the model (set `false` if the endpoint rejects `tools`) |

## What happens on `analyze`

1. **Fetch** — provider chain: JSON folder → yfinance → demo. Provenance (`data_source`,
   `data_quality`) is attached to every report.
2. **Compute** — `compute.py` builds ~30 ratios; `scoring.py` maps 19 of them onto 0..1 ramps,
   aggregates five pillars, and runs the red-flag rules.
3. **Draft** — `heuristics.py` writes a full deterministic note (verdict, conviction, scenario
   maths). This becomes the prompt prior, the offline answer and the failure fallback.
4. **Ask** — the model receives the evidence pack, the draft and five read-only tool schemas.
   Tool calls are executed server-side and recorded with durations and summaries.
5. **Validate** — the JSON is parsed out of prose/fences, validated against the pydantic
   contract, and repaired once if malformed.
6. **Ground** — every checkable number in the narrative must match the evidence set
   (rounded, percent and multiple forms accepted). Unverified figures trigger one rewrite, then
   removal.
7. **Package** — a `FundamentalReport` with ratios, scores, grounding, tool audit, token usage,
   warnings and duration.

### Tools available to the agent

| Tool | Purpose |
|---|---|
| `get_financials` | Annual statements as JSON |
| `get_ratios` | Deterministic ratios, optionally filtered |
| `get_score_breakdown` | Pillars, components, red flags |
| `compute_scenario` | Implied price from growth/margin/multiple assumptions |
| `get_company_profile` | Identity, provenance, peers |

`compute_scenario` exists so the model has a sanctioned way to talk about price: it must state
assumptions and gets arithmetic back, instead of inventing a target.

## API

```bash
curl -s localhost:8000/health
curl -s localhost:8000/api/v1/status | jq .settings
curl -s localhost:8000/api/v1/agents | jq '.available'
curl -s localhost:8000/api/v1/companies/NOVA/preview | jq '.scores.overall'   # no LLM call
curl -s -X POST localhost:8000/api/v1/agents/fundamental/analyze \
     -H 'Content-Type: application/json' \
     -d '{"ticker":"NOVA","focus":"margin durability","horizon":"12-24 months"}' | jq .analysis
curl -s -X POST localhost:8000/api/v1/team/brief \
     -H 'Content-Type: application/json' -d '{"ticker":"HELX"}' | jq .headline
```

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness plus active LLM mode |
| GET | `/api/v1/status` | Settings (secrets masked), agents, providers, tools |
| GET | `/api/v1/agents` | Roster: available and planned |
| GET | `/api/v1/providers` | Provider readiness |
| POST | `/api/v1/agents/fundamental/analyze` | Full report |
| POST | `/api/v1/team/brief` | All available agents + roadmap |
| GET | `/api/v1/reports` | Session history |
| GET | `/api/v1/reports/{id}` | One report |
| GET | `/api/v1/companies/{ticker}/preview` | Deterministic snapshot, no tokens |
| GET | `/ui/` | Single-file dashboard |
| GET | `/docs` | OpenAPI docs |

Errors are typed: `404`/`data_provider_error` for unknown tickers, `502`/`llm_error` for model
failures (with `retryable`), `422` for invalid requests. Key material is redacted from every
error string before it leaves the process.

## Data providers

`demo` — fictional, offline, deterministic. Used for tests and demos.

`json` — point `STRATA_RESEARCH_DATA_DIR` at a folder. Either one file per ticker or an
aggregate file:

```json
{
  "companies": [
    {
      "profile": {
        "ticker": "ACME", "name": "Acme Industries", "sector": "Industrials",
        "currency": "USD", "price": 42.5, "shares_outstanding": 100.0,
        "dividend_per_share": 0.4, "beta": 1.1
      },
      "fiscal_years": [
        {"fiscal_year": 2025, "revenue": 1000, "gross_profit": 400,
         "operating_income": 120, "pretax_income": 110, "income_tax_expense": 22,
         "net_income": 88, "eps": 0.88, "depreciation_amortization": 40,
         "total_assets": 1500, "total_equity": 700, "total_debt": 300,
         "cash_and_equivalents": 150, "current_assets": 600,
         "current_liabilities": 400, "inventory": 200,
         "operating_cash_flow": 140, "capex": 50}
      ],
      "peers": ["PEER1", "PEER2"]
    }
  ]
}
```

All figures are in **millions** of the reporting currency except `eps`, `price` and
`dividend_per_share`. See `examples/fundamentals/ACME.json`.

`yfinance` — optional (`pip install -e ".[live]"`). Best-effort field mapping; single-source
vendor data, so reports say so. Coverage of non-US listings and some sectors is patchy; treat
missing values as missing rather than zero.

## Extending the team

Each planned agent has a card in `agents/__init__.py`. To promote one:

1. Implement `MyAgent(BaseAgent)` with a `run(request) -> ReportModel`.
2. Give it its own tools in `tools.py` (pure functions over already-fetched data).
3. Add a factory to `FACTORIES` and flip `status` to `"available"`.
4. Call it from `ResearchTeam.brief` and add its section to the `TeamBrief` coverage.

The orchestrator already records per-agent status, verdicts, conviction, runtime and warnings, so
the UI and API extend without changes. `prompts.build_team_brief_prompt` is the seam for the
Portfolio Manager synthesis step.

## Security and operating limits

- The browser only ever talks to this backend; LLM keys never reach the client.
- `Settings.public_dict()` masks the key; error strings are scrubbed of `sk-…` patterns and the
  configured key.
- Tools are read-only and cannot fetch network data, so a tool loop cannot exfiltrate or mutate.
- The agent loop is bounded (3 tool rounds, 1 repair) and every run has a request timeout.
- Reports are stored in process memory only (`STRATA_RESEARCH_REPORT_HISTORY`). Nothing is
  written to disk unless you pass `--save`.
- Output is research, not advice. Synthetic demo data is labelled everywhere it appears.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `mode: template_llm` | No API key found. Set `STRATA_API_KEY` or pass `--offline` deliberately. |
| `404 data_provider_error` | Ticker missing from the active provider. Demo only has NOVA/HELX/ARCL. |
| `502 llm_error` | Endpoint unreachable or rejected the key. Check `status`, then the tunnel URL. |
| `400` mentioning `tools` | The endpoint does not support tool calling. Set `STRATA_RESEARCH_TOOLS=false`. |
| `Grounding check could not verify…` | Model invented numbers and the rewrite also failed; unsupported bullets were removed. Lower temperature or use a stronger model. |
| Report says `INSUFFICIENT_DATA` | Evidence coverage < 35% or no price/share count, so valuation cannot be grounded. |
| yfinance returns no statements | Add a JSON provider for that ticker; vendor coverage is incomplete. |

## Tests

```bash
python -m pip install -e ".[api,dev]"
python -m pytest -q tests/test_research_desk.py
```

The suite covers ratio maths, scoring regressions (including a net-cash leverage case), red-flag
detection, grounding, JSON extraction, tool round-trips, repair and fallback paths, httpx retry
and key-redaction behaviour, every API route, and the CLI.
