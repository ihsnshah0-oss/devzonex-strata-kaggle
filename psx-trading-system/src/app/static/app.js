/* PSX Live & Research dashboard app */
const $ = s => document.querySelector(/^[#.]/.test(s) || s.includes(" ") ? s : "#" + s);
const S = { universe: [], presets: [], pulse: null, sym: "OGDC", bars: [],
  rangeM: 12, sTab: "research", newsTab: "news", R: {}, P: {}, N: {}, F: {}, D: {}, watchMeta: [],
  cfg: null, wlEdit: [] };

const fmtRs = v => v == null ? "—" : "Rs " + Number(v).toLocaleString("en-PK", { maximumFractionDigits: 2 });
const fmtN = v => v == null ? "—" : Number(v).toLocaleString("en-PK", { maximumFractionDigits: 2 });
const fmtPct = v => v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
const cls = v => v == null ? "" : (v >= 0 ? "pos" : "neg");
const fmtMcap = v => {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(1);
  if (a >= 1e6) return (v / 1e9).toFixed(2);
  return fmtN(v);
};
function toast(m) {
  const t = $("#toast"); t.textContent = m; t.style.display = "block";
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display = "none", 3200);
}
const APP_VERSION = "1.2.0";
// Safe binder: a missing button can never crash the whole app again.
function on(id, ev, fn) {
  const el = document.getElementById(id);
  if (el) el.addEventListener(ev, fn);
  else console.warn("PSX Live & Research: missing element #" + id);
}
// Any unexpected error becomes a visible message instead of silence.
window.addEventListener("error", e => {
  try { toast("Error: " + (e.message || "unknown") + " — open Settings, Run health check"); } catch (_) {}
});
async function GET(u) {
  const r = await fetch(u);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
async function POST(u, body) {
  const r = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
async function PUT(u, body) {
  const r = await fetch(u, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
function pill(t) {
  t = (t || "").toUpperCase();
  if (["BUY", "STRONG BUY", "ACCUMULATE"].includes(t)) return `<span class="pill p-buy">${t}</span>`;
  if (["SELL", "STRONG SELL", "REDUCE"].includes(t)) return `<span class="pill p-sell">${t}</span>`;
  return `<span class="pill p-hold">${t || "HOLD"}</span>`;
}
function quickSignal(s) {
  if (!s || s.error) return "—";
  let p = 0;
  if (s.above_ema50) p++; else p--;
  if (s.above_ema200) p++; else p--;
  if (s.macd_bull) p++; else p--;
  const rsi = s.rsi14;
  if (rsi != null) { if (rsi > 70) p--; else if (rsi < 30) p++; else if (rsi >= 50) p++; else p--; }
  if (s.breakout_20d) p++;
  if (s.breakdown_20d) p--;
  return p >= 3 ? "STRONG BUY" : p >= 1 ? "BUY" : p <= -3 ? "STRONG SELL" : p <= -1 ? "SELL" : "HOLD";
}

/* -- state memory: reopen where you left off (browser localStorage) -- */
const MEM_KEY = "psx_alpha_ui_v1";
function memLoad() { try { return JSON.parse(localStorage.getItem(MEM_KEY)) || {}; } catch (e) { return {}; } }
function memSave(patch) {
  try {
    const cur = memLoad();
    localStorage.setItem(MEM_KEY, JSON.stringify(Object.assign(cur, patch, { ts: Date.now() })));
  } catch (e) { /* storage blocked (private mode) - state just won't persist */ }
}
on("repSym", "change", e => memSave({ repSym: e.target.value }));

/* -- tabs / router -- */
on("tabs", "click", e => {
  const b = e.target.closest("button"); if (!b || !b.dataset.view) return;
  showView(b.dataset.view);
});
function showView(v) {
  if (!v) return;
  memSave({ view: v });
  document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("active", x.dataset.view === v));
  document.querySelectorAll(".view").forEach(x => x.classList.toggle("active", x.id === "v-" + v));
  if (v === "paper") { loadBroker(); loadPaper(); }
  if (v === "home") { loadNews(); if (S.newsTab === "ann") loadAnn(); if (S.newsTab === "rep") loadRep(); }
  if (v === "heatmap") loadHeatmap();
  if (v === "sectors") loadSectors();
  if (v === "settings") loadSettings();
  if (v === "money") loadMoney();
  if (v === "report") { fillRepSyms(); paintRepPane(S.repMode || "single"); loadDesk(); }
  window.scrollTo({ top: 0 });
}
function paintRepPane(mode) {
  S.repMode = mode;
  const s = $("#reportPane"), c = $("#comparePane");
  if (s) s.style.display = mode === "single" ? "" : "none";
  if (c) c.style.display = mode === "compare" ? "" : "none";
  document.querySelectorAll("#repModeTabs button").forEach(b => b.classList.toggle("active", b.dataset.k === mode));
}
document.querySelectorAll("#repModeTabs button").forEach(b =>
  b.addEventListener("click", () => paintRepPane(b.dataset.k)));

/* ── search ── */
/* one search engine, two boxes (header + dashboard hero) */
function bindSearchBox(inp, sug) {
  if (!inp || !sug) return;
  inp.addEventListener("input", () => {
    const q = inp.value.trim().toUpperCase();
    if (q.length < 1) { sug.style.display = "none"; return; }
    const hits = (S.universe || []).filter(u => u.symbol.includes(q)).slice(0, 9);
    sug.innerHTML = hits.map(h =>
      `<div data-s="${h.symbol}"><b>${h.symbol}</b> · ${fmtRs(h.price)} <span class="${cls(h.chg)}">${fmtPct(h.chg)}</span></div>`).join("")
      || `<div>No match</div>`;
    sug.style.display = "block";
  });
  sug.addEventListener("click", e => {
    const d = e.target.closest("div[data-s]"); if (!d) return;
    sug.style.display = "none"; inp.value = "";
    openStock(d.dataset.s);
  });
  inp.addEventListener("keydown", e => {
    if (e.key === "Enter" && inp.value.trim()) {
      sug.style.display = "none"; openStock(inp.value.trim().toUpperCase()); inp.value = "";
    }
  });
}
const sIn = $("#search"), sUg = $("#suggest");
bindSearchBox(sIn, sUg);
document.addEventListener("click", e => {
  if (!e.target.closest(".searchbox")) { if (sUg) sUg.style.display = "none"; }
});
document.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); sIn && sIn.focus(); }
});

/* ── clock (PKT + local) / signals status / refresh + auto-refresh ── */
function tickClock() {
  if (!document.getElementById("clock")) return;
  try {
    const pk = new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Karachi", hour12: false });
    const d = new Date().toLocaleDateString("en-GB", { timeZone: "Asia/Karachi", day: "2-digit", month: "short" });
    const local = new Date().toLocaleTimeString("en-GB", { hour12: false });
    $("#clock").innerHTML = `${d} · ${pk} PKT <span class="local">(${local} local)</span>`;
  } catch (e) { $("#clock").textContent = new Date().toLocaleTimeString(); }
}
setInterval(tickClock, 1000); tickClock();

function fmtTs(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      timeZone: "Asia/Karachi", day: "2-digit", month: "short",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  } catch (e) { return iso; }
}
async function loadSigStatus() {
  try {
    const s = await GET("/api/signals/status");
    $("#sigTime").textContent = "Signals: " + (s.last_watchlist_signals_at ? fmtTs(s.last_watchlist_signals_at) : "—");
    const m = $("#mktBadge");
    const open = s.market_status === "OPEN";
    m.textContent = open ? "● MARKET OPEN" : "○ MARKET CLOSED";
    m.className = "mkt " + (open ? "open" : "closed");
    m.title = s.market_note || "";
    const w = $("#wlUpdated");
    if (w && s.last_watchlist_signals_at)
      w.textContent = "· Signals updated " + fmtTs(s.last_watchlist_signals_at) + " PKT";
  } catch (e) { /* status stays blank */ }
}

let refreshing = false, autoLeft = 60, autoTimer = null;
function paintCountdown() {
  const el = $("#autoIn");
  if (!el) return;
  const ui = (S.cfg && S.cfg.ui) || {};
  if (!ui.auto_refresh_enabled) { el.textContent = ""; return; }
  el.textContent = refreshing ? "⟳ refreshing…" : `auto ⟳ in ${autoLeft}s`;
}
async function doRefresh(auto) {
  if (refreshing) return;
  refreshing = true; paintCountdown();
  const b = $("#refreshBtn");
  b.disabled = true; b.classList.add("spinning");
  b.textContent = auto ? "⟳ Auto…" : "⟳ Refreshing…";
  try {
    const r = await POST("/api/refresh", { full: false });
    S.R = {}; S.P = {}; S.N = {};  // drop saved reports → recompute fresh
    await Promise.all([loadPulse(), loadWatch(), loadSigStatus()]);
    const active = (document.querySelector(".view.active") || {}).id;
    if (active === "v-stock") loadStock();
    if (active === "v-paper") loadPaper();
    if (active === "v-home") { loadLanding(); loadNews(); }
    if (active === "v-heatmap") loadHeatmap();
    if (!auto) {
      let msg = "✅ Data + signals refreshed · " + fmtTs(r.refreshed_at) + " PKT";
      if (r.pulse_error) msg = "Pulse issue: " + r.pulse_error;
      else if (r.watchlist_error) msg = "Watchlist issue: " + r.watchlist_error;
      toast(msg);
    }
  } catch (e) { toast((auto ? "Auto-refresh" : "Refresh") + " failed: " + e.message); }
  b.disabled = false; b.classList.remove("spinning"); b.textContent = "⟳ Refresh";
  refreshing = false; paintCountdown();
}
on("refreshBtn", "click", () => doRefresh(false));
on("settingsIconBtn", "click", () => showView("settings"));
function setupAutoRefresh() {
  clearInterval(autoTimer);
  const ui = (S.cfg && S.cfg.ui) || {};
  autoLeft = Math.max(30, Math.min(600, +ui.auto_refresh_sec || 60));
  paintCountdown();
  autoTimer = setInterval(() => {
    const u2 = (S.cfg && S.cfg.ui) || {};
    if (!u2.auto_refresh_enabled || document.hidden || refreshing) return;
    autoLeft--;
    if (autoLeft <= 0) {
      autoLeft = Math.max(30, Math.min(600, +u2.auto_refresh_sec || 60));
      doRefresh(true);
    }
    paintCountdown();
  }, 1000);
}

/* ── HOME ── */
async function loadPulse() {
  try {
    const p = await GET("/api/pulse");
    S.pulse = p;
    $("#idxGrid").innerHTML = p.indices.length ? p.indices.map(i =>
      `<div class="idx"><div class="n">${i.name}</div><div class="v">${fmtN(i.value)}</div>
       <div class="${i.change >= 0 ? "up" : "down"}">${i.change >= 0 ? "▲" : "▼"} ${fmtN(Math.abs(i.change))} (${fmtPct(i.pct)})</div></div>`).join("")
      : `<div class="idx"><div class="n">INDICES</div><div class="v">—</div><div>offline</div></div>`;
    const b = p.breadth;
    $("#breadth").textContent = `▲ ${b.advancing} advancing · ▼ ${b.declining} declining · ━ ${b.unchanged} unchanged (of ${b.total})`;
    const o = p.official || {};
    if (o.status && o.breadth && o.breadth.advanced != null) {
      const ob = o.breadth;
      $("#officialPulse").innerHTML =
        `🏛️ Official PSX: <b>${o.status}</b> (as of ${o.as_of || "?"}) · ` +
        `▲ ${ob.advanced} adv / ▼ ${ob.declined} dec / ━ ${ob.unchanged} unch (of ${ob.total}) · ` +
        `Volume ${niceNum(o.volume)} · Value Rs ${niceNum(o.value)} · Trades ${niceNum(o.trades)}`;
    } else { $("#officialPulse").innerHTML = ""; }
    const activeTab = (document.querySelector("#mktTabs button.active") || {}).dataset;
    renderMkt((activeTab && activeTab.k) || "gainers");
  } catch (e) { toast("Market pulse failed: " + e.message); }
}
function renderMkt(k) {
  let rows = (S.pulse && S.pulse[k]) || [];
  if (S.wlSet && S.wlSet.size) rows = rows.filter(r => S.wlSet.has(String(r.symbol || "").toUpperCase()));
  $("#mktTbl tbody").innerHTML = rows.map(r =>
    `<tr class="clickable" data-s="${r.symbol}"><td><b>${r.symbol}</b></td><td>${fmtRs(r.price)}</td>
     <td class="${cls(r.change_pct)}">${fmtPct(r.change_pct)}</td><td>${fmtN(r.pe_ratio)}</td>
     <td>${r.dividend_yield == null ? "—" : Number(r.dividend_yield).toFixed(1) + "%"}</td>
     <td>${r.volume_avg_30d ? niceNum(r.volume_avg_30d) : "—"}</td></tr>`).join("");
}
on("mktTabs", "click", e => {
  const b = e.target.closest("button"); if (!b) return;
  document.querySelectorAll("#mktTabs button").forEach(x => x.classList.toggle("active", x === b));
  renderMkt(b.dataset.k);
});
document.addEventListener("click", e => {
  const tr = e.target.closest("tr.clickable[data-s]");
  if (tr) openStock(tr.dataset.s);
});
/* ── watchlist: multiple lists + color flags + EMA chips ── */
const FLAG_COLORS = ["red", "orange", "yellow", "green", "blue", "purple"];
let WL = { master: [], lists: [], flags: {}, notes: {}, current: "master" };
const escA = t => String(t == null ? "" : t).replace(/&/g, "&amp;")
  .replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function loadWlMeta() {
  try {
    const d = await GET("/api/watchlists");
    WL.master = d.master; WL.lists = d.lists; WL.flags = d.flags;
    WL.notes = d.notes || {};
  } catch (e) { /* meta is optional — table still renders */ }
  S.wlSet = new Set((WL.master || []).map(x => String(x).toUpperCase()));
  if (S.pulse) {
    const at = (document.querySelector("#mktTabs button.active") || {}).dataset;
    if (at && at.k) renderMkt(at.k);
  }
  paintWlListsBar();
}
function curListSymbols() {
  if (WL.current === "master") return WL.master;
  const l = WL.lists.find(x => x.name === WL.current);
  return l ? l.symbols : [];
}
function paintWlListsBar() {
  const bar = $("#wlListsBar"); if (!bar) return;
  const chip = (name, active, label) =>
    `<button class="btn small ${active ? "primary" : "ghost"} wlChip" data-list="${name}" title="Show ${name}">${label}</button>`;
  let html = chip("master", WL.current === "master", `⭐ Master (${WL.master.length})`);
  for (const l of WL.lists) html += chip(l.name, WL.current === l.name, `${l.name} (${l.symbols.length})`);
  html += `<button class="btn small ghost" id="wlNewList" title="Create a new sub-list (stocks come from the Master list)">＋ New list</button>`;
  if (WL.current !== "master") {
    html += `<button class="btn small ghost" id="wlDelList" title="Delete this list (stocks stay in Master)">🗑 Delete list</button>`;
    const missing = WL.master.filter(s => !curListSymbols().includes(s));
    if (missing.length) html += `<select id="wlAddSel" class="sub" style="max-width:160px"><option value="">＋ add stock…</option>` +
      missing.map(s => `<option value="${s}">${s}</option>`).join("") + `</select>`;
  }
  bar.innerHTML = html;
  bar.querySelectorAll(".wlChip").forEach(b => b.onclick = () => { WL.current = b.dataset.list; loadWatch(); });
  const nl = $("#wlNewList");
  if (nl) nl.onclick = async () => {
    const name = (prompt("Name for the new list:") || "").trim();
    if (!name) return;
    const r = await POST("/api/watchlists/list", { name, symbols: [] });
    if (!r.ok) { toast("❌ " + r.error); return; }
    WL.current = name; await loadWlMeta(); loadWatch();
  };
  const dl = $("#wlDelList");
  if (dl) dl.onclick = async () => {
    if (!confirm(`Delete the list "${WL.current}"? Its stocks stay in the Master list.`)) return;
    await fetch("/api/watchlists/list/" + encodeURIComponent(WL.current), { method: "DELETE" });
    WL.current = "master"; await loadWlMeta(); loadWatch();
  };
  const asel = $("#wlAddSel");
  if (asel) asel.onchange = async () => {
    const sym = asel.value; if (!sym) return;
    await POST("/api/watchlists/list", { name: WL.current, symbols: [...curListSymbols(), sym] });
    await loadWlMeta(); loadWatch();
  };
}
/* ── FLAG COLOR PICKER: click a flag dot → popup with 6 colors + clear ── */
let FLAG_POP_CLEANUP = null;
function closeFlagPicker() {
  if (FLAG_POP_CLEANUP) { FLAG_POP_CLEANUP(); FLAG_POP_CLEANUP = null; }
  const p = $("#flagPop"); if (p) p.remove();
}
function openFlagPicker(dotEl, sym) {
  closeFlagPicker();
  const cur = WL.flags[sym] || "";
  const pop = document.createElement("div");
  pop.id = "flagPop";
  pop.style.cssText = "position:absolute;z-index:999;display:flex;gap:9px;align-items:center;padding:9px 11px;" +
    "background:#14251d;border:1px solid #2c4a3c;border-radius:10px;box-shadow:0 8px 20px rgba(0,0,0,.55)";
  const sw = (cls, colr, label) =>
    `<span class="fl-dot ${cls}" data-fc="${colr}" title="${label}"` +
    ` style="width:18px;height:18px${cur === colr ? ";outline:2px solid #e5e7eb;outline-offset:2px" : ""}"></span>`;
  pop.innerHTML = FLAG_COLORS.map(c => sw("fl-" + c, c, c[0].toUpperCase() + c.slice(1) + " flag")).join("") +
    `<span class="fl-dot" data-fc="" title="Clear the flag" style="width:18px;height:18px;display:inline-flex;` +
    `align-items:center;justify-content:center;font-size:11px;color:#9ca3af${cur === "" ? ";outline:2px solid #e5e7eb;outline-offset:2px" : ""}">✕</span>`;
  document.body.appendChild(pop);
  const r = dotEl.getBoundingClientRect();
  let left = r.left + window.scrollX - 12;
  pop.style.top = (r.bottom + window.scrollY + 7) + "px";
  pop.style.left = Math.max(8, left) + "px";
  if (left + pop.offsetWidth > document.documentElement.clientWidth - 8) {
    pop.style.left = Math.max(8, r.right + window.scrollX - pop.offsetWidth) + "px";
  }
  pop.querySelectorAll("[data-fc]").forEach(sp => sp.onclick = async ev => {
    ev.stopPropagation();
    const res = await POST("/api/watchlists/flag", { symbol: sym, color: sp.dataset.fc });
    if (res.ok) { WL.flags = res.flags; loadWatch(); }
    closeFlagPicker();
  });
  const outside = ev => { if (!pop.contains(ev.target)) closeFlagPicker(); };
  const onKey = ev => { if (ev.key === "Escape") closeFlagPicker(); };
  FLAG_POP_CLEANUP = () => {
    document.removeEventListener("click", outside);
    window.removeEventListener("keydown", onKey);
  };
  setTimeout(() => {
    document.addEventListener("click", outside);
    window.addEventListener("keydown", onKey);
  }, 0);
}

