"""Portal mirror — offline market data straight from the PSX Data Portal.

`data/portal.db` (or `data/portal.db.gz`, expanded on first use) is a SQLite
mirror of **dps.psx.com.pk**, written by the portal ingest job in the parent
repository (`strata_research/psxdb/`):

    company_snapshots   one row per symbol — price, P/E, mcap, yield, 52-week
                        range, circuit bands, 30-day average volume
    eod_bars            full OHLCV history per symbol (~10 years)
    index_bars          levels per index code (KSE100, KMI30, …)
    index_memberships   KSE100 / KMI30 constituents
    symbols             name, sector, sector code, listed-in indexes
    company_financials  reported sales, profit after tax, EPS, margins, growth

Everything here is real portal data captured at `meta()['as_of']`. Nothing in
this module touches the network, so it is the backbone of the system's offline
mode: the dashboard keeps working when PSX, Yahoo or the news feeds are
unreachable.

Priority ladder used by `psx_client`: fresh disk cache → **mirror** → live →
stale cache. The mirror usually wins because it carries up to ten years of bars
where the live path only pulls a couple of years.

NB: the mirror is deliberately *not* `data/psx.db` — that name belongs to the
paper-trading ledger.
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data"
DB_PATH = DATA / "portal.db"

# Where a gzip mirror may be found, in order. The parent repository ships the
# same file as data/psx.db.gz, so the app does not need its own 7 MB copy.
GZ_SOURCES = (
    DATA / "portal.db.gz",
    DATA / "psx.db.gz",
    BASE.parent / "data" / "psx.db.gz",
    BASE.parent / "data" / "psx.db",
    DATA / "psx-mirror.db.gz",
    DATA / "psx-mirror.db",
)

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None
_STATE = {"tried": False, "path": None, "error": None}
_META: dict | None = None

SOURCE = "PSX Data Portal mirror (dps.psx.com.pk)"

# Column order the rest of the app expects from `get_market_snapshot()`.
SNAPSHOT_COLUMNS = [
    "symbol", "sector", "listed_in", "market_cap", "price", "change_pct",
    "change_1y_pct", "pe_ratio", "dividend_yield", "free_float",
    "volume_avg_30d",
]


# ── connection handling ─────────────────────────────────────────────
def _expand(gz: Path, target: Path) -> Path | None:
    """Gunzip `gz` into `target` (atomic), or copy a plain SQLite file."""
    tmp = target.with_name(target.name + ".tmp")
    try:
        if gz.suffix == ".gz":
            with gzip.open(gz, "rb") as src, open(tmp, "wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
        else:
            shutil.copyfile(gz, tmp)
        tmp.replace(target)
        return target
    except Exception as exc:  # pragma: no cover - disk problems only
        _STATE["error"] = f"mirror expand failed: {exc}"
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _locate() -> Path | None:
    """Find the mirror, expanding a compressed copy into data/portal.db."""
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        return DB_PATH
    for candidate in GZ_SOURCES:
        if not candidate.exists() or candidate.stat().st_size == 0:
            continue
        if candidate == DB_PATH:
            return candidate
        out = _expand(candidate, DB_PATH)
        if out is not None:
            return out
    return None


def conn() -> sqlite3.Connection | None:
    """Read-only connection (None when no mirror has been shipped)."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            return _CONN
        if _STATE["tried"] and _STATE["path"] is None:
            return None
        _STATE["tried"] = True
        path = _locate()
        if path is None:
            _STATE["path"] = None
            return None
        try:
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                                check_same_thread=False, timeout=5.0)
            c.row_factory = sqlite3.Row
            c.execute("select 1 from company_snapshots limit 1").fetchone()
        except Exception as exc:
            _STATE["error"] = str(exc)
            _STATE["path"] = None
            return None
        _CONN = c
        _STATE["path"] = path
        return c


def available() -> bool:
    return conn() is not None


def path() -> Path | None:
    conn()
    return _STATE["path"]


def error() -> str | None:
    return _STATE["error"]


def _sql(sql: str, params: tuple | list = ()) -> pd.DataFrame:
    c = conn()
    if c is None:
        return pd.DataFrame()
    try:
        with _LOCK:
            return pd.read_sql_query(sql, c, params=params)
    except Exception as exc:  # pragma: no cover - corrupt file only
        _STATE["error"] = str(exc)
        return pd.DataFrame()


