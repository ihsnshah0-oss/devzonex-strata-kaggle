"""Full-scale PSX stock screener.

Stage 1 filters the KSE All-Share snapshot (ALLSHR constituents: price, mcap,
P/E, yield, volume, day/1y change, sector). Stage 2 enriches the survivors
with technicals from EOD history (RSI, SMAs, volume spikes, 52-week
position, crosses) — capped for speed, everything cached.
"""
import pandas as pd

from ..analysis import indicators as ind
from ..data import psx_client as psx

def _tech_cap() -> int:
    """Max symbols deep-checked per screen (Settings tab → Trading)."""
    try:
        from ..data import appconfig as appcfg
        v = int(appcfg.get_settings().get("screener_max_stocks", 80) or 80)
        return max(20, min(120, v))
    except Exception:
        return 80


TECH_CAP = 80  # fallback; live value comes from _tech_cap()


def universe() -> pd.DataFrame:
    """KSE All-Share (ALLSHR) constituents only — the system's universe."""
    df = psx.get_market_snapshot().copy()
    df["symbol"] = df["symbol"].astype(str).str.upper()
    for c in ("price", "market_cap", "pe_ratio", "dividend_yield",
              "volume_avg_30d", "change_pct", "change_1y_pct"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    try:
        allshr = set(psx.get_allshr())
        df["symbol_n"] = df["symbol"].map(psx._norm)
        df = df[df["symbol_n"].isin(allshr)].drop(columns=["symbol_n"]).copy()
        df["in_allshr"] = True
    except Exception:
        df["in_allshr"] = True          # if the index fetch fails, keep snapshot
    try:
        kse = set(psx.get_kse100())
        df["in_kse100"] = df["symbol"].map(psx._norm).isin(kse)
    except Exception:
        df["in_kse100"] = False
    return df


def _fnum(v, default=None):
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _sector_key(v) -> str:
    """Normalise a sector code or name so "0820", 820 and 820.0 all match."""
    if v is None:
        return ""
    txt = str(v).strip()
    if not txt or txt.lower() in ("nan", "none"):
        return ""
    try:
        return str(int(float(txt)))
    except (TypeError, ValueError):
        return txt.lower()


def apply_fundamental(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    q = df.copy()
    if f.get("kse100_only"):
        q = q[q["in_kse100"]]
    sectors = f.get("sectors") or []
    if sectors:
        # The snapshot carries the portal's numeric sector code in `sector` and
        # the human name in `sector_label`; the dropdown sends names, older
        # callers send codes — accept either.
        want = {_sector_key(s) for s in sectors}
        codes = q["sector"].map(_sector_key)
        labels = (q["sector_label"].map(_sector_key)
                  if "sector_label" in q else codes)
        q = q[codes.isin(want) | labels.isin(want)]
    for key, col, op in (
            ("min_price", "price", "ge"), ("max_price", "price", "le"),
            ("min_mcap", "market_cap", "ge"), ("max_mcap", "market_cap", "le"),
            ("min_pe", "pe_ratio", "ge"), ("max_pe", "pe_ratio", "le"),
            ("min_yield", "dividend_yield", "ge"), ("max_yield", "dividend_yield", "le"),
            ("min_avgvol", "volume_avg_30d", "ge"),
            ("min_day_chg", "change_pct", "ge"), ("max_day_chg", "change_pct", "le"),
            ("min_1y_chg", "change_1y_pct", "ge"), ("max_1y_chg", "change_1y_pct", "le")):
        v = _fnum(f.get(key))
        if v is not None and col in q:
            q = q[q[col] >= v] if op == "ge" else q[q[col] <= v]
    if f.get("exclude_zero_pe"):
        q = q[q["pe_ratio"] > 0]
    return q


def enrich_technical(symbols: list[str], workers: int = 4) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    def one(sym: str) -> dict | None:
        try:
            # reuse full cache when fresh, else fetch the small lite history
            h = psx._read_fresh_csv(psx.CACHE / f"eod_{sym}.csv", 24, min_rows=210)
            if h is None:
                h = psx.get_history(sym, max_age_hours=24, lite=True)
            if len(h) < 60:
                return None
            s = ind.snapshot(h)
            if "error" in s:
                return None
            s["symbol"] = sym
            return s
        except Exception:
            return None

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for s in ex.map(one, symbols[:_tech_cap()]):
            if s:
                rows.append(s)
    return pd.DataFrame(rows)


def apply_technical(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    q = df.copy()
    rsi_min, rsi_max = _fnum(f.get("rsi_min")), _fnum(f.get("rsi_max"))
    if rsi_min is not None:
        q = q[q["rsi14"] >= rsi_min]
    if rsi_max is not None:
        q = q[q["rsi14"] <= rsi_max]
    if f.get("above_sma50") is True:
        q = q[q["above_sma50"] == True]  # noqa: E712
    if f.get("above_sma50") is False:
        q = q[q["above_sma50"] == False]  # noqa: E712
    if f.get("above_sma200") is True:
        q = q[q["above_sma200"] == True]  # noqa: E712
    if f.get("above_sma200") is False:
        q = q[q["above_sma200"] == False]  # noqa: E712
    if f.get("golden_cross"):
        q = q[q["golden_cross"] == True]  # noqa: E712
    if f.get("macd_bull") is True:
        q = q[q["macd_bull"] == True]  # noqa: E712
    if f.get("breakout_20d"):
        q = q[q["breakout_20d"] == True]  # noqa: E712
    if f.get("breakdown_20d"):
        q = q[q["breakdown_20d"] == True]  # noqa: E712
    vr = _fnum(f.get("min_vol_ratio"))
    if vr is not None:
        q = q[q["vol_ratio"] >= vr]
    near_hi = _fnum(f.get("near_52w_high_pct"))
    if near_hi is not None:
        q = q[q["off_52w_high_pct"] >= -abs(near_hi)]
    near_lo = _fnum(f.get("near_52w_low_pct"))
    if near_lo is not None and "low_52w" in q:
        q = q[((q["close"] / q["low_52w"] - 1) * 100 <= abs(near_lo))]
    return q


def run(filters: dict | None = None) -> dict:
    f = filters or {}
    base = universe()
    stage1 = apply_fundamental(base, f)
    needs_tech = any(k in f for k in (
        "rsi_min", "rsi_max", "above_sma50", "above_sma200", "golden_cross",
        "macd_bull", "breakout_20d", "breakdown_20d", "min_vol_ratio",
        "near_52w_high_pct", "near_52w_low_pct")) or f.get("include_technicals", True)
    tech = pd.DataFrame()
    if needs_tech and len(stage1):
        # enrich most liquid first
        order = stage1.sort_values("volume_avg_30d", ascending=False,
                                   na_position="last")["symbol"].tolist()
        tech = enrich_technical(order)
    merged = stage1.merge(tech, on="symbol", how="left", suffixes=("", "_t")) if len(tech) else stage1
    if needs_tech and len(tech):
        merged = apply_technical(merged, f)
    sort = f.get("sort", "market_cap")
    if sort in merged.columns:
        merged = merged.sort_values(sort, ascending=bool(f.get("ascending", False)),
                                    na_position="last")
    limit = int(f.get("limit", 50) or 50)
    rows = merged.head(limit).replace({pd.NA: None}).to_dict(orient="records")
    clean = [{k: (None if (isinstance(v, float) and pd.isna(v)) else v)
              for k, v in r.items()} for r in rows]
    return {"count": len(merged), "showing": len(clean),
            "tech_enriched": len(tech), "rows": clean}


# ── one-click preset screens (TickerAnalysts-style) ─────────────────
PRESETS = {
    "fresh-breakout": {"label": "Fresh Breakout", "desc": "Breaking 20-day highs on rising volume",
                       "filters": {"breakout_20d": True, "min_vol_ratio": 1.2, "min_avgvol": 100000}},
    "volume-shockers": {"label": "Volume Shockers", "desc": "Today's volume exploding vs average",
                        "filters": {"min_vol_ratio": 2.0, "min_avgvol": 100000, "sort": "vol_ratio"}},
    "momentum-surge": {"label": "Momentum Surge", "desc": "Strong trend + healthy RSI + volume",
                       "filters": {"above_sma50": True, "rsi_min": 55, "rsi_max": 75,
                                   "min_vol_ratio": 1.1, "min_avgvol": 200000}},
    "oversold-bounce": {"label": "Oversold Bounce", "desc": "Washed-out RSI, snap-back candidates",
                        "filters": {"rsi_max": 32, "min_avgvol": 100000, "sort": "rsi14", "ascending": True}},
    "golden-cross": {"label": "Golden Cross", "desc": "50DMA just crossed above 200DMA",
                     "filters": {"golden_cross": True}},
    "near-52w-high": {"label": "Near 52-Week High", "desc": "Within 5% of yearly highs — leaders",
                      "filters": {"near_52w_high_pct": 5, "min_avgvol": 200000}},
    "value-picks": {"label": "Value Picks", "desc": "Cheap earnings, liquid names",
                    "filters": {"max_pe": 10, "exclude_zero_pe": True, "min_avgvol": 200000,
                                "min_mcap": 5_000_000_000, "sort": "pe_ratio", "ascending": True}},
    "dividend-kings": {"label": "Dividend Kings", "desc": "High yield + profitable + liquid",
                       "filters": {"min_yield": 7, "exclude_zero_pe": True, "min_avgvol": 100000,
                                   "sort": "dividend_yield"}},
    "blue-chip-quality": {"label": "Blue-Chip Quality", "desc": "KSE-100, uptrend, pays dividend",
                          "filters": {"kse100_only": True, "above_sma50": True, "min_yield": 2}},
    "hidden-accumulation": {"label": "Hidden Accumulation", "desc": "Volume building, price calm",
                            "filters": {"min_vol_ratio": 1.4, "min_day_chg": -2, "max_day_chg": 2,
                                        "min_avgvol": 300000}},
    "falling-knives": {"label": "Falling Knives", "desc": "20-day breakdowns — avoid or stalk",
                       "filters": {"breakdown_20d": True, "sort": "change_pct", "ascending": True}},
    "illiquid-avoid": {"label": "Low Liquidity (Avoid)", "desc": "Thin volume — trade with care",
                       "filters": {"max_price": 1e12, "sort": "volume_avg_30d", "ascending": True,
                                   "limit": 50}},
}