async function loadWatch() {
  if (!WL.master.length) await loadWlMeta(); else paintWlListsBar();
  try {
    const q = WL.current === "master" ? "" : ("?list=" + encodeURIComponent(WL.current));
    const d = await GET("/api/watchlist" + q);
    WL.flags = d.flags || WL.flags;
    /* ── price cross-check status (Yahoo → TradingView → PSX Portal) ── */
    const wlu = $("#wlUpdated");
    if (wlu && d.verify && !d.verify.error) {
      const v = d.verify;
      const srcs = (v.sources || []).join(" · ");
      wlu.title = `Expected last session: ${v.expected}\nSources checked: ${srcs}` +
        (v.patched && v.patched.length ? `\nFresh close added from TradingView for: ${v.patched.join(", ")}` : "");
      if (v.mismatches && v.mismatches.length)
        wlu.innerHTML = `· <b style="color:#f59e0b">⚠ TradingView shows different prices for ${v.mismatches.join(", ")}</b>`;
      else if (v.stale)
        wlu.innerHTML = `· <b style="color:#f59e0b">⚠ prices as of ${v.as_of || "?"} — ${v.expected} not published yet</b>`;
      else
        wlu.textContent = `· ✓ prices cross-checked as of ${v.as_of || "?"}${v.live ? " · LIVE session" : ""} · ${srcs}`;
    } else if (wlu && d.verify && d.verify.error) {
      wlu.textContent = "· ⚠ price cross-check unavailable";
    }
    /* order: best-performing BUY stocks first, then HOLD, then SELL */
    const sigRank = t => t.indexOf("BUY") >= 0 ? 0 : (t.indexOf("SELL") >= 0 ? 2 : 1);
    d.rows.sort((a, b) => {
      const ra = a.error ? 3 : sigRank(quickSignal(a.snapshot || {}));
      const rb = b.error ? 3 : sigRank(quickSignal(b.snapshot || {}));
      if (ra !== rb) return ra - rb;
      const ca = a.day_chg == null ? -1e9 : a.day_chg, cb = b.day_chg == null ? -1e9 : b.day_chg;
      return cb - ca;
    });
    $("#watchTbl tbody").innerHTML = d.rows.map(r => {
      if (r.error) return `<tr><td></td><td><b>${r.symbol}</b></td><td colspan="7" class="sub">${r.error}</td></tr>`;
      const s = r.snapshot || {};
      const chip = (above, lvl, val) => above == null
        ? `<span class="sub" title="${lvl}-day average not ready yet">·${lvl}</span>`
        : (above ? `<span class="pos sma-c" title="Price above the ${lvl}-day EMA (${val != null ? fmtRs(val) : ""})">▲${lvl}</span>`
                 : `<span class="neg sma-c" title="Price below the ${lvl}-day EMA (${val != null ? fmtRs(val) : ""})">▼${lvl}</span>`);
      const trendCell = [chip(s.above_ema5, 5, s.ema5), chip(s.above_ema10, 10, s.ema10),
                         chip(s.above_ema20, 20, s.ema20), chip(s.above_ema50, 50, s.ema50),
                         chip(s.above_ema100, 100, s.ema100), chip(s.above_ema200, 200, s.ema200)].join(" ");
      const color = WL.flags[r.symbol] || "";
      const dot = `<span class="fl-dot${color ? " fl-" + color : ""}" data-fl="${r.symbol}" title="Click to pick a flag color for ${r.symbol}"></span>`;
      const rem = WL.current !== "master"
        ? ` <button class="btn small ghost wlRm" data-rm="${r.symbol}" title="Remove from ${WL.current}">✕</button>` : "";
      /* 🔍 hover-only indicator readings: RSI + MACD + both divergences */
      const rsiZone = s.rsi14 == null ? "" : (s.rsi14 >= 70 ? " · overbought" : s.rsi14 <= 30 ? " · oversold" : " · neutral");
      const macdR = s.macd_bull == null ? "—" : (s.macd_bull ? "bullish ▲" : "bearish ▼");
      const divR = (s.rsi_div || s.macd_div)
        ? `RSI ${s.rsi_div ? `<b class="${s.rsi_div === "bullish" ? "pos" : "neg"}">${s.rsi_div}</b>` : "—"} · MACD ${s.macd_div ? `<b class="${s.macd_div === "bullish" ? "pos" : "neg"}">${s.macd_div}</b>` : "—"}`
        : "none on either";
      const indLine = `RSI ${s.rsi14 == null ? "—" : Number(s.rsi14).toFixed(1) + rsiZone} · MACD ${macdR} · Divergence: ${divR}`;
      /* signal colors: green = buy, golden = hold, reddish = sell */
      const sig = quickSignal(s);
      const sigBg = sig.indexOf("BUY") >= 0 ? "background:rgba(34,197,94,.16)"
                  : sig.indexOf("SELL") >= 0 ? "background:rgba(239,68,68,.15)"
                  : "background:rgba(234,179,8,.13)";
      /* 📝 per-stock note (sub-lists only) — hover to read, click to edit */
      const noteTxt = ((WL.notes[WL.current] || {})[r.symbol]) || "";
      const noteBtn = WL.current !== "master"
        ? ` <span class="wl-note${noteTxt ? " has" : ""}" data-note="${r.symbol}"
             data-tip="${noteTxt ? escA(noteTxt) : "Click to add a note for " + r.symbol}">📝</span>` : "";
      return `<tr class="clickable" data-s="${r.symbol}">
        <td>${dot}</td>
        <td class="symcell" title="${(r.name || "").replace(/"/g, "&quot;")}"><b>${r.symbol}</b><span class="wl-name">${r.name || ""}</span><span class="wl-ind">${indLine}</span>${rem}${noteBtn}</td>
        <td class="px-main">${fmtRs(s.close)}</td><td class="${cls(r.day_chg)}">${fmtPct(r.day_chg)}</td>
        <td>${s.rsi14 == null ? "—" : Number(s.rsi14).toFixed(0)}</td>
        <td style="font-size:12px;white-space:nowrap">${trendCell}</td>
        <td>${fmtN(r.pe)}</td><td>${r.yield == null ? "—" : Number(r.yield).toFixed(1) + "%"}</td>
        <td style="${sigBg}">${pill(sig)}</td></tr>`;
    }).join("") || `<tr><td colspan="9" class="sub">This list is empty — use "＋ add stock…" above (only stocks already in the Master list).</td></tr>`;
    $("#watchTbl tbody").querySelectorAll(".fl-dot").forEach(el => el.onclick = e => {
      e.stopPropagation();
      openFlagPicker(el, el.dataset.fl);
    });
    $("#watchTbl tbody").querySelectorAll(".wlRm").forEach(el => el.onclick = async e => {
      e.stopPropagation();
      await POST("/api/watchlists/list", { name: WL.current, symbols: curListSymbols().filter(s => s !== el.dataset.rm) });
      await loadWlMeta(); loadWatch();
    });
    /* 📝 note: click → type / edit / clear (empty = remove note) */
    loadSetups();
    $("#watchTbl tbody").querySelectorAll(".wl-note").forEach(el => el.onclick = async e => {
      e.stopPropagation();
      const sym = el.dataset.note;
      const cur = ((WL.notes[WL.current] || {})[sym]) || "";
      const t = prompt(`📝 Note for ${sym} on the "${WL.current}" list\n(leave empty to remove the note):`, cur);
      if (t === null) return;                       // Cancel pressed
      const r = await POST("/api/watchlists/note", { list: WL.current, symbol: sym, text: t.trim() });
      if (!r.ok) { toast("❌ " + (r.error || "Could not save the note")); return; }
      WL.notes = r.notes || {};
      loadWatch();
    });
  } catch (e) { toast("Watchlist failed: " + e.message); }
}
/* Screener preset explainers — hover the ? beside each preset */
const PRESET_INFO = {
  "fresh-breakout": { t: "Fresh Breakout",
    w: "Stocks that closed above their 20-day high with rising volume today — new buyers are stepping in.",
    u: "Hunt swing entries: strong breakouts often continue higher. Buy near the breakout bar and keep the stop just below it.",
    s: "🟢 Buying opportunity — momentum is turning up. Works best when the overall market is also rising." },
  "volume-shockers": { t: "Volume Shockers",
    w: "Today's volume is several times the 30-day average — unusual activity: news, results, block trades or big players moving.",
    u: "Spot where attention is flowing. Check the News + Filings tabs for the cause BEFORE trading — volume precedes big moves in both directions.",
    s: "⚠️ Neutral-to-bullish: a spike near support = accumulation (buy), a spike on a red candle = distribution (wait)." },
  "momentum-surge": { t: "Momentum Surge",
    w: "Strong uptrend (price above moving averages) + healthy RSI (not overheated) + rising volume — a trend in good shape.",
    u: "Trend-following: buy small pullbacks toward the 10/20-day average and ride until momentum breaks.",
    s: "🟢 Buying opportunity — one of the most reliable swing setups on PSX." },
  "oversold-bounce": { t: "Oversold Bounce",
    w: "RSI washed out below ~30 after a hard sell-off — the stock is stretched down and can snap back quickly.",
    u: "Contrarian bounce trades: small size, tight stop, quick target (a few days). Check the News tab for WHY it fell.",
    s: "⚠️ Risky buy: bounces are fast but fail in strong downtrends — wait for the first green reversal candle." },
  "golden-cross": { t: "Golden Cross",
    w: "The 50-day moving average just crossed ABOVE the 200-day average — the classic long-term trend reversal.",
    u: "Position/investing entries meant to be held for weeks or months; also great for spotting sector rotation.",
    s: "🟢 Bullish long-term signal — historically marks the start of multi-month uptrends." },
  "near-52w-high": { t: "Near 52-Week High",
    w: "Stocks within 5% of the highest price of the last year — market leaders that everyone is buying.",
    u: "Strength trading: leaders near highs often make new highs. Buy the pullback or a tight consolidation, not the spike.",
    s: "🟢 Bullish — but avoid chasing; wait for a dip to enter with a sensible stop." },
  "value-picks": { t: "Value Picks",
    w: "Cheap on earnings (low P/E) AND liquid enough to actually get in and out of.",
    u: "Find undervalued names before the market re-prices them. Best for patient holders willing to wait a quarter or two.",
    s: "🟢 Buying opportunity for investors — value can stay cheap for a while, so build positions in parts." },
  "dividend-kings": { t: "Dividend Kings",
    w: "High dividend yield + profitable + liquid — you get paid while you wait.",
    u: "Income portfolios and defensive positions; especially useful when the market is choppy.",
    s: "🟢 Buy-and-hold income play — check the payout is sustainable before results season." },
  "blue-chip-quality": { t: "Blue-Chip Quality",
    w: "KSE-100 members in an uptrend that also pay dividends — the safest corner of PSX.",
    u: "Core holdings and ideal first positions for newer traders.",
    s: "🟢 Low-risk buy candidates — slower movers, but steady." },
  "hidden-accumulation": { t: "Hidden Accumulation",
    w: "Volume quietly rising while price stays calm — larger players likely buying before a move.",
    u: "Early positioning: buy in the calm zone, sell into the spike when others notice.",
    s: "🟢 Stealth buy signal — confirm with a breakout before increasing size." },
  "falling-knives": { t: "Falling Knives",
    w: "Stocks that broke below their 20-day lows — active sellers are in control right now.",
    u: "Mostly a list of what NOT to hold. Advanced traders 'stalk' these for capitulation bottoms — never catch blindly.",
    s: "🔴 Avoid — wait for a higher-low confirmation before any bounce trade." },
  "illiquid-avoid": { t: "Low Liquidity (Avoid)",
    w: "Very thin trading volume — wide spreads and hard to enter or exit at your price.",
    u: "An exclusion list: flags names where stop-losses may not actually work.",
    s: "🔴 Avoid for swing trading — prices can gap against you with no buyers." },
};
function showTip(html, x, y) {
  let tb = $("#tipBox");
  if (!tb) { tb = document.createElement("div"); tb.id = "tipBox"; document.body.appendChild(tb); }
  tb.innerHTML = html; tb.style.display = "block";
  const r = tb.getBoundingClientRect();
  let L = Math.min(x + 14, window.innerWidth - r.width - 10);
  let T = y + 18;
  if (T + r.height > window.innerHeight - 8) T = y - r.height - 12;
  tb.style.left = Math.max(8, L) + "px"; tb.style.top = Math.max(8, T) + "px";
}
function hideTip() { const tb = $("#tipBox"); if (tb) tb.style.display = "none"; }
function presetTipHTML(id) {
  const i = PRESET_INFO[id]; if (!i) return "";
  return `<b class="ttl">${i.t}</b>
    <span class="tip-k">What it is:</span> ${i.w}<br>
    <span class="tip-k">Use it for:</span> ${i.u}<br>
    <span class="tip-k">Signal:</span> ${i.s}`;
}
document.addEventListener("mouseover", e => {
  const q = e.target.closest(".preset-q"); if (!q) return;
  showTip(presetTipHTML(q.dataset.tip), q.getBoundingClientRect().left, q.getBoundingClientRect().bottom);
});
document.addEventListener("mouseout", e => { if (e.target.closest && e.target.closest(".preset-q")) hideTip(); });
document.addEventListener("click", e => {           // touch devices: tap toggles
  const q = e.target.closest(".preset-q"); if (!q) return;
  e.stopPropagation();
  const tb = $("#tipBox");
  if (tb && tb.style.display === "block" && tb.dataset.for === q.dataset.tip) { hideTip(); return; }
  if (tb) tb.dataset.for = q.dataset.tip;
  const r = q.getBoundingClientRect();
  showTip(presetTipHTML(q.dataset.tip), r.left, r.bottom);
});

async function loadPresets() {
  try {
    const d = await GET("/api/screener/presets");
    S.presets = d.presets;
    const html = d.presets.map(p =>
      `<div class="preset" data-p="${p.id}"><b>${p.label}<span class="preset-q" data-tip="${p.id}" role="button" tabindex="0" aria-label="What is ${p.label}?">?</span></b><p>${p.desc}</p></div>`).join("");
    const g1 = $("#presetGrid"); if (g1) g1.innerHTML = html;
    const g2 = $("#presetGrid2"); if (g2) g2.innerHTML = html;
  } catch (e) { /* ignore */ }
}
document.addEventListener("click", e => {
  const p = e.target.closest(".preset");
  if (!p || e.target.closest(".preset-q")) return;
  const pr = S.presets.find(x => x.id === p.dataset.p);
  if (pr) { applyFilters(pr.filters); showView("screener"); runScreen(); }
});

/* ── STOCK ── */
let stockReq = 0;
function openStock(sym) {
  S.sym = sym.toUpperCase();
  memSave({ sym: S.sym });
  $("#poSym").value = S.sym; $("#btSym").value = S.sym;
  showView("stock");
  loadStock();
}
/* fetch ANY PSX symbol, even outside the ALLSHR universe */
function anyFetch() {
  const v = ($("#anySym").value || "").trim().toUpperCase();
  if (!v) return;
  $("#anySuggest").style.display = "none";
  openStock(v);
}
on("anyGo", "click", anyFetch);
$("#anySym").addEventListener("keydown", e => { if (e.key === "Enter") anyFetch(); });
$("#anySym").addEventListener("input", () => {
  const q = $("#anySym").value.trim().toUpperCase(), sug = $("#anySuggest");
  if (q.length < 1) { sug.style.display = "none"; return; }
  const hits = (S.universe || []).filter(u => u.symbol.includes(q)).slice(0, 8);
  sug.innerHTML = hits.map(h => `<div data-s="${h.symbol}"><b>${h.symbol}</b> · ${fmtRs(h.price)}</div>`).join("")
    + `<div data-s="${q}">↳ Fetch <b>${q}</b> anyway (any listed PSX symbol)</div>`;
  sug.style.display = "block";
});
$("#anySuggest").addEventListener("click", e => { const d = e.target.closest("[data-s]"); if (d) { $("#anySym").value = d.dataset.s; anyFetch(); } });
document.addEventListener("click", e => { if (!e.target.closest("#anySym") && !e.target.closest("#anySuggest")) $("#anySuggest").style.display = "none"; });
on("rangeTabs", "click", e => {
  const b = e.target.closest("button"); if (!b) return;
  document.querySelectorAll("#rangeTabs button").forEach(x => x.classList.toggle("active", x === b));
  S.rangeM = +b.dataset.m; memSave({ rangeM: S.rangeM });
  paintChart();
});
on("stTabs", "click", e => {
  const b = e.target.closest("button"); if (!b) return;
  document.querySelectorAll("#stTabs button").forEach(x => x.classList.toggle("active", x === b));
  S.sTab = b.dataset.k; memSave({ sTab: S.sTab });
  renderStockTab();
});
/* 🌐 PSX Data Portal link: opens the official portal page in a new tab,
   and at the same moment kicks an automatic re-fetch so the local data
   catches up with whatever the portal shows. */
