/* Zero-dependency canvas charts (works offline on laptop/phone). */
function setupCanvas(cv) {
  const dpr = window.devicePixelRatio || 1;
  const r = cv.getBoundingClientRect();
  cv.width = Math.max(r.width * dpr, 50);
  cv.height = Math.max(r.height * dpr, 50);
  const ctx = cv.getContext("2d");
  ctx.scale(dpr, dpr);
  return { ctx, W: r.width, H: r.height };
}

function niceNum(x) {
  if (x == null || isNaN(x)) return "—";
  const a = Math.abs(x);
  if (a >= 1e9) return (x / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (x / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (x / 1e3).toFixed(1) + "K";
  return (+x).toFixed(2);
}

function drawCandles(cv, bars, opts = {}) {
  /* TradingView-style interactive candles: hover crosshair + OHLC legend,
     mouse-wheel zoom, drag-to-pan, double-click to reset. Zero libraries. */
  if (!bars || !bars.length) {
    const { ctx } = setupCanvas(cv);
    ctx.clearRect(0, 0, cv._W || 800, cv._H || 400);
    ctx.fillStyle = "#9CA3AF"; ctx.font = "14px sans-serif";
    ctx.fillText("No chart data", 20, 40); return;
  }
  cv._bars = bars;
  if (!cv._view || cv._view.n !== bars.length)
    cv._view = { i0: 0, i1: bars.length - 1, n: bars.length };
  if (!cv._bound) {
    cv._bound = true;
    cv.addEventListener("wheel", e => {
      e.preventDefault();
      const v = cv._view, n = cv._bars.length, span = v.i1 - v.i0;
      const r = cv.getBoundingClientRect();
      const fx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
      const step = Math.max(2, Math.round(span * 0.15)) * (e.deltaY > 0 ? 1 : -1);
      let i0 = v.i0 - Math.round(step * fx), i1 = v.i1 + Math.round(step * (1 - fx));
      if (i1 - i0 < 12) { const c = Math.round((v.i0 + v.i1) / 2); i0 = c - 6; i1 = c + 6; }
      if (i1 - i0 > n - 1) { i0 = 0; i1 = n - 1; }
      v.i0 = Math.max(0, i0); v.i1 = Math.min(n - 1, Math.max(v.i0 + 12, i1));
      cv._mouse = null; _renderCandles(cv);
    }, { passive: false });
    cv.addEventListener("mousedown", e => { cv._drag = { x: e.clientX, i0: cv._view.i0, i1: cv._view.i1 }; });
    window.addEventListener("mouseup", () => { cv._drag = null; });
    cv.addEventListener("mousemove", e => {
      const r = cv.getBoundingClientRect();
      cv._mouse = { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height };
      if (cv._drag) {
        const v = cv._view, span = cv._drag.i1 - cv._drag.i0;
        const shift = Math.round((cv._drag.x - e.clientX) / (r.width / (span + 1)));
        let i0 = cv._drag.i0 + shift, i1 = cv._drag.i1 + shift;
        if (i0 < 0) { i0 = 0; i1 = span; }
        if (i1 > cv._bars.length - 1) { i1 = cv._bars.length - 1; i0 = i1 - span; }
        v.i0 = i0; v.i1 = i1;
      }
      _renderCandles(cv);
    });
    cv.addEventListener("mouseleave", () => { cv._mouse = null; _renderCandles(cv); });
    cv.addEventListener("dblclick", () => {
      cv._view = { i0: 0, i1: cv._bars.length - 1, n: cv._bars.length };
      cv._mouse = null; _renderCandles(cv);
    });
  }
  _renderCandles(cv);
}

function _renderCandles(cv) {
  const bars = cv._bars; if (!bars) return;
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  const v = cv._view;
  const view = bars.slice(v.i0, v.i1 + 1);
  const n = view.length;
  const padL = 8, padR = 66, padT = 26, padB = 22;
  const volH = Math.floor((H - padT - padB) * 0.20);
  const pxH = H - padT - padB - volH - 8;
  const slot = (W - padL - padR) / n;
  const bw = Math.max(Math.min(slot * 0.62, 14), 1.5);
  let lo = Infinity, hi = -Infinity, vmax = 0;
  view.forEach(b => {
    lo = Math.min(lo, b.low); hi = Math.max(hi, b.high);
    vmax = Math.max(vmax, b.volume || 0);
    ["sma20", "sma50", "sma200"].forEach(k => { if (b[k]) { lo = Math.min(lo, b[k]); hi = Math.max(hi, b[k]); } });
  });
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const X = i => padL + slot * i + slot / 2;
  const Y = p => padT + pxH - (p - lo) / (hi - lo) * pxH;
  // grid + price labels
  ctx.strokeStyle = "#1E1E22"; ctx.fillStyle = "#8A8F98";
  ctx.font = "11px sans-serif"; ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const p = lo + (hi - lo) * g / 4, y = Y(p);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillText(p.toFixed(1), W - padR + 6, y + 4);
  }
  const step = Math.ceil(n / 6);
  for (let i = 0; i < n; i += step)
    ctx.fillText(String(view[i].date).slice(2), X(i) - 24, H - 8);
  // volume
  const vy0 = padT + pxH + 8;
  view.forEach((b, i) => {
    const h = vmax ? (b.volume || 0) / vmax * (volH - 2) : 0;
    ctx.fillStyle = b.close >= b.open ? "rgba(16,185,129,.38)" : "rgba(251,113,133,.34)";
    ctx.fillRect(X(i) - bw / 2, vy0 + volH - h, bw, h);
  });
  // candles
  view.forEach((b, i) => {
    const up = b.close >= b.open;
    ctx.strokeStyle = up ? "#10B981" : "#FB7185";
    ctx.fillStyle = up ? "#10B981" : "#FB7185";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(X(i), Y(b.high)); ctx.lineTo(X(i), Y(b.low)); ctx.stroke();
    const yO = Y(b.open), yC = Y(b.close);
    ctx.fillRect(X(i) - bw / 2, Math.min(yO, yC), bw, Math.max(Math.abs(yC - yO), 1.2));
  });
  // SMA overlays
  const lines = [["sma20", "#F59E0B"], ["sma50", "#818CF8"], ["sma200", "#9CA3AF"]];
  lines.forEach(([k, col]) => {
    ctx.strokeStyle = col; ctx.lineWidth = 1.4; ctx.beginPath();
    let started = false;
    view.forEach((b, i) => {
      if (b[k]) { if (!started) { ctx.moveTo(X(i), Y(b[k])); started = true; } else ctx.lineTo(X(i), Y(b[k])); }
    });
    ctx.stroke();
  });
  ctx.font = "bold 11px sans-serif";
  [["SMA20", "#F59E0B"], ["SMA50", "#818CF8"], ["SMA200", "#9CA3AF"]].forEach(([t, c], i) => {
    ctx.fillStyle = c; ctx.fillText("— " + t, padL + 8 + i * 76, padT + 10);
  });
  // ── crosshair + OHLC legend ──
  let hi_i = n - 1;
  const m = cv._mouse;
  if (m && m.x >= padL && m.x <= W - padR) {
    hi_i = Math.max(0, Math.min(n - 1, Math.floor((m.x - padL) / slot)));
    const b = view[hi_i], cx = X(hi_i);
    ctx.strokeStyle = "rgba(156,163,175,.4)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, H - padB); ctx.stroke();
    if (m.y > padT && m.y < padT + pxH) {
      ctx.beginPath(); ctx.moveTo(padL, m.y); ctx.lineTo(W - padR, m.y); ctx.stroke();
      const pv = lo + (1 - (m.y - padT) / pxH) * (hi - lo);
      ctx.setLineDash([]);
      ctx.fillStyle = "#26262a"; ctx.fillRect(W - padR + 2, m.y - 9, padR - 4, 18);
      ctx.fillStyle = "#E8E6E3"; ctx.font = "bold 10.5px sans-serif";
      ctx.fillText(pv.toFixed(1), W - padR + 6, m.y + 3.5);
    }
    ctx.setLineDash([]);
    ctx.fillStyle = "#26262a"; ctx.fillRect(cx - 30, H - padB + 2, 60, 16);
    ctx.fillStyle = "#E8E6E3"; ctx.font = "bold 10px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(String(b.date).slice(2), cx, H - padB + 13); ctx.textAlign = "left";
  }
  const lb = view[hi_i];
  if (lb) {
    const chg = lb.open ? ((lb.close / lb.open) - 1) * 100 : 0;
    ctx.font = "bold 11px sans-serif";
    const txt = `${lb.date}   O ${lb.open}   H ${lb.high}   L ${lb.low}   C ${lb.close}   ${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%   Vol ${niceNum(lb.volume || 0)}`;
    ctx.fillStyle = "rgba(13,13,12,.75)";
    ctx.fillRect(padL + 4, padT - 22, ctx.measureText(txt).width + 12, 16);
    ctx.fillStyle = chg >= 0 ? "#10B981" : "#FB7185";
    ctx.fillText(txt, padL + 10, padT - 10);
  }
  // zoom hint (fades once user interacts)
  if (!cv._interacted) {
    ctx.fillStyle = "rgba(156,163,175,.5)"; ctx.font = "10.5px sans-serif";
    ctx.fillText("scroll = zoom · drag = pan · double-click = reset", W - padR - 250, padT + 10);
    cv.addEventListener("wheel", () => cv._interacted = true, { once: true });
    cv.addEventListener("mousedown", () => cv._interacted = true, { once: true });
  }
}

function drawLine(cv, pts, opts = {}) {
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  if (!pts || pts.length < 2) {
    ctx.fillStyle = "#9CA3AF"; ctx.font = "14px sans-serif";
    ctx.fillText("Not enough points", 20, 40); return;
  }
  const padL = 10, padR = 70, padT = 14, padB = 22;
  const vs = pts.map(p => p.y);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad; hi += pad;
  const X = i => padL + (W - padL - padR) * i / (pts.length - 1);
  const Y = v => padT + (H - padT - padB) - (v - lo) / (hi - lo) * (H - padT - padB);
  ctx.strokeStyle = "#1E1E22";
  ctx.fillStyle = "#8A8F98"; ctx.font = "11px sans-serif";
  for (let g = 0; g <= 4; g++) {
    const v = lo + (hi - lo) * g / 4, y = Y(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillText(niceNum(v), W - padR + 6, y + 4);
  }
  // area fill
  const col = opts.color || "#6366F1";
  const grad = ctx.createLinearGradient(0, padT, 0, H - padB);
  grad.addColorStop(0, "rgba(99,102,241,.30)"); grad.addColorStop(1, "rgba(99,102,241,0)");
  ctx.beginPath();
  pts.forEach((p, i) => i ? ctx.lineTo(X(i), Y(p.y)) : ctx.moveTo(X(0), Y(p.y)));
  ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.stroke();
  ctx.lineTo(X(pts.length - 1), H - padB); ctx.lineTo(X(0), H - padB); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  // baseline dot + last value
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.arc(X(pts.length - 1), Y(pts[pts.length - 1].y), 3.5, 0, 7); ctx.fill();
  ctx.font = "bold 12px sans-serif";
  ctx.fillText(niceNum(pts[pts.length - 1].y), W - padR + 6, Y(pts[pts.length - 1].y) - 6);
  const step = Math.ceil(pts.length / 6);
  ctx.fillStyle = "#8A8F98"; ctx.font = "11px sans-serif";
  for (let i = 0; i < pts.length; i += step)
    ctx.fillText(String(pts[i].x).slice(2), X(i) - 22, H - 8);
}

/* ── simple bar chart: items = [{label, value}] ── */
function drawBars(cv, items, opts = {}) {
  if (!items || !items.length) return;
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  const padL = 12, padR = 12, padT = 26, padB = 26;
  const vals = items.map(i => Number(i.value) || 0);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const span = (hi - lo) || 1;
  const zeroY = padT + (hi / span) * (H - padT - padB);
  const bw = (W - padL - padR) / items.length;
  ctx.font = "11px sans-serif"; ctx.textAlign = "center";
  items.forEach((it, i) => {
    const v = Number(it.value) || 0;
    const h = Math.abs(v / span) * (H - padT - padB);
    const x = padL + i * bw + bw * 0.18, w = bw * 0.64;
    const y = v >= 0 ? zeroY - h : zeroY;
    
    ctx.fillRect(x, y, w, Math.max(h, 1));
    ctx.fillStyle = "#E8E6E3"; ctx.font = "bold 11px sans-serif";
    ctx.fillText(niceNum(v), x + w / 2, v >= 0 ? y - 4 : y + h + 12);
    ctx.fillStyle = "#8A8F98"; ctx.font = "11px sans-serif";
    ctx.fillText(String(it.label), x + w / 2, H - 8);
  });
  ctx.strokeStyle = "#ccc2ae"; ctx.beginPath();
  ctx.moveTo(padL, zeroY); ctx.lineTo(W - padR, zeroY); ctx.stroke();
  ctx.textAlign = "left";
}

/* ── multi-line overlay: series = [{name, color, pts:[{x,y}]}] ── */
function drawMultiLine(cv, series, opts = {}) {
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  const all = series.flatMap(s => s.pts.map(p => p.y));
  if (!all.length) { ctx.fillStyle = "#9CA3AF"; ctx.fillText("No data", 20, 30); return; }
  const padL = 12, padR = 12, padT = 14, padB = 22;
  let lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const n = Math.max(...series.map(s => s.pts.length));
  const X = i => padL + (W - padL - padR) * i / Math.max(1, n - 1);
  const Y = v => padT + (H - padT - padB) - (v - lo) / (hi - lo) * (H - padT - padB);
  ctx.strokeStyle = "#1E1E22";
  for (let g = 0; g <= 4; g++) {
    const y = padT + (H - padT - padB) * g / 4;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
  }
  series.forEach(s => {
    ctx.beginPath();
    s.pts.forEach((p, i) => i ? ctx.lineTo(X(i), Y(p.y)) : ctx.moveTo(X(0), Y(p.y)));
    ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.stroke();
  });
  // legend
  let lx = padL + 4;
  ctx.font = "bold 11px sans-serif";
  series.forEach(s => {
    ctx.fillStyle = s.color; ctx.fillRect(lx, padT - 8, 10, 3);
    ctx.fillStyle = "#E8E6E3";
    const last = s.pts.length ? s.pts[s.pts.length - 1].y : 0;
    const t = `${s.name} ${Number(last).toFixed(0)}`;
    ctx.fillText(t, lx + 14, padT - 3);
    lx += 14 + ctx.measureText(t).width + 16;
  });
}

/* ── horizontal gauge (e.g. 52-week range): {low, high, now, labels} ── */
function drawGauge(cv, g) {
  if (!g || g.low == null || g.high == null) return;
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  const pad = 18, y = H * 0.42;
  const lo = Number(g.low), hi = Number(g.high), now = Number(g.now);
  const frac = Math.max(0, Math.min(1, (now - lo) / (hi - lo || 1)));
  ctx.fillStyle = "#26262a";
  ctx.fillRect(pad, y - 6, W - pad * 2, 12);
  ctx.fillStyle = "#10B981";
  ctx.fillRect(pad, y - 6, (W - pad * 2) * frac, 12);
  const nx = pad + (W - pad * 2) * frac;
  ctx.fillStyle = "#6366F1";
  ctx.beginPath(); ctx.arc(nx, y, 7, 0, 7); ctx.fill();
  ctx.font = "11px sans-serif"; ctx.fillStyle = "#8A8F98"; ctx.textAlign = "center";
  ctx.fillText("Low " + niceNum(lo), pad + 24, y + 24);
  ctx.fillText("High " + niceNum(hi), W - pad - 24, y + 24);
  ctx.fillStyle = "#E8E6E3"; ctx.font = "bold 12px sans-serif";
  ctx.fillText("Now " + niceNum(now), nx, y - 12);
  ctx.textAlign = "left";
}

/* ── AI trend chart: smooth curve, violet glow, NO gridlines ── */
function drawTrend(cv, dates, vals) {
  const pts = [];
  for (let i = 0; i < vals.length; i++) if (vals[i] != null) pts.push({ x: dates[i], y: vals[i] });
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  if (pts.length < 2) { ctx.fillStyle = "#9CA3AF"; ctx.fillText("Building trend…", 20, 36); return; }
  const padL = 8, padR = 66, padT = 16, padB = 26;
  const vs = pts.map(p => p.y);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  const pad = (hi - lo) * 0.10 || 1; lo -= pad; hi += pad;
  const X = i => padL + (W - padL - padR) * i / (pts.length - 1);
  const Y = v => padT + (H - padT - padB) - (v - lo) / (hi - lo) * (H - padT - padB);
  // soft glow area under the curve
  const grad = ctx.createLinearGradient(0, padT, 0, H - padB);
  grad.addColorStop(0, "rgba(99,102,241,.34)");
  grad.addColorStop(0.6, "rgba(99,102,241,.10)");
  grad.addColorStop(1, "rgba(99,102,241,0)");
  ctx.beginPath();
  pts.forEach((p, i) => {
    const x = X(i), y = Y(p.y);
    if (!i) ctx.moveTo(x, y);
    else { const px = X(i - 1), py = Y(pts[i - 1].y), cx = (px + x) / 2; ctx.bezierCurveTo(cx, py, cx, y, x, y); }
  });
  ctx.strokeStyle = "#818CF8"; ctx.lineWidth = 2.4;
  ctx.shadowColor = "rgba(99,102,241,.55)"; ctx.shadowBlur = 16; ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.lineTo(X(pts.length - 1), H - padB); ctx.lineTo(X(0), H - padB); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  // endpoint dot + value
  const lp = pts[pts.length - 1];
  ctx.fillStyle = "#818CF8";
  ctx.beginPath(); ctx.arc(X(pts.length - 1), Y(lp.y), 4, 0, 7); ctx.fill();
  ctx.fillStyle = "#E8E6E3"; ctx.font = "bold 12px sans-serif";
  ctx.fillText(lp.y.toFixed(1), W - padR + 8, Y(lp.y) - 8);
  // sparse date labels only (no gridlines)
  ctx.fillStyle = "#6B7280"; ctx.font = "10.5px sans-serif";
  const step = Math.ceil(pts.length / 5);
  for (let i = 0; i < pts.length; i += step)
    ctx.fillText(String(pts[i].x).slice(2), X(i) - 22, H - 8);
}

/* ── tiny sparkline for bento cards ── */
function drawSpark(cv, vals, color) {
  if (!vals || vals.length < 2) return;
  const { ctx, W, H } = setupCanvas(cv);
  ctx.clearRect(0, 0, W, H);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || 1; lo -= pad; hi += pad;
  const X = i => 2 + (W - 4) * i / (vals.length - 1);
  const Y = v => 2 + (H - 4) - (v - lo) / (hi - lo) * (H - 4);
  const col = color || "#818CF8";
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, col + "44"); grad.addColorStop(1, col + "00");
  ctx.beginPath();
  vals.forEach((v, i) => i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(0), Y(v)));
  ctx.strokeStyle = col; ctx.lineWidth = 1.8; ctx.stroke();
  ctx.lineTo(X(vals.length - 1), H); ctx.lineTo(X(0), H); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
}
/* Infographic donut: layered bezel rings, gradient segment arcs,
   big colored % in the center. segments: [{v, color, color2}]. */
