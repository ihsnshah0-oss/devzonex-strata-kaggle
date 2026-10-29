"""Command line interface.

Examples::

    python -m strata_research status
    python -m strata_research agents
    python -m strata_research analyze NOVA
    python -m strata_research analyze NOVA --save reports/nova.md
    python -m strata_research brief NOVA --json
    python -m strata_research serve --port 8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .config import Settings
from .data import DataProviderError
from .llm import LLMError
from .orchestrator import ResearchTeam
from .render import brief_to_markdown, report_to_console, report_to_markdown


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _write(path: str, content: str) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"Saved {target}")


def cmd_status(args: argparse.Namespace, team: ResearchTeam) -> int:
    status = team.status()
    if args.json:
        print(_dump(status))
        return 0
    settings = status["settings"]
    print(f"Desk:  {status['desk']} v{__version__}")
    print(f"Mode:  {'offline (deterministic)' if settings['llm_kind'] == 'template' else 'LLM'}"
          f"  ·  model: {settings['model']}")
    print(f"LLM endpoint: {settings['base_url']}  ·  key: {settings['api_key']}")
    if settings["llm_kind"] == "template":
        print("Hint: set STRATA_API_KEY (or OPENAI_API_KEY) to let the agent write "
              "the narrative itself instead of the rule-based draft.")
    print("Providers:")
    for entry in status["providers"]:
        print(f"  - {entry['name']}: {'ready' if entry['available'] else 'unavailable'}"
              f"{' (network)' if entry['requires_network'] else ''}")
    print(f"Demo tickers: {', '.join(status['demo_tickers'])}")
    print("Agents:")
    for card in status["agents"]:
        print(f"  {card['order']}. {card['title']} [{card['status']}]")
    return 0


def cmd_agents(args: argparse.Namespace, team: ResearchTeam) -> int:
    cards = team.cards()
    if args.json:
        print(_dump(cards))
        return 0
    for card in cards:
        print(f"\n{card['title']}  [{card['status']}]")
        print(f"  {card['description']}")
        print(f"  inputs:  {card['inputs']}")
        print(f"  outputs: {card['outputs']}")
        if card["tools"]:
            print(f"  tools:   {', '.join(card['tools'])}")
    return 0


def cmd_providers(args: argparse.Namespace, team: ResearchTeam) -> int:
    payload = team.status()["providers"]
    print(_dump(payload))
    return 0


def cmd_analyze(args: argparse.Namespace, team: ResearchTeam) -> int:
    report = team.analyse_ticker(args.ticker, focus=args.focus, horizon=args.horizon)
    if args.json:
        payload = report.model_dump(mode="json")
        print(_dump(payload))
        if args.save:
            _write(args.save, _dump(payload))
        return 0
    print(report_to_console(report))
    if args.save:
        _write(args.save, report_to_markdown(report))
    return 0


def cmd_brief(args: argparse.Namespace, team: ResearchTeam) -> int:
    brief = team.brief(args.ticker, focus=args.focus, horizon=args.horizon)
    if args.json:
        print(_dump(brief.model_dump(mode="json")))
        return 0
    print(f"Desk brief — {brief.ticker}")
    print(brief.headline)
    print()
    for entry in brief.coverage:
        print(f"  {entry['title']}: {entry['status']} · {entry['verdict']} "
              f"· conviction {entry['conviction']:.2f}")
    if brief.roadmap:
        print("\nNot yet available:")
        for item in brief.roadmap:
            print(f"  - {item['title']}")
    print()
    for report in brief.reports:
        print(report_to_console(report))
    if args.save:
        _write(args.save, brief_to_markdown(brief))
    return 0


def cmd_serve(args: argparse.Namespace, team: ResearchTeam) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install 'strata-research[api]'", file=sys.stderr)
        return 1
    print(f"Starting the research desk on http://{args.host}:{args.port} "
          f"(UI at /ui/, docs at /docs)")
    uvicorn.run(
        "strata_research.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="strata-research",
        description="Team of LLM research agents on a Python backend.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--offline", action="store_true",
                        help="force the deterministic LLM (no network calls)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="show configuration and agent roster")
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=cmd_status)

    agents = subparsers.add_parser("agents", help="describe every agent on the desk")
    agents.add_argument("--json", action="store_true")
    agents.set_defaults(handler=cmd_agents)

    providers = subparsers.add_parser("providers", help="show data provider readiness")
    providers.set_defaults(handler=cmd_providers)

    analyze = subparsers.add_parser("analyze", help="run the Fundamental Analyst")
    analyze.add_argument("ticker")
    analyze.add_argument("--focus", default="balanced fundamental view")
    analyze.add_argument("--horizon", default="12-24 months")
    analyze.add_argument("--json", action="store_true", help="print the raw report JSON")
    analyze.add_argument("--save", metavar="PATH", help="write a Markdown (or JSON) file")
    analyze.set_defaults(handler=cmd_analyze)

    brief = subparsers.add_parser("brief", help="run the whole available desk")
    brief.add_argument("ticker")
    brief.add_argument("--focus", default="balanced fundamental view")
    brief.add_argument("--horizon", default="12-24 months")
    brief.add_argument("--json", action="store_true")
    brief.add_argument("--save", metavar="PATH", help="write a Markdown brief")
    brief.set_defaults(handler=cmd_brief)

    serve = subparsers.add_parser("serve", help="run the HTTP API + UI")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--log-level", default="info")
    serve.set_defaults(handler=cmd_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    if args.offline:
        settings = settings.with_llm("template")
    team = ResearchTeam(settings)
    if settings.offline:
        print("(offline mode: deterministic LLM, no network calls)", file=sys.stderr)
    try:
        return int(args.handler(args, team))
    except (DataProviderError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    finally:
        team.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