on("stPortal", "click", () => {
  const sym = S.sym;
  toast("🌐 Opening PSX Data Portal — fetching the latest " + sym + " data right now…");
  POST("/api/stock/" + encodeURIComponent(sym) + "/resync")
    .then(r => {
      if (r && r.ok) toast("✅ " + sym + " updated with the latest portal data");
      else toast("⚠️ " + sym + " re-sync issue: " + ((r && r.error) || "source unreachable — showing cached data"));
      loadStock();
      if (document.querySelector("#v-watchlist.active")) loadWatch();
      if (document.querySelector("#v-home.active")) loadLanding();
    })
    .catch(() => loadStock());
});
async function loadStock() {
  const my = ++stockReq;
  const sym = S.sym;
  $("#stName").textContent = sym + " …";
  $("#stVerdict").outerHTML = '<span class="pill p-hold" id="stVerdict">—</span>';
  $("#stBody").innerHTML = `<p class="sub">Loading…</p>`;
  try {
    const [info, hist] = await Promise.all([
      GET("/api/stock/" + sym), GET("/api/stock/" + sym + "/history")
    ]);
    if (my !== stockReq) return;  // user clicked another stock meanwhile
    S.info = info; S.bars = hist.bars;
    const s = info.snapshot || {};
    const meta = (S.watchMeta.find(w => w.symbol === sym) || {});
    $("#stName").textContent = `${sym} · ${info.name || meta.name || ""}`;
    $("#stPrice").textContent = fmtRs(s.close);
    const chg = (info.fundamentals || {}).change_pct;
    $("#stChg").innerHTML = `<b class="${cls(chg)}">${fmtPct(chg)}</b> <span class="sub">as of ${s.date || ""}</span>`;
    $("#stMeta").textContent = `${info.sector || ""}`;
    const pl = $("#stPortal");
    if (pl) { pl.href = "https://dps.psx.com.pk/company/" + sym;
              pl.title = "Open dps.psx.com.pk/company/" + sym + " (official PSX Data Portal). Clicking also re-syncs this stock's data automatically."; }
    const pd = $("#stPdf");
    if (pd) { pd.href = "/api/stock/" + encodeURIComponent(sym) + "/report.pdf";
              pd.title = "Download the full A-to-Z executive report for " + sym + " as a PDF."; }
    paintChart();
    $("#stStats").innerHTML = [
      ["RSI 14", s.rsi14 == null ? "—" : Number(s.rsi14).toFixed(1)],
      ["MACD", s.macd_bull == null ? "—" : (s.macd_bull ? "Bullish" : "Bearish")],
      ["vs 50DMA", s.above_sma50 == null ? "—" : (s.above_sma50 ? "Above ▲" : "Below ▼")],
      ["vs 200DMA", s.above_sma200 == null ? "—" : (s.above_sma200 ? "Above ▲" : "Below ▼")],
      ["ATR", fmtRs(s.atr14)], ["Vol ×", s.vol_ratio == null ? "—" : Number(s.vol_ratio).toFixed(1) + "×"],
      ["52W High", fmtRs(s.high_52w)], ["52W Low", fmtRs(s.low_52w)],
      ["Support", fmtRs(s.support_1)], ["Resistance", fmtRs(s.resistance_1)],
    ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
    const iv = info.intrinsic || {};
    const ivRow = (m, v2) => `<div class="iv-r"><span class="iv-m">${m}</span><b>${v2 == null ? "—" : fmtRs(v2)}</b><span class="sub iv-n">${(iv.notes || {})[m] || ""}</span></div>`;
    $("#stStats").innerHTML += iv.value != null ? `
      <div class="stat iv-wide" title="Four-method intrinsic value: DCF (15% discount, 6%→4%), Gordon DDM (14%/8%), Asset NAV, P/E multiple — averaged, then 20% margin of safety applied to the buy target.">
        <div class="k">🧮 Intrinsic Value — 4-Method Blend <span class="sub">(avg of ${Object.keys(iv.methods).length} models)</span></div>
        <div class="v ${iv.upside_pct >= 0 ? "pos" : "neg"}">${fmtRs(iv.value)}</div>
        <div class="sub">${iv.upside_pct >= 0 ? "▲ " + iv.upside_pct.toFixed(1) + "% upside" : "▼ " + Math.abs(iv.upside_pct).toFixed(1) + "% downside"} vs market ${fmtRs(iv.price)} &nbsp;·&nbsp; <b style="color:#f5d76e">Buy target ${fmtRs(iv.buy_target)}</b> (after ${iv.mos_pct}% margin of safety) &nbsp;·&nbsp; ${iv.verdict || ""}</div>
        <div class="iv-grid">${["DCF Model", "DDM Model", "Asset NAV", "P/E Multiple"].map(m => ivRow(m, iv.methods[m])).join("")}</div>
        <div class="sub iv-m">Inputs: EPS ${iv.inputs.eps != null ? "Rs " + iv.inputs.eps : "—"} · DPS ${iv.inputs.dps != null ? "Rs " + iv.inputs.dps : "—"} · BV/share ${iv.inputs.bvps != null ? "Rs " + iv.inputs.bvps : "—"} · target P/E ${iv.inputs.target_pe}×</div>
      </div>` : `
      <div class="stat iv-wide"><div class="k">🧮 Intrinsic Value — 4-Method Blend</div>
        <div class="v sub">—</div><div class="sub">not enough published fundamentals for this stock</div></div>`;
    renderStockTab();
  } catch (e) {
    if (my !== stockReq) return;
    $("#stBody").innerHTML = `<p class="neg">Failed to load ${sym}: ${e.message}</p>`;
  }
}
function paintChart() {
  const n = S.rangeM <= 3 ? 66 : S.rangeM <= 6 ? 132 : S.rangeM <= 12 ? 264 : S.bars.length;
  drawCandles($("#mainChart"), S.bars.slice(-n));
  /* OHLC strip just under the chart — close is always the most highlighted */
  const oh = $("#stOhlc"); if (!oh) return;
  const lb = (S.bars && S.bars.length) ? S.bars[S.bars.length - 1] : null;
  if (!lb) { oh.innerHTML = ""; return; }
  const up = lb.close >= lb.open;
  oh.innerHTML =
    `<span class="sub">as of ${lb.date}</span>` +
    `<span>Open <b>${fmtRs(lb.open)}</b></span>` +
    `<span>High <b class="pos">${fmtRs(lb.high)}</b></span>` +
    `<span>Low <b class="neg">${fmtRs(lb.low)}</b></span>` +
    `<span>Close <b style="color:#f5d76e;font-size:16px">${fmtRs(lb.close)}</b> ` +
    `<b class="${up ? "pos" : "neg"}">${up ? "▲" : "▼"}</b></span>`;
}
async function renderStockTab() {
  const sym = S.sym, k = S.sTab, B = $("#stBody");
  B.innerHTML = `<p class="sub">Loading ${k}…</p>`;
  try {
    if (k === "research") {
      if (!S.R[sym]) S.R[sym] = await GET("/api/stock/" + sym + "/research");
      if (sym !== S.sym) return;
      const r = S.R[sym];
      if (r.error) { B.innerHTML = `<p class="neg">${r.error}</p>`; return; }
      $("#stVerdict").outerHTML = pill(r.discussion.verdict).replace('class="pill', 'id="stVerdict" class="pill');
      B.innerHTML = `
        <h3>${r.discussion.verdict} <span class="sub">· confidence ${r.discussion.confidence}% · net ${r.discussion.net_score}</span></h3>
        <p class="sub">Generated ${fmtTs(r.generated_at)} PKT · press ⟳ Refresh for the latest</p>
        <p>${r.discussion.summary}</p>
        <div class="grid g2">
          <div><h3>🐂 Bullish case (${r.bullish.score})</h3>
            ${r.bullish.factors.map(f => `<div class="ev bull"><b>${f.factor}</b> (+${f.points})<br>${f.detail}</div>`).join("") || "<p class='sub'>No bullish factors.</p>"}</div>
          <div><h3>🐻 Bearish case (${r.bearish.score})</h3>
            ${r.bearish.factors.map(f => `<div class="ev bear"><b>${f.factor}</b> (+${f.points})<br>${f.detail}</div>`).join("") || "<p class='sub'>No bearish factors.</p>"}</div>
        </div>
        <h3 style="margin-top:14px">⚖ Risk / Reward</h3>
        <dl class="kv"><dt>Reference</dt><dd>${fmtRs(r.risk_reward.entry_ref)}</dd>
        <dt>Stop</dt><dd>${fmtRs(r.risk_reward.stop)}</dd>
        <dt>Target 1 / 2</dt><dd>${fmtRs(r.risk_reward.target_1)} / ${fmtRs(r.risk_reward.target_2)}</dd>
        <dt>Assessment</dt><dd>${r.risk_reward.assessment}</dd></dl>`;
    } else if (k === "proposal") {
      if (!S.P[sym]) S.P[sym] = await GET("/api/stock/" + sym + "/proposal");
      if (sym !== S.sym) return;
      const p = S.P[sym];
      if (p.error) { B.innerHTML = `<p class="neg">${p.error}</p>`; return; }
      const pr = p.proposal;
      B.innerHTML = `
        <h3>Trader: ${p.trader.action} ${pill(p.trader.action)} <span class="sub">score ${p.trader.score} · valid till ${pr.valid_until}</span></h3>
        <p class="sub">Generated ${fmtTs(p.generated_at)} PKT · press ⟳ Refresh for the latest</p>
        <dl class="kv"><dt>Entry range</dt><dd>${fmtRs(pr.entry_range[0])} – ${fmtRs(pr.entry_range[1])}</dd>
        <dt>Stop loss</dt><dd>${fmtRs(pr.stop_loss)}</dd>
        <dt>Targets</dt><dd>${fmtRs(pr.target_1)} / ${fmtRs(pr.target_2)} (R:R ${pr.reward_risk_t1} / ${pr.reward_risk_t2})</dd>
        <dt>Suggested qty</dt><dd>${fmtN(pr.suggested_qty)} shares ≈ ${fmtRs(pr.est_cost_rs)} (risk ${fmtRs(pr.risk_rs)})</dd>
        <dt>Plan sized for</dt><dd>${fmtRs(pr.capital_assumed)} at ${pr.risk_pct}% risk (change in ⚙ Settings → Trading)</dd></dl>
        <div class="grid g2" style="margin-top:12px">
          <div><h3>✅ Buy evidence</h3>${p.buy_evidence.map(e => `<div class="ev bull">${e}</div>`).join("")}</div>
          <div><h3>🛑 Sell evidence</h3>${p.sell_evidence.map(e => `<div class="ev bear">${e}</div>`).join("")}</div>
        </div>
        <h3 style="margin-top:14px">🧠 Deep Thinking <span class="sub">(${p.deep_thinking.engine})</span></h3>
        <div class="think">${p.deep_thinking.steps.join("\n\n")}</div>
        ${p.deep_thinking.llm_narrative ? `<h3 style="margin-top:10px">Local-AI note</h3><div class="think">${p.deep_thinking.llm_narrative}</div>` : ""}
        <p class="sub" style="margin-top:10px">${p.disclaimer}</p>`;
    } else if (k === "fund") {
      const f = (S.info || {}).fundamentals || {};
      const hs = f.history_stats || {}, yf = f.yfinance || {};
      B.innerHTML = `
        <div class="grid g2"><div><h3>Market</h3><dl class="kv">
          <dt>Price</dt><dd>${fmtRs(f.price)}</dd><dt>Day change</dt><dd class="${cls(f.change_pct)}">${fmtPct(f.change_pct)}</dd>
          <dt>1Y change</dt><dd class="${cls(f.change_1y_pct)}">${fmtPct(f.change_1y_pct)}</dd>
          <dt>P/E</dt><dd>${fmtN(f.pe_ratio)}</dd><dt>Div yield</dt><dd>${f.dividend_yield == null ? "—" : Number(f.dividend_yield).toFixed(2) + "%"}</dd>
          <dt>Mkt cap</dt><dd>Rs ${fmtMcap(f.market_cap)} bn</dd><dt>Sector</dt><dd>${f.sector_name || ""}</dd></dl></div>
        <div><h3>Performance (EOD)</h3><dl class="kv">
          <dt>1M / 3M</dt><dd>${fmtPct(hs.perf_1m)} / ${fmtPct(hs.perf_3m)}</dd>
          <dt>6M / 1Y</dt><dd>${fmtPct(hs.perf_6m)} / ${fmtPct(hs.perf_1y)}</dd>
          <dt>52W range</dt><dd>${fmtRs(hs.low_52w)} – ${fmtRs(hs.high_52w)}</dd>
          <dt>Off high</dt><dd>${fmtPct(hs.off_high_pct)}</dd></dl></div></div>
        ${Object.keys(yf).length ? `<h3 style="margin-top:12px">Ratios (Yahoo)</h3><dl class="kv">` +
          [["Trailing P/E", yf.trailingPE], ["Forward P/E", yf.forwardPE], ["P/B", yf.priceToBook],
           ["ROE", yf.returnOnEquity], ["Profit margin", yf.profitMargins], ["EPS (ttm)", yf.trailingEps],
           ["Payout", yf.payoutRatio], ["Debt/Equity", yf.debtToEquity]].map(([k2, v]) =>
            `<dt>${k2}</dt><dd>${v == null ? "—" : fmtN(v)}</dd>`).join("") + `</dl>` : ""}
        <div class="grid g2" style="margin-top:14px">
          <div><h3>Performance by period (%)</h3><canvas class="chart" id="fundPerf" height="170"></canvas></div>
          <div><h3>Key ratios</h3><canvas class="chart" id="fundRatios" height="170"></canvas></div>
        </div>
        <h3 style="margin-top:10px">52-week price range</h3><canvas class="chart" id="fundRange" height="70"></canvas>
        <p class="sub" style="margin-top:10px">Sources: ${(f.sources || []).join(" · ")}</p>`;
      const fp = [["1M", hs.perf_1m], ["3M", hs.perf_3m], ["6M", hs.perf_6m], ["1Y", hs.perf_1y]]
        .filter(([, v]) => v != null).map(([label, value]) => ({ label, value }));
      if (fp.length) drawBars($("#fundPerf"), fp);
      const rpct = v => { const x = Number(v); return Math.abs(x) <= 3 ? x * 100 : x; };
      const fr = [["P/E", f.pe_ratio || yf.trailingPE], ["Yield %", f.dividend_yield],
                  ["ROE %", yf.returnOnEquity != null ? rpct(yf.returnOnEquity) : null],
                  ["Margin %", yf.profitMargins != null ? rpct(yf.profitMargins) : null],
                  ["D/E", yf.debtToEquity]].filter(([, v]) => v != null)
        .map(([label, value]) => ({ label, value: Number(Number(value).toFixed(2)) }));
      if (fr.length) drawBars($("#fundRatios"), fr);
      if (hs.low_52w != null) drawGauge($("#fundRange"), { low: hs.low_52w, high: hs.high_52w, now: f.price || hs.last_close });
    } else if (k === "filings") {
      if (!S.F[sym]) S.F[sym] = await GET("/api/stock/" + sym + "/filings");
      if (sym !== S.sym) return;
      const f = S.F[sym];
      if (f.error && !f.items.length) { B.innerHTML = `<p class="neg">${f.error}</p>`; return; }
      B.innerHTML = `
        <h3>📄 Official filings <span class="sub">· financials.psx.com.pk (PSX reports portal)</span></h3>
        <p class="sub">Annual &amp; quarterly financial reports filed with the exchange — PDFs open directly from PSX.</p>` +
        (f.items.map(r => `
          <div class="news-item">
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
              <span style="font-size:11px;font-weight:700;border:1px solid var(--line);border-radius:99px;padding:2px 9px">${r.type}</span>
              <b>${r.period_ended ? "Period ended " + r.period_ended : ""}</b>
              <span class="sub">posted ${r.posted || "?"}</span>
              ${r.pdf_url ? `<a href="${r.pdf_url}" target="_blank" rel="noopener" style="font-size:12px">📄 Open PDF</a>` : ""}
            </div>
          </div>`).join("")
        || `<p class="sub">No official filings found for ${sym}.</p>`);
    } else if (k === "deep") {
      if (!S.D[sym]) {
        B.innerHTML = `<p class="sub">🧠 running the analysis agents for ${sym}…</p>`;
        S.D[sym] = await GET("/api/stock/" + sym + "/deep");
      }
      if (sym !== S.sym) return;
      const d = S.D[sym], pr = d.profile || {}, st = d.statements || {},
            ra = d.ratios || {}, va = d.valuation || {}, pe = d.peers || {}, it = d.intel || {};
      const fb = v => v == null ? "—" : (Math.abs(v) >= 1e12 ? "Rs " + (v/1e12).toFixed(2) + " T"
        : Math.abs(v) >= 1e9 ? "Rs " + (v/1e9).toFixed(1) + " B"
        : Math.abs(v) >= 1e6 ? "Rs " + (v/1e6).toFixed(1) + " M" : "Rs " + Number(v).toLocaleString("en-PK", {maximumFractionDigits:1}));
      const pc = v => v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(1) + "%";
      const row = (label, vals) => `<tr><td><b>${label}</b></td>${vals.map(v => `<td>${v == null ? "—" : fb(v)}</td>`).join("")}</tr>`;
      B.innerHTML = `
        <h3>🧠 Deep Analysis — ${pr.company || sym} <span class="sub">· ${pr.sector || ""} · generated ${d.generated_at}</span></h3>
        <div class="grid g2">
          <div>
            <h3>🏢 Business model</h3><p>${pr.business || "—"}</p>
            <p class="sub"><b>Customers:</b> ${pr.customers || "—"}</p>
            <h3>🏰 Economic moat</h3><p>${pr.moat || "—"}</p>
          </div>
          <div>
            <h3>💼 Balance sheet (assets)</h3>
            <div class="stat-grid">
              <div class="stat"><div class="k">Total assets</div><div class="v">${fb((pr.assets||{}).total_assets)}</div></div>
              <div class="stat"><div class="k">Equity</div><div class="v">${fb((pr.assets||{}).total_equity)}</div></div>
              <div class="stat"><div class="k">Liabilities</div><div class="v">${fb((pr.assets||{}).total_liabilities)}</div></div>
              <div class="stat"><div class="k">Market cap</div><div class="v">${fb((pr.assets||{}).market_cap)}</div></div>
            </div>
          </div>
        </div>
        <h3>📈 Industry trend: <span class="${(it.sector_perf||{}).y1 >= 0 ? "pos" : "neg"}">${it.industry_trend || "—"}</span>
          <span class="sub">${it.sector_perf ? `· sector 1Y ${pc(it.sector_perf.y1)} · 3M ${pc(it.sector_perf.m3)}` : ""}</span></h3>
        <h3>👔 Management quality</h3>
        <ul>${(it.management || []).map(m => `<li>${m}</li>`).join("")}</ul>
        <h3>📒 Financial statements (PKR, latest → older)</h3>
        <div class="tbl-scroll"><table class="tbl"><thead><tr><th>Metric</th>${(st.years||[]).map(y=>`<th>${y}</th>`).join("")}</tr></thead><tbody>
          ${row("Revenue", st.revenue||[])}${row("Net income", st.net_income||[])}
          ${row("Free cash flow", st.fcf||[])}${row("Total assets", st.assets||[])}
          ${row("Liabilities", st.liabilities||[])}${row("Equity", st.equity||[])}
        </tbody></table></div>
        <div class="stat-grid">
          <div class="stat"><div class="k">Revenue 3Y CAGR</div><div class="v ${st.revenue_cagr_3y>=0?"pos":"neg"}">${pc(st.revenue_cagr_3y)}</div></div>
          <div class="stat"><div class="k">Profit 3Y CAGR</div><div class="v ${st.ni_cagr_3y>=0?"pos":"neg"}">${pc(st.ni_cagr_3y)}</div></div>
          <div class="stat"><div class="k">Net margin</div><div class="v">${pc(st.net_margin_pct)}</div></div>
          <div class="stat"><div class="k">Debt/Equity</div><div class="v">${st.de_ratio ?? "—"}</div></div>
        </div>
        <h3>🔢 Key ratios</h3>
        <div class="stat-grid">
          <div class="stat"><div class="k">P/E</div><div class="v">${ra.pe ? Number(ra.pe).toFixed(1) : "—"}</div></div>
          <div class="stat"><div class="k">P/B</div><div class="v">${ra.pb ?? "—"}</div></div>
          <div class="stat"><div class="k">ROE</div><div class="v">${pc(ra.roe)}</div></div>
          <div class="stat"><div class="k">ROA</div><div class="v">${pc(ra.roa)}</div></div>
          <div class="stat"><div class="k">Div yield</div><div class="v">${pc(ra.dividend_yield_pct)}</div></div>
          <div class="stat"><div class="k">Payout</div><div class="v">${pc(ra.payout_ratio_pct)}${ra.dividend_sustainable ? " ✅" : " ⚠️"}</div></div>
          <div class="stat"><div class="k">FCF yield</div><div class="v">${pc(ra.fcf_yield_pct)}</div></div>
          <div class="stat"><div class="k">D/E</div><div class="v">${ra.debt_equity ?? "—"}</div></div>
        </div>
        <h3>️ Valuation</h3>
        <div class="stat-grid">
          ${Object.entries(va.models || {}).map(([m, v]) => `<div class="stat"><div class="k">${m}</div><div class="v">Rs ${Number(v).toLocaleString("en-PK",{maximumFractionDigits:0})}</div></div>`).join("")}
          <div class="stat"><div class="k">Fair value (blend)</div><div class="v">${va.fair_value ? "Rs " + Number(va.fair_value).toLocaleString("en-PK",{maximumFractionDigits:0}) : "—"}</div></div>
          <div class="stat"><div class="k">Margin of safety</div><div class="v ${va.margin_of_safety_pct>=0?"pos":"neg"}">${pc(va.margin_of_safety_pct)}</div></div>
        </div>
        <p><b class="${va.verdict === "UNDERVERVALUED" ? "pos" : va.verdict === "OVERVALUED" ? "neg" : "sub"}">${va.verdict || ""}</b>
          <span class="sub">vs price ${va.price ? "Rs " + Number(va.price).toLocaleString("en-PK") : "—"} · discount rate ${va.discount_pct}% · terminal ${va.terminal_pct}%</span></p>
        <ul class="sub">${(va.notes || []).map(n => `<li>${n}</li>`).join("")}</ul>
        ${pe.peers && pe.peers.length ? `<h3> Peers — ${pe.sector} <span class="sub">median P/E ${pe.sector_pe_median ? Number(pe.sector_pe_median).toFixed(1) : "—"} · median yield ${pe.sector_dy_median ? Number(pe.sector_dy_median).toFixed(1) + "%" : "—"}${pe.target_rank ? " · " + sym + " ranks " + pe.target_rank + " on P/E" : ""}</span></h3>
        <div class="tbl-scroll"><table class="tbl"><thead><tr><th>Symbol</th><th>Mcap</th><th>P/E</th><th>Yield</th></tr></thead><tbody>
          ${pe.peers.slice(0,10).map(p => `<tr><td><b>${p.s}</b></td><td>${fb(p.mcap)}</td><td>${p.pe ? Number(p.pe).toFixed(1) : "—"}</td><td>${p.dy ? Number(p.dy).toFixed(1) + "%" : "—"}</td></tr>`).join("")}
        </tbody></table></div>` : ""}
        <div class="grid g2">
          <div><h3>👍 PROs</h3><ul>${(it.pros || []).map(x => `<li class="pos" style="color:inherit">${x}</li>`).join("") || "<li>—</li>"}</ul></div>
          <div><h3>👎 CONs</h3><ul>${(it.cons || []).map(x => `<li>${x}</li>`).join("") || "<li>—</li>"}</ul></div>
        </div>`;
    } else {
      if (!S.N[sym]) S.N[sym] = await GET("/api/stock/" + sym + "/news");
      if (sym !== S.sym) return;
      const n = S.N[sym];
      B.innerHTML = `<h3>Sentiment: ${n.sentiment.label} <span class="sub">(score ${n.sentiment.score}, ${n.sentiment.count} items)</span></h3>` +
        (n.items.map(i => `<div class="news-item"><a href="${i.link}" target="_blank" rel="noopener">${i.title || "(no title)"}</a>
          ${i.pdf ? ` · <a href="${i.pdf}" target="_blank" rel="noopener" style="font-size:12px">📄 Original PSX PDF</a>` : ""}
          <div class="meta">${i.source || ""} · ${i.published || ""} · sentiment ${i.sentiment}</div></div>`).join("")
        || `<p class="sub">No recent mentions found.</p>`);
    }
  } catch (e) {
    if (sym !== S.sym) return;
    B.innerHTML = `<p class="neg">Failed: ${e.message}</p>`;
  }
}

/* ── SCREENER ── */
const FDEFS = [
  ["min_price", "Min price"], ["max_price", "Max price"],
  ["min_mcap", "Min mcap (Rs)"], ["max_mcap", "Max mcap (Rs)"],
  ["min_pe", "Min P/E"], ["max_pe", "Max P/E"], ["min_yield", "Min yield %"],
  ["min_avgvol", "Min avg vol"], ["min_day_chg", "Min day %"], ["max_day_chg", "Max day %"],
  ["min_1y_chg", "Min 1Y %"], ["max_1y_chg", "Max 1Y %"],
  ["rsi_min", "RSI min"], ["rsi_max", "RSI max"],
  ["min_vol_ratio", "Min vol ×"], ["near_52w_high_pct", "Near 52W hi %"],
  ["near_52w_low_pct", "Near 52W low %"], ["limit", "Limit"],
];
const FSEL = [
  ["above_sma50", "Above 50DMA"], ["above_sma200", "Above 200DMA"], ["macd_bull", "MACD bullish"],
  ["sort", "Sort by"], ["sortdir", "Sort direction"],
];
const FCHK = [["kse100_only", "KSE-100 only"], ["exclude_zero_pe", "Exclude P/E ≤ 0"],
  ["golden_cross", "Golden cross"], ["breakout_20d", "20D breakout"], ["breakdown_20d", "20D breakdown"]];
(function buildForm() {
  const el = $("#screenForm");
  el.innerHTML = FDEFS.map(([k, l]) =>
    `<div><label>${l}</label><input data-f="${k}" type="number" step="any" ${k === "limit" ? 'value="50"' : ""}></div>`).join("")
    + FSEL.map(([k, l]) => {
      if (k === "sort") return `<div><label>${l}</label><select data-f="sort">${["market_cap", "price", "change_pct", "change_1y_pct", "pe_ratio", "dividend_yield", "volume_avg_30d", "vol_ratio", "rsi14"].map(o => `<option>${o}</option>`).join("")}</select></div>`;
      if (k === "sortdir") return `<div><label>${l}</label><select data-f="sortdir"><option value="desc">High → low</option><option value="asc">Low → high</option></select></div>`;
      return `<div><label>${l}</label><select data-f="${k}"><option value="">Any</option><option value="true">Yes</option><option value="false">No</option></select></div>`;
    }).join("")
    + FCHK.map(([k, l]) => `<div><label>${l}</label><select data-f="${k}"><option value="">No</option><option value="true">Yes</option></select></div>`).join("");
})();
function readFilters() {
  const f = {};
  document.querySelectorAll("#screenForm [data-f]").forEach(i => {
    const k = i.dataset.f, v = i.value;
    if (v === "" || v == null) return;
    if (["above_sma50", "above_sma200", "macd_bull"].includes(k)) f[k] = v === "true";
    else if (FCHK.map(x => x[0]).includes(k)) { if (v === "true") f[k] = true; }
    else if (k === "sort") f.sort = v;
    else if (k === "sortdir") f.ascending = (v === "asc");
    else f[k] = +v;
  });
  return f;
}
function applyFilters(f) {
  document.querySelectorAll("#screenForm [data-f]").forEach(i => {
    const k = i.dataset.f;
    if (k === "sortdir") { i.value = f.ascending ? "asc" : "desc"; return; }
    const v = f[k];
    i.value = v == null ? (k === "sort" ? "market_cap" : "") : String(v);
    if (k === "limit" && v == null) i.value = "50";
  });
}
on("clrScreen", "click", () => applyFilters({}));
on("runScreen", "click", runScreen);
async function runScreen() {
  const btn = $("#runScreen");
  btn.disabled = true; btn.textContent = "Screening… (may take a bit on first run)";
  try {
    const d = await POST("/api/screener/run", { filters: readFilters() });
    $("#screenCount").textContent = `Results — ${d.count} match${d.count === 1 ? "" : "es"} (${d.tech_enriched} with technicals)`;
    $("#screenTbl tbody").innerHTML = d.rows.map(r =>
      `<tr class="clickable" data-s="${r.symbol}"><td><b>${r.symbol}</b></td><td>${fmtRs(r.price)}</td>
       <td class="${cls(r.change_pct)}">${fmtPct(r.change_pct)}</td>
       <td class="${cls(r.change_1y_pct)}">${fmtPct(r.change_1y_pct)}</td>
       <td>${fmtN(r.pe_ratio)}</td><td>${r.dividend_yield == null ? "—" : Number(r.dividend_yield).toFixed(1) + "%"}</td>
       <td>${fmtMcap(r.market_cap)}</td><td>${r.rsi14 == null ? "—" : Number(r.rsi14).toFixed(0)}</td>
       <td>${r.above_sma50 == null ? "—" : (r.above_sma50 ? "Yes" : "No")}</td>
       <td>${r.vol_ratio == null ? "—" : Number(r.vol_ratio).toFixed(1) + "×"}</td></tr>`).join("")
      || `<tr><td colspan="10" class="sub">No matches — loosen filters.</td></tr>`;
  } catch (e) { toast("Screener failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Run screen";
}

/* ── BACKTEST ── */
async function loadStrats() {
  try {
    const d = await GET("/api/backtest/strategies");
    S.strats = d.strategies;
    $("#btStrat").innerHTML = d.strategies.map(s => `<option value="${s.id}">${s.name}</option>`).join("");
    on("btStrat", "change", e => {
      const st = S.strats.find(x => x.id === e.target.value);
      $("#btDesc").textContent = (st && st.desc) || "";
    });
    $("#btDesc").textContent = (d.strategies[0] || {}).desc || "";
  } catch (e) { /* ignore */ }
}
function paintBtCosts() {
  const s = (S.cfg && S.cfg.settings) || {};
  $("#btCosts").textContent = `Costs per side: ${s.commission_pct ?? 0.15}% commission + ${s.slippage_pct ?? 0.1}% slippage (change in ⚙ Settings → Trading)`;
}
on("runBt", "click", async () => {
  const btn = $("#runBt"); btn.disabled = true; btn.textContent = "Running…";
  try {
    memSave({ bt: { sym: $("#btSym").value.trim().toUpperCase(), strat: $("#btStrat").value,
      start: $("#btStart").value, end: $("#btEnd").value, cap: $("#btCap").value, atr: $("#btAtr").value } });
    const d = await POST("/api/backtest/run", {
      symbol: $("#btSym").value.trim().toUpperCase(), strategy: $("#btStrat").value,
      start: $("#btStart").value || null, end: $("#btEnd").value || null,
      capital: +$("#btCap").value || null, atr_mult: +$("#btAtr").value || 2.0,
    });
    if (d.error) { toast(d.error); return; }
    $("#btOut").style.display = "block";
    document.querySelector("#btTrades thead").innerHTML =
      "<tr><th>Entry</th><th>Exit</th><th>Buy</th><th>Sell</th><th>Qty</th><th>Ret %</th><th>Reason</th></tr>";
    const m = d.metrics;
    const statRows = [
      ["Total return", fmtPct(m.total_return_pct)], ["Buy & hold", fmtPct(m.buy_hold_pct)],
      ["CAGR", fmtPct(m.cagr_pct)], ["Sharpe", fmtN(m.sharpe)],
      ["Max drawdown", fmtPct(m.max_drawdown_pct)], ["Trades", m.trades],
      ["Win rate", m.win_rate_pct + "%"], ["Profit factor", fmtN(m.profit_factor)],
    ];
    if (m.open_trade) statRows.push(["Open position",
      `${fmtPct(m.open_trade.unrealized_pct)} unrealized since ${m.open_trade.entry_date} (still held - not in win-rate)`]);
    $("#btStats").innerHTML = statRows.map(([k, v]) =>
      `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
    drawLine($("#eqChart"), d.equity.map(e => ({ x: e.date, y: e.equity })));
    $("#btTrades tbody").innerHTML = d.trades.slice().reverse().map(t =>
      `<tr><td>${t.entry_date}</td><td>${t.exit_date}</td><td>${fmtRs(t.entry)}</td><td>${fmtRs(t.exit)}</td>
       <td>${fmtN(t.qty)}</td><td class="${cls(t.return_pct)}">${fmtPct(t.return_pct)}</td><td>${t.reason}</td></tr>`).join("");
  } catch (e) { toast("Backtest failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Run backtest";
});
/* ── PAPER ── */
async function loadPaper() {
  try {
    const [a, h] = await Promise.all([GET("/api/paper/account"), GET("/api/paper/history")]);
    $("#paperTop").innerHTML = [
      ["Equity", fmtRs(a.equity)], ["Cash", fmtRs(a.cash)],
      ["Invested", fmtRs(a.market_value)], ["Realized P&L", fmtRs(a.realized_pnl)],
    ].map(([k, v]) => `<div class="card"><h3>${k}</h3><div class="price-big" style="font-size:22px">${v}</div></div>`).join("");
    $("#posTbl tbody").innerHTML = a.positions.map(p =>
      `<tr class="clickable" data-s="${p.symbol}"><td><b>${p.symbol}</b></td><td>${fmtN(p.qty)}</td>
       <td>${fmtRs(p.avg_price)}</td><td>${fmtRs(p.last)}</td>
       <td class="${cls(p.unrealized_rs)}">${fmtRs(p.unrealized_rs)} (${fmtPct(p.unrealized_pct)})</td></tr>`).join("")
      || `<tr><td colspan="5" class="sub">No open positions.</td></tr>`;
    $("#ordTbl tbody").innerHTML = h.orders.map(o =>
      `<tr><td>${new Date(o.ts * 1000).toLocaleString()}</td><td><b>${o.symbol}</b></td>
       <td>${pill(o.side.toUpperCase() === "BUY" ? "BUY" : "SELL")}</td><td>${fmtN(o.qty)}</td>
       <td>${fmtRs(o.price)}</td><td class="sub">${o.note || ""}</td></tr>`).join("")
      || `<tr><td colspan="6" class="sub">No orders yet.</td></tr>`;
  } catch (e) { toast("Paper account failed: " + e.message); }
}
/* REAL broker account — live editable book (seeded from statement W615) */
async function loadBroker() {
  try {
    const d = await GET("/api/broker/account");
    const t = d.totals || {}, m = d.meta || {};
    $("#bkMeta").textContent = `${m.broker || ""} · account ${m.account || ""} · ${m.client || ""} · statement trades incl. commission · saved live in ${m.store || "broker_account.json"}`;
    const chip = (k, v, tone) => `<div class="stat"><div class="k">${k}</div><div class="v ${tone || ""}" style="font-size:18px">${v}</div></div>`;
    $("#bkTop").innerHTML =
      chip("Still invested", fmtRs(t.still_invested)) +
      chip("Market value", t.market_value != null ? fmtRs(t.market_value) : "—") +
      chip("Unrealized P&L", t.unrealized_pnl != null ? fmtRs(t.unrealized_pnl) : "—", cls(t.unrealized_pnl)) +
      chip("Realized P&L", fmtRs(t.realized_pnl), cls(t.realized_pnl));
    $("#bkPos tbody").innerHTML = (d.positions || []).map(p =>
      `<tr><td><b class="clickable" data-s="${p.symbol}">${p.symbol}</b></td><td>${fmtN(p.qty)}</td>
       <td>${fmtRs(p.avg_cost)}</td><td>${p.last != null ? fmtRs(p.last) : "—"}</td>
       <td>${fmtRs(p.invested)}</td><td>${p.market_value != null ? fmtRs(p.market_value) : "—"}</td>
       <td class="${cls(p.unrealized)}">${p.unrealized != null ? fmtRs(p.unrealized) + " (" + fmtPct(p.unrealized_pct) + ")" : "—"}</td>
       <td><button class="btn ghost bk-close" data-s="${p.symbol}" data-q="${p.qty}" title="Sell at live price">✕ Close</button></td></tr>`).join("")
      || `<tr><td colspan="8" class="sub">No open positions.</td></tr>`;
    $("#bkReal tbody").innerHTML = (d.realized || []).map(r =>
      `<tr><td>${r.date}</td><td><b>${r.symbol}</b></td><td>${fmtN(r.qty)}</td><td>${fmtRs(r.rate)}</td>
       <td>${fmtRs(r.proceeds)}</td><td>${fmtRs(r.cost)}</td>
       <td class="${cls(r.pnl)}">${fmtRs(r.pnl)}</td></tr>`).join("")
      || `<tr><td colspan="7" class="sub">None.</td></tr>`;
    $("#bkHistSum").textContent = `Full transaction history (${(d.trades || []).length} trades)`;
    $("#bkTrades tbody").innerHTML = (d.trades || []).map(x =>
      `<tr><td>${x.date}</td><td><b>${x.symbol}</b></td>
       <td>${x.side === "buy" ? '<span class="pill p-buy">BUY</span>' : '<span class="pill p-sell">SELL</span>'}</td>
       <td>${fmtN(x.qty)}</td><td>${fmtRs(x.rate)}</td><td>${fmtRs(x.amount)}</td>
       <td class="sub">${x.source === "manual" || x.source === "close" ? "added here" : "statement W615"}</td></tr>`).join("");
  } catch (e) { toast("Broker book failed: " + e.message); }
}
on("bkAdd", "click", async () => {
  const msg = $("#bkMsg"); msg.textContent = "Adding…";
  try {
    const d = await POST("/api/broker/trade", {
      symbol: $("#bkSym").value.trim().toUpperCase(), side: $("#bkSide").value,
      qty: +$("#bkQty").value, rate: $("#bkRate").value ? +$("#bkRate").value : null,
    });
    if (d.error) { msg.textContent = "❌ " + d.error; return; }
    const t = d.trade;
    msg.textContent = `✅ ${t.side.toUpperCase()} ${fmtN(t.qty)} ${t.symbol} @ ${fmtRs(t.rate)} recorded`;
    loadBroker();
  } catch (e) { msg.textContent = "❌ " + e.message; }
});
$("#bkPos").addEventListener("click", async e => {
  const b = e.target.closest(".bk-close"); if (!b) return;
  const sym = b.dataset.s, have = +b.dataset.q;
  const qty = prompt(`Close ${sym} — how many shares? (blank = all ${fmtN(have)})`, "");
  if (qty === null) return;
  try {
    const d = await POST("/api/broker/close", { symbol: sym, qty: qty ? +qty : null, rate: null });
    if (d.error) { toast("❌ " + d.error); return; }
    toast(`✅ Sold ${fmtN(d.trade.qty)} ${sym} @ ${fmtRs(d.trade.rate)}`);
    loadBroker();
  } catch (er) { toast("❌ " + er.message); }
});
on("bkReset", "click", async () => {
  if (!confirm("Reset the real broker book to the original W615 statement trades? Trades added here will be removed.")) return;
  await POST("/api/broker/reset"); loadBroker();
});
on("bkAdvice", "click", async () => {
  const out = $("#bkAdviceOut");
  out.style.display = ""; out.textContent = "🤖 Thinking — reading your positions…";
  try {
    const d = await POST("/api/broker/advice", {});
    out.textContent = (d.ai ? "🤖 AI assessment:\n\n" : "") + (d.text || d.error || "No reply.");
  } catch (e) { out.textContent = "❌ " + e.message; }
});
/* ── broker statement upload (PDF → positions preview → apply) ── */
let BK_STMT_ROWS = [];
on("bkStmtParse", "click", async () => {
  const f = $("#bkStmtFile").files[0], msg = $("#bkStmtMsg"), prev = $("#bkStmtPrev");
  if (!f) { msg.textContent = "Choose a PDF file first."; return; }
  msg.textContent = "Reading " + f.name + " …"; prev.innerHTML = "";
  const fd = new FormData(); fd.append("file", f);
  try {
    const r = await fetch("/api/broker/statement/parse", { method: "POST", body: fd });
    const d = await r.json();
    if (!d.ok) { msg.textContent = "❌ " + (d.error || "could not read the file"); return; }
    BK_STMT_ROWS = d.rows; msg.textContent = "";
    renderStmtPreview(d.notes, f.name);
  } catch (e) { msg.textContent = "❌ " + e; }
});
function renderStmtPreview(notes, fname) {
  const prev = $("#bkStmtPrev");
  if (!BK_STMT_ROWS.length) {
    prev.innerHTML = `<p class="sub">${(notes || []).join("<br>")}</p>`;
    return;
  }
  prev.innerHTML = `
    <p class="sub">${(notes || []).join("<br>")}</p>
    <div style="overflow-x:auto"><table><thead><tr>
      <th></th><th>Symbol</th><th>Qty (editable)</th><th>Avg cost Rs (editable)</th><th>Value</th><th>How detected</th>
    </tr></thead><tbody>` +
    BK_STMT_ROWS.map((r, i) => `<tr>
      <td><input type="checkbox" class="stChk" data-i="${i}" checked></td>
      <td><b>${r.symbol}</b></td>
      <td><input class="stQty" data-i="${i}" type="number" step="1" value="${r.qty}" style="width:110px"></td>
      <td><input class="stRate" data-i="${i}" type="number" step="0.01" value="${r.rate}" style="width:110px"></td>
      <td class="stVal">${fmtRs(r.value)}</td>
      <td class="sub" style="font-size:11px">${r.how}</td></tr>`).join("") +
    `</tbody></table></div>
    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
      <label class="sub">Positions dated <input type="date" id="stDate" value="${new Date().toISOString().slice(0, 10)}"></label>
      <button class="btn primary" id="stApply">✅ Apply — replace my book with these positions</button>
      <button class="btn ghost" id="stCancel">Cancel</button>
    </div>
    <p class="sub" style="margin-top:6px">Applying REPLACES the current book — earlier closed-trade history is cleared.
    Each position becomes an opening BUY at its average cost. Source: ${fname}.</p>`;
  prev.querySelectorAll(".stQty,.stRate").forEach(inp => inp.addEventListener("input", () => {
    const i = +inp.dataset.i, isQty = inp.classList.contains("stQty");
    BK_STMT_ROWS[i][isQty ? "qty" : "rate"] = +inp.value;
    prev.querySelectorAll(".stVal")[i].textContent =
      fmtRs(Math.round((BK_STMT_ROWS[i].qty || 0) * (BK_STMT_ROWS[i].rate || 0) * 100) / 100);
  }));
  on("stCancel", "click", () => {
    BK_STMT_ROWS = []; prev.innerHTML = "";
    $("#bkStmtMsg").textContent = "Cancelled — nothing changed.";
  });
  on("stApply", "click", async () => {
    const chks = prev.querySelectorAll(".stChk");
    const rows = BK_STMT_ROWS.filter((r, i) => chks[i].checked && r.qty > 0 && r.rate > 0);
    if (!rows.length) { alert("Tick at least one position first."); return; }
    if (!confirm("Replace your whole broker book with these " + rows.length +
                 " positions? The previous closed-trade history will be cleared.")) return;
    const d = await POST("/api/broker/statement/apply", { rows, date: $("#stDate").value || null });
    if (!d.ok) { alert("Apply failed: " + d.error); return; }
    toast("✅ Book updated: " + d.positions + " positions from the statement");
    BK_STMT_ROWS = []; prev.innerHTML = "";
    $("#bkStmtMsg").textContent = ""; $("#bkStmtFile").value = "";
    loadBroker();
  });
}
on("placeOrder", "click", async () => {
  try {
    const d = await POST("/api/paper/order", {
      symbol: $("#poSym").value.trim().toUpperCase(), side: $("#poSide").value,
      qty: +$("#poQty").value, price: $("#poPrice").value ? +$("#poPrice").value : null,
    });
    $("#poMsg").textContent = d.error ? "❌ " + d.error : `✅ ${d.side.toUpperCase()} ${d.qty} ${d.symbol} @ ${fmtRs(d.price)}`;
    loadPaper();
  } catch (e) { $("#poMsg").textContent = "❌ " + e.message; }
});
on("resetPaper", "click", async () => {
  const cash = (S.cfg && S.cfg.settings && S.cfg.settings.paper_cash) || 1000000;
  if (!confirm(`Reset paper account to ${fmtRs(cash)}?`)) return;
  await POST("/api/paper/reset"); loadPaper();
});

/* ── NEWS ── */
async function loadNews() {
  try {
    const d = await GET("/api/news?limit=40");
    $("#newsSent").textContent = `Overall mood: ${d.sentiment.label} (score ${d.sentiment.score} across ${d.sentiment.count} stories)`;
    $("#newsList").innerHTML = d.items.map(i =>
      `<div class="news-item"><a href="${i.link}" target="_blank" rel="noopener">${i.title || "(no title)"}</a>
       <div class="meta">${i.source || ""} · ${i.published || ""} · sentiment ${i.sentiment}</div></div>`).join("")
      || `<p class="sub">No news right now.</p>`;
  } catch (e) { toast("News failed: " + e.message); }
}

/* ── PSX announcements (via Investify, free) ── */
function paintNewsTabs(tab) {
  S.newsTab = tab;
  $("#newsPaneNews").style.display = tab === "news" ? "" : "none";
  $("#newsPaneAnn").style.display = tab === "ann" ? "" : "none";
  $("#newsPaneRep").style.display = tab === "rep" ? "" : "none";
  $("#newsTabNews").classList.toggle("active", tab === "news");
  $("#newsTabAnn").classList.toggle("active", tab === "ann");
  $("#newsTabRep").classList.toggle("active", tab === "rep");
}
on("newsTabNews", "click", () => { paintNewsTabs("news"); loadNews(); });
on("newsTabAnn", "click", () => { paintNewsTabs("ann"); loadAnn(); });
on("newsTabRep", "click", () => { paintNewsTabs("rep"); loadRep(); });
on("annWlOnly", "change", loadAnn);

/* ── official company reports calendar (financials.psx.com.pk) ── */
async function loadRep() {
  $("#repList").innerHTML = '<p class="sub">Loading official reports calendar…</p>';
  try {
    const d = await GET("/api/filings/recent?limit=40");
    $("#repCount").textContent = `Latest ${d.count} filings across PSX`;
    $("#repList").innerHTML = d.items.map(r => `
      <div class="news-item">
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <span class="pill p-hold" style="cursor:pointer" data-annsym="${r.symbol}" title="Open ${r.symbol}">${r.symbol}</span>
          <b>${r.company || ""}</b>
          <span class="sub">filed ${r.last_filed}</span>
          ${r.last_annual ? `<span class="sub" style="font-size:11px;border:1px solid var(--line);border-radius:99px;padding:1px 8px">Annual ${r.last_annual}</span>` : ""}
          ${r.last_quarter ? `<span class="sub" style="font-size:11px;border:1px solid var(--line);border-radius:99px;padding:1px 8px">Quarterly ${r.last_quarter}</span>` : ""}
        </div>
      </div>`).join("")
      || `<p class="sub">No filings found.</p>`;
    $("#repList").querySelectorAll("[data-annsym]").forEach(el =>
      el.addEventListener("click", () => openStock(el.dataset.annsym)));
  } catch (e) { toast("Reports calendar failed: " + e.message); }
}

async function loadAnn() {
  const wl = $("#annWlOnly").checked;
  $("#annList").innerHTML = '<p class="sub">Loading filings…</p>';
  try {
    const d = await GET("/api/announcements?limit=30" + (wl ? "&watchlist_only=true" : ""));
    $("#annCount").textContent = `${d.count} filing${d.count === 1 ? "" : "s"} shown`;
    $("#annList").innerHTML = d.items.map(a => `
      <div class="news-item">
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:3px">
          <span class="pill p-hold" style="cursor:pointer" data-annsym="${a.symbol}" title="Open ${a.symbol}">${a.symbol}</span>
          <span style="font-size:11px;font-weight:700;border:1px solid var(--line);border-radius:99px;padding:2px 9px">${a.category || "Filing"}</span>
          ${a.sentiment && a.sentiment !== "Neutral" ? `<span class="sub" style="font-weight:700">${a.sentiment}</span>` : ""}
          <span class="sub">${a.when || ""}</span>
        </div>
        <a href="${a.link}" target="_blank" rel="noopener">${a.title}</a>
        ${a.pdf ? ` · <a href="${a.pdf}" target="_blank" rel="noopener" style="font-size:12px">📄 Original PDF</a>` : ""}
        <div class="meta">${a.company || ""}${a.summary ? " — " + a.summary : ""}</div>
      </div>`).join("")
      || `<p class="sub">No filings found${wl ? " for your watchlist today" : ""}.</p>`;
    $("#annList").querySelectorAll("[data-annsym]").forEach(el =>
      el.addEventListener("click", () => openStock(el.dataset.annsym)));
  } catch (e) { $("#annList").innerHTML = `<p class="neg">Announcements failed: ${e.message}</p>`; }
}

/* ── SETTINGS ── */
const TRADE_DEFS = [
  ["paper_cash", "Starting paper cash (Rs)", "Fake money for practice. Also used to size trade plans."],
  ["default_risk_pct", "Risk per trade (%)", "How much of your money one idea may risk. 1 = careful, 2 = bold."],
  ["circuit_breaker_pct", "Circuit breaker (%)", "PSX daily price limit. Keep 7.5 unless PSX changes the rule."],
  ["commission_pct", "Broker commission, per side (%)", "What your broker + taxes cost on each buy/sell. Check your broker statement."],
  ["slippage_pct", "Slippage, per side (%)", "Extra cost because price moves while you order. 0.10 is normal."],
  ["proposal_valid_days", "Proposal valid (days)", "After this many days a trade plan is old — make a new one."],
  ["screener_max_stocks", "Screener depth (20–120)", "How many stocks get full technical checking per screen. Higher = slower."],
];
function renderWlEdit() {
  $("#setWlTbl tbody").innerHTML = S.wlEdit.map((w, i) =>
    `<tr><td><input data-wl="${i}:symbol" value="${(w.symbol || "").replace(/"/g, "")}" style="min-width:80px"></td>
     <td><input data-wl="${i}:name" value="${(w.name || "").replace(/"/g, "")}"></td>
     <td><input data-wl="${i}:sector" value="${(w.sector || "").replace(/"/g, "")}"></td>
     <td><input data-wl="${i}:reason" value="${(w.reason || "").replace(/"/g, "")}"></td>
     <td><button class="btn small ghost" data-wldel="${i}">✕</button></td></tr>`).join("")
    || `<tr><td colspan="5" class="sub">No stocks — add one below.</td></tr>`;
}
document.addEventListener("input", e => {
  const el = e.target.closest("[data-wl]");
  if (!el) return;
  const [i, k] = el.dataset.wl.split(":");
  if (S.wlEdit[+i]) S.wlEdit[+i][k] = el.value;
});
document.addEventListener("click", e => {
  const b = e.target.closest("[data-wldel]");
  if (!b) return;
  S.wlEdit.splice(+b.dataset.wldel, 1);
  renderWlEdit();
});
async function loadSettings() {
  try {
    const d = await GET("/api/settings");
    S.cfg = d.config;
    const c = S.cfg;
    S.wlEdit = JSON.parse(JSON.stringify(c.watchlist || []));
    renderWlEdit();
    $("#setTrade").innerHTML = TRADE_DEFS.map(([k, label, hint]) =>
      `<label>${label}</label><input data-tr="${k}" type="number" step="any" value="${c.settings[k] ?? ""}">
       <div class="hint">${hint}</div>`).join("");
    $("#olEnabled").value = String(!!c.ollama.enabled);
    $("#olUrl").value = c.ollama.base_url || "";
    $("#olTimeout").value = (c.llm && c.llm.timeout_sec) ?? c.ollama.timeout_sec ?? 25;
    $("aiProvider").value = (c.llm && c.llm.provider) || "ollama";
    paintAiProvider();
    $("#uiAuto").value = String(c.ui.auto_refresh_enabled !== false);
    $("#uiSec").value = c.ui.auto_refresh_sec ?? 60;
    $("#uiStock").value = c.ui.default_stock || "OGDC";
    $("#paperCash").value = c.settings.paper_cash ?? 1000000;
    $("#aboutBox").innerHTML = `PSX Live & Research v1.0 · free &amp; open-source · data: DPS PSX (psxdata), Yahoo Finance, public RSS · ` +
      `${c.watchlist.length} watchlist stocks · auto-refresh ${c.ui.auto_refresh_enabled ? "ON (" + c.ui.auto_refresh_sec + "s)" : "OFF"} · ` +
      `AI notes ${c.ollama.enabled ? "ON (" + ((c.llm && c.llm.provider) || "ollama") + ")" : "OFF"} · ` +
      `Cloud backup (R2) ${(c.cloud && c.cloud.r2_configured) ? "credentials saved \u2713" : "not configured"} · Full guides in the <b>docs/</b> folder · API docs at <b>/docs</b>`;
    loadCacheInfo();
    loadFitStatus();
    paintBtCosts();
  } catch (e) { toast("Settings failed: " + e.message); }
}
async function loadCacheInfo() {
  try {
    const c = await GET("/api/cache/info");
    $("#cacheInfo").textContent = `${c.files} saved files · ${(c.total_kb / 1024).toFixed(1)} MB total` +
      (c.top.length ? ` · biggest: ${c.top.slice(0, 3).map(f => f.name + " " + f.kb + "KB").join(", ")}` : "");
  } catch (e) { $("#cacheInfo").textContent = "Could not read cache info."; }
}
/* -- Strategy Fit Guide (regenerate + download) -- */
let FIT_TIMER = null;
async function loadFitStatus() {
  try {
    const s = await GET("/api/fit-guide");
    const msg = $("#fitMsg"); if (!msg) return;
    if (s.status === "running") { msg.textContent = "Crunching all backtests… about a minute."; return; }
    if (s.error) { msg.textContent = "Last run failed: " + s.error; return; }
    msg.textContent = s.exists
      ? `PDF ready (${(s.size / 1024).toFixed(0)} KB)` + (s.last_run ? ` · last generated ${fmtTs(s.last_run)} PKT` : "") + " — press Download."
      : "Not generated yet — press Regenerate.";
  } catch (e) { /* settings tab degraded */ }
}
on("fitRun", "click", async () => {
  const msg = $("#fitMsg"); const btn = $("#fitRun");
  btn.disabled = true; msg.textContent = "Started — crunching every backtest (about a minute)…";
  try { await POST("/api/fit-guide/run", {}); }
  catch (e) { msg.textContent = "❌ " + e.message; btn.disabled = false; return; }
  clearInterval(FIT_TIMER);
  FIT_TIMER = setInterval(async () => {
    const s = await GET("/api/fit-guide").catch(() => null);
    if (!s) return;
    if (s.status === "running") { msg.textContent = "Still crunching… please wait."; return; }
    clearInterval(FIT_TIMER); btn.disabled = false;
    if (s.status === "done") { msg.textContent = "✅ Done — press Download PDF."; }
    else { msg.textContent = "❌ " + (s.error || "generation failed"); }
  }, 4000);
});
/* -- AI provider picker -- */
const AI_SIGNUP = { groq: "https://console.groq.com/keys", openrouter: "https://openrouter.ai/keys",
                    gemini: "https://aistudio.google.com/apikey", cerebras: "https://cloud.cerebras.ai" };
const AI_DEFAULT_MODEL = { ollama: "llama3.1", groq: "llama-3.3-70b-versatile",
                           openrouter: "meta-llama/llama-3.3-70b-instruct:free", gemini: "gemini-2.0-flash",
                           cerebras: "llama3.1-8b" };
function paintAiProvider() {
  const p = $("aiProvider").value, L = (S.cfg && S.cfg.llm) || {};
  $("aiOllamaFields").style.display = p === "ollama" ? "" : "none";
  $("aiCloudFields").style.display = p === "ollama" ? "none" : "";
  if (p === "ollama") {
    $("olModel").value = ((S.cfg || {}).ollama || {}).model || AI_DEFAULT_MODEL.ollama;
  } else {
    const sub = L[p] || {};
    $("olModel").value = sub.model || AI_DEFAULT_MODEL[p] || "";
    $("aiKey").value = sub.api_key || "";
    $("aiKeyHelp").innerHTML = 'Free key (sign up, copy, paste above): <a href="' + AI_SIGNUP[p] +
      '" target="_blank" rel="noopener">' + AI_SIGNUP[p] + "</a>";
  }
  loadAiModels(p);   // fill the free-model dropdown for this provider
}
on("aiProvider", "change", paintAiProvider);
async function loadAiModels(p) {
  const sel = $("#aiModelSel");
  if (!sel) return;
  sel.innerHTML = '<option value="">Loading free models…</option>';
  try {
    const d = await GET("/api/ai/models?provider=" + p);
    const ms = d.models || [];
    if (ms.length) {
      sel.innerHTML = ms.map(m => `<option value="${m}">${m}</option>`).join("");
      const cur = $("#olModel").value.trim();
      if (cur && ms.includes(cur)) sel.value = cur;
    } else {
      sel.innerHTML = `<option value="">${d.note || "no models listed"}</option>`;
    }
    if (d.note && ms.length) sel.title = d.note;
  } catch (e) {
    sel.innerHTML = '<option value="">fetch failed — type the model name below</option>';
  }
}
on("aiModelSel", "change", () => {
  if ($("#aiModelSel").value) $("#olModel").value = $("#aiModelSel").value;
});

on("wlAdd", "click", () => {
  const sym = $("#wlSym").value.trim().toUpperCase();
  if (!sym) { $("#wlMsg").textContent = "Type a symbol first (e.g. SYS)."; return; }
  S.wlEdit.push({ symbol: sym, name: $("#wlName").value.trim() || sym,
    sector: $("#wlSector").value.trim(), reason: $("#wlReason").value.trim() });
  $("#wlSym").value = $("#wlName").value = $("#wlSector").value = $("#wlReason").value = "";
  $("#wlMsg").textContent = "";
  renderWlEdit();
});
on("wlSave", "click", async () => {
  try {
    const d = await PUT("/api/settings", { watchlist: S.wlEdit });
    if (!d.ok) { $("#wlMsg").textContent = "❌ " + d.errors.join(" "); return; }
    S.cfg = d.config;
    S.watchMeta = d.config.watchlist;
    $("#wlMsg").textContent = "✅ Saved — Home watchlist updated.";
    loadWatch(); loadSigStatus(); loadSettings();
  } catch (e) { $("#wlMsg").textContent = "❌ " + e.message; }
});
on("tradeSave", "click", async () => {
  try {
    const s = {};
    document.querySelectorAll("#setTrade [data-tr]").forEach(i => { s[i.dataset.tr] = i.value === "" ? null : +i.value; });
    const d = await PUT("/api/settings", { settings: s });
    if (!d.ok) { $("#tradeMsg").textContent = "❌ " + d.errors.join(" "); return; }
    S.cfg = d.config;
    $("#tradeMsg").textContent = "✅ Saved — proposals, backtests & paper reset now use these.";
    paintBtCosts();
  } catch (e) { $("#tradeMsg").textContent = "❌ " + e.message; }
});
on("olSave", "click", async () => {
  try {
    const p = $("aiProvider").value, tout = +$("#olTimeout").value || 25;
    const ollama = { enabled: $("#olEnabled").value === "true", base_url: $("#olUrl").value.trim(),
      model: p === "ollama" ? $("#olModel").value.trim()
             : (((S.cfg || {}).ollama || {}).model || "llama3.1"),
      timeout_sec: tout };
    const llm = { provider: p, timeout_sec: tout };
    if (p !== "ollama") llm[p] = { api_key: $("#aiKey").value.trim(), model: $("#olModel").value.trim() };
    const d = await PUT("/api/settings", { ollama, llm });
    if (!d.ok) { $("#olMsg").textContent = "❌ " + d.errors.join(" "); return; }
    S.cfg = d.config;
    paintAiBadge(S.cfg);
    $("#olMsg").textContent = "✅ Saved." + (d.config.ollama.enabled ? " Press Test connection to verify." : " AI is OFF — built-in reasoning still works.");
    loadSettings();
  } catch (e) { $("#olMsg").textContent = "❌ " + e.message; }
});
on("olTest", "click", async () => {
  const p = $("#aiProvider").value;
  $("#olMsg").textContent = "Testing… (may take up to a minute on first run)";
  try {
    const body = p === "ollama"
      ? { provider: "ollama", model: $("#olModel").value.trim() }
      : { provider: p, model: $("#olModel").value.trim(), api_key: $("#aiKey").value.trim() };
    const d = await POST("/api/settings/test-ai", body);
    $("#olMsg").textContent = (d.ok ? "✅ " : "❌ ") + d.message +
      (d.ok ? " — press Save AI settings to keep it." : "");
  } catch (e) { $("#olMsg").textContent = "❌ " + e.message; }
});
/* -- watchlist: search stock by ticker, pull its data on select -- */
const wlS = $("#wlSym"), wlSug = $("#wlSuggest");
wlS.addEventListener("input", () => {
  const q = wlS.value.trim().toUpperCase();
  if (!q) { wlSug.style.display = "none"; return; }
  const hits = (S.universe || []).filter(u => u.symbol.includes(q)).slice(0, 8);
  wlSug.innerHTML = hits.map(h =>
    `<div data-s="${h.symbol}"><b>${h.symbol}</b> \u00b7 ${fmtRs(h.price)} ` +
    `<span class="${cls(h.chg)}">${fmtPct(h.chg)}</span></div>`).join("") ||
    "<div>No match \u2014 press + Add to add the ticker as typed</div>";
  wlSug.style.display = "block";
});
wlSug.addEventListener("click", async e => {
  const d = e.target.closest("div[data-s]"); if (!d) return;
  wlSug.style.display = "none";
  const sym = d.dataset.s; wlS.value = sym;
  $("#wlMsg").textContent = "\u23f3 Pulling " + sym + " data\u2026";
  try {
    const st = await GET("/api/stock/" + sym);
    const yf = ((st.fundamentals || {}).yfinance) || {};
    $("wlName").value = (yf.longName || yf.shortName || (st.name !== sym ? st.name : "") || sym);
    $("wlSector").value = st.sector || "";
    $("#wlMsg").textContent = "\u2705 " + sym + " loaded \u2014 name & sector filled. Press + Add stock.";
  } catch (err) {
    $("#wlMsg").textContent = sym + " typed in \u2014 could not fetch details, press + Add to add anyway.";
  }
});
document.addEventListener("click", e => {
  if (!e.target.closest("#wlSym") && !e.target.closest("#wlSuggest")) wlSug.style.display = "none";
});
on("uiSave", "click", async () => {
  try {
    const d = await PUT("/api/settings", { ui: {
      auto_refresh_enabled: $("#uiAuto").value === "true",
      auto_refresh_sec: +$("#uiSec").value || 60,
      default_stock: $("#uiStock").value.trim().toUpperCase() || "OGDC" } });
    if (!d.ok) { $("#uiMsg").textContent = "❌ " + d.errors.join(" "); return; }
    S.cfg = d.config;
    setupAutoRefresh();
    $("#uiMsg").textContent = "✅ Saved — auto-refresh " + (d.config.ui.auto_refresh_enabled ? `runs every ${d.config.ui.auto_refresh_sec}s.` : "is OFF.");
  } catch (e) { $("#uiMsg").textContent = "❌ " + e.message; }
});
on("cacheReload", "click", loadCacheInfo);
on("cacheClear", "click", async () => {
  if (!confirm("Delete all saved market data? It will download fresh (slower once).")) return;
  try {
    const d = await POST("/api/cache/clear");
    $("#maintMsg").textContent = `✅ Cleared ${d.cleared} files. Press ⟳ Refresh to reload.`;
    loadCacheInfo();
  } catch (e) { $("#maintMsg").textContent = "❌ " + e.message; }
});
on("paperReset2", "click", async () => {
  const cash = +$("#paperCash").value || null;
  if (!confirm(`Reset paper account to ${fmtRs(cash || ((S.cfg && S.cfg.settings.paper_cash) || 1000000))}? All practice trades will be deleted.`)) return;
  try {
    await POST("/api/paper/reset" + (cash ? `?cash=${cash}` : ""));
    $("#maintMsg").textContent = "✅ Paper account reset.";
  } catch (e) { $("#maintMsg").textContent = "❌ " + e.message; }
});

/* ── diagnostics ── */
async function runDiag() {
  const b = $("#diagBox"); if (!b) return;
  b.innerHTML = "Checking…";
  const rows = [];
  rows.push(["App version", APP_VERSION + " (if this looks old, hard-refresh: Ctrl+Shift+R)"]);
  rows.push(["Page address", location.href]);
  try {
    const h = await GET("/api/health");
    rows.push(["Server API", "OK — watchlist: " + (h.watchlist || []).join(", ")]);
  } catch (e) { rows.push(["Server API", "FAILED: " + e.message + " — is the server running?"]); }
  try {
    const s = await GET("/api/signals/status");
    rows.push(["Server time (PKT)", s.server_time_pkt + " · market " + s.market_status]);
    rows.push(["Last signals", s.last_watchlist_signals_at || "none yet — press Refresh"]);
  } catch (e) { rows.push(["Server time", "FAILED: " + e.message]); }
  rows.push(["Browser time", new Date().toString()]);
  const ui = (S.cfg && S.cfg.ui) || {};
  rows.push(["Auto-refresh setting", ui.auto_refresh_enabled === false ? "OFF" : ("ON, every " + (ui.auto_refresh_sec || 60) + "s")]);
  rows.push(["Watchlist rows loaded", String(document.querySelectorAll("#watchTbl tbody tr").length)]);
  b.innerHTML = rows.map(([k, v]) => `<div><b>${k}:</b> ${v}</div>`).join("");
}
on("diagRun", "click", runDiag);

/* ── init ── */
/* -- REPORT (A-to-Z executive report + PDF) -- */
function fillRepSyms() {
  const sel = $("#repSym"); if (!sel) return;
  const wl = (S.cfg && S.cfg.watchlist) || S.watchMeta || [];
  if (!wl.length) { if (!sel.options.length) sel.innerHTML = `<option value="OGDC">OGDC</option>`; return; }
  const cur = sel.value;
  sel.innerHTML = wl.map(w => `<option value="${w.symbol}">${w.symbol} - ${(w.name || w.symbol).slice(0, 30)}</option>`).join("");
  if (cur) sel.value = cur;
}
function repKV(rows) {
  return `<div style="overflow-x:auto"><table><tbody>` + (rows || []).map(r =>
    `<tr><td style="white-space:nowrap"><b>${r[0]}</b></td><td>${r[1]}</td></tr>`).join("") + `</tbody></table></div>`;
}
function repList(items) {
  return `<ul>` + (items || []).map(i => `<li>${i}</li>`).join("") + `</ul>`;
}
async function genReport() {
  const sym = (($("#repSym") || {}).value || "OGDC").toUpperCase();
  const out = $("#repOut"), meta = $("#repMeta"), btn = $("#repGen"), pdf = $("#repPdf");
  btn.disabled = true; btn.textContent = "Generating... (may take ~30s)";
  out.innerHTML = `<div class="card"><p class="sub">Crunching ${sym}: research + proposal + backtest...</p></div>`;
  try {
    const r = await GET(`/api/stock/${encodeURIComponent(sym)}/report`);
    if (r.error) { out.innerHTML = `<div class="card">Error: ${r.error}</div>`; return; }
    meta.innerHTML = `<b>${r.symbol}</b> - ${r.company} - ${r.sector || ""} - data as of ${r.as_of} - generated ${fmtTs(r.generated_at)} PKT`;
    pdf.href = `/api/stock/${encodeURIComponent(sym)}/report.pdf`;
    const ex = r.executive || {}, q = r.quant || {}, t = q.trader || {}, d = r.debate || {},
          tp = (r.trade_plan || {}).proposal || {}, b = r.backtest || {}, dt = r.deep_thinking || {};
    const er = tp.entry_range || ["--", "--"];
    out.innerHTML = `
    <div class="card"><h2 style="margin-top:0">Verdict ${pill(ex.verdict)} &nbsp; Action ${pill(ex.action)} &nbsp; <span class="sub">confidence ${ex.confidence}</span></h2>
      <h3>1 - Executive summary</h3>${repList(ex.thesis)}</div>
    <div class="card"><h3>2 - Key stats at a glance</h3>${repKV(r.key_stats)}</div>
    <div class="card"><h3>3 - Price & trend</h3>${repKV(r.price_trend)}</div>
    <div class="card"><h3>4 - Technical signals</h3>${repKV(r.technicals)}</div>
    <div class="card"><h3>5 - Quant scorecard</h3><p>Trader action: ${pill(t.action)} <span class="sub">(score ${t.score})</span></p>
      ${repList((q.votes || []).map(v => `<b>${v.strategy}:</b> ${pill(v.signal)} - ${v.note}`))}</div>
    <div class="card"><h3>6 - Bull vs bear (bulls ${d.bull_score} vs bears ${d.bear_score}, net ${d.net})</h3>
      <h4>Bull case - why it can rise</h4>${repList((d.bull_factors || []).map(f => `<b>${f.factor}:</b> ${f.detail}`))}
      <h4>Bear case - why it can fall</h4>${repList((d.bear_factors || []).map(f => `<b>${f.factor}:</b> ${f.detail}`))}</div>
    <div class="card"><h3>7 - Trade plan (swing 2-8 weeks)</h3>${repKV([
      ["Action", pill(tp.action)], ["Buy zone", `Rs${er[0]} - Rs${er[1]}`],
      ["Stop loss", `Rs${tp.stop_loss} (exit if this breaks - idea is wrong)`],
      ["Target 1 / 2", `Rs${tp.target_1} / Rs${tp.target_2}`],
      ["Reward : risk", `${tp.reward_risk_t1} / ${tp.reward_risk_t2}`],
      ["Suggested size", `${Number(tp.suggested_qty || 0).toLocaleString()} shares = Rs${tp.est_cost_rs}`],
      ["Money at risk", `Rs${tp.risk_rs} (${tp.risk_pct}% of Rs${tp.capital_assumed})`],
      ["Valid until", tp.valid_until], ["Assessment", (r.trade_plan || {}).assessment || "--"]])}</div>
    <div class="card"><h3>8 - Fundamentals (complete A-to-Z data)</h3>
      <div class="grid g2">
        <div><h4>Performance by period (%)</h4><canvas class="chart" id="fcPerf" height="170"></canvas></div>
        <div><h4>Key ratios</h4><canvas class="chart" id="fcRatios" height="170"></canvas></div>
      </div>
      <h4 style="margin-top:10px">52-week price range</h4><canvas class="chart" id="fcRange" height="70"></canvas>
      <details open><summary style="cursor:pointer;font-weight:700;margin:10px 0">Full fundamental data table</summary>
      ${repKV(r.fundamentals)}</details></div>
    <div class="card"><h3>9 - News & sentiment</h3>${(r.news || []).length ? repList(r.news.map(n =>
      `<a href="${n.link}" target="_blank" rel="noopener">${n.title}</a> <span class="sub">(${n.source}, ${n.published}) [${n.sentiment}]</span>` +
      (n.summary ? `<br><span class="sub">${n.summary}</span>` : ""))) : `<p class="sub">No fresh company headlines.</p>`}</div>
    <div class="card"><h3>10 - Strategy check (3-year backtest)</h3>${b.error ? `<p class="sub">Unavailable: ${b.error}</p>` :
      `<p>${b.line}</p>` + repKV([["Total return", `${b.metrics.total_return_pct}% (buy-hold ${b.metrics.buy_hold_pct}%)`],
        ["CAGR", b.metrics.cagr_pct + "%"], ["Sharpe", b.metrics.sharpe], ["Max fall", b.metrics.max_drawdown_pct + "%"],
        ["Trades", b.metrics.trades], ["Win rate", b.metrics.win_rate_pct + "%"], ["Profit factor", b.metrics.profit_factor]])}</div>
    <div class="card"><h3>11 - Deep thinking checklist</h3>${repList(dt.steps)}
      ${dt.llm_narrative ? `<h4>Local-AI analyst note (bonus)</h4><p>${dt.llm_narrative}</p>` : ""}
      <p class="sub">Engine: ${dt.engine || ""}</p>
      <p style="color:#a00"><i>Disclaimer: ${r.disclaimer}</i></p></div>`;
    const fc = r.fund_charts || {};
    if ((fc.performance || []).length) drawBars($("#fcPerf"), fc.performance);
    if ((fc.ratios || []).length) drawBars($("#fcRatios"), fc.ratios);
    if (fc.range52 && fc.range52.low != null) drawGauge($("#fcRange"), fc.range52);
  } catch (e) { out.innerHTML = `<div class="card">Error: ${e.message}</div>`; toast("Report failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Generate report";
}
on("repGen", "click", genReport);

/* ── REAL ACCOUNT BRIEF: minimalist pies + since-last-visit progress ── */
async function paintBrief() {
  try {
    const b = await GET("/api/broker/brief");
    const G = ["#34d399", "#0d9f6e"], R = ["#f8717a", "#dc2626"],
          B = ["#60a5fa", "#2563eb"], A = ["#fbbf24", "#d97706"];
    const pct = (v, t) => t ? Math.round(v / t * 1000) / 10 : 0;
    const allN = b.open_n + b.closed_n, allW = b.open_win + b.closed_win;
    const oP = pct(b.open_win, b.open_n), aP = pct(allW, allN);
    const drv = (rows, f) => rows.map(r =>
      `<div style="display:flex;justify-content:space-between;gap:8px"><span><b>${r.symbol}</b></span><span class="${cls(r.v)}">${f(r)}</span></div>`).join("");
    const legend = (items, t) => items.map(([c, l, v]) =>
      `<div style="display:flex;justify-content:space-between;gap:8px"><span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${c};margin-right:6px"></i>${l}</span><span>${v} · ${pct(v, t)}%</span></div>`).join("");
    $("#briefGrid").innerHTML = `
      <div class="bcard brief" data-bc="bopen">
        <div class="k" style="color:#ec4899">Open trades</div>
        <div class="v ${oP >= 50 ? "tone-up" : "tone-down"}">${oP}%</div>
        <div class="s">in profit · ${b.open_n} open (${b.open_win} ▲ / ${b.open_loss} ▼)</div>
        <div class="more"><canvas id="pieOpen" class="bdonut"></canvas>
          <div class="drv">${legend([[G[0], "In profit", b.open_win], [R[0], "In loss", b.open_loss]], b.open_n)}</div>
          <div class="drv-label">Drivers — live P&amp;L</div>
          <div class="drv">${drv((b.open_rows || []).map(x => ({ symbol: x.symbol, v: x.pct })), r => fmtPct(r.v))}</div>
        </div>
      </div>
      <div class="bcard brief" data-bc="bclosed">
        <div class="k" style="color:#f97316">Closed trades</div>
        <div class="v ${ (b.success_rate || 0) >= 50 ? "tone-up" : "tone-amber"}">${b.success_rate != null ? b.success_rate + "%" : "—"}</div>
        <div class="s">success rate · ${b.closed_n} closed (${b.closed_win} wins)</div>
        <div class="more"><canvas id="pieClosed" class="bdonut"></canvas>
          <div class="drv">${legend([[B[0], "Wins", b.closed_win], [A[0], "Losses", b.closed_loss]], b.closed_n)}</div>
          <div class="drv-label">Drivers — realized P&amp;L</div>
          <div class="drv">${drv((b.closed_rows || []).map(x => ({ symbol: x.symbol + " · " + x.date, v: x.rs })), r => fmtRs(r.v))}</div>
        </div>
      </div>
      <div class="bcard brief" data-bc="ball">
        <div class="k" style="color:#3b82f6">Overall book</div>
        <div class="v ${aP >= 50 ? "tone-up" : "tone-down"}">${aP}%</div>
        <div class="s">win rate · ${allN} trades (${b.open_n} open + ${b.closed_n} closed)</div>
        <div class="more"><canvas id="pieAll" class="bdonut"></canvas>
          <div class="drv">${legend([[G[0], "Open · profit", b.open_win], [R[0], "Open · loss", b.open_loss],
                                      [B[0], "Closed · win", b.closed_win], [A[0], "Closed · loss", b.closed_loss]], allN)}</div>
        </div>
      </div>`;
    document.querySelectorAll("#briefGrid .bcard").forEach(x =>
      x.addEventListener("click", () => x.classList.toggle("open")));
    drawDonut($("#pieOpen"),
      [{ v: b.open_win, color: G[0], color2: G[1] }, { v: b.open_loss, color: R[0], color2: R[1] }],
      { center: oP + "%", centerColor: "#ec4899", sub: "IN PROFIT" });
    drawDonut($("#pieClosed"),
      [{ v: b.closed_win, color: B[0], color2: B[1] }, { v: b.closed_loss, color: A[0], color2: A[1] }],
      { center: (b.success_rate != null ? b.success_rate + "%" : "—"), centerColor: "#f97316", sub: "SUCCESS" });
    drawDonut($("#pieAll"),
      [{ v: b.open_win, color: G[0], color2: G[1] }, { v: b.open_loss, color: R[0], color2: R[1] },
       { v: b.closed_win, color: B[0], color2: B[1] }, { v: b.closed_loss, color: A[0], color2: A[1] }],
      { center: aP + "%", centerColor: "#3b82f6", sub: "WIN RATE" });
    const t = b.totals || {};
    $("#abChips").innerHTML = [
      ["Invested", fmtRs(t.still_invested), ""],
      ["Market value", t.market_value != null ? fmtRs(t.market_value) : "—", ""],
      ["Unrealized P&L", t.unrealized_pnl != null ? fmtRs(t.unrealized_pnl) : "—", cls(t.unrealized_pnl)],
      ["Realized P&L", fmtRs(t.realized_pnl), cls(t.realized_pnl)],
    ].map(([k, v, c]) => `<div class="ab-chip"><span>${k}</span><b class="${c}">${v}</b></div>`).join("");
    // progress since the previous time the system was opened
    const dlt = b.since_last; let prog;
    if (!dlt) {
      prog = `First visit — your book was imported from statement W615 (${b.book_trades} trades). This brief updates every time you open the system.`;
    } else {
      const parts = [];
      if (dlt.mv_chg != null) parts.push(`market value ${dlt.mv_chg >= 0 ? "+" : "−"}Rs ${Math.abs(dlt.mv_chg).toLocaleString()}`);
      if (dlt.upnl_chg != null) parts.push(`unrealized P&L ${dlt.upnl_chg >= 0 ? "+" : "−"}Rs ${Math.abs(dlt.upnl_chg).toLocaleString()}`);
      if (dlt.rpnl_chg != null && dlt.rpnl_chg !== 0) parts.push(`realized ${dlt.rpnl_chg >= 0 ? "+" : "−"}Rs ${Math.abs(dlt.rpnl_chg).toLocaleString()}`);
      if ((dlt.trades_added || 0) > 0) parts.push(`${dlt.trades_added} new trade${dlt.trades_added > 1 ? "s" : ""} recorded`);
      const when = String(dlt.at || "").replace("T", " ").slice(0, 16);
      prog = `📈 Since your last visit (${when}): ` + (parts.length ? parts.join(" · ") : "no change in value or trades.");
    }
    if ((b.top || []).length) prog += "  ·  Now: " + b.top.map(p =>
      `${p.symbol} ${p.unrealized_pct != null ? (p.unrealized_pct >= 0 ? "+" : "") + p.unrealized_pct + "%" : ""}`).join(", ");
    const lt = b.last_trade;
    if (lt) prog += `  ·  Last trade: ${lt.side.toUpperCase()} ${fmtN(lt.qty)} ${lt.symbol} @ ${fmtRs(lt.rate)} on ${lt.date}.`;
    $("#abProgress").textContent = prog;
  } catch (e) { /* brief optional */ }
}
on("abOpenTrading", "click", () => showView("paper"));

