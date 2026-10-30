# 14 — Connect a Local LLM (Ollama) — Full Guide

A local LLM is a **free AI that runs on your own laptop**. Nothing is sent to
the internet, no account, no API key, no cost — ever.

## What it does in this system (and what it does NOT)

- **DOES:** adds a short 5-line "Local-AI note" to each Trade Proposal and
  Executive Report — a second opinion in plain words.
- **DOES NOT:** make decisions. The real engine (6 Deep Thinking steps,
  analyst debate, quant votes) is rule-based and always runs with or without
  AI. If Ollama is closed, the system silently skips the note — nothing breaks.

## Step 1 — Install Ollama (once, ~5 minutes)

| Your computer | What to do |
|---|---|
| **Windows** | Go to `https://ollama.com/download/windows` → download → run the installer → Ollama starts automatically (look for the 🦙 icon near the clock). |
| **Mac** | Go to `https://ollama.com/download/mac` → download → open the app → press "Next" until done. |
| **Linux** | Run this command: |

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Check it installed:

```bash
ollama --version
```

You should see something like `ollama version 0.11.x`. If the command is not
found, close and reopen your terminal (Windows: reopen PowerShell) and try again.

> 📱 **Phone users:** Ollama must run on the **laptop that serves the
> dashboard**, not on your phone. Your phone just shows the results.

## Step 2 — Download a model (once per model, ~5–20 minutes)

A "model" is the AI's brain file. Download one that fits your RAM:

| Your laptop RAM | Command (copy-paste) | Size | Speed/quality |
|---|---|---|---|
| 8 GB | `ollama pull qwen2.5:3b` | ~2 GB | ⭐ Fast, good notes |
| 8 GB | `ollama pull llama3.2` | ~2 GB | Fast backup choice |
| 16 GB | `ollama pull llama3.1` | ~5 GB | ⭐ Balanced default |
| 16 GB | `ollama pull deepseek-r1:8b` | ~5 GB | ⭐ Thinks step-by-step, slower but deeper |
| 16 GB | `ollama pull qwen2.5:14b` | ~9 GB | Smarter, needs free RAM |
| 32 GB+ | `ollama pull deepseek-r1:32b` | ~20 GB | Best reasoning |

**DeepSeek notes (important):**

- Only use the small sizes above (`deepseek-r1:8b` etc.). The full 671B
  DeepSeek-R1 needs a datacenter and **cannot** run on any laptop.
- Reasoning models "think" before answering, so they need a longer timeout
  (Step 3 below — set 90–120 seconds).
- The system automatically removes DeepSeek's private `<think>` thinking —
  you only see the clean 5-line note.

Test the model talks:

```bash
ollama run llama3.1 "Say hello in one line"
```

(Replace `llama3.1` with whatever you pulled.) Press `Ctrl+D` to exit.
See all your downloaded models anytime with `ollama list`.

## Step 3 — Connect it in the dashboard (2 minutes)

1. Open the dashboard → **⚙ Settings** → scroll to **🤖 Local AI (Ollama)**.
2. Fill in:
   - **Enabled:** ✅ checked
   - **Server:** `http://localhost:11434` (default — change only if Ollama runs on another machine)
   - **Model:** the exact name you pulled, e.g. `deepseek-r1:8b`
   - **Timeout:** `25` for normal models, **`90`–`120` for DeepSeek-R1 / reasoning models**
3. Press **Save AI**, then press **Test connection**.
   - ✅ Green + reply time = connected.
   - ❌ Red = read the message — it tells you the exact fix (usually "is Ollama running?" or "run: ollama pull NAME").

**No restart needed** — saving applies instantly.

<details>
<summary>Alternative: edit the file directly (same result)</summary>

In `config/watchlist.yaml`, bottom section:

```yaml
ollama:
  enabled: true
  base_url: http://localhost:11434
  model: deepseek-r1:8b
  timeout_sec: 90
```

Also instant — no restart needed.
</details>

## Step 4 — See it working

1. Open any stock → **Trade Proposal** (or 📄 Report tab → Generate).
2. Look under Deep Thinking for **"Local-AI note"** — your 5-line AI opinion.
3. First note takes 20–90 seconds (model loads into memory). Later notes are faster.

## Switching models later

1. `ollama pull NEW-NAME` (e.g. `ollama pull qwen2.5:14b`)
2. Settings → AI → change **Model** → **Save AI** → **Test connection**
3. First note on the new model is slow once (loading), then fast.

Free up disk anytime: `ollama rm OLD-NAME` deletes a downloaded model.
`ollama list` shows sizes.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Cannot reach Ollama at…" | Ollama is not running. Windows/Mac: open the Ollama app. Linux: `systemctl start ollama` (or run `ollama serve`). Then Test again. |
| "Is model 'X' downloaded?" | Run exactly what it says: `ollama pull X`. Names must match letter-for-letter (`deepseek-r1:8b` ≠ `deepseek-r1`). |
| Test works but notes never appear | Timeout too short for a reasoning model → set Timeout 90–120, Save, regenerate the report. |
| Notes appear but are slow | Normal on first use. Close heavy apps (Chrome tabs, games) to free RAM. Smaller model = faster (`qwen2.5:3b`). |
| Proposals work, AI section missing | Ollama was closed when you generated → open Ollama, then regenerate (press Generate again). |
| Works on laptop, not via phone | Ollama runs on the laptop — that is correct and enough. If the laptop sleeps, AI (and the dashboard) stop for the phone too. |

## ☁️ Alternative: FREE cloud APIs (no install at all)

Don't want to install Ollama? You can use a **free cloud API** instead —
sign up, copy a free key, paste it in Settings. All of these run
**open-source models** on free tiers:

| Provider | What you get | Free key from | Suggested model |
|---|---|---|---|
| **Groq** ⭐ | Very fast, Llama models | `https://console.groq.com/keys` | `llama-3.3-70b-versatile` |
| **OpenRouter** | Many free open models | `https://openrouter.ai/keys` | `meta-llama/llama-3.3-70b-instruct:free` |
| **Google Gemini** | Generous free API tier | `https://aistudio.google.com/apikey` | `gemini-2.0-flash` |

**Steps (2 minutes):**
1. Sign up at the link, create an API key, copy it.
2. Dashboard → ⚙ Settings → 🤖 AI notes:
   **Provider** = Groq / OpenRouter / Gemini → paste the **API key** →
   keep the suggested **Model name** → **Save AI settings** → **Test connection**.
3. Done — reports now include the AI note.

Notes:
- Your key is saved in `config/watchlist.yaml` on your machine only, and the
  Settings screen always shows it masked (`••••••6789`).
- Free tiers have daily limits — plenty for a personal dashboard. If you hit a
  limit you'll see a clear "429 — wait a bit" message.
- **Ollama is still the most private choice** (nothing leaves your PC); cloud
  APIs send the prompt to that provider.

## Uninstall (if you ever want to remove AI)

1. Settings → AI → uncheck **Enabled** → **Save AI** (system back to pure rules).
2. Optional: `ollama rm MODEL-NAME` per model, then uninstall the Ollama app.

## Links

- Download: `https://ollama.com/download`
- All models: `https://ollama.com/library`
- Quick version of this guide: `09-how-to-enable-ollama-ai.md`