# ── metadata ────────────────────────────────────────────────────────
def meta(refresh: bool = False) -> dict:
    """Counts + data date, for the UI's "data source" badge."""
    global _META
    if _META is not None and not refresh:
        return _META
    if conn() is None:
        _META = {"available": False, "error": _STATE["error"], "source": SOURCE}
        return _META

    def one(sql: str, default=None):
        try:
            with _LOCK:
                row = _CONN.execute(sql).fetchone()  # type: ignore[union-attr]
            return row[0] if row is not None else default
        except Exception:
            return default

    _META = {
        "available": True,
        "source": SOURCE,
        "as_of": one("select max(as_of) from company_snapshots"),
        "last_bar": one("select max(trade_date) from eod_bars"),
        "first_bar": one("select min(trade_date) from eod_bars"),
        "symbols": one("select count(distinct symbol) from company_snapshots", 0),
        "bar_symbols": one("select count(distinct symbol) from eod_bars", 0),
        "bars": one("select count(*) from eod_bars", 0),
        "indices": one("select count(*) from indices", 0),
        "path": str(_STATE["path"] or ""),
    }
    return _META


def as_of() -> str | None:
    return meta().get("as_of")


def age_days() -> float | None:
    """How stale the mirror is (days). None when unknown."""
    a = as_of()
    if not a:
        return None
    try:
        d = datetime.strptime(str(a)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (date.today() - d).days


def _fix_market_cap(df: pd.DataFrame) -> pd.DataFrame:
    """Repair the mirror's market-cap scaling before anything else uses it.

    The portal publishes market cap in *thousands of PKR* on company pages and
    in rupees in the screener; the ingest writes whatever it captured, so some
    rows land 1000× too large (e.g. ENGRO at 260 trillion instead of 260 bn).

    Rule, in order:
      1. `shares` present → market cap = shares × price (exact).
      2. otherwise, implied shares (= mcap / price) more than 1000× the free
         float → assume the thousands mix-up and divide by 1000.
      3. otherwise keep the captured value.
    `mcap_source` records which rule was used, so the UI can stay honest.
    """
    if df.empty:
        return df
    price = pd.to_numeric(df.get("price"), errors="coerce")
    cap = pd.to_numeric(df.get("market_cap"), errors="coerce")
    shares = pd.to_numeric(df.get("shares"), errors="coerce")
    free_float = pd.to_numeric(df.get("free_float"), errors="coerce")
    out = cap.copy()
    src = pd.Series("portal", index=df.index, dtype=object)

    has_shares = shares.fillna(0) > 0
    has_price = price.fillna(0) > 0
    use_shares = has_shares & has_price
    out.loc[use_shares] = (shares * price).loc[use_shares]
    src.loc[use_shares] = "shares x price"

    implied = cap / price.where(has_price)
    too_big = ((~use_shares) & (free_float.fillna(0) > 0)
               & (implied > 1000 * free_float.fillna(0)))
    out.loc[too_big] = (cap / 1000).loc[too_big]
    src.loc[too_big] = "portal / 1000"

    src.loc[cap.fillna(0) <= 0] = "missing"
    df["market_cap"] = out.round(0)
    df["mcap_source"] = src
    return df


# ── snapshot (screener / pulse / quotes) ────────────────────────────
_SNAP_SQL = """
select c.symbol                as symbol,
       s.sector                as sector_name,
       s.sector_code           as sector_code,
       s.listed_in             as listed_in,
       s.name                  as name,
       s.is_etf                as is_etf,
       s.is_debt               as is_debt,
       c.as_of                 as as_of,
       c.price                 as price,
       c.prev_close            as prev_close,
       c.volume                as volume,
       c.pe                    as pe_ratio,
       c.pb                    as pb,
       c.market_cap            as market_cap,
       c.dividend_yield        as dividend_yield,
       c.free_float            as free_float,
       c.free_float_pct        as free_float_pct,
       c.avg_volume_30d        as volume_avg_30d,
       c.year_change_pct       as change_1y_pct,
       c.ytd_change_pct        as ytd_change_pct,
       c.high_52w              as high_52w,
       c.low_52w               as low_52w,
       c.circuit_high          as circuit_high,
       c.circuit_low           as circuit_low,
       c.shares                as shares
  from company_snapshots c
  join symbols s on s.symbol = c.symbol
"""


def snapshot() -> pd.DataFrame:
    """One row per listed symbol, shaped like the live screener table."""
    df = _sql(_SNAP_SQL)
    if df.empty:
        return df
    num = ("price", "prev_close", "volume", "pe_ratio", "pb", "market_cap",
           "dividend_yield", "free_float", "free_float_pct", "volume_avg_30d",
           "change_1y_pct", "ytd_change_pct", "high_52w", "low_52w",
           "circuit_high", "circuit_low", "shares")
    for c in num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    with_change = df["prev_close"].notna() & (df["prev_close"] > 0)
    df["change_pct"] = None
    df.loc[with_change, "change_pct"] = (
        (df.loc[with_change, "price"] / df.loc[with_change, "prev_close"] - 1) * 100
    ).round(2)
    df["change"] = (df["price"] - df["prev_close"]).round(2)
    df = _fix_market_cap(df)
    # `sector` carries the numeric portal code (what the live feed returns and
    # what fundamentals' sector-name lookup expects); `sector_label` is the
    # human-readable name used by the UI and the screener's sector filter.
    df["sector"] = (df["sector_code"].astype(str).str.strip()
                    .replace({"None": "", "nan": ""}))
    # Portal names arrive SHOUTING ("OIL & GAS EXPLORATION COMPANIES"); the UI
    # shows them in title case. Codes stay untouched — they are the join key.
    df["sector_label"] = (df["sector_name"].fillna("").astype(str).str.strip()
                          .str.title())
    df["source"] = SOURCE
    return df


def quote(symbol: str) -> dict:
    """Latest bar + snapshot fields for one symbol."""
    sym = str(symbol).upper().strip()
    df = _sql(_SNAP_SQL + " where c.symbol = ?", (sym,))
    if df.empty:
        return {}
    r = df.iloc[0].to_dict()
    last = last_bar(sym)

    def num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if f != f else f

    price = num(r.get("price"))
    prev = num(r.get("prev_close"))
    change = None if (price is None or prev is None) else round(price - prev, 2)
    change_pct = (None if (price is None or not prev)
                  else round((price / prev - 1) * 100, 2))
    out = {
        "symbol": sym,
        "ldcp": prev,
        "open": num(last.get("open")),
        "high": num(last.get("high")),
        "low": num(last.get("low")),
        "close": price,
        "change": change,
        "change_pct": change_pct,
        "volume": num(r.get("volume")),
        "avg_volume_30d": num(r.get("volume_avg_30d")),
        "market_cap": num(r.get("market_cap")),
        "pe_ratio": num(r.get("pe_ratio")),
        "pb": num(r.get("pb")),
        "dividend_yield": num(r.get("dividend_yield")),
        "free_float": num(r.get("free_float")),
        "shares": num(r.get("shares")),
        "high_52w": num(r.get("high_52w")),
        "low_52w": num(r.get("low_52w")),
        "circuit_high": num(r.get("circuit_high")),
        "circuit_low": num(r.get("circuit_low")),
        "change_1y_pct": num(r.get("change_1y_pct")),
        "ytd_change_pct": num(r.get("ytd_change_pct")),
        "sector": r.get("sector_name"),
        "sector_code": r.get("sector_code"),
        "name": r.get("name"),
        "date": str(last.get("date") or r.get("as_of") or ""),
        "as_of": r.get("as_of"),
        "source": SOURCE,
    }
    if out["market_cap"]:
        # same repair as the snapshot, for the single-symbol path
        fixed = _fix_market_cap(pd.DataFrame([r]))
        out["market_cap"] = num(fixed["market_cap"].iloc[0])
    return {k: v for k, v in out.items() if v is not None}


# ── history ─────────────────────────────────────────────────────────
def history(symbol: str, start: str | None = None,
            end: str | None = None) -> pd.DataFrame:
    """Ascending OHLCV bars: date, open, high, low, close, volume."""
    sym = str(symbol).upper().strip()
    sql = ("select trade_date as date, open, high, low, close, volume "
           "from eod_bars where symbol = ?")
    params: list = [sym]
    if start:
        sql += " and trade_date >= ?"
        params.append(str(start)[:10])
    if end:
        sql += " and trade_date <= ?"
        params.append(str(end)[:10])
    sql += " order by trade_date"
    df = _sql(sql, tuple(params))
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


def last_bar(symbol: str) -> dict:
    sym = str(symbol).upper().strip()
    df = _sql("select trade_date as date, open, high, low, close, volume "
              "from eod_bars where symbol = ? order by trade_date desc limit 1",
              (sym,))
    return df.iloc[0].to_dict() if not df.empty else {}


def has_history(symbol: str, min_rows: int = 30) -> bool:
    sym = str(symbol).upper().strip()
    df = _sql("select count(*) as n from eod_bars where symbol = ?", (sym,))
    try:
        return int(df["n"].iloc[0]) >= min_rows
    except Exception:
        return False


def symbols_with_history() -> list[str]:
    df = _sql("select distinct symbol from eod_bars order by symbol")
    return df["symbol"].tolist() if not df.empty else []


# ── indexes ─────────────────────────────────────────────────────────
INDEX_LABELS = {
    "KSE100": "KSE-100", "KSE30": "KSE-30", "KMI30": "KMI-30",
    "ALLSHR": "KSE All-Share", "KMIALLSHR": "KMI All-Share",
    "BKTI": "Banking Index", "OGTI": "Oil & Gas Index",
    "PSXDIV20": "PSX Dividend 20", "MII30": "MII-30",
    "UPP9": "UPP-9", "NITPGI": "NIT Pakistan Gateway",
    "NBPPGI": "NBP Pakistan Gateway", "MZNPI": "Meezan Pakistan",
    "JSMFI": "JS Momentum Factor", "JSGBKTI": "JS Global Banking",
    "ACI": "ACI", "KSE100PR": "KSE-100 (Price Return)",
    "HBLTTI": "HBL Total Treasury",
}


def indices() -> list[dict]:
    """Index levels with change %, newest captured session."""
    df = _sql("select code, name, level, change, change_pct, high, low, volume, as_of "
              "from indices order by code")
    if df.empty:
        return []
    for c in ("level", "change", "change_pct"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    missing = df["change_pct"].isna() & df["level"].notna()
    if missing.any():
        prev = df.loc[missing, "level"] - df.loc[missing, "change"]
        df.loc[missing, "change_pct"] = (
            df.loc[missing, "change"] / prev.replace(0, pd.NA) * 100
        ).astype(float).round(2)
    order = {k: i for i, k in enumerate(INDEX_LABELS)}
    rows = []
    for r in df.to_dict(orient="records"):
        code = str(r.get("code") or "").upper()
        rows.append({
            "code": code,
            "name": INDEX_LABELS.get(code, str(r.get("name") or code)),
            "value": None if pd.isna(r.get("level")) else round(float(r["level"]), 2),
            "change": None if pd.isna(r.get("change")) else round(float(r["change"]), 2),
            "pct": None if pd.isna(r.get("change_pct")) else round(float(r["change_pct"]), 2),
            "as_of": r.get("as_of"),
            "source": SOURCE,
        })
    rows.sort(key=lambda r: (order.get(r["code"], 99), r["code"]))
    return [r for r in rows if r["value"]]


def index_history(code: str, limit: int = 260) -> pd.DataFrame:
    df = _sql("select trade_date as date, open, high, low, close, volume "
              "from index_bars where index_code = ? order by trade_date desc limit ?",
              (str(code).upper(), int(limit)))
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def members(index_code: str = "KSE100") -> list[str]:
    df = _sql("select symbol from index_memberships where index_code = ? order by symbol",
              (str(index_code).upper(),))
    return df["symbol"].tolist() if not df.empty else []


def all_symbols() -> list[str]:
    """Every symbol the mirror knows — the full listed universe."""
    df = _sql("select symbol from symbols order by symbol")
    return df["symbol"].tolist() if not df.empty else []


def listed_in(index_code: str = "ALLSHR") -> list[str]:
    """Symbols whose `listed_in` mentions the index (KSE100 / ALLSHR / …)."""
    df = _sql("select symbol from symbols where listed_in like ? order by symbol",
              (f"%{str(index_code).upper()}%",))
    return df["symbol"].tolist() if not df.empty else []


# ── sectors ─────────────────────────────────────────────────────────
def sectors() -> pd.DataFrame:
    """Sector table with psxdata's column names: code, name, breadth, mcap."""
    df = snapshot()
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["sector_label"] = (df["sector_label"].replace("", pd.NA)
                                          .fillna("Unclassified"))
    df["_up"] = (df["change_pct"] > 0).fillna(False).astype(int)
    df["_down"] = (df["change_pct"] < 0).fillna(False).astype(int)
    df["_flat"] = (df["change_pct"] == 0).fillna(False).astype(int)
    df["_turnover"] = df["price"].fillna(0) * df["volume"].fillna(0)
    g = df.groupby("sector", dropna=False)
    out = pd.DataFrame({
        "sector_code": g["sector"].first(),
        "sector_name": g["sector_label"].first(),
        "advance": g["_up"].sum(),
        "decline": g["_down"].sum(),
        "unchanged": g["_flat"].sum(),
        "turnover": g["_turnover"].sum(),
        "market_cap_b": g["market_cap"].sum(min_count=1) / 1e9,
        "stocks": g.size(),
    }).reset_index(drop=True)
    out["sector_name"] = out["sector_name"].astype(str).str.title()
    out = out.sort_values("market_cap_b", ascending=False, na_position="last")
    return out.reset_index(drop=True)


def sector_symbols() -> dict[str, list[str]]:
    """{SECTOR NAME UPPER: [symbols]} for the Sectors tab."""
    df = _sql("select symbol, sector from symbols where sector is not null and sector != ''")
    if df.empty:
        return {}
    out: dict[str, list[str]] = {}
    for sym, sec in zip(df["symbol"], df["sector"]):
        out.setdefault(str(sec).upper(), []).append(str(sym))
    return out


# ── extra series for the Sectors tab ────────────────────────────────
def performance(symbol: str) -> dict:
    """Window returns + 52-week range from the mirror's own bar history."""
    h = history(symbol)
    if h.empty:
        return {}
    close = h["close"].astype(float)
    last = float(close.iloc[-1])

    def back(n: int):
        if len(close) > n and float(close.iloc[-1 - n]) > 0:
            return round((last / float(close.iloc[-1 - n]) - 1) * 100, 2)
        return None

    year = close.tail(252)
    return {
        "last": last,
        "chg_1w": back(5), "chg_1m": back(21), "chg_3m": back(63),
        "chg_6m": back(126), "chg_1y": back(252),
        "high_52w": float(year.max()) if len(year) else None,
        "low_52w": float(year.min()) if len(year) else None,
        "bars": int(len(close)),
        "last_date": str(h["date"].iloc[-1].date()),
    }


def week_changes() -> dict:
    """{symbol: weekly % change} in one query (last close vs close 5 bars back)."""
    df = _sql(
        "with ranked as ("
        "  select symbol, close, row_number() over ("
        "    partition by symbol order by trade_date desc) as rn"
        "  from eod_bars)"
        " select symbol,"
        "   max(case when rn = 1 then close end) as last_close,"
        "   max(case when rn = 6 then close end) as week_ago"
        " from ranked where rn <= 6 group by symbol")
    out: dict = {}
    if df.empty:
        return out
    for sym, last, old in zip(df["symbol"], df["last_close"], df["week_ago"]):
        try:
            if last and old and float(old) > 0:
                out[str(sym)] = round((float(last) / float(old) - 1) * 100, 2)
        except (TypeError, ValueError):
            continue
    return out


# ── reported financials ─────────────────────────────────────────────
def financials(symbol: str) -> pd.DataFrame:
    """Every reported metric for a symbol: rows = period × metric."""
    df = _sql("select period, metric, fiscal_year, quarter, label, value "
              "from company_financials where symbol = ? "
              "order by fiscal_year, quarter, metric", (str(symbol).upper(),))
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def has_financials(symbol: str) -> bool:
    return not financials(symbol).empty


FIN_METRICS = ("revenue", "net_income", "eps", "gross_margin_pct",
               "net_margin_pct", "eps_growth_pct", "peg")


def statements(symbol: str) -> dict:
    """Annual + quarterly statements, shaped like the yfinance branch.

    Values arrive from the portal in **thousands of PKR**; they are scaled to
    absolute PKR here so every downstream ratio and report is unit-safe.
    Nothing is invented: metrics the portal does not publish stay empty.
    """
    df = financials(symbol)
    if df.empty:
        return {}
    annual = df[df["quarter"].isna()]
    if annual.empty:
        annual = df[df["period"].astype(str).str.fullmatch(r"\d{4}")]

    def series(frame: pd.DataFrame, metric: str, scale: float = 1000.0) -> list:
        """Newest-first values. Money is in thousands on the portal (×1000 to
        rupees); per-share figures such as EPS are already rupees (scale 1)."""
        rows = frame[frame["metric"] == metric].sort_values(
            by=["fiscal_year"], ascending=False)
        vals = []
        for v in rows["value"]:
            try:
                vals.append(None if v != v else float(v) * scale)
            except (TypeError, ValueError):
                vals.append(None)
        return vals

    def pct_series(frame: pd.DataFrame, metric: str) -> list:
        rows = frame[frame["metric"] == metric].sort_values(
            by=["fiscal_year"], ascending=False)
        return [None if v != v else float(v) for v in rows["value"]]

    # newest-first, matching the yfinance column order the agents expect
    years = [str(int(y)) for y in
             sorted(annual["fiscal_year"].dropna().unique(), reverse=True)]
    rev = series(annual, "revenue")
    ni = series(annual, "net_income")
    eps = series(annual, "eps", scale=1.0)
    quarters = (df[df["quarter"].notna()]
                .drop_duplicates("period")
                .sort_values(["fiscal_year", "quarter"])
                .tail(4)["period"].tolist())
    out = {
        "source": SOURCE,
        "unit": "PKR (absolute)",
        "years": years,
        "quarters": quarters,
        "revenue": rev,
        "net_income": ni,
        "eps": eps,
        "gross_margin_pct": pct_series(annual, "gross_margin_pct"),
        "net_margin_pct_hist": pct_series(annual, "net_margin_pct"),
        "eps_growth_pct_hist": pct_series(annual, "eps_growth_pct"),
        "fcf": [], "assets": [], "liabilities": [], "equity": [],
        "revenue_cagr_3y": _cagr(rev[3] if len(rev) > 3 else (rev[1] if len(rev) > 1 else None),
                                 rev[0] if rev else None, 3 if len(rev) > 3 else 1),
        "ni_cagr_3y": _cagr(ni[3] if len(ni) > 3 else (ni[1] if len(ni) > 1 else None),
                            ni[0] if ni else None, 3 if len(ni) > 3 else 1),
        "net_margin_pct": (round(ni[0] / rev[0] * 100, 1)
                           if rev and ni and rev[0] and ni[0] else None),
        "de_ratio": None,
        "quarterly": _quarterly_table(df),
    }
    return out


def _quarterly_table(df: pd.DataFrame) -> list[dict]:
    """Recent quarters, newest last, one row per period."""
    q = df[df["quarter"].notna()]
    if q.empty:
        return []
    rows = []
    for period, grp in q.groupby("period", sort=False):
        vals = dict(zip(grp["metric"], grp["value"]))
        rows.append({
            "period": period,
            "fiscal_year": int(grp["fiscal_year"].iloc[0]),
            "quarter": int(grp["quarter"].iloc[0]),
            "revenue": _scaled(vals.get("revenue")),
            "net_income": _scaled(vals.get("net_income")),
            "eps": _scaled(vals.get("eps"), 1.0),
        })
    rows.sort(key=lambda r: (r["fiscal_year"], r["quarter"]))
    return rows[-8:]


def _scaled(v, factor: float = 1000.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f * factor


def _cagr(old, new, years):
    try:
        if old and new and old > 0 and new > 0 and years:
            return round(((new / old) ** (1 / years) - 1) * 100, 1)
    except Exception:
        pass
    return None


def coverage() -> dict:
    """What the mirror can serve, for docs / diagnostics."""
    m = meta()
    if not m.get("available"):
        return m
    return {
        **m,
        "age_days": age_days(),
        "history_symbols": len(symbols_with_history()),
    }


__all__ = [
    "SOURCE", "SNAPSHOT_COLUMNS", "available", "path", "error", "meta", "as_of",
    "age_days", "snapshot", "quote", "history", "last_bar", "has_history",
    "symbols_with_history", "indices", "index_history", "members", "all_symbols",
    "listed_in", "sectors", "sector_symbols", "performance", "financials",
    "has_financials", "statements", "week_changes", "coverage",
]