/* ── LANDING (Stalwart): brief · headline · quote · bento · trend · alerts · heatmap ── */
async function loadLanding() {
  try {
    const d = await GET("/api/landing");
    $("#ldMktStatus").textContent =
      ((d.market_status || "").toUpperCase() || "PSX") + " · " + ((d.pulse || {}).label || "").toUpperCase();
    paintBrief();   // real-account pies + progress since last visit
    $("#ldHeadline").textContent = d.headline || "";
    $("#ldQuote").textContent = "“" + (d.quote || {}).text + "”";
    $("#ldQuoteBy").textContent = "— " + (d.quote || {}).author;
    $("#ldQuoteLesson").textContent = "💡 " + ((d.quote || {}).lesson || "");
    // bento cards
    $("#bentoGrid").innerHTML = (d.metrics || []).map(m => {
      const tone = m.tone === "up" ? "tone-up" : m.tone === "down" ? "tone-down" : "";
      const spark = (m.spark || []).length ?
        `<canvas class="spark" id="spark_${m.id}"></canvas>` : "";
      const drv = (m.drivers || []).map(x =>
        `<div style="display:flex;justify-content:space-between;gap:8px"><span><b>${x.symbol}</b></span><span class="${cls(x.chg)}">${fmtPct(x.chg)}</span></div>`).join("");
      return `<div class="bcard" data-bc="${m.id}">
        <div class="k">${m.label}</div>
        <div class="v ${tone}">${m.value}</div>
        <div class="s">${m.sub || ""}</div>
        <div class="more">${spark}
          ${drv ? `<div class="drv-label">${m.driver_label || "Drivers"}</div><div class="drv">${drv}</div>` : ""}
        </div></div>`;
    }).join("");
    document.querySelectorAll(".bcard").forEach(b =>
      b.addEventListener("click", () => b.classList.toggle("open")));
    (d.metrics || []).forEach(m => {
      const cv = $("#spark_" + m.id);
      if (cv && (m.spark || []).length)
        drawSpark(cv, m.spark, m.tone === "down" ? "#FB7185" : "#818CF8");
    });
    // trend chart + label
    const t = d.trend || {};
    $("#trendLabel").textContent = t.label || "";
    if ((t.series || []).length) drawTrend($("#trendChart"), t.dates || [], t.series);
    // alerts feed
    $("#alertsList").innerHTML = (d.alerts || []).map(a => `
      <div class="alert-item">
        <a href="${a.link || "#"}" target="_blank" rel="noopener">${a.title || "(untitled)"}</a>
        <div class="meta"><span class="sym">${a.symbol || ""}</span> · ${a.kind || ""} · ${a.time || ""}</div>
      </div>`).join("") || `<p class="sub">No fresh alerts.</p>`;
    // sector heatmap data no longer needed on the landing page —
    // the Heatmap tab builds its own master-watchlist treemap
    S.heatmap = [];
  } catch (e) { /* landing is decorative — never block the dashboard */ }
}
/* ── 🔥 HEATMAP: master-watchlist treemap (size = mcap, colour = day change) ── */
let HM = { rows: [], at: null, mode: localStorage.psxHmMode || "d" };
const hmChg = r => HM.mode === "w" ? (r.chg5 != null ? r.chg5 : r.day_chg)
             : HM.mode === "m" ? (r.chg21 != null ? r.chg21 : r.day_chg) : r.day_chg;
