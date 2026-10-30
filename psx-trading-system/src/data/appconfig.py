"""Central config access — ONE reader for config/watchlist.yaml.

Every module (server, strategy, risk, ledger, screener) reads settings
through here, so the Settings tab changes take effect immediately with
NO server restart and NO coding.
"""
from pathlib import Path

import yaml

CFG = Path(__file__).resolve().parents[2] / "config" / "watchlist.yaml"

DEFAULT_SETTINGS = {
    "currency": "PKR",
    "timezone": "Asia/Karachi",
    "paper_cash": 1000000,
    "default_risk_pct": 1.0,
    "circuit_breaker_pct": 7.5,
    "commission_pct": 0.15,
    "slippage_pct": 0.10,
    "proposal_valid_days": 5,
    "screener_max_stocks": 80,
}
DEFAULT_OLLAMA = {
    "enabled": False,
    "base_url": "http://localhost:11434",
    "model": "llama3.1",
    "timeout_sec": 25,
}
DEFAULT_LLM = {
    # Which engine writes the AI notes when they are switched on.
    # ollama = local & free | groq / openrouter / gemini = free cloud API tiers
    "provider": "ollama",
    "timeout_sec": 25,
    "groq": {"api_key": "", "model": "llama-3.3-70b-versatile"},
    "openrouter": {"api_key": "", "model": "meta-llama/llama-3.3-70b-instruct:free"},
    "gemini": {"api_key": "", "model": "gemini-2.0-flash"},
    "cerebras": {"api_key": "", "model": "llama3.1-8b"},
}
DEFAULT_UI = {
    "auto_refresh_enabled": True,
    "auto_refresh_sec": 60,
    "default_stock": "OGDC",
}
FALLBACK_WATCH = ["OGDC", "HBL", "LUCK", "FFC", "MEBL"]


def load() -> dict:
    try:
        return yaml.safe_load(CFG.read_text()) or {}
    except Exception:
        return {}


def _merged(key: str, defaults: dict) -> dict:
    out = dict(defaults)
    try:
        user = (load().get(key, {}) or {})
        for k, v in user.items():
            if v is not None:
                out[k] = v
    except Exception:
        pass
    return out


def get_watchlist() -> list[dict]:
    try:
        wl = load().get("watchlist", []) or []
        wl = [w for w in wl if isinstance(w, dict) and w.get("symbol")]
        if wl:
            return wl
    except Exception:
        pass
    return [{"symbol": s} for s in FALLBACK_WATCH]


def get_settings() -> dict:
    return _merged("settings", DEFAULT_SETTINGS)


def get_ollama() -> dict:
    return _merged("ollama", DEFAULT_OLLAMA)


SECRETS = CFG.parent / "secrets.yaml"


def get_secrets() -> dict:
    """Local secrets (config/secrets.yaml) — read-only, never written back,
    never included in API responses. Missing file = empty dict."""
    try:
        return yaml.safe_load(SECRETS.read_text()) or {}
    except Exception:
        return {}


def get_r2() -> dict:
    return get_secrets().get("cloudflare_r2", {}) or {}


def r2_configured() -> bool:
    r = get_r2()
    return bool(r.get("configured") and r.get("access_key_id")
                and r.get("secret_access_key") and r.get("endpoint"))



def get_llm() -> dict:
    """LLM provider settings, with per-provider sub-dicts deep-merged."""
    out = _merged("llm", {k: v for k, v in DEFAULT_LLM.items()
                          if not isinstance(v, dict)})
    user = (load().get("llm", {}) or {})
    for p in ("groq", "openrouter", "gemini"):
        sub = dict(DEFAULT_LLM[p])
        sub.update({k: v for k, v in (user.get(p) or {}).items() if v is not None})
        out[p] = sub
    # API keys belong in config/secrets.yaml (git-ignored), never in a file
    # that ships with the app. Anything set there wins.
    secret_llm = (get_secrets().get("llm") or {})
    for name, sub in secret_llm.items():
        if isinstance(sub, dict) and name in out and isinstance(out[name], dict):
            out[name].update({k: v for k, v in sub.items() if v})
    return out


def get_ui() -> dict:
    return _merged("ui", DEFAULT_UI)


def get_lists() -> list:
    """Extra watchlists: [{name, symbols:[...]}] — each is a subset of master."""
    out = []
    for it in (load().get("watchlists", []) or []):
        name = str((it or {}).get("name", "")).strip()
        syms = [str(s).upper() for s in ((it or {}).get("symbols", []) or [])]
        if name:
            out.append({"name": name, "symbols": syms})
    return out


def get_flags() -> dict:
    """Color flags per symbol: {SYMBOL: color-name-or-empty}."""
    return {str(k).upper(): str(v) for k, v in (load().get("flags", {}) or {}).items() if v}


def get_list_notes() -> dict:
    """Per-stock notes inside extra watchlists: {list-name: {SYMBOL: note-text}}."""
    out = {}
    for lst, per_sym in (load().get("list_notes", {}) or {}).items():
        lst = str(lst).strip()
        if not lst:
            continue
        notes = {str(s).upper().strip(): str(t).strip()
                 for s, t in (per_sym or {}).items() if str(t).strip()}
        if notes:
            out[lst] = notes
    return out


def save(new_cfg: dict) -> dict:
    """Merge patch into config file. Returns full config."""
    cfg = load()
    for section in ("watchlist", "settings", "ollama", "ui", "llm",
                    "watchlists", "flags", "list_notes"):
        if section in new_cfg and new_cfg[section] is not None:
            if section in ("watchlist", "watchlists", "flags", "list_notes"):
                cfg[section] = new_cfg[section]
            else:
                base = dict(cfg.get(section, {}) or {})
                base.update({k: v for k, v in new_cfg[section].items()
                             if v is not None})
                cfg[section] = base
    # keep sub-lists & flags consistent with the master list
    master = {str(w.get("symbol", "")).upper() for w in cfg.get("watchlist", []) or []}
    cfg["watchlists"] = [{"name": l["name"],
                          "symbols": [s for s in l.get("symbols", []) if s in master]}
                         for l in cfg.get("watchlists", []) or []]
    cfg["flags"] = {k: v for k, v in (cfg.get("flags", {}) or {}).items() if k in master}
    # notes: keep only existing sub-lists and master-list symbols
    keep_lists = {l["name"] for l in cfg.get("watchlists", []) or []}
    cfg["list_notes"] = {
        lst: {s: t for s, t in (per or {}).items() if s in master}
        for lst, per in (cfg.get("list_notes", {}) or {}).items() if lst in keep_lists}
    cfg["list_notes"] = {l: p for l, p in cfg["list_notes"].items() if p}
    header = ("# PSX Live & Research settings — safe to edit by hand OR via the Settings tab.\n")
    CFG.write_text(header + yaml.safe_dump(
        {k: cfg.get(k) for k in ("watchlist", "settings", "ollama", "ui", "llm",
                                 "watchlists", "flags", "list_notes")
         if cfg.get(k) is not None},
        sort_keys=False, allow_unicode=True))
    return {"watchlist": get_watchlist(), "settings": get_settings(),
            "ollama": get_ollama(), "ui": get_ui(), "llm": get_llm(),
            "watchlists": get_lists(), "flags": get_flags(),
            "list_notes": get_list_notes()}
