"""Unified AI-notes layer — local Ollama + free cloud APIs.

Providers (all usable at zero cost):
  ollama      — runs on your own PC (https://ollama.com). No key, no internet.
  groq        — free API tier, open models  (key: https://console.groq.com/keys)
  openrouter  — free ':free' open models    (key: https://openrouter.ai/keys)
  gemini      — Google API free tier        (key: https://aistudio.google.com/apikey)

The rest of the system never calls a provider directly — it calls
`narrative()` / `generate()` here, so adding a provider only touches
this file + the Settings dropdown.
"""
import re
import time

import requests

from ..data import appconfig as appcfg

PROVIDERS = {
    "ollama": {"label": "Ollama — local on your PC (fully free, no key needed)",
               "needs_key": False, "signup": "",
               "default_model": "llama3.1"},
    "groq": {"label": "Groq — free cloud API running open models (very fast)",
             "needs_key": True, "signup": "https://console.groq.com/keys",
             "default_model": "llama-3.3-70b-versatile"},
    "openrouter": {"label": "OpenRouter — free open models (names ending ':free')",
                   "needs_key": True, "signup": "https://openrouter.ai/keys",
                   "default_model": "meta-llama/llama-3.3-70b-instruct:free"},
    "gemini": {"label": "Google Gemini — free API tier",
               "needs_key": True, "signup": "https://aistudio.google.com/apikey",
               "default_model": "gemini-2.0-flash"},
    "cerebras": {"label": "Cerebras — free cloud inference, very fast",
                 "needs_key": True, "signup": "https://cloud.cerebras.ai",
                 "default_model": "llama3.1-8b"},
}

_MASK = "\u2022"  # bullet used to mask saved API keys in GET responses


def _clean(txt: str) -> str:
    """Reasoning models (DeepSeek-R1 etc.) wrap private thinking in
     tags — strip it so only the note is kept."""
    return re.sub(r"", "", txt or "", flags=re.S).strip()


def generate(prompt: str, timeout: float | None = None, cfg: dict | None = None) -> str | None:
    """Ask the configured provider. Raises RuntimeError with a helpful
    message when something is wrong; returns None on empty replies.
    `cfg` lets the Settings test-button try another provider without saving."""
    cfg = cfg or appcfg.get_llm()
    prov = (cfg.get("provider") or "ollama").lower()
    t = float(timeout or cfg.get("timeout_sec", 25))

    if prov == "ollama":
        o = appcfg.get_ollama()
        try:
            r = requests.post(
                f"{o.get('base_url', 'http://localhost:11434')}/api/generate",
                json={"model": o.get("model", "llama3.1"), "prompt": prompt,
                      "stream": False},
                timeout=min(t, 180))
        except requests.exceptions.RequestException:
            raise RuntimeError(
                f"Cannot reach Ollama at {o.get('base_url', 'http://localhost:11434')}. "
                "Open the Ollama app (or run 'ollama serve'), then press Test again.")
        if r.status_code == 200:
            return _clean(r.json().get("response") or "") or None
        raise RuntimeError(
            f"Ollama answered status {r.status_code}. Is model "
            f"'{o.get('model')}' downloaded? Try: ollama pull {o.get('model')}")

    sub = cfg.get(prov) or {}
    key, model = str(sub.get("api_key") or ""), str(sub.get("model") or "")
    if not key or key.startswith(_MASK):
        raise RuntimeError(f"No API key saved for {prov} yet — paste your free "
                           f"key in Settings. Get one at: {PROVIDERS[prov]['signup']}")
    if not model:
        raise RuntimeError(f"No model name saved for {prov} — set one in Settings.")

    if prov in ("groq", "openrouter", "cerebras"):
        url = {"groq": "https://api.groq.com/openai/v1/chat/completions",
               "openrouter": "https://openrouter.ai/api/v1/chat/completions",
               "cerebras": "https://api.cerebras.ai/v1/chat/completions"}[prov]
        headers = {"Authorization": f"Bearer {key}",
                   "Content-Type": "application/json"}
        if prov == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:8111"
        r = requests.post(url, headers=headers,
                          json={"model": model,
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=min(t, 180))
        if r.status_code == 200:
            return _clean(r.json()["choices"][0]["message"]["content"]) or None
        raise RuntimeError(_cloud_err(prov, r, model))

    if prov == "gemini":
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]},
                          timeout=min(t, 180))
        if r.status_code == 200:
            parts = r.json()["candidates"][0]["content"]["parts"]
            return _clean("".join(p.get("text", "") for p in parts)) or None
        raise RuntimeError(_cloud_err(prov, r, model))

    raise RuntimeError(f"Unknown AI provider '{prov}'.")