function paintHmTabs() {
  document.querySelectorAll("#hmModeTabs button").forEach(b =>
    b.classList.toggle("active", b.dataset.hm === HM.mode));
}
on("hmModeTabs", "click", e => {
  const b = e.target.closest("button"); if (!b) return;
  HM.mode = b.dataset.hm; localStorage.psxHmMode = HM.mode;
  paintHmTabs(); renderHeatmap(); renderWheels();
});
const HM_UP = ["#252c33", "#17493a", "#11563f", "#0c6f4c", "#0a8a5c"];
const HM_DN = ["#252c33", "#4a262a", "#63232a", "#7f1f26", "#a11a22"];
const hmVal = r => r.mcap || HM.floor || 1;
function hmColor(chg) {
  const c = chg == null ? 0 : chg, a = Math.abs(c);
  const i = a < 0.15 ? 0 : a < 1 ? 1 : a < 2 ? 2 : a < 3.5 ? 3 : 4;
  return (c >= 0 ? HM_UP : HM_DN)[i];
}
function hmMcap(v) {
  if (v == null) return "—";
  if (v >= 1e12) return "Rs " + (v / 1e12).toFixed(2) + " T";
  if (v >= 1e9) return "Rs " + (v / 1e9).toFixed(1) + " B";
  if (v >= 1e6) return "Rs " + (v / 1e6).toFixed(1) + " M";
  return fmtRs(v);
}
async function loadHeatmap() {
  const m0 = $("#hmMeta");
  if (m0 && !HM.rows.length) m0.textContent = "fetching your master watchlist…";
  try {
    const d = await GET("/api/watchlist");               // master list, full snapshots
    HM.rows = (d.rows || []).filter(r => !r.error && r.snapshot);
    const caps = HM.rows.map(r => r.mcap).filter(v => v > 0).sort((a, b) => a - b);
    HM.floor = caps.length ? caps[Math.floor(caps.length / 2)] * 0.25 : 1;
    HM.at = new Date();
  } catch (e) { /* keep last good data */ }
  renderHeatmap(); loadWheels();
}
/* binary-split treemap layout: items [{v, o}] get o.r = {x,y,w,h} */
function layoutTM(items, x, y, w, h) {
  const sum = items.reduce((a, b) => a + b.v, 0);
  if (!sum || w <= 0 || h <= 0) return;
  const rec = (arr, x, y, w, h, sum) => {
    if (!arr.length) return;
    if (arr.length === 1) { arr[0].o.r = { x, y, w, h }; return; }
    let acc = 0, split = 1;
    for (let i = 0; i < arr.length; i++) { acc += arr[i].v; split = i + 1; if (acc >= sum / 2) break; }
    split = Math.max(1, Math.min(split, arr.length - 1));
    const A = arr.slice(0, split), B = arr.slice(split);
    const sa = A.reduce((p, q) => p + q.v, 0), sb = sum - sa;
    if (w >= h) { const wa = w * sa / sum; rec(A, x, y, wa, h, sa); rec(B, x + wa, y, w - wa, h, sb); }
    else { const ha = h * sa / sum; rec(A, x, y, w, ha, sa); rec(B, x, y + ha, w, h - ha, sb); }
  };
  rec(items.slice().sort((a, b) => b.v - a.v), x, y, w, h, sum);
}
function renderHeatmap() {
  const grid = $("#heatmapGrid"); if (!grid) return;
  const rows = HM.rows;
  if (!rows.length) {
    grid.innerHTML = `<div class="hm-sec" style="inset:0;display:flex;align-items:center;justify-content:center">Heatmap warming up — master watchlist data is loading…</div>`;
    return;
  }
  const W = grid.clientWidth, H = grid.clientHeight;
  const secs = {};
  rows.forEach(r => { const k = (r.sector || "Other").trim() || "Other"; (secs[k] = secs[k] || []).push(r); });
  const secList = Object.keys(secs).map(k => {
    const rs = secs[k].sort((a, b) => hmVal(b) - hmVal(a));
    const v = rs.reduce((a, r) => a + hmVal(r), 0);
    const chg = rs.reduce((a, r) => a + (hmChg(r) || 0) * hmVal(r), 0) / v;
    return { name: k, rows: rs, v, chg };
  }).sort((a, b) => b.v - a.v);
  layoutTM(secList.map(s => ({ v: s.v, o: s })), 0, 0, W, H);
  let html = "";
  secList.forEach(s => {
    const R = s.r; if (!R || R.w < 4 || R.h < 4) return;
    const headH = R.h > 84 ? 24 : 0;
    if (headH) html += `<div class="hm-sec" style="left:${R.x + 2}px;top:${R.y + 2}px;width:${R.w - 4}px">${s.name} › <b class="${cls(s.chg)}">${fmtPct(s.chg)}</b></div>`;
    layoutTM(s.rows.map(r => ({ v: hmVal(r), o: r })),
             R.x + 2, R.y + headH + 1, Math.max(R.w - 4, 1), Math.max(R.h - headH - 3, 1));
    s.rows.forEach(r => {
      const t = r.r; if (!t || t.w < 4 || t.h < 4) return;
      const big = t.w > 96 && t.h > 84, med = t.w > 52 && t.h > 42;
      const fs = Math.max(10, Math.min(26, Math.round(Math.min(t.w, t.h) / 4.4)));
      html += `<div class="hm-tile" data-s="${r.symbol}" style="left:${(t.x + 1).toFixed(1)}px;top:${(t.y + 1).toFixed(1)}px;width:${Math.max(t.w - 2, 2).toFixed(1)}px;height:${Math.max(t.h - 2, 2).toFixed(1)}px;background:${hmColor(hmChg(r))}" title="">
        ${big ? `<div class="hm-logo">${(r.name || r.symbol).replace(/[^A-Za-z]/g, "").slice(0, 1) || "•"}</div>` : ""}
        ${med ? `<div class="hm-sym" style="font-size:${fs}px">${r.symbol}</div>` : ""}
        ${med ? `<div class="hm-chg" style="font-size:${Math.max(9, fs - 4)}px">${fmtPct(hmChg(r))}</div>` : ""}
      </div>`;
    });
  });
  grid.innerHTML = html;
  grid.querySelectorAll(".hm-tile").forEach(el => {
    const r = HM.rows.find(x => x.symbol === el.dataset.s);
    el.addEventListener("click", () => openStock(el.dataset.s));
    el.addEventListener("mouseenter", e => hmShowTip(r, e));
    el.addEventListener("mousemove", e => hmMoveTip(e));
    el.addEventListener("mouseleave", hmHideTip);
  });
  const m = $("#hmMeta");
  paintHmTabs();
  const modeTxt = HM.mode === "w" ? "1 week" : HM.mode === "m" ? "1 month" : "today";
  if (m) m.innerHTML = `${rows.length} master stocks · ${secList.length} sectors · coloured by ${modeTxt} · updated ${HM.at ? fmtTs(HM.at.toISOString()) : "—"} PKT`
}
function hmShowTip(r, e) {
  const t = $("#hmTip"); if (!t || !r) return;
  const s = r.snapshot || {};
  const tr = [5, 10, 20, 50, 100, 200].map(L => s["above_ema" + L] == null
    ? `<span class="sub">·${L}</span>`
    : (s["above_ema" + L] ? `<span class="pos">▲${L}</span>` : `<span class="neg">▼${L}</span>`)).join(" ");
  const row = (k, v) => `<tr><td>${k}</td><td>${v}</td></tr>`;
  t.innerHTML = `
    <div class="tt-h"><b>${r.symbol}</b><span class="${cls(r.day_chg)}" style="font-weight:800">${fmtPct(r.day_chg)}</span></div>
    <div class="sub" style="margin:-2px 0 8px">${r.name || ""} · ${r.sector || ""}</div>
    <table>
      ${row("Price", fmtRs(s.close))}
      ${row("Today / 1W / 1M", `${fmtPct(r.day_chg)} · ${fmtPct(r.chg5)} · ${fmtPct(r.chg21)}`)}
      ${row("RSI (14)", s.rsi14 == null ? "—" : Number(s.rsi14).toFixed(0))}
      ${row("Trend 5–200 (EMA)", `<span style="font-size:11px">${tr}</span>`)}
      ${row("P/E", fmtN(r.pe))}
      ${row("Div yield", r.yield == null ? "—" : Number(r.yield).toFixed(1) + "%")}
      ${row("Market cap", hmMcap(r.mcap))}
      ${row("52-wk range", s.low_52w != null && s.high_52w != null ? fmtRs(s.low_52w) + " – " + fmtRs(s.high_52w) : "—")}
      ${row("Off 52-wk high", s.off_52w_high_pct == null ? "—" : Number(s.off_52w_high_pct).toFixed(1) + "%")}
      ${row("Volume vs avg", s.vol_ratio == null ? "—" : Number(s.vol_ratio).toFixed(1) + "×")}
      ${row("ATR (14)", s.atr_pct == null ? "—" : Number(s.atr_pct).toFixed(1) + "%")}
      ${row("Signal", pill(quickSignal(s)))}
    </table>
    <div class="sub" style="margin-top:7px">Click the tile → full research page</div>`;
  t.style.display = "block";
  hmMoveTip(e);
}
function hmMoveTip(e) {
  const t = $("#hmTip"); if (!t) return;
  const pad = 14, w = 310, h = t.offsetHeight || 280;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > innerWidth - 8) x = Math.max(8, e.clientX - w - pad);
  if (y + h > innerHeight - 8) y = Math.max(8, innerHeight - h - 8);
  t.style.left = x + "px"; t.style.top = y + "px";
}
function hmHideTip() { const t = $("#hmTip"); if (t) t.style.display = "none"; }
let hmRz = null;
window.addEventListener("resize", () => { clearTimeout(hmRz); hmRz = setTimeout(() => { renderHeatmap(); renderWheels(); }, 220); });

