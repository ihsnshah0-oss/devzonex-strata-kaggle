# 04 — How to Research a Stock (read a report like a pro)

## Steps

1. Search the symbol (e.g. `HBL`) or click it anywhere.
2. Look at the **chart + stat boxes** first: trend? RSI hot or cold? near support or resistance?
3. Open the **Research Desk** sub-tab. Read in this order:
   - **Verdict + confidence** (top). Example: `BUY · confidence 68% · net 63`.
   - **Debate sentence** — who won, bulls or bears, and by how much?
   - **🐂 Bullish case** — each reason shows `+points`. More points = stronger reason.
   - **🐻 Bearish case** — same for the risks. Never skip this side.
   - **⚖ Risk/Reward** — reference price, stop, targets, and the R:R grade.
4. Open **Trade Proposal**: check the trader's action, entry range, stop, targets,
   suggested quantity, and the Buy/Sell evidence lists.
5. Read the **🧠 Deep Thinking** box — the system's written reasoning, step by step.
6. Check **Fundamentals** (P/E, yield, 1-year change) and **News** (mood) for surprises.

## How to read the verdict

| Verdict | Simple meaning | What most users do |
|---|---|---|
| STRONG BUY (75+) | Many signals agree upside | Research size, plan entry + stop |
| BUY (60–74) | Evidence favors upside | Consider, wait for good price |
| HOLD (46–59) | Fight is even | Wait, no new position |
| SELL (31–45) | Evidence favors downside | Avoid new buys; review if held |
| STRONG SELL (≤30) | Many signals agree downside | Stay away |

## Rules of thumb

- **Confidence < 45%?** The team is unsure — treat any verdict as weak.
- **Verdict BUY but R:R "Poor"?** Setup is bad even if direction is right. Wait.
- **Bull 80 but Bear 70?** High bull score alone means little — the *gap* matters.
- Always decide the **stop-loss first**. If the stop hurts too much, buy less or skip.

## Same report from command line

```bash
python3 -c "
from src.analysis import researcher as R
r = R.full_report('HBL', 'Habib Bank Limited')
print('Verdict:', r['discussion']['verdict'], '| Net:', r['discussion']['net_score'])
print('Bull:', r['bullish']['score'], '| Bear:', r['bearish']['score'])
print('R:R:', r['risk_reward']['assessment'])"
```