def _cloud_err(prov: str, r, model: str) -> str:
    body = r.text[:160].replace("\n", " ")
    if r.status_code in (401, 403):
        return f"{prov}: the API key was rejected (401/403). Check the key in Settings."
    if r.status_code == 429:
        return f"{prov}: free-tier limit hit (429). Wait a bit, or pick another free model."
    if r.status_code == 402:
        return (f"{prov}: this account has no quota yet (402). Log in at "
                f"{PROVIDERS[prov]['signup']} and enable the free tier, then test again.")
    if r.status_code == 404:
        return f"{prov}: model '{model}' not found (404). Check the exact model name."
    return f"{prov}: status {r.status_code} — {body}"


def narrative(symbol: str, report: dict, votes: list, trader: dict) -> str | None:
    """The 5-line trading note appended to proposals/reports. Never breaks
    the system: any failure just returns None."""
    try:
        prompt = (
            f"You are a PSX equity analyst. {symbol}: verdict "
            f"{report['discussion']['verdict']} (net {report['discussion']['net_score']}), "
            f"trader action {trader['action']}. Bull points: "
            f"{[f['factor'] for f in report['bullish']['factors']][:5]}. Bear points: "
            f"{[f['factor'] for f in report['bearish']['factors']][:5]}. "
            "Write a 5-line trading note with entry logic, invalidation, and targets.")
        out = generate(prompt)
        return out[:2000] if out else None
    except Exception:
        return None


def test_connection(provider: str | None = None, model: str | None = None,
                    api_key: str | None = None) -> dict:
    """Used by the Settings 'Test' button. With no arguments it tests the
    active (saved) provider; with arguments it tests exactly what the user
    typed into the Settings form, without saving anything."""
    cfg = appcfg.get_llm()
    if provider:
        cfg = dict(cfg)
        prov = provider.lower()
        cfg["provider"] = prov
        sub = dict(cfg.get(prov) or {})
        if model:
            sub["model"] = model
        given = str(api_key or "")
        if given and not given.startswith(_MASK):
            sub["api_key"] = given
        cfg[prov] = sub
    prov = (cfg.get("provider") or "ollama").lower()
    t0 = time.time()
    try:
        out = generate("Reply with exactly: OK", timeout=60, cfg=cfg)
        ms = int((time.time() - t0) * 1000)
        if out:
            return {"ok": True, "provider": prov, "ms": ms,
                    "message": f"Connected to {prov} in {ms}ms. Reply: {out[:120]}"}
        return {"ok": False, "provider": prov,
                "message": f"{prov} answered but returned an empty reply."}
    except Exception as e:
        return {"ok": False, "provider": prov, "message": str(e)[:240]}


def mask_keys(llm_cfg: dict) -> dict:
    """Copy of the llm config with API keys masked (for GET responses)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in llm_cfg.items()}
    for p in ("groq", "openrouter", "gemini", "cerebras"):
        k = (out.get(p) or {}).get("api_key", "")
        out[p]["api_key"] = (_MASK * 8 + k[-4:]) if k else ""
    return out


def unmask_payload(llm_patch: dict, saved: dict) -> dict:
    """If the client sent a masked/empty key, keep the previously saved one."""
    out = dict(llm_patch)
    for p in ("groq", "openrouter", "gemini", "cerebras"):
        sub = dict(out.get(p) or {})
        key = str(sub.get("api_key", "") or "")
        if key.startswith(_MASK):           # untouched masked value -> keep saved key
            sub["api_key"] = (saved.get(p) or {}).get("api_key", "")
        # empty string = user cleared the field on purpose -> stays cleared
        out[p] = sub
    return out