/* ──  INDEX WHEELS: KSE-100 + Master Watchlist sunbursts ─────────── */
let WH = { kse: null };
async function loadWheels() {
  const meta = $("#wheelsMeta");
  if (meta && !WH.kse) meta.textContent = "fetching live KSE-100 tape…";
  try { WH.kse = await GET("/api/heatmap/kse100"); } catch (e) { WH.kse = null; }
  renderWheels();
}
function renderWheels() {
  const meta = $("#wheelsMeta");
  // KSE-100 wheel
  if (WH.kse && WH.kse.rows && WH.kse.rows.length) {
    const rows = WH.kse.rows.map(r => ({ s: r.s, sec: r.sec, mcap: r.mcap, c: r.c,
      d: r.chg, w: r.w, vol: r.vol }));
    const idxChg = WH.kse.index ? WH.kse.index.chg : null;
    drawWheel("wheelKse", rows, "KSE 100", idxChg);
    if (meta) meta.textContent =
      `${WH.kse.count}/${WH.kse.total} constituents live · ${WH.kse.rows.length ? "source: TradingView tape" : ""} · ` +
      (WH.kse.index ? `index ${Number(WH.kse.index.close).toLocaleString("en-PK", { maximumFractionDigits: 0 })} (${fmtPct(idxChg)}) · ` : "") +
      `as of ${fmtTs(WH.kse.as_of)} PKT`;
  } else if (meta) meta.textContent = "KSE-100 tape unreachable right now.";
  // Master watchlist wheel
  const wl0 = (HM.rows || []).filter(r => r.snapshot).map(r => ({
    s: r.symbol, sec: r.sector, mcap: r.mcap, c: r.snapshot.close,
    d: r.day_chg, w: r.chg5 }));
  if (wl0.length) {
    const tot = wl0.reduce((a, r) => a + (r.mcap || 1), 0);
    const wchg = wl0.reduce((a, r) => a + (whChg(r) || 0) * (r.mcap || 1), 0) / tot;
    drawWheel("wheelWl", wl0, "MASTER", wchg);
  }
}
const whChg = r => HM.mode === "w" ? (r.w != null ? r.w : r.d) : r.d;
function drawWheel(id, rows, label, centerChg) {
  const cv = $(id ? "#" + id : id); if (!cv) return;
  const W = cv.clientWidth || 520, dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = W * dpr;
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, W);
  const cx = W / 2, cy = W / 2, R = W / 2 - 6;
  const r0 = R * 0.30, r1 = R * 0.62, r2 = R;
  const base = centerChg == null ? 0 : centerChg;   // colour = relative to index
  // group by sector
  const secs = {};
  rows.forEach(r => { const k = (r.sec || "Other").trim() || "Other"; (secs[k] = secs[k] || []).push(r); });
  const list = Object.keys(secs).map(k => {
    const rs = secs[k].sort((a, b) => (b.mcap || 1) - (a.mcap || 1));
    const v = rs.reduce((a, r) => a + (r.mcap || 1), 0);
    const chg = rs.reduce((a, r) => a + (whChg(r) || 0) * (r.mcap || 1), 0) / v;
    return { name: k, rows: rs, v, chg };
  }).sort((a, b) => b.v - a.v);
  const total = list.reduce((a, s) => a + s.v, 0);
  const geo = [];
  let a = -Math.PI / 2;
  const gap = 0.012;
  ctx.strokeStyle = "#07090b"; ctx.lineWidth = 1.4;
  list.forEach(sec => {
    const span = sec.v / total * Math.PI * 2;
    const a0 = a, a1 = a + span; a = a1;
    // inner ring: sector (coloured by relative strength vs index)
    ctx.beginPath();
    ctx.arc(cx, cy, r1 - 1.5, a0 + gap, a1 - gap);
    ctx.arc(cx, cy, r0, a1 - gap, a0 + gap, true);
    ctx.closePath();
    ctx.fillStyle = hmColor((sec.chg || 0) - base); ctx.fill(); ctx.stroke();
    // sector label (curved) when there is room, else a straight tick label
    if (span > 0.16) arcText(ctx, sec.name.toUpperCase().slice(0, 24), cx, cy, (r0 + r1) / 2, a0, a1,
      "rgba(255,255,255,.94)", Math.max(9, Math.min(13, span * R * 0.10)));
    // outer ring: stocks
    let sa = a0;
    sec.rows.forEach(r => {
      const sspan = (r.mcap || 1) / sec.v * span;
      const s0 = sa, s1 = sa + sspan; sa = s1;
      ctx.beginPath();
      ctx.arc(cx, cy, r2, s0 + gap * 0.6, s1 - gap * 0.6);
      ctx.arc(cx, cy, r1 + 1.5, s1 - gap * 0.6, s0 + gap * 0.6, true);
      ctx.closePath();
      ctx.fillStyle = hmColor((whChg(r) || 0) - base); ctx.fill(); ctx.stroke();
      geo.push({ a0: s0, a1: s1, row: r });
      const deg = sspan * 180 / Math.PI;
      if (deg > 3.2) radialText(ctx, r.s, cx, cy, r1 + 8, (s0 + s1) / 2,
        "rgba(255,255,255,.95)", Math.max(8.5, Math.min(13, deg * 1.1)));
    });
  });
  // hub
  ctx.beginPath(); ctx.arc(cx, cy, r0 - 2, 0, Math.PI * 2);
  ctx.fillStyle = "#0b0e11"; ctx.fill();
  ctx.strokeStyle = "#1d232b"; ctx.lineWidth = 1; ctx.stroke();
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillStyle = "#e8eef4"; ctx.font = "800 " + Math.max(13, R * 0.11) + "px system-ui";
  ctx.fillText(label, cx, cy - R * 0.055);
  ctx.fillStyle = centerChg == null ? "#8b98a5" : centerChg >= 0 ? "#26a69a" : "#ef5350";
  ctx.font = "800 " + Math.max(12, R * 0.10) + "px system-ui";
  ctx.fillText(centerChg == null ? "—" : fmtPct(centerChg), cx, cy + R * 0.075);
  cv._geo = { geo, cx, cy, r0, r1, r2 };
  cv.onmousemove = e => {
    const rc = cv.getBoundingClientRect();
    const x = e.clientX - rc.left - cx, y = e.clientY - rc.top - cy;
    const rad = Math.hypot(x, y);
    let ang = Math.atan2(y, x);
    while (ang < -Math.PI / 2) ang += Math.PI * 2;
    const hit = rad > r1 && rad < r2 && cv._geo.geo.find(g => ang >= g.a0 && ang <= g.a1);
    cv.style.cursor = hit ? "pointer" : "default";
    if (hit) {
      const r = hit.row, t = $("#hmTip");
      const inMaster = (HM.rows || []).some(x => x.symbol === r.s);
      t.innerHTML = `
        <div class="tt-h"><b>${r.s}</b><span class="${cls(whChg(r))}" style="font-weight:800">${fmtPct(whChg(r))}</span></div>
        <div class="sub" style="margin:-2px 0 8px">${r.sec || ""}</div>
        <table>
          <tr><td>Price</td><td>${fmtRs(r.c)}</td></tr>
          <tr><td>Today / 1W</td><td>${fmtPct(r.d)} · ${fmtPct(r.w)}</td></tr>
          <tr><td>Market cap</td><td>${hmMcap(r.mcap)}</td></tr>
          ${r.vol != null ? `<tr><td>Volume</td><td>${Number(r.vol).toLocaleString()}</td></tr>` : ""}
        </table>
        <div class="sub" style="margin-top:7px">${inMaster ? "Click → full research page" : "KSE-100 constituent"}</div>`;
      t.style.display = "block"; hmMoveTip(e);
    } else hmHideTip();
  };
  cv.onmouseleave = hmHideTip;
  cv.onclick = e => {
    const rc = cv.getBoundingClientRect();
    const x = e.clientX - rc.left - cx, y = e.clientY - rc.top - cy;
    const rad = Math.hypot(x, y);
    let ang = Math.atan2(y, x);
    while (ang < -Math.PI / 2) ang += Math.PI * 2;
    const hit = rad > r1 && rad < r2 && cv._geo.geo.find(g => ang >= g.a0 && ang <= g.a1);
    if (hit && (HM.rows || []).some(rr => rr.symbol === hit.row.s)) { hmHideTip(); openStock(hit.row.s); }
  };
}
function arcText(ctx, text, cx, cy, radius, a0, a1, color, size) {
  const mid = (a0 + a1) / 2;
  const flip = mid > 0 && mid < Math.PI;  // bottom half → flip for readability
  ctx.save(); ctx.translate(cx, cy);
  ctx.fillStyle = color; ctx.font = `700 ${size}px system-ui, sans-serif`;
  const widths = [...text].map(ch => ctx.measureText(ch).width);
  const tot = widths.reduce((p, q) => p + q, 0);
  let ang = mid - tot / 2 / radius;
  [...text].forEach((ch, i) => {
    const step = widths[i] / radius;
    ctx.save();
    ctx.rotate(ang + step / 2 + (flip ? Math.PI : 0));
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(ch, 0, flip ? radius : -radius);
    ctx.restore();
    ang += step;
  });
  ctx.restore();
}
function radialText(ctx, text, cx, cy, radius, angle, color, size) {
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(angle);
  const flip = angle > Math.PI / 2 && angle < Math.PI * 1.5;
  if (flip) ctx.rotate(Math.PI);
  ctx.fillStyle = color; ctx.font = `800 ${size}px system-ui, sans-serif`;
  ctx.textAlign = flip ? "right" : "left"; ctx.textBaseline = "middle";
  ctx.fillText(text, flip ? -radius - 4 : radius + 4, 0);
  ctx.restore();
}
/* ── ⚡ TODAY'S SWING SETUPS (master list, best first) ── */
async function loadSetups() {
  const box = $("#wlSetups"); if (!box) return;
  try {
    const d = await GET("/api/watchlist");
    const hits = [];
    for (const r of (d.rows || [])) {
      const s = r.snapshot; if (!s) continue;
      let pts = 0; const why = [];
      if (s.breakout_20d) { pts += 2; why.push("20-day breakout"); }
      if (s.sma20_cross_up) { pts += 2; why.push("crossed SMA-20"); }
      if (s.sma50_cross_up) { pts += 2; why.push("crossed SMA-50"); }
      if (s.macd_cross_up) { pts += 2; why.push("MACD turned up"); }
      if (s.golden_cross) { pts += 2; why.push("golden cross"); }
      if (s.macd_bull) { pts += 1; why.push("MACD bullish"); }
      if (s.rsi14 != null && s.rsi14 < 30) { pts += 1; why.push("RSI oversold"); }
      else if (s.rsi14 != null && s.rsi14 >= 45 && s.rsi14 <= 65) { pts += 1; why.push("RSI in rising zone"); }
      if (s.above_sma200) pts += 1;
      if ((s.vol_ratio || 0) >= 1.5) { pts += 1; why.push("volume " + Number(s.vol_ratio).toFixed(1) + "×"); }
      if (pts >= 4) hits.push({ r, pts, why });
    }
    hits.sort((a, b) => b.pts - a.pts);
    box.innerHTML = hits.length ? hits.slice(0, 8).map(h => `
      <div class="setupRow" data-s="${h.r.symbol}" style="display:flex;gap:8px;align-items:center;margin:6px 0;cursor:pointer">
        <span class="pill ${h.pts >= 6 ? "p-buy" : "p-hold"}" style="min-width:58px;text-align:center">${h.pts} pts</span>
        <b>${h.r.symbol}</b><span class="sub">${h.why.slice(0, 3).join(" · ")}</span>
      </div>`).join("")
      : `<p class="sub">No swing setups right now — patience is also a position ✅</p>`;
    box.querySelectorAll(".setupRow").forEach(el => el.onclick = () => openStock(el.dataset.s));
  } catch (e) { box.innerHTML = `<p class="sub">Setup scan unavailable.</p>`; }
}

/* ──  CONDITION ALERTS on the master list (checked with the bell poll) ── */
const CA_RULES = [
  { id: "rsi30", label: "RSI falls below 30 (oversold)", test: (r, s) => s.rsi14 != null && s.rsi14 < 30 },
  { id: "rsi70", label: "RSI climbs above 70 (overbought)", test: (r, s) => s.rsi14 != null && s.rsi14 > 70 },
  { id: "sma20", label: "Crosses ABOVE the 20-day average", test: (r, s) => !!s.sma20_cross_up },
  { id: "sma50", label: "Crosses ABOVE the 50-day average", test: (r, s) => !!s.sma50_cross_up },
  { id: "brk20", label: "20-day breakout (new high)", test: (r, s) => !!s.breakout_20d },
  { id: "vol2", label: "Volume 2× the 20-day average", test: (r, s) => (s.vol_ratio || 0) >= 2 },
];
let CA_ON = JSON.parse(localStorage.psxCA || "null") || Object.fromEntries(CA_RULES.map(r => [r.id, true]));
let CA_LAST = null;
function paintCaRules() {
  const box = $("#caRules"); if (!box) return;
  box.innerHTML = CA_RULES.map(ru => `
    <label style="display:flex;gap:8px;align-items:center;font-size:12.5px;cursor:pointer">
      <input type="checkbox" data-ca="${ru.id}" ${CA_ON[ru.id] ? "checked" : ""}> ${ru.label}</label>`).join("");
  box.querySelectorAll("input[data-ca]").forEach(c => c.onchange = () => {
    CA_ON[c.dataset.ca] = c.checked; localStorage.psxCA = JSON.stringify(CA_ON); paintCaLast();
  });
}
function paintCaLast() {
  const el = $("#caLast"); if (!el) return;
  el.textContent = CA_LAST
    ? `Last scan ${CA_LAST.toLocaleTimeString()} · ${CA_RULES.filter(r => CA_ON[r.id]).length} rules active`
    : "";
}
async function caScan(items) {
  try {
    const wd = await GET("/api/watchlist");
    const today = new Date().toISOString().slice(0, 10);
    for (const r of (wd.rows || [])) {
      const s = r.snapshot; if (!s) continue;
      for (const ru of CA_RULES) {
        if (!CA_ON[ru.id] || !ru.test(r, s)) continue;
        items.push({ id: `c:${ru.id}:${r.symbol}:${today}`, type: "⚡ Alert",
          title: `${r.symbol} — ${ru.label}`,
          sub: `price ${s.close != null ? fmtRs(s.close) : ""} · RSI ${s.rsi14 != null ? Number(s.rsi14).toFixed(0) : "—"}` });
      }
    }
    CA_LAST = new Date(); paintCaLast();
  } catch (e) { /* alerts optional */ }
}
paintCaRules();

/* ── 🤖 MORNING BRIEF ── */
on("mbBtn", "click", async () => {
  const btn = $("#mbBtn"); btn.disabled = true; btn.textContent = "🤖 Writing your brief…";
  try {
    const d = await POST("/api/ai/brief", { force: true });
    $("#mbCard").style.display = "";
    $("#mbWhen").textContent = d.ai ? "· written by your AI engine"
      : "· rule-based" + (d.note ? " (AI note: " + d.note + ")" : " (switch AI on in Settings for a written brief)");
    $("#mbBody").textContent = d.text || "";
    btn.textContent = "🤖 Refresh morning brief";
  } catch (e) { toast("Brief failed: " + e.message); }
  btn.disabled = false;
});

/* ──  OPEN SWINGS handlers ─ */
on("mnOAdd", "click", async () => {
  const sym = ($("#mnOSym").value || "").trim().toUpperCase();
  if (!sym) { toast("Type the stock symbol first"); return; }
  const r = await POST("/api/money/open", { symbol: sym, qty: +$("#mnOQty").value,
    entry: +$("#mnOEntry").value, stop: +$("#mnOStop").value || 0,
    target: +$("#mnOTarg").value || 0, entry_date: $("#mnODate").value || null });
  if (!r.ok) { toast("Could not add: " + r.error); return; }
  toast("Open swing added: " + sym);
  $("#mnOQty").value = ""; $("#mnOEntry").value = ""; $("#mnOStop").value = ""; $("#mnOTarg").value = "";
  MN = r.state; loadMoney();
});
document.addEventListener("click", async e => {
  const c = e.target.closest(".mnOClose");
  const d2 = e.target.closest(".mnODel");
  if (c) {
    const o = (MN.opens || []).find(x => x.id === c.dataset.id); if (!o) return;
    const ex = prompt(`Close ${o.symbol} at what exit price?`, o.last != null ? o.last : o.entry);
    if (ex === null || ex === "" || isNaN(+ex)) return;
    const r = await POST("/api/money/open/" + c.dataset.id + "/close", { exit: +ex, exit_date: MN.today });
    if (r.ok) { toast("Closed & logged: " + fmtRs(r.trade.pnl)); MN = r.state; loadMoney(); }
    else toast("❌ " + r.error);
  } else if (d2) {
    if (!confirm("Remove this open swing WITHOUT logging it to the journal?")) return;
    const r = await fetch("/api/money/open/" + d2.dataset.id, { method: "DELETE" });
    const d = await r.json(); if (d.ok) { MN = d.state; loadMoney(); }
  }
});

function initReveal() {
  if (!("IntersectionObserver" in window)) {
    document.querySelectorAll(".reveal").forEach(x => x.classList.add("in")); return;
  }
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { threshold: 0.08 });
  document.querySelectorAll(".reveal").forEach(x => io.observe(x));
}
function paintAiBadge(cfg) {
  const b = $("#aiBadge"), t = $("#aiBadgeTxt");
  if (!b || !t) return;
  const llm = (cfg && cfg.llm) || {}, ol = (cfg && cfg.ollama) || {};
  const prov = String(llm.provider || "ollama");
  const key = String(((llm[prov] || {}).api_key) || "").trim();
  const hasKey = !!key && key !== "''" && key !== "—";
  const on = !!ol.enabled;
  const ready = on && (prov === "ollama" ? !!String(ol.model || "").trim() : hasKey);
  b.classList.toggle("ready", ready);
  t.textContent = !on ? "AI ENGINE · OFF"
    : ready ? "AI ENGINE · READY"
    : prov === "ollama" ? "AI ENGINE · SET A MODEL"
    : "AI ENGINE · MANUAL KEY";
}

