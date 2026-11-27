// Minimal SVG chart toolkit: scales, nice ticks, axes, responsive redraw.

const NS = "http://www.w3.org/2000/svg";

export function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid) el.append(kid);
  return el;
}

export function niceStep(span, n) {
  const raw = span / Math.max(1, n);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const r = raw / mag;
  return (r >= 5 ? 10 : r >= 2 ? 5 : r >= 1 ? 2 : 1) * mag;
}

export function niceTicks(min, max, n = 5) {
  const step = niceStep(max - min, n);
  const out = [];
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

export function linear([d0, d1], [r0, r1]) {
  const f = v => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  f.invert = p => d0 + ((p - r0) / (r1 - r0)) * (d1 - d0);
  f.domain = [d0, d1];
  f.ticks = n => niceTicks(Math.min(d0, d1), Math.max(d0, d1), n);
  return f;
}

export function log([d0, d1], [r0, r1]) {
  const l0 = Math.log10(d0), l1 = Math.log10(d1);
  const f = v => r0 + ((Math.log10(v) - l0) / (l1 - l0)) * (r1 - r0);
  f.invert = p => Math.pow(10, l0 + ((p - r0) / (r1 - r0)) * (l1 - l0));
  f.domain = [d0, d1];
  f.ticks = () => {
    const out = [];
    for (let e = Math.floor(l0); e <= Math.ceil(l1); e++)
      for (const m of [1, 2, 5]) { const v = m * Math.pow(10, e); if (v >= d0 * 0.999 && v <= d1 * 1.001) out.push(v); }
    return out;
  };
  return f;
}

export function extent(arr, acc = d => d) {
  let lo = Infinity, hi = -Infinity;
  for (const d of arr) { const v = acc(d); if (v == null || Number.isNaN(v)) continue; if (v < lo) lo = v; if (v > hi) hi = v; }
  return [lo, hi];
}

/** Redraw `draw(width)` into `el` whenever the element's width changes. */
export function responsive(el, draw) {
  let last = 0;
  const run = () => {
    const w = Math.round(el.clientWidth);
    if (w && w !== last) { last = w; el.replaceChildren(); draw(w); }
  };
  new ResizeObserver(run).observe(el);
  run();
  return () => { last = 0; run(); };
}

export function gridX(g, x, ticks, y0, y1) {
  g.append(s("g", { class: "grid" }, ticks.map(t => s("line", { x1: x(t), x2: x(t), y1: y0, y2: y1 }))));
}
export function gridY(g, y, ticks, x0, x1) {
  g.append(s("g", { class: "grid" }, ticks.map(t => s("line", { x1: x0, x2: x1, y1: y(t), y2: y(t) }))));
}
export function axisX(g, x, ticks, y, fmt = String, { x0, x1, line = true } = {}) {
  const a = s("g", { class: "axis tick" });
  if (line) a.append(s("line", { x1: x0 ?? x(x.domain[0]), x2: x1 ?? x(x.domain[1]), y1: y, y2: y }));
  for (const t of ticks) a.append(s("text", { x: x(t), y: y + 16, "text-anchor": "middle", text: fmt(t) }));
  g.append(a);
}
export function axisY(g, y, ticks, x, fmt = String) {
  const a = s("g", { class: "tick" });
  for (const t of ticks) a.append(s("text", { x: x - 8, y: y(t) + 3.5, "text-anchor": "end", text: fmt(t) }));
  g.append(a);
}

export function svgRoot(width, height, label) {
  return s("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": label });
}

/** Rounded data-end bar: 4px radius on the far end only, square at the baseline. */
export function barPath(x0, x1, y, hgt, r = 4) {
  const w = x1 - x0;
  if (Math.abs(w) < 0.5) return "";
  const dir = Math.sign(w), rr = Math.min(r, Math.abs(w), hgt / 2);
  const xe = x1 - dir * rr;
  return `M${x0},${y}H${xe}Q${x1},${y} ${x1},${y + rr}V${y + hgt - rr}Q${x1},${y + hgt} ${xe},${y + hgt}H${x0}Z`;
}
