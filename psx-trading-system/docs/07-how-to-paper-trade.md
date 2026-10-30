# 07 — How to Paper Trade (practice with fake money)

Paper trading = real prices, fake money. Start with Rs 1,000,000 virtual cash.
Your diary is saved in `data/psx.db` (a single file — back it up by copying it).

## Steps

1. Research a stock first (guide 04) and open its **Trade Proposal**.
2. Note the **action, entry range, stop, targets, suggested qty**.
3. Open the **Paper Trade** tab.
4. Fill the order form:
   - **Symbol:** e.g. `OGDC`
   - **Side:** BUY (or SELL to close/trim)
   - **Qty:** use the proposal's suggested qty (or your risk-sized number)
   - **Price:** leave **blank** to fill at the live market price
5. Click **Execute (paper)**. Read the ✅ message.
6. Watch the **positions table**: qty, average price, live price, unrealized P&L.
7. When your stop or target hits (check the stock page), place the SELL order.
8. **Reset** wipes the diary and restores Rs 1,000,000 (asks first).

## Good habits

- Write your reason in trades: after buying, you know *why* from the proposal's evidence lists.
- Log **every** idea — winners and losers. A diary with only wins is lying to you.
- Risk rule: one trade should never risk more than **1–2%** of total equity.
- Heat rule: all open risks added together should stay under **6%** of equity.
- Review weekly: which verdicts worked? Which strategies paid? Adjust.

## From command line

```bash
# buy 100 LUCK at live price
python3 -c "from src.paper import ledger; print(ledger.place_order('LUCK', 'buy', 100))"

# see cash + positions + realized profit
python3 -c "from src.paper import ledger; print(ledger.positions())"

# order history
python3 -c "from src.paper import ledger; print(ledger.history(5))"

# reset to Rs 1,000,000
python3 -c "from src.paper import ledger; print(ledger.reset(1000000))"
```