/* ── COMPARE: up to 5 stocks side by side, A to Z ── */
S.cmp = [];
const CMP_COLORS = ["#818CF8", "#10B981", "#F59E0B", "#FB7185", "#9CA3AF"];
function cmpChips() {
  $("#cmpChips").innerHTML = S.cmp.map((s, i) =>
    `<span class="pill p-hold" style="margin:2px 4px 2px 0;cursor:pointer" data-cmpx="${s}" title="Remove ${s}">${s} ✕</span>`).join("");
  $("#cmpMeta").textContent = S.cmp.length ? `${S.cmp.length} selected — press Compare A-to-Z.` : "Pick up to 5 stocks, then press Compare A-to-Z.";
}
function cmpAdd(sym) {
  sym = String(sym || "").trim().toUpperCase();
  if (!sym) return;
  if (S.cmp.includes(sym)) { toast(sym + " is already in the list"); return; }
  if (S.cmp.length >= 5) { toast("Maximum 5 stocks — remove one first"); return; }
  S.cmp.push(sym); $("#cmpSym").value = ""; $("#cmpSuggest").style.display = "none"; cmpChips();
}
on("cmpAdd", "click", () => cmpAdd($("#cmpSym").value));
on("cmpClear", "click", () => { S.cmp = []; cmpChips(); $("#cmpOut").innerHTML = ""; $("#cmpChartCard").style.display = "none"; });
$("#cmpChips").addEventListener("click", e => {
  const x = e.target.closest("[data-cmpx]"); if (!x) return;
  S.cmp = S.cmp.filter(s => s !== x.dataset.cmpx); cmpChips();
});
$("#cmpSym").addEventListener("keydown", e => { if (e.key === "Enter") cmpAdd($("#cmpSym").value); });
$("#cmpSym").addEventListener("input", () => {
  const q = $("#cmpSym").value.trim().toUpperCase(), sug = $("#cmpSuggest");
  if (q.length < 1) { sug.style.display = "none"; return; }
  const hits = (S.universe || []).filter(u => u.symbol.includes(q)).slice(0, 8);
  sug.innerHTML = hits.map(h => `<div data-s="${h.symbol}"><b>${h.symbol}</b> · ${fmtRs(h.price)} <span class="${cls(h.chg)}">${fmtPct(h.chg)}</span></div>`).join("") || `<div>No match in ALLSHR</div>`;
  sug.style.display = "block";
});
$("#cmpSuggest").addEventListener("click", e => { const d = e.target.closest("[data-s]"); if (d) cmpAdd(d.dataset.s); });
document.addEventListener("click", e => { if (!e.target.closest("#cmpSym") && !e.target.closest("#cmpSuggest")) $("#cmpSuggest").style.display = "none"; });

function _cmpCell(v, fmt) {
  if (v == null || v === "" || (typeof v === "number" && isNaN(v))) return '<span class="sub">—</span>';
  return fmt ? fmt(v) : String(v);
}
async function cmpRun() {
  if (!S.cmp.length) { toast("Add at least one stock first"); return; }
  const out = $("#cmpOut");
  out.innerHTML = `<div class="card"><p class="sub">Comparing ${S.cmp.join(", ")}… fetching everything A-to-Z (faster on second run — data is cached).</p></div>`;
  $("#cmpChartCard").style.display = "none";
  try {
    const d = await GET("/api/compare?symbols=" + S.cmp.join(","));
    const st = d.stocks || [];
    if (!st.length) { out.innerHTML = `<div class="card">No data.</div>`; return; }
    const head = `<tr><th style="min-width:190px">Metric (A-to-Z)</th>${st.map((s, i) =>
      `<th style="color:${CMP_COLORS[i % 5]}">${s.symbol}</th>`).join("")}</tr>`;
    const F = st.map(s => s.fund || {}), T = st.map(s => s.tech || {});
    const row = (label, fn) => `<tr><td><b>${label}</b></td>${st.map((s, i) =>
      `<td>${fn(F[i], T[i], s, i)}</td>`).join("")}</tr>`;
    const sec = t => `<tr><td colspan="${st.length + 1}" style="background:var(--accent-soft);font-weight:700">${t}</td></tr>`;
    const pct = v => `<span class="${cls(v)}">${fmtPct(v)}</span>`;
    const above = (v) => v == null ? '<span class="sub">—</span>' : (v ? '<span class="pos">▲ above</span>' : '<span class="neg">▼ below</span>');
    const pctF = v => { try { const x = Number(v); return _cmpCell(Math.abs(x) <= 3 ? (x * 100).toFixed(1) + "%" : x.toFixed(1) + "%"); } catch (e) { return _cmpCell(v); } };
    let html = `<div class="card"><div style="overflow-x:auto"><table>${head}`;
    const SE = st.map(s => s.session || {});
    const RS = st.map(s => s.price_cagr != null ? s.price_cagr : null);
    html += sec("MARKET") +
      row("Company name", f => _cmpCell(f.name)) +
      row("Sector", f => _cmpCell(f.sector)) +
      row("Price", f => _cmpCell(f.price, fmtRs)) +
      row("Day change", f => _cmpCell(f.change_pct, v => pct(v))) +
      row("Today — open / high / low", (f, t, s, i) => _cmpCell(SE[i] && SE[i].open != null ?
        `${fmtRs(SE[i].open)} / ${fmtRs(SE[i].high)} / ${fmtRs(SE[i].low)}` : null)) +
      row("Volume today", (f, t, s, i) => _cmpCell(SE[i] && SE[i].volume ? SE[i].volume : null, niceNum)) +
      row("Who is winning today", (f, t, s, i) => SE[i] && SE[i].direction ?
        (SE[i].direction.indexOf("Buyers") === 0 ? '<span class="pos">Buyers ▲</span>' : '<span class="neg">Sellers ▼</span>') : _cmpCell(null)) +
      row("Market cap", f => _cmpCell(f.market_cap, v => "Rs " + fmtMcap(v) + " bn")) +
      row("Avg volume (30d)", f => _cmpCell(f.avg_vol_30d, niceNum)) +
      row("Index membership", f => _cmpCell(f.indices)) +
      row("Last official filing", (f, t, s) => _cmpCell(s.last_filing));
    html += sec("PERFORMANCE") +
      row("1 month", f => _cmpCell(f.perf_1m, pct)) +
      row("3 months", f => _cmpCell(f.perf_3m, pct)) +
      row("6 months", f => _cmpCell(f.perf_6m, pct)) +
      row("1 year", f => _cmpCell(f.perf_1y, pct)) +
      row("Price CAGR (full history)", (f, t, s, i) => _cmpCell(RS[i], pct)) +
      row("52-week high / low", f => _cmpCell(f.high_52w != null ? `${fmtRs(f.high_52w)} / ${fmtRs(f.low_52w)}` : null)) +
      row("Position in 52-week range", f => _cmpCell(f.wk52_pos, v => Number(v).toFixed(0) + "% of range")) +
      row("Off 52-week high", f => _cmpCell(f.off_high_pct, pct));
    html += sec("FY FINANCIAL SNAPSHOT (latest annual)") +
      row("Total revenue", f => _cmpCell(f.revenue, v => "Rs " + (Number(v) / 1e9).toFixed(1) + " bn")) +
      row("Net profit", f => _cmpCell(f.net_income, v => "Rs " + (Number(v) / 1e9).toFixed(1) + " bn")) +
      row("Revenue growth YoY", f => _cmpCell(f.revenue_growth_y, pct)) +
      row("Net profit growth YoY", f => _cmpCell(f.net_income_growth, pct)) +
      row("EPS growth YoY", f => _cmpCell(f.eps_growth, pct)) +
      row("Total assets", f => _cmpCell(f.total_assets, v => "Rs " + (Number(v) / 1e9).toFixed(0) + " bn")) +
      row("Total equity", f => _cmpCell(f.total_equity, v => "Rs " + (Number(v) / 1e9).toFixed(0) + " bn")) +
      row("Total liabilities", f => _cmpCell(f.total_liabilities, v => "Rs " + (Number(v) / 1e9).toFixed(0) + " bn")) +
      row("Total debt", f => _cmpCell(f.total_debt, v => "Rs " + (Number(v) / 1e9).toFixed(1) + " bn"));
    html += sec("VALUATION") +
      row("P/E (trailing)", f => _cmpCell(f.pe_ratio, fmtN)) +
      row("P/E (forward)", f => _cmpCell(f.forward_pe, fmtN)) +
      row("Price / book", f => _cmpCell(f.price_to_book, fmtN)) +
      row("Dividend yield", f => _cmpCell(f.dividend_yield == null ? null : Number(f.dividend_yield).toFixed(2) + "%")) +
      row("Payout ratio", f => _cmpCell(f.payout_ratio == null ? null : f.payout_ratio + "%")) +
      row("EPS (ttm)", f => _cmpCell(f.eps, v => "Rs " + fmtN(v)));
    html += sec("PROFITABILITY & FINANCIAL HEALTH") +
      row("ROE", f => _cmpCell(f.roe, pctF)) +
      row("ROA", f => _cmpCell(f.roa, pctF)) +
      row("Net profit margin", f => _cmpCell(f.profit_margin, pctF)) +
      row("Debt / equity", f => _cmpCell(f.debt_equity, fmtN)) +
      row("Current ratio", f => _cmpCell(f.current_ratio, fmtN)) +
      row("Free cash flow", f => _cmpCell(f.free_cashflow, v => "Rs " + (Number(v) / 1e9).toFixed(1) + " bn")) +
      row("Book value / share", f => _cmpCell(f.book_value, v => "Rs " + fmtN(v))) +
      row("Beta", f => _cmpCell(f.beta, fmtN));
    html += sec("TECHNICALS") +
      row("RSI (14)", (f, t) => _cmpCell(t.rsi14, v => Number(v).toFixed(0))) +
      row("vs 20-day average", (f, t) => above(t.close != null && t.sma20 != null ? t.close >= t.sma20 : null)) +
      row("vs 50-day average", (f, t) => above(t.above_sma50)) +
      row("vs 200-day average", (f, t) => above(t.above_sma200)) +
      row("MACD", (f, t) => t.macd_bull == null ? '<span class="sub">—</span>' : (t.macd_bull ? '<span class="pos">bullish</span>' : '<span class="neg">bearish</span>')) +
      row("ATR (daily swing)", (f, t) => _cmpCell(t.atr_pct, v => Number(v).toFixed(1) + "%")) +
      row("Volume vs average", (f, t) => _cmpCell(t.vol_ratio, v => Number(v).toFixed(2) + "×")) +
      row("20-day breakout", (f, t) => t.breakout_20d ? '<span class="pos">Breakout ▲</span>' : (t.breakdown_20d ? '<span class="neg">Breakdown ▼</span>' : "Inside range"));
    html += `</table></div>
      <p class="sub" style="margin-top:8px">Sources: DPS snapshot + EOD history (psxdata) · Yahoo Finance ratios · financials.psx.com.pk filings. Cached ~1h for speed.</p></div>`;
    out.innerHTML = html;
    const pdfBtn = $("#cmpPdf"); pdfBtn.href = "/api/compare.pdf?symbols=" + S.cmp.join(","); pdfBtn.style.display = "";
    // performance chart
    const series = st.map((s, i) => ({ name: s.symbol, color: CMP_COLORS[i % 5],
      pts: (s.perf12m || []).map(p => ({ x: p.d, y: p.v })) })).filter(s => s.pts.length > 5);
    if (series.length) { $("#cmpChartCard").style.display = ""; drawMultiLine($("#cmpChart"), series); }
  } catch (e) { out.innerHTML = `<div class="card">Compare failed: ${e.message}</div>`; }
}
on("cmpGo", "click", cmpRun);

/* ── 🔔 NOTIFICATION SOUND: soft two-note chime, made with Web Audio (no file) ── */
let SND = { ctx: null, muted: localStorage.psxSndMuted === "1" };
function sndCtx() {
  try {
    if (!SND.ctx) SND.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (SND.ctx.state === "suspended") SND.ctx.resume();
    return SND.ctx;
  } catch (e) { return null; }
}
/* browsers only allow sound after the user interacted once — unlock then */
["click", "keydown"].forEach(ev =>
  document.addEventListener(ev, function unlock() { sndCtx(); document.removeEventListener(ev, unlock); }, { once: true, capture: true }));
function playChime() {
  if (SND.muted) return;
  const ctx = sndCtx(); if (!ctx || ctx.state !== "running") return;
  const t = ctx.currentTime;
  [[880, 0, .20], [1174.7, .16, .26]].forEach(([freq, off, vol]) => {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine"; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t + off);
    g.gain.exponentialRampToValueAtTime(vol, t + off + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + off + 0.9);
    o.connect(g); g.connect(ctx.destination);
    o.start(t + off); o.stop(t + off + 0.95);
  });
}
function sndPaint() {
  const b = $("#sndBtn"); if (!b) return;
  b.textContent = SND.muted ? "🔇" : "🔊";
  b.classList.toggle("muted", SND.muted);
  b.title = SND.muted ? "Notification sound is OFF — click to unmute"
                      : "Notification sound is ON — click to mute";
}
/* ── 🔔 NOTIFICATIONS: bell + pop-ups for new news & announcements ── */
const BELL = { unread: JSON.parse(localStorage.psxUnread || "[]"),
                seen: JSON.parse(localStorage.psxSeenNews || "{}"),
                seeded: !!localStorage.psxBellSeeded, timer: null };
function bellSave() {
  localStorage.psxUnread = JSON.stringify(BELL.unread.slice(0, 200));
  localStorage.psxSeenNews = JSON.stringify(BELL.seen);
}
function bellBadge() {
  const b = $("#bellCount"); if (!b) return;
  b.textContent = BELL.unread.length;
  b.style.display = BELL.unread.length ? "" : "none";
}
function bellRender() {
  bellBadge();
  const list = $("#bellList"); if (!list) return;
  if (!BELL.unread.length) { list.innerHTML = '<p class="sub" style="padding:6px">All caught up — new news, PSX announcements and company reports will appear here.</p>'; return; }
  list.innerHTML = BELL.unread.map((n, i) => `
    <div class="bell-item">
      <div class="bt">${n.title}</div>
      <div class="bm">${n.type} · ${n.sub || ""}</div>
      <div class="ba">
        <button class="btn ghost" data-read="${i}" style="font-size:11px">✓ I have read it</button>
        ${n.url ? `<a class="btn ghost" href="${n.url}" target="_blank" rel="noopener" style="font-size:11px">Open ↗</a>` : ""}
      </div>
    </div>`).join("");
}
function bellMarkRead(i) { BELL.unread.splice(i, 1); bellSave(); bellRender(); }
function newsPop(n) {
  const old = document.querySelector(".news-pop"); if (old) old.remove();
  const d = document.createElement("div");
  d.className = "news-pop";
  d.innerHTML = `<div class="np-t">${n.title}</div>
    <div class="np-s">${n.type} · ${n.sub || ""}${BELL.unread.length > 1 ? " · +" + (BELL.unread.length - 1) + " more in 🔔" : ""}</div>
    <div class="np-a">
      <button class="btn ghost" id="npRead" style="font-size:11.5px">✓ I have read it</button>
      ${n.url ? `<a class="btn ghost" href="${n.url}" target="_blank" rel="noopener" style="font-size:11.5px">Open ↗</a>` : ""}
      <button class="btn ghost" id="npClose" style="font-size:11.5px">Close</button>
    </div>`;
  document.body.appendChild(d);
  d.querySelector("#npRead").addEventListener("click", () => {
    const i = BELL.unread.findIndex(u => u.id === n.id);
    if (i >= 0) bellMarkRead(i);
    d.remove();
  });
  d.querySelector("#npClose").addEventListener("click", () => d.remove());
  setTimeout(() => d.remove(), 20000);
}
async function bellPoll() {
  try {
    const [nw, an] = await Promise.all([GET("/api/news?limit=40"), GET("/api/announcements?limit=40")]);
    const items = [];
    (nw.items || []).forEach(i => items.push({ id: "n:" + i.link, type: "📰 Market News",
      title: i.title, sub: (i.source || "") + " · " + (i.published || ""), url: i.link }));
    (an.items || []).forEach(i => items.push({ id: "a:" + (i.link || i.title + i.when),
      type: "📢 " + (i.category || "PSX Announcement"), title: i.title,
      sub: (i.symbol || "") + " · " + (i.when || ""), url: i.link || i.pdf }));
    caScan(items);
    const fresh = items.filter(i => !BELL.seen[i.id]);
    if (!fresh.length) return;
    fresh.forEach(i => BELL.seen[i.id] = 1);
    if (!BELL.seeded) {           // first visit: learn what exists, stay quiet
      BELL.seeded = true; localStorage.psxBellSeeded = "1"; bellSave(); return;
    }
    fresh.forEach(i => BELL.unread.unshift(i));
    bellSave(); bellRender();
    /* 🔔 ring the bell + pop the badge + play the chime — unmissable */
    playChime();
    const bb = $("#bellBtn");
    if (bb) { bb.classList.remove("ring"); void bb.offsetWidth; bb.classList.add("ring");
      setTimeout(() => bb.classList.remove("ring"), 3600); }
    const bg = $("#bellCount");
    if (bg) { bg.classList.remove("pop"); void bg.offsetWidth; bg.classList.add("pop"); }
    const latest = fresh[0];
    newsPop(latest);
    try {
      if ("Notification" in window && Notification.permission === "granted")
        new Notification("PSX Live & Research — " + latest.type.replace(/^[^ ]+ /, ""),
          { body: latest.title });
    } catch (e) { /* notifications optional */ }
  } catch (e) { /* feeds down — silent */ }
}
on("bellBtn", "click", () => {
  const drop = $("#bellDrop");
  drop.style.display = drop.style.display === "none" ? "" : "none";
  bellRender();
  try { if ("Notification" in window && Notification.permission === "default")
    Notification.requestPermission(); } catch (e) {}
});
document.addEventListener("click", e => {
  document.querySelectorAll(".bell-wrap").forEach(w => {
    if (!w.contains(e.target)) {
      const d = w.querySelector(".bell-drop");
      if (d) d.style.display = "none";
    }
  });
});
/* 🩺 System Check — find out why data is missing on a given PC */
$("#bellList").addEventListener("click", e => {
  const b = e.target.closest("[data-read]"); if (!b) return;
  bellMarkRead(+b.dataset.read);
});
on("bellAllRead", "click", () => { BELL.unread = []; bellSave(); bellRender(); });
/* 🔊 mute / unmute the notification chime (saved on this browser) */
on("sndBtn", "click", () => {
  SND.muted = !SND.muted;
  localStorage.psxSndMuted = SND.muted ? "1" : "0";
  sndPaint();
  if (!SND.muted) playChime();   // short test note so you hear it works
});
sndPaint();

(async function init() {
  const today = new Date().toISOString().slice(0, 10);
  $("#btEnd").value = today;
  try {
    const s = await GET("/api/settings");
    S.cfg = s.config;
    paintAiBadge(S.cfg);
    const ui = S.cfg.ui || {}, st = S.cfg.settings || {};
    const mem0 = memLoad();
    S.sym = (mem0.sym || ui.default_stock || "OGDC").toUpperCase();
    $("#btSym").value = S.sym; $("#poSym").value = S.sym;
    if (st.paper_cash) $("#btCap").value = st.paper_cash;
  } catch (e) { /* defaults stand */ }
  paintBtCosts();
  try {
    const u = await GET("/api/universe");
    S.universe = u.symbols;
    $("#symList").innerHTML = u.symbols.map(s => `<option value="${s.symbol}">`).join("");
  } catch (e) { /* search degraded */ }
  try {
    const w = await GET("/api/watchlist-meta");
    S.watchMeta = w.watchlist;
  } catch (e) { /* ignore */ }
  loadPresets(); loadPulse(); loadWatch(); loadStrats(); loadSigStatus(); fillRepSyms();
  loadLanding(); loadNews(); initReveal();
  setupAutoRefresh();
  /* FIRST REFRESH: instantly pull current PSX data + prices, then repaint live */
  POST("/api/refresh", { full: false }).then(() => {
    loadPulse(); loadWatch(); loadLanding();
  }).catch(() => { /* network hiccup — cached data stays on screen */ });
  // restore remembered session (view immediately; forms once dropdowns are filled)
  const mem = memLoad();
  setTimeout(() => {
    if (mem.repSym) { const sel = $("#repSym");
      if (sel && [...sel.options].some(o => o.value === mem.repSym)) sel.value = mem.repSym; }
    if (mem.bt) {
      if (mem.bt.sym) $("#btSym").value = mem.bt.sym;
      const st = $("#btStrat");
      if (mem.bt.strat && st && [...st.options].some(o => o.value === mem.bt.strat)) st.value = mem.bt.strat;
      if (mem.bt.start) $("#btStart").value = mem.bt.start;
      if (mem.bt.end) $("#btEnd").value = mem.bt.end;
      if (mem.bt.cap) $("#btCap").value = mem.bt.cap;
      if (mem.bt.atr) $("#btAtr").value = mem.bt.atr;
    }
    if (mem.rangeM) { S.rangeM = mem.rangeM;
      document.querySelectorAll("#rangeTabs button").forEach(x => x.classList.toggle("active", +x.dataset.m === mem.rangeM)); }
    if (mem.sTab) { S.sTab = mem.sTab;
      document.querySelectorAll("#stTabs button").forEach(x => x.classList.toggle("active", x.dataset.k === mem.sTab)); }
  }, 700);
  // Always open on the Dashboard, every time the app starts.
  // (no last-tab restore)
  // prefetch default stock so the tab opens instantly (guarded against races)
  const ds = S.sym;
  GET("/api/stock/" + ds).then(d => { if (S.sym === ds) S.info = d; }).catch(() => {});
  GET("/api/stock/" + ds + "/history").then(h => { if (S.sym === ds) S.bars = h.bars; }).catch(() => {});
  // 🔔 notification bell: first pass seeds quietly, then every 90 s new
  // news / PSX announcements / company reports pop up + sit in the bell
  bellPoll(); BELL.timer = setInterval(bellPoll, 90000);



})();

