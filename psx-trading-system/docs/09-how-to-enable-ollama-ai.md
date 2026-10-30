# 09 — How to Enable Local AI Notes (Ollama — optional, free)

> **New here?** Read the full step-by-step manual instead:
> **`14-connect-local-llm.md`** (install for Windows/Mac/Linux, model picker
> incl. DeepSeek, connect, test, troubleshooting). This page is the short version.

By default the system thinks with built-in rules (fast, offline, no setup).
Optionally, you can add a **free AI that runs on your own laptop** (nothing is
sent to the internet). It adds a short 5-line analyst note to each proposal.

## Step 1 — Install Ollama

1. Go to `https://ollama.com` and download Ollama for your computer.
2. Install and open it (it runs quietly in the background).

## Step 2 — Download a small free model

```bash
ollama pull llama3.1
```
This downloads ~4–5 GB once. Smaller/faster option: `ollama pull llama3.2`
(~2 GB, fine for short notes).

Check it works:
```bash
ollama run llama3.1 "Say hello in one line"
```
Press `Ctrl+D` to exit the chat.

## Step 2b — Other models you can use (including DeepSeek)

Any model on `https://ollama.com/library` works — the system just sends the
name to Ollama. Pick by your laptop's RAM:

| Laptop RAM | Recommended command | Size | Notes |
|---|---|---|---|
| 8 GB | `ollama pull qwen2.5:3b` | ~2 GB | Fast, good notes |
| 8 GB | `ollama pull llama3.2` | ~2 GB | Fast backup choice |
| 16 GB | `ollama pull llama3.1` | ~5 GB | Default, balanced |
| 16 GB | `ollama pull deepseek-r1:8b` | ~5 GB | Thinks step-by-step, slower |
| 16 GB | `ollama pull qwen2.5:14b` | ~9 GB | Smarter, needs free RAM |
| 32 GB+ | `ollama pull deepseek-r1:32b` | ~20 GB | Best reasoning |

DeepSeek notes:
- Use the **distilled** sizes above (`deepseek-r1:8b` etc.). The full
  671B DeepSeek-R1 cannot run on any laptop — ignore it.
- Reasoning models think before answering, so set **Timeout** to 90–120
  seconds in Settings → AI (default 25s is too short for them).
- The system automatically removes DeepSeek's private `<think>` thinking —
  you only see the clean 5-line note.
- First note after switching models is slow (model loads into RAM).

After pulling, type the exact name (e.g. `deepseek-r1:8b`) into
⚙ Settings → 🤖 Local AI → **Model**, press **Save AI**, then **Test connection**.

## Step 3 — Switch it on in the system

Open `config/watchlist.yaml`, find the bottom part, and set `enabled: true`:

```yaml
ollama:
  enabled: true
  base_url: http://localhost:11434
  model: llama3.1
  timeout_sec: 25
```

Restart the server. Open any stock → **Trade Proposal** → look for
**"Local-AI note"** under Deep Thinking.

## Notes

- First AI note takes ~20–60 seconds (model loads into memory). Later ones are faster.
- Needs ~8 GB free RAM for `llama3.1`; use `llama3.2` on weaker laptops.
- If Ollama is closed, the system silently skips the AI note — proposals still work.
- The AI note is a **bonus opinion**, not the decision-maker. The 6 rule-based
  Deep Thinking steps remain the real engine.