function drawDonut(cv, segments, opt = {}) {
  if (!cv) return;
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth || 150, H = cv.clientHeight || 150;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 2;
  /* depth bezel (three concentric rings) */
  [[ "#232327", R, R * 0.93], ["#1b1b1f", R * 0.93, R * 0.87],
   ["#232327", R * 0.87, R * 0.81]].forEach(([c, r0, r1]) => {
    ctx.beginPath(); ctx.arc(cx, cy, (r0 + r1) / 2, 0, Math.PI * 2);
    ctx.strokeStyle = c; ctx.lineWidth = Math.max(1, r0 - r1); ctx.stroke();
  });
  const rOut = R * 0.79, rIn = R * 0.55, rMid = (rOut + rIn) / 2, ringW = rOut - rIn;
  /* track */
  ctx.beginPath(); ctx.arc(cx, cy, rMid, 0, Math.PI * 2);
  ctx.strokeStyle = "#141417"; ctx.lineWidth = ringW; ctx.stroke();
  const total = segments.reduce((a, s) => a + (s.v > 0 ? s.v : 0), 0);
  if (total > 0) {
    let a0 = -Math.PI / 2;
    segments.forEach(s => {
      if (!(s.v > 0)) return;
      const a1 = a0 + (s.v / total) * Math.PI * 2;
      const g = ctx.createLinearGradient(cx - rOut, cy - rOut, cx + rOut, cy + rOut);
      g.addColorStop(0, s.color2 || s.color); g.addColorStop(1, s.color);
      ctx.beginPath(); ctx.arc(cx, cy, rMid, a0 + 0.03, Math.max(a0 + 0.03, a1 - 0.03));
      ctx.strokeStyle = g; ctx.lineWidth = ringW; ctx.stroke();
      a0 = a1;
    });
  }
  /* inner disc */
  const ig = ctx.createRadialGradient(cx, cy, 1, cx, cy, rIn * 0.94);
  ig.addColorStop(0, "#202024"); ig.addColorStop(1, "#121215");
  ctx.beginPath(); ctx.arc(cx, cy, rIn * 0.94, 0, Math.PI * 2);
  ctx.fillStyle = ig; ctx.fill();
  /* center text */
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillStyle = opt.centerColor || "#fff";
  ctx.font = "800 " + Math.round(R * 0.27) + "px system-ui, sans-serif";
  ctx.fillText(opt.center || "", cx, cy - (opt.sub ? R * 0.06 : 0));
  if (opt.sub) {
    ctx.fillStyle = "#84848c";
    ctx.font = "700 " + Math.round(R * 0.10) + "px system-ui, sans-serif";
    ctx.fillText(opt.sub, cx, cy + R * 0.16);
  }
}