/* ── 📊 SECTORS tab: all 36 PSX sectors, live aggregates ── */
let SEC = { data: null, period: "d", sub: "overview", full: false };
const SEC_PKEY = { d: "chg", w: "w1", m: "w1m", ytd: "ytd", y: "w1y" };
async function loadSectors() {
  if (SEC.data) { paintSectors(); return; }
  try { SEC.data = await GET("/api/sectors"); } catch (e) { SEC.data = null; }
  paintSectors();
}
function paintSectors() {
  const meta = $("#secMeta");
  if (!SEC.data || !SEC.data.sectors) {
    if (meta) meta.textContent = "sector tape unreachable — check connectivity";
    return;
  }
  const S = SEC.data.sectors;
  if (meta) meta.textContent = S.length + " sectors · " + SEC.data.live + " live stocks" +
    (SEC.data.dps ? " · official DPS feed" : "") + " · updated " + fmtTs(SEC.data.as_of) + " PKT";
  $("#secLanding").style.display = SEC.full ? "none" : "";
  $("#secFull").style.display = SEC.full ? "" : "none";
  $("#secViewAll").style.display = SEC.full ? "none" : "";
  if (!SEC.full) paintSecLanding(S); else paintSecTable(S);
}
function paintSecLanding(S) {
  const key = SEC_PKEY[SEC.period];
  const rows = S.filter(r => r[key] != null).sort((a, b) => b[key] - a[key]);
  const up = rows.filter(r => r[key] > 0).length;
  const dn = rows.filter(r => r[key] < 0).length;
  const flat = rows.length - up - dn;
  const total = rows.length || 1;
  $("#secUpDn").innerHTML =
    '<span class="dn">' + dn + " Sectors Down" + (flat ? " · " + flat + " flat" : "") + "</span>" +
    '<div class="bar"><i style="width:' + (dn / total * 100).toFixed(1) + '%;background:#ef5350"></i>' +
    '<i style="width:' + ((up + flat) / total * 100).toFixed(1) + '%;background:#26a69a"></i></div>' +
    '<span class="up">' + up + " Sectors Up</span>";
  const maxAbs = Math.max(1, ...rows.map(r => Math.abs(r[key])));
  $("#secBars").innerHTML = rows.map(r => {
    const v = r[key];
    const wpc = Math.max(6, Math.min(100, Math.abs(v) / maxAbs * 100)) * 0.62;
    const col = v >= 0 ? "#26a69a" : "#ef5350";
    const tip = r.name + " · mcap " + hmMcap(r.mcap) + " · " + r.n + " companies" +
      (r.turnover ? " · turnover " + hmMcap(r.turnover) : "") +
      (r.adv != null ? " · " + r.adv + "▲ / " + r.dec + "▼" : "");
    const tick = '<span class="tick" style="background:' + col + '"></span>';
    const nm = '<span class="nm">' + r.name + "</span>";
    const pc = '<span class="pc ' + (v >= 0 ? "pos" : "neg") + '">' + fmtPct(v) + "</span>";
    const down = '<span class="bwrap l"><i style="width:' + wpc.toFixed(1) + "%;background:" + col + '"></i></span>';
    const up = '<span class="bwrap r"><i style="width:' + wpc.toFixed(1) + "%;background:" + col + '"></i></span>';
    // diverging: [name] [bar←left grows left] value% [bar right→]
    return '<div class="sec-row" title="' + tip + '">' + tick + nm +
      (v >= 0 ? '<span class="bwrap l"></span>' + pc + up : down + pc + '<span class="bwrap r"></span>') +
      "</div>";
  }).join("");
}
const SEC_COLS = {
  overview: [["name", "Sectors", "s"], ["mcap", "Market Cap (PKR Mn)", "mn"], ["chg", "Today's Change (%)", "p"],
    ["weight", "Weight (%)", "p"], ["n", "Constituents", "i"], ["pat3", "PAT (3-Year CAGR)", "x"],
    ["sal3", "Sales (3-Year CAGR)", "x"], ["fpi", "1Y FPI (USD)", "x"]],
  financials: [["name", "Sectors", "s"], ["sg", "Sales Growth (1 Year)", "x"], ["eg", "EPS Growth (1YR)", "x"],
    ["sales", "Sales (PKR TTM)", "big"], ["pat", "PAT (PKR TTM)", "big"], ["eps", "EPS (PKR TTM)", "n2"],
    ["assets", "Total Assets (PKR)", "big"], ["liab", "Total Liabilities (PKR)", "big"]],
  valuations: [["name", "Sectors", "s"], ["mcap", "Market Cap (PKR Mn)", "mn"], ["pe", "PE Ratio", "n2"],
    ["ps", "PS Ratio", "n2"], ["shares", "Shares", "big"], ["ff", "Free Float", "big"],
    ["bv", "NA/ Share (PKR)", "n2"], ["bv2", "BV (PKR)", "n2"]],
  performance: [["name", "Sectors", "s"], ["h52", "52 week High", "n2"], ["l52", "52 week Low", "n2"],
    ["w1", "1 Week (%)", "p"], ["w1m", "1 Month (%)", "p"], ["w3m", "3 Month (%)", "p"],
    ["w6m", "6 Month (%)", "p"], ["w1y", "1 Year (%)", "p"], ["ytd", "YTD (%)", "p"]],
  dividends: [["name", "Sectors", "s"], ["d1", "Total Dividend (Last Year)", "x"],
    ["d5", "Total Dividend (Last 5 Years)", "x"], ["dyl", "Dividend Yield (Live)", "x"],
    ["dyt", "Dividend Yield (TTM)", "x"], ["dylast", "Dividend Yield (Last Year)", "x"],
    ["dc", "Dividend Cover (times)", "x"], ["pr", "Payout Ratio (%)", "x"]],
};
function fmtSecCell(key, fmt, r) {
  if (fmt === "s") return r[key] == null ? "—" : r[key];
  if (fmt === "x") return '<span class="sub">—</span>';
  const v = r[key];
  if (v == null) return '<span class="sub">—</span>';
  if (fmt === "p") return '<span class="' + (v > 0 ? "pos" : v < 0 ? "neg" : "sub") + '">' + fmtPct(v) + "</span>";
  if (fmt === "mn") return Number(v / 1e6).toLocaleString("en-PK", { maximumFractionDigits: 2 });
  if (fmt === "big") return Number(v).toLocaleString("en-PK", { maximumFractionDigits: 0 });
  if (fmt === "n2") return Number(v).toLocaleString("en-PK", { maximumFractionDigits: 2 });
  if (fmt === "i") return String(v);
  return String(v);
}
function paintSecTable(S) {
  const cols = SEC_COLS[SEC.sub];
  $("#secTbl").innerHTML =
    "<thead><tr>" + cols.map(c => "<th>" + c[1] + "</th>").join("") + "</tr></thead>" +
    "<tbody>" + S.map(r => "<tr>" + cols.map(c => "<td>" + fmtSecCell(c[0], c[2], r) + "</td>").join("") + "</tr>").join("") + "</tbody>";
  $("#secNote").textContent = SEC.sub === "dividends"
    ? "Dividend feeds are not exposed by the free public data sources this system uses — columns kept for parity with the PSX portal."
    : (SEC.sub === "overview"
        ? "3-year PAT/Sales CAGR and 1Y FPI are not exposed by free feeds — shown as —."
        : "Aggregated live from all listed companies · market-cap weighted · refreshed every 5 minutes.");
}
on("secPeriodTabs", "click", e => {
  const b = e.target.closest("button[data-p]");
  if (!b) return;
  SEC.period = b.dataset.p;
  $("#secPeriodTabs").querySelectorAll("button").forEach(x => x.classList.toggle("active", x === b));
  if (!SEC.full) paintSectors();
});
on("secSubTabs", "click", e => {
  const b = e.target.closest("button[data-st]");
  if (!b) return;
  SEC.sub = b.dataset.st;
  $("#secSubTabs").querySelectorAll("button[data-st]").forEach(x => x.classList.toggle("active", x === b));
  paintSectors();
});
on("secViewAll", "click", () => { SEC.full = true; paintSectors(); });
on("secBack", "click", () => { SEC.full = false; paintSectors(); });
on("secExport", "click", () => {
  if (!SEC.data || !SEC.data.sectors) return;
  const cols = SEC_COLS[SEC.sub];
  const esc = s => '"' + String(s == null ? "" : s).replace(/"/g, '""') + '"';
  let csv = cols.map(c => esc(c[1])).join(",") + "\n";
  for (const r of SEC.data.sectors) {
    csv += cols.map(c => {
      const v = r[c[0]];
      if (c[0] === "name") return esc(v);
      if (c[2] === "x" || v == null) return '""';
      if (c[2] === "mn") return String(Math.round(v / 1e6 * 100) / 100);
      if (typeof v === "number") return String(Math.round(v * 10000) / 10000);
      return esc(v);
    }).join(",") + "\n";
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "psx_sectors_" + SEC.sub + ".csv";
  a.click();
  URL.revokeObjectURL(a.href);
});

/* ── 💰 Money Management tab ── */
let MN = null;
function mnWatch() { return (S.watchMeta && S.watchMeta.length) ? S.watchMeta : []; }
function fillMnSelects() {
  const opts = mnWatch().map(w =>
    `<option value="${w.symbol}">${w.symbol}${w.price ? " · Rs " + Number(w.price).toFixed(2) : ""}</option>`).join("");
  const a = $("#mnSym");
  if (a) a.innerHTML = opts || "<option>No watchlist</option>";
  // free-text fields get suggestions: watchlist first, then the full PSX universe
  const dl = $("#mnTPList");
  if (dl) {
    const seen = new Set(mnWatch().map(w => w.symbol));
    const extra = ((S.universe || []).map(u => u.symbol) || []).filter(s => !seen.has(s));
    dl.innerHTML = mnWatch().map(w => `<option value="${w.symbol}">`).join("") +
                   extra.map(s => `<option value="${s}">`).join("");
  }
}
async function loadMoney() {
  try { MN = await GET("/api/money"); } catch { return; }
  const P = MN.plan;
  $("#mnBalance").textContent = fmtRs(MN.balance);
  $("#mnBalanceSub").innerHTML = `Capital ${fmtRs(MN.capital)} · Total P&amp;L <b class="${cls(MN.total_pnl)}">${fmtRs(MN.total_pnl)}</b>`;
  const wp = $("#mnWeekPnl");
  wp.textContent = fmtRs(MN.week_pnl); wp.className = "price-big " + cls(MN.week_pnl);
  $("#mnWeekSub").textContent = `${MN.week_trades} closed swing${MN.week_trades === 1 ? "" : "s"} in the last 7 days`;
  $("#mnWinRate").textContent = MN.win_rate != null ? MN.win_rate + "%" : "—";
  $("#mnWinSub").innerHTML = MN.wins + MN.losses
    ? `${MN.wins}W / ${MN.losses}L${MN.profit_factor != null ? " · PF " + MN.profit_factor : ""}${MN.avg_r != null ? " · avg " + MN.avg_r + "R" : ""}`
    : "Log your first swing in the journal.";
  const wl = $("#mnWeekLimit");
  wl.textContent = fmtRs(MN.weekly_limit_rs);
  wl.className = "price-big" + (MN.stop_week ? " down" : "");
  $("#mnWeekLimitSub").textContent = MN.stop_week ? "USED UP this week" : `${fmtRs(MN.loss_left_week)} of limit left this week`;

  let al = "";
  if (MN.stop_week)
    al += `<div class="pill p-sell" style="display:inline-block;padding:12px 16px;font-size:15px">🛑 STOP — your weekly loss limit is hit. No new swings until next week; review what went wrong.</div>`;
  else if (MN.losing_streak >= 2)
    al += `<div class="pill p-hold" style="display:inline-block;padding:12px 16px;font-size:15px">⚠️ Losing streak: ${MN.losing_streak} swings in a row. Pause, review your setups — never average down to "win it back".</div>`;
  if (MN.over_hold > 0)
    al += ` <div class="pill p-hold" style="display:inline-block;padding:12px 16px;font-size:15px">⏰ ${MN.over_hold} logged swing${MN.over_hold === 1 ? "" : "s"} ran past your ${P.max_hold_days}-day window — exit or re-evaluate at the deadline.</div>`;
  for (const o of (MN.opens || [])) {
    if (o.status !== "OPEN")
      al += ` <div class="pill ${o.status.indexOf("TARGET") === 0 ? "p-buy" : "p-sell"}" style="display:inline-block;padding:12px 16px;font-size:15px">${o.status.indexOf("TARGET") === 0 ? "🎯" : "🛑"} ${o.symbol}: ${o.status}</div>`;
  }
  $("#mnAlerts").innerHTML = al;

  $("#mnCapital").value = P.capital; $("#mnRiskPct").value = P.risk_per_trade_pct;
  $("#mnTargetPct").value = P.target_per_trade_pct; $("#mnStopPct").value = P.stop_per_trade_pct;
  $("#mnMaxPos").value = P.max_positions; $("#mnHoldDays").value = P.max_hold_days;
  $("#mnWeekLimitPct").value = P.weekly_loss_limit_pct;
  const rr = P.stop_per_trade_pct > 0 ? (P.target_per_trade_pct / P.stop_per_trade_pct).toFixed(1) : "∞";
  $("#mnRules").innerHTML = `📖 Plan: risk <b>${P.risk_per_trade_pct}%</b> per swing · aim <b>${P.target_per_trade_pct}%</b> gain vs <b>${P.stop_per_trade_pct}%</b> stop (${rr}:1) · hold ≤ <b>${P.max_hold_days} days</b> · max <b>${P.max_positions}</b> open swings · stop trading at <b>${P.weekly_loss_limit_pct}%</b> weekly loss.`;
  fillMnSelects();

  const stopPct = P.stop_per_trade_pct || 1;
  $("#mnJRows").innerHTML = MN.journal.map(t => {
    const pct = t.pct != null ? t.pct : (t.entry ? ((t.exit - t.entry) / t.entry * 100) : null);
    const r = pct != null ? (pct / stopPct).toFixed(1) + "R" : "—";
    const tip = t.setup ? ` title="Setup: ${escA(t.setup)}"` : "";
    return `<tr>
      <td>${t.exit_date || t.date}</td><td${tip}><b>${t.symbol}</b></td>
      <td>${t.days_held != null ? t.days_held : "—"}</td>
      <td>${fmtRs(t.entry)}</td><td>${fmtRs(t.exit)}</td>
      <td class="${cls(pct)}">${pct != null ? (pct > 0 ? "+" : "") + Number(pct).toFixed(1) + "%" : "—"}</td>
      <td class="${cls(pct)}">${r}</td>
      <td class="${cls(t.pnl)}"><b>${fmtRs(t.pnl)}</b></td>
      <td><button class="btn ghost mnDel" data-id="${t.id}" title="Delete this entry">✕</button></td></tr>`;
  }).join("") || `<tr><td colspan="9" class="sub">No swings logged yet.</td></tr>`;
  $("#mnJSum").innerHTML = MN.wins + MN.losses
    ? `All-time: ${MN.wins}W / ${MN.losses}L${MN.win_rate != null ? " · win rate " + MN.win_rate + "%" : ""}${MN.avg_win_pct != null ? " · avg win +" + MN.avg_win_pct + "%" : ""}${MN.avg_loss_pct != null ? " · avg loss " + MN.avg_loss_pct + "%" : ""}${MN.avg_hold_days != null ? " · avg hold " + MN.avg_hold_days + " days" : ""} · fees deducted automatically.`
    : "";
  // 📂 open swings
  const ops = MN.opens || [];
  $("#mnORows").innerHTML = ops.map(o => `<tr>
    <td><b>${o.symbol}</b>${o.note ? `<span class="sub" title="${escA(o.note)}"> 📝</span>` : ""}</td>
    <td>${o.days != null ? o.days : "—"}</td><td>${o.qty}</td>
    <td>${fmtRs(o.entry)}</td><td>${o.last != null ? fmtRs(o.last) : "—"}</td>
    <td class="${cls(o.upnl)}"><b>${o.upnl != null ? fmtRs(o.upnl) : "—"}</b></td>
    <td class="sub">${o.stop ? fmtRs(o.stop) : "—"} → ${o.target ? fmtRs(o.target) : "—"}</td>
    <td>${o.status === "OPEN" ? '<span class="pill p-hold">OPEN</span>'
         : `<span class="pill ${o.status.indexOf("TARGET") === 0 ? "p-buy" : "p-sell"}">${o.status}</span>`}</td>
    <td style="white-space:nowrap">
      <button class="btn ghost mnOClose" data-id="${o.id}" title="Close it & log to the journal">Close</button>
      <button class="btn ghost mnODel" data-id="${o.id}" title="Remove without logging">✕</button>
    </td></tr>`).join("")
    || `<tr><td colspan="9" class="sub">No open swings — add one above when you enter a trade.</td></tr>`;
  if (!$("#mnODate").value) $("#mnODate").value = MN.today;
  if (!$("#mnJExitDate").value) $("#mnJExitDate").value = MN.today;
  if (!$("#mnLadBase").value) $("#mnLadBase").value = Math.round(MN.capital * P.risk_per_trade_pct / 100);
  if (!$("#mnLadPay").value) $("#mnLadPay").value = 92;
  renderLadder();
}
function renderLadder() {
  if (!MN) return;
  const base = +$("#mnLadBase").value || 0, pay = (+$("#mnLadPay").value || 92) / 100;
  let lost = 0, rows = "";
  for (let i = 1; i <= 10; i++) {
    const stake = pay > 0 ? (base + lost) / pay : 0;
    rows += `<tr><td>${i}</td><td>${fmtRs(Math.round(stake))}</td><td>${fmtRs(Math.round(lost))}</td>
      <td class="${lost / MN.capital > 0.2 ? "down" : ""}">${MN.capital ? (lost / MN.capital * 100).toFixed(1) + "%" : "—"}</td></tr>`;
    lost += stake;
  }
  $("#mnLadRows").innerHTML = rows;
}
on("mnPlanSave", "click", async () => {
  const body = {
    capital: +$("#mnCapital").value, risk_per_trade_pct: +$("#mnRiskPct").value,
    target_per_trade_pct: +$("#mnTargetPct").value, stop_per_trade_pct: +$("#mnStopPct").value,
    max_positions: +$("#mnMaxPos").value, max_hold_days: +$("#mnHoldDays").value,
    weekly_loss_limit_pct: +$("#mnWeekLimitPct").value };
  const r = await POST("/api/money/plan", body);
  if (r.ok) { $("#mnPlanMsg").textContent = "✅ Saved — swing sizes use the new rules."; toast("Swing plan saved"); loadMoney(); }
  else $("#mnPlanMsg").textContent = "Save failed";
});
function mnEntryVal() { return +$("#mnEntry").value || 0; }
function mnFillFromPlan(force) {
  if (!MN) return;
  const e = mnEntryVal(); if (!e) { toast("Set the entry price first"); return; }
  const P = MN.plan;
  if (force || !$("#mnStop").value) $("#mnStop").value = (e * (1 - P.stop_per_trade_pct / 100)).toFixed(2);
  if (force || !$("#mnTarg").value) $("#mnTarg").value = (e * (1 + P.target_per_trade_pct / 100)).toFixed(2);
}
on("mnFillPlan", "click", () => mnFillFromPlan(true));
on("mnSym", "change", () => {
  const w = mnWatch().find(x => x.symbol === $("#mnSym").value);
  if (w && w.price) { $("#mnEntry").value = Number(w.price).toFixed(2); mnFillFromPlan(false); }
});
on("mnSizeBtn", "click", async () => {
  const r = await POST("/api/money/size", { symbol: $("#mnSym").value,
    entry: +$("#mnEntry").value, stop: +$("#mnStop").value, target: +$("#mnTarg").value });
  if (!r.ok) { $("#mnSizeOut").innerHTML = `<span class="down">${r.error}</span>`; return; }
  const sz = r.sizing, ck = r.check, pu = r.plan_used;
  const lotNote = sz.qty_lot !== sz.qty
    ? `<p class="sub">PSX lot: rounded to <b>${sz.qty_lot}</b> shares (${fmtRs(sz.cost_lot_rs)}) in 100-share board lots</p>` : "";
  $("#mnSizeOut").innerHTML = `
    <div class="bento" style="grid-template-columns:repeat(3,1fr)">
      <div><h4>Buy</h4><div style="font-size:20px"><b>${sz.qty}</b> shares</div>
        <p class="sub">${fmtRs(sz.cost_rs)} position (${sz.position_pct}% of capital)</p>${lotNote}</div>
      <div><h4>Risk at stop</h4><div style="font-size:20px"><b class="down">${fmtRs(sz.risk_rs)}</b></div>
        <p class="sub">capped by ${sz.capped_by} · risk/swing ${pu.risk_per_trade_pct}%</p></div>
      <div><h4>Reward : Risk</h4><div style="font-size:20px"><b>${ck.reward_risk} : 1</b></div>
        <p class="sub">${ck.ok ? "setup passes your rules" : "fails a hard rule — see below"}</p></div>
    </div>
    <p class="sub" style="margin-top:10px">🗓 Swing window: hold up to <b>${pu.max_hold_days} days</b> for the target; if the stop is hit, exit the same day — never add to a losing swing.</p>` +
    (ck.warnings.length ? `<ul style="margin:10px 0 0;padding-left:18px;color:#ffcf7b">` +
      ck.warnings.map(w => `<li>${w}</li>`).join("") + `</ul>` : "");
});
on("mnJAdd", "click", async () => {
  const jsym = ($("#mnJSym").value || "").trim().toUpperCase();
  if (!jsym) { toast("Type the stock symbol first"); return; }
  const r = await POST("/api/money/trade", { symbol: jsym, qty: +$("#mnJQty").value,
    entry: +$("#mnJEntry").value, exit: +$("#mnJExit").value,
    entry_date: $("#mnJEntryDate").value || null, exit_date: $("#mnJExitDate").value || null,
    setup: ($("#mnJSetup").value || "").trim() });
  if (!r.ok) { toast("Could not add swing: " + r.error); return; }
  toast("Swing logged: " + fmtRs(r.trade.pnl) + (r.trade.pnl >= 0 ? " profit" : " loss"));
  $("#mnJQty").value = ""; $("#mnJEntry").value = ""; $("#mnJExit").value = ""; $("#mnJSetup").value = "";
  $("#mnJEntryDate").value = "";
  MN = r.state; loadMoney();
});
document.addEventListener("click", async e => {
  const b = e.target.closest(".mnDel"); if (!b) return;
  const r = await fetch("/api/money/trade/" + b.dataset.id, { method: "DELETE" });
  const d = await r.json(); if (d.ok) { MN = d.state; loadMoney(); }
});
on("mnLadBase", "input", renderLadder);
on("mnLadPay", "input", renderLadder);
on("mnTPBtn", "click", async () => {
  const sym = ($("#mnTPSym").value || "").trim().toUpperCase(), msg = $("#mnTPMsg"), btn = $("#mnTPBtn");
  if (!sym) { msg.textContent = "Type a stock symbol first (e.g. OGDC)."; return; }
  btn.disabled = true; btn.textContent = "Building…";
  msg.textContent = "Building the " + sym + " trade plan PDF — backtesting all 33 strategies on it. About 15–30 s…";
  try {
    const r = await fetch("/api/money/trade-plan/" + encodeURIComponent(sym));
    const ct = r.headers.get("content-type") || "";
    if (!r.ok || ct.includes("application/json")) {
      let err = "request failed";
      try { err = (await r.json()).error || err; } catch {}
      msg.innerHTML = `<span class="down">Could not build: ${err}</span>`; return;
    }
    const blob = await r.blob();
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u; a.download = "trade_plan_" + sym + ".pdf";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 5000);
    msg.innerHTML = `✅ Downloaded <b>trade_plan_${sym}.pdf</b> — research + best strategy + sized trade plan.`;
    toast("Trade Plan PDF ready: " + sym);
  } catch (e) {
    msg.innerHTML = `<span class="down">Failed: ${e}</span>`;
  } finally {
    btn.disabled = false; btn.textContent = "Build & download PDF";
  }
});


/* ── 🏛 PSX OFFICIAL DESK (reports tab) ── */
let DESK = null;
async function loadDesk() {
  const body = $("#deskBody");
  if (!body) return;
  if (!DESK) {
    body.innerHTML = '<p class="sub">contacting psx.com.pk / dps.psx.com.pk…</p>';
    try { DESK = await GET("/api/desk"); }
    catch (e) { body.innerHTML = `<p class="neg">Desk unavailable: ${e.message}</p>`; return; }
  }
  const d = DESK;
  const idx = d.indices || {};
  let html = "";
  if (idx.kse100) html += `<div class="stat" style="margin-bottom:10px">
    <div class="k">KSE-100 official close · ${idx.date}</div>
    <div class="v">${Number(idx.kse100).toLocaleString("en-PK")}
      <span class="${idx.change >= 0 ? "pos" : "neg"}">${idx.change >= 0 ? "+" : ""}${Number(idx.change).toLocaleString("en-PK")}</span></div>
    <div class="sub">source: DPS monthly indices report (${idx.month})</div></div>`;
  const reg = (d.eligible || [])[0];
  if (reg) html += `<div class="stat" style="margin-bottom:10px">
    <div class="k">Eligible scrips — ${reg.group}</div>
    <div class="v">${reg.count} symbols</div>
    <div class="sub">${(reg.symbols || []).slice(0, 16).join(", ")}${reg.count > 16 ? "…" : ""}</div></div>`;
  if ((d.monthly || []).length) {
    html += `<h3 style="margin:10px 0 6px">📚 Monthly report archive</h3><ul class="sub" style="line-height:1.7">` +
      d.monthly.slice(0, 6).map(m => `<li><b>${m.month}</b> — ` +
        m.links.map(l => `<a href="${l.href}" target="_blank" rel="noopener">${l.label}</a>`).join(" · ") +
        `</li>`).join("") + `</ul>`;
  }
  html += `<h3 style="margin:12px 0 6px">🔗 Official source wiring</h3><div class="grid g2">` +
    (d.links || []).map(l => {
      let host = ""; try { host = new URL(l.url).host; } catch (e) {}
      return `<div class="stat"><div class="k">${l.live ? "🟢" : "🔗"} ${l.name}</div>
        <div class="sub" style="margin-top:4px">${l.wired}</div>
        <a href="${l.url}" target="_blank" rel="noopener" style="font-size:11px">${host} ↗</a></div>`;
    }).join("") + `</div>`;
  body.innerHTML = html;
  const meta = $("#deskMeta");
  if (meta) meta.textContent = "· fetched " + (d.fetched_at || "");
}
