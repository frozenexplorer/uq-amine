import { fmt, readable } from "../data.js";
import { $, esc, seg, showTip, hideTip, tipRows, onVisible, reduceMotion } from "../ui.js";
import { s, linear, responsive, gridX, axisX, svgRoot, barPath, niceTicks } from "../chart.js";
import { COST_PARTS, HEX } from "./common.js";
import { openDetail } from "./detail.js";

const SANS = getComputedStyle(document.documentElement).getPropertyValue("--sans") || "sans-serif";

// ------------------------------------------------------------------ performance small multiples
function perf(d) {
  const rows = [
    { name: "MEA 30%", short: "MEA 30%", r: d.mea, color: "#8b9bb3" },
    { name: "PZ 30%", short: "PZ 30%", r: d.pz, color: HEX.reference },
    { name: d.yellow[0].composition, short: "Best yellow", r: d.featuredByComp[d.yellow[0].composition], color: HEX.yellow },
    { name: d.blue[0].composition, short: "Best blue", r: d.featuredByComp[d.blue[0].composition], color: HEX.blue },
  ];
  $("#perf-legend").innerHTML = rows.map(x => `<span><i style="background:${x.color}"></i>${x.short === x.name ? esc(x.name) : `${x.short}: ${esc(x.name)}`}</span>`).join("");
  const metrics = [
    { key: "cyclic_cement_mol_per_kg", t: "Cyclic capacity", u: "mol/kg · higher is better", dg: 2 },
    { key: "q_reb_cement_gj_per_t", t: "Reboiler duty", u: "GJ/t CO₂ · lower is better", dg: 2 },
    { key: "makeup_kg_per_t", t: "Amine make-up", u: "kg/t CO₂ · lower is better", dg: 2 },
    { key: "cost_usd_per_t", t: "Running cost", u: "$/t CO₂ · lower is better", dg: 1 },
  ];
  const box = $("#chart-perf");
  for (const m of metrics) {
    const cell = document.createElement("div");
    cell.innerHTML = `<div class="sm-title">${m.t}</div><div class="sm-sub">${m.u}</div><div class="chart"></div>`;
    box.append(cell);
    const el = cell.querySelector(".chart");
    responsive(el, w => {
      const H = 4 * 30 + 30, L = 84, R = 14, T = 4;
      const max = Math.max(...rows.map(x => x.r[m.key])) * 1.02;
      const x = linear([0, max], [L, w - R]);
      const svg = svgRoot(w, H, `${m.t} for MEA, PZ, best yellow and best blue`);
      const g = s("g");
      gridX(g, x, x.ticks(3), T, T + 4 * 30);
      rows.forEach((row, i) => {
        const y = T + i * 30 + 6, v = row.r[m.key];
        g.append(s("text", { class: "row-label", x: L - 10, y: y + 13, "text-anchor": "end", text: row.short }));
        const p = s("path", { class: "mark", d: barPath(x(0), x(v), y, 18), fill: row.color });
        g.append(p);
        const inside = x(v) - x(0) > 48;
        g.append(s("text", { class: "val-label", x: inside ? x(v) - 6 : x(v) + 6, y: y + 13, "text-anchor": inside ? "end" : "start", fill: inside ? "#0b0b0b" : null, style: inside ? "fill:#0b0b0b;font-weight:600" : null, text: fmt.n(v, m.dg) }));
        g.append(s("rect", { class: "hit", x: 0, y: y - 4, width: w, height: 26,
          onmousemove: e => showTip(tipRows(row.name, [[m.t, `${fmt.n(v, m.dg)} ${m.u.split(" ·")[0]}`], ["vs MEA", fmt.signed(100 * (v / d.mea[m.key] - 1), 0) + "%"]]), e.clientX, e.clientY),
          onmouseleave: hideTip }));
      });
      const xm = x(d.mea[m.key]);
      g.append(s("line", { x1: xm, x2: xm, y1: T - 2, y2: T + 4 * 30 + 2, stroke: "#c9d3e0", "stroke-width": 1, "stroke-dasharray": "2 3", opacity: 0.6 }));
      axisX(g, x, x.ticks(3), T + 4 * 30, v => (m.dg === 1 ? v.toFixed(0) : String(+v.toFixed(2))));
      svg.append(g);
      el.append(svg);
    });
  }
}

// ------------------------------------------------------------------ cost breakdown
function cost(d) {
  const rows = [
    ...d.yellow.slice(0, 6).map(r => d.featuredByComp[r.composition]),
    ...d.blue.slice(0, 6).map(r => d.featuredByComp[r.composition]),
    d.pz, d.mea,
  ].filter(Boolean);
  let mode = "abs";
  const share = (r, k) => Math.max(0, r[k]) / COST_PARTS.reduce((a, p) => a + Math.max(0, r[p.key]), 0);
  $("#cost-legend").innerHTML = COST_PARTS.map(p => `<span><i style="background:${p.color}"></i>${p.label}</span>`).join("");
  const meaE = d.mea.cost_energy / d.mea.cost_usd_per_t, pzE = d.pz.cost_energy / d.pz.cost_usd_per_t;
  $("#cost-sub").innerHTML = `Running cost in $ per tonne CO₂, mean of cement and coal, for the six best of each family and the two references. Energy is <b>${fmt.pct(meaE)}</b> of MEA's cost and ${fmt.pct(pzE)} of PZ's.`;
  const el = $("#chart-cost");
  const redraw = responsive(el, w => {
    const above = w < 560;
    const L = above ? 0 : Math.min(220, w * 0.36), R = 46, rowH = above ? 40 : 26, T = 4;
    const H = T + rows.length * rowH + 30 + (rows.length > 12 ? 8 : 0);
    const max = mode === "abs" ? Math.max(...rows.map(r => r.cost_usd_per_t)) * 1.02 : 1;
    const x = linear([0, max], [L, w - R]);
    const svg = svgRoot(w, H, "Cost breakdown by component");
    const g = s("g");
    gridX(g, x, mode === "abs" ? x.ticks(5) : [0, 0.25, 0.5, 0.75, 1], T, H - 30);
    rows.forEach((r, i) => {
      const gap = i >= 12 ? 8 : i >= 6 ? 4 : 0;
      const y = T + i * rowH + gap + (above ? 16 : 4), bh = 16;
      const fam = r.group;
      g.append(s("circle", { cx: above ? 4 : L - 12, cy: above ? y - 9 : y + 8, r: 3.5, fill: HEX[fam] }));
      g.append(s("text", { class: "row-label", x: above ? 12 : L - 22, y: above ? y - 5 : y + 12, "text-anchor": above ? "start" : "end", text: r.composition, "font-size": above ? 11 : 12 }));
      let x0 = 0;
      const segs = s("g", { class: "mark" });
      COST_PARTS.forEach((p, j) => {
        const v = mode === "abs" ? Math.max(0, r[p.key]) : share(r, p.key);
        if (v <= 0) return;
        const xa = x(x0) + (j ? 1 : 0), xb = x(x0 + v) - 1;
        if (xb > xa) segs.append(s("rect", { x: xa, y, width: xb - xa, height: bh, fill: p.color, rx: j === 0 ? 0 : 0 }));
        x0 += v;
      });
      g.append(segs);
      g.append(s("text", { class: "val-label", x: x(x0) + 6, y: y + 12, text: mode === "abs" ? fmt.n(r.cost_usd_per_t, 1) : "" }));
      const tip = e => showTip(tipRows(r.composition, [
        ...COST_PARTS.map(p => [p.label, `$${r[p.key].toFixed(2)}`]),
        ["Total", `$${r.cost_usd_per_t.toFixed(2)}/t`],
        ["Energy share", fmt.pct(r.cost_energy / r.cost_usd_per_t)]], r.cost_viscosity < 0 ? "Negative viscosity cost: thinner than MEA (bar shows zero)." : "Click for details", fam), e.clientX, e.clientY);
      g.append(s("rect", { class: "hit", x: 0, y: y - (above ? 16 : 4), width: w, height: rowH, onmousemove: tip, onmouseleave: hideTip, onclick: () => openDetail(r) }));
    });
    axisX(g, x, mode === "abs" ? x.ticks(5) : [0, 0.25, 0.5, 0.75, 1], H - 30, v => (mode === "abs" ? "$" + v : Math.round(v * 100) + "%"));
    svg.append(g);
    el.append(svg);
  });
  seg($("#cost-mode"), v => { mode = v; redraw(); }, "mode");
}

// ------------------------------------------------------------------ savings forest
function forest(d) {
  let fam = "yellow";
  const el = $("#chart-forest");
  const all = [...d.yellow.slice(0, 15), ...d.blue.slice(0, 15)];
  const lo = Math.min(...all.map(r => r.saving_lo90)), hi = Math.max(...all.map(r => r.saving_hi90));
  const redraw = responsive(el, w => {
    const rows = d[fam].slice(0, 15);
    const above = w < 380;
    const L = above ? 8 : Math.min(200, w * 0.42), R = 12, rowH = above ? 34 : 22, T = 22;
    const H = T + rows.length * rowH + 30;
    const x = linear([Math.floor(lo), Math.ceil(hi)], [L, w - R]);
    const svg = svgRoot(w, H, `Saving against MEA with 90% intervals, top 15 ${fam}`);
    const g = s("g");
    const ticks = niceTicks(Math.floor(lo), Math.ceil(hi), 5);
    gridX(g, x, ticks, T - 6, H - 30);
    g.append(s("line", { x1: x(0), x2: x(0), y1: T - 10, y2: H - 30, stroke: "#c9d3e0", "stroke-width": 1 }));
    g.append(s("text", { x: x(0), y: T - 12, "text-anchor": "middle", class: "axis-title", text: "MEA" }));
    rows.forEach((r, i) => {
      const y = T + i * rowH + (above ? 22 : 10);
      if (above) g.append(s("text", { class: "row-label", x: L, y: y - 10, text: `${i + 1}. ${r.composition}`, "font-size": 11 }));
      else g.append(s("text", { class: "row-label", x: L - 10, y: y + 4, "text-anchor": "end", text: r.composition, "font-size": 11.5 }));
      const m = s("g", { class: "mark" });
      m.append(s("line", { x1: x(r.saving_lo90), x2: x(r.saving_hi90), y1: y, y2: y, stroke: "#6f7f97", "stroke-width": 2, "stroke-linecap": "round" }));
      m.append(s("circle", { cx: x(r.saving_vs_mea), cy: y, r: 4.5, fill: HEX[r.group], stroke: "#0d1524", "stroke-width": 2 }));
      g.append(m);
      if (i === 0) g.append(s("text", { class: "val-label", x: x(r.saving_vs_mea), y: y - 8, "text-anchor": "middle", text: fmt.usdSigned(r.saving_vs_mea) }));
      g.append(s("rect", { class: "hit", x: 0, y: y - rowH / 2 - (above ? 6 : 0), width: w, height: rowH,
        onmousemove: e => showTip(tipRows(r.composition, [["Median saving", fmt.usdSigned(r.saving_vs_mea) + "/t"], ["90 % interval", `${fmt.usdSigned(r.saving_lo90)} to ${fmt.usdSigned(r.saving_hi90)}`], ["P(cheaper than MEA)", fmt.pct(r.p_cheaper_than_mea)], ["Overall rank", "#" + r.rank]], "Click for details", r.group), e.clientX, e.clientY),
        onmouseleave: hideTip, onclick: () => openDetail(r) }));
    });
    axisX(g, x, ticks, H - 30, v => (v > 0 ? "+" : "") + v);
    g.append(s("text", { class: "axis-title", x: w - R, y: H - 2, "text-anchor": "end", text: "saving, $/t CO₂ →" }));
    svg.append(g);
    el.append(svg);
  });
  seg($("#forest-fam"), v => { fam = v; redraw(); }, "fam");
}

// ------------------------------------------------------------------ sensitivity
const SCALAR_LABEL = {
  q_mea_pilot: ["MEA reboiler duty", "GJ/t"], heat_cement: ["Heat price, cement", "$/GJ"],
  heat_coal: ["Heat price, coal", "$/GJ"], makeup_floor: ["Non-oxidative amine loss", "kg/t"],
  makeup_ox_mea: ["MEA oxidative loss", "kg/t"], vapour_mea_coal: ["MEA vapour loss", "kg/t"],
  corrosion_mea: ["Corrosion cost scale", "$/t"], viscosity_base: ["Viscosity cost scale", "$/t"],
};
function sensitivity(d) {
  const sens = d.checks.sensitivity, sc = d.siteData.scalars, n = sens.top_n;
  const names = Object.keys(sc);
  const box = $("#chart-sens");
  for (const fam of ["yellow", "blue"]) {
    const cell = document.createElement("div");
    cell.innerHTML = `<div class="sm-title"><i class="dot ${fam}" style="margin-right:6px"></i>${fam === "yellow" ? "Yellow" : "Blue"} top ${n}</div><div class="sm-sub">kept in the top ${n} when one assumption moves</div><div class="chart"></div>`;
    box.append(cell);
    const el = cell.querySelector(".chart");
    responsive(el, w => {
      const L = Math.min(200, w * 0.45), R = 16, rowH = 34, T = 6;
      const H = T + names.length * rowH + 28;
      const x = linear([10, n], [L, w - R]);
      const svg = svgRoot(w, H, `Sensitivity of the ${fam} top ${n}`);
      const g = s("g");
      gridX(g, x, [10, 12, 14, 16, 18, 20], T, H - 28);
      names.forEach((k, i) => {
        const y = T + i * rowH + 15;
        const [lab, unit] = SCALAR_LABEL[k] || [k, ""];
        const [lo, , hi] = sc[k];
        g.append(s("text", { class: "row-label", x: L - 12, y: y - 1, "text-anchor": "end", text: lab, "font-size": 11.5 }));
        g.append(s("text", { class: "tick", x: L - 12, y: y + 11, "text-anchor": "end", text: `${lo}–${hi} ${unit}`, "font-size": 9.5, fill: "#6f7f97" }));
        const vl = sens.kept_in_top_n[`${k}=low`][fam], vh = sens.kept_in_top_n[`${k}=high`][fam];
        const off = vl === vh ? 4 : 0;
        g.append(s("line", { x1: x(vl), x2: x(vh), y1: y, y2: y, stroke: "#34435c", "stroke-width": 2 }));
        g.append(s("circle", { cx: x(vl), cy: y - off, r: 5, fill: "#0d1524", stroke: HEX[fam], "stroke-width": 2 }));
        g.append(s("circle", { cx: x(vh), cy: y + off, r: 5, fill: HEX[fam], stroke: "#0d1524", "stroke-width": 1.5 }));
        g.append(s("rect", { class: "hit", x: 0, y: y - rowH / 2, width: w, height: rowH,
          onmousemove: e => showTip(tipRows(lab, [[`Low (${lo} ${unit})`, `${vl} of ${n} kept`], [`High (${hi} ${unit})`, `${vh} of ${n} kept`]]), e.clientX, e.clientY),
          onmouseleave: hideTip }));
      });
      axisX(g, x, [10, 12, 14, 16, 18, 20], H - 28, String);
      svg.append(g);
      el.append(svg);
    });
  }
  let worst = { v: Infinity };
  for (const [k, v] of Object.entries(sens.kept_in_top_n)) {
    const m = Math.min(v.yellow, v.blue);
    if (m < worst.v) worst = { v: m, k };
  }
  const [wk, wend] = worst.k.split("=");
  $("#sens-callout span").innerHTML = `Under every single change, at least <b>${sens.worst_case.yellow} yellow</b> and <b>${sens.worst_case.blue} blue</b> of the top ${n} stay. The largest effect comes from the ${(SCALAR_LABEL[wk]?.[0] || wk).toLowerCase()} at its ${wend} end.`;
}

// ------------------------------------------------------------------ scatter (canvas)
export function initScatter(d, mix) {
  const el = $("#chart-scatter");
  const pts = mix.filter(m => m.cyclic_cement_mol_per_kg != null && m.q_reb_cement_gj_per_t != null);
  const xs = pts.map(p => p.cyclic_cement_mol_per_kg).sort((a, b) => a - b);
  const ys = pts.map(p => p.q_reb_cement_gj_per_t).sort((a, b) => a - b);
  const q = (arr, f) => arr[Math.min(arr.length - 1, Math.floor(f * arr.length))];
  const xd = [Math.max(0, q(xs, 0.0) - 0.05), q(xs, 1) + 0.08];
  const yd = [Math.floor((q(ys, 0) - 0.1) * 10) / 10, q(ys, 0.995)];
  const hiddenN = pts.filter(p => p.q_reb_cement_gj_per_t > yd[1]).length;
  let cheaperOnly = false, hover = null;

  const wrap = document.createElement("div");
  wrap.style.cssText = "position:relative;width:100%;height:100%";
  const base = document.createElement("canvas"), over = document.createElement("canvas");
  over.style.cssText = "position:absolute;inset:0";
  wrap.append(base, over);
  el.append(wrap);
  const note = document.createElement("div");
  note.className = "faint mono";
  note.style.cssText = "font-size:11px;margin-top:6px";
  note.textContent = hiddenN ? `${hiddenN} mixtures with duty above ${yd[1].toFixed(1)} GJ/t lie above the plot and are not drawn.` : "";
  el.after(note);

  let W, H, dpr, x, y, grid;
  const M = { l: 54, r: 16, t: 12, b: 42 };
  const order = ["blue", "yellow"];

  function size() {
    dpr = Math.min(2, devicePixelRatio || 1);
    W = el.clientWidth; H = el.clientHeight;
    for (const c of [base, over]) { c.width = W * dpr; c.height = H * dpr; c.style.width = W + "px"; c.style.height = H + "px"; }
    x = linear(xd, [M.l, W - M.r]);
    y = linear(yd, [H - M.b, M.t]);
    grid = new Map();
    for (const p of pts) {
      if (p.q_reb_cement_gj_per_t > yd[1]) continue;
      p._x = x(p.cyclic_cement_mol_per_kg); p._y = y(p.q_reb_cement_gj_per_t);
      const k = `${Math.floor(p._x / 14)},${Math.floor(p._y / 14)}`;
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push(p);
    }
  }

  function draw() {
    const c = base.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    c.font = `10.5px ${getComputedStyle(document.body).getPropertyValue("--mono") || "monospace"}`;
    c.strokeStyle = "#1b2638"; c.lineWidth = 1; c.fillStyle = "#6f7f97";
    for (const t of x.ticks(8)) { const px = Math.round(x(t)) + 0.5; c.beginPath(); c.moveTo(px, M.t); c.lineTo(px, H - M.b); c.stroke(); c.textAlign = "center"; c.fillText(t.toFixed(1), px, H - M.b + 16); }
    for (const t of y.ticks(6)) { const py = Math.round(y(t)) + 0.5; c.beginPath(); c.moveTo(M.l, py); c.lineTo(W - M.r, py); c.stroke(); c.textAlign = "right"; c.fillText(t.toFixed(1), M.l - 8, py + 3.5); }
    c.font = `11px ${SANS}`; c.fillStyle = "#6f7f97"; c.textAlign = "center";
    c.fillText("cyclic capacity, mol CO₂ per kg solvent →", (M.l + W - M.r) / 2, H - 6);
    c.save(); c.translate(14, (M.t + H - M.b) / 2); c.rotate(-Math.PI / 2); c.fillText("← reboiler duty, GJ per t CO₂ (lower is better)", 0, 0); c.restore();
    // MEA crosshair
    const mea = pts.find(p => p.composition === "MEA 30%");
    c.strokeStyle = "rgba(201,211,224,.35)"; c.setLineDash([3, 4]);
    c.beginPath(); c.moveTo(mea._x, M.t); c.lineTo(mea._x, H - M.b); c.moveTo(M.l, mea._y); c.lineTo(W - M.r, mea._y); c.stroke();
    c.setLineDash([]);
    for (const fam of order) {
      c.fillStyle = HEX[fam];
      for (const p of pts) {
        if (p.group !== fam || p._x == null || p.q_reb_cement_gj_per_t > yd[1]) continue;
        const ok = !cheaperOnly || p.saving_vs_mea > 0;
        c.globalAlpha = ok ? (fam === "blue" ? (cheaperOnly ? 0.9 : 0.3) : 0.95) : 0.05;
        c.beginPath(); c.arc(p._x, p._y, fam === "blue" ? (cheaperOnly && ok ? 2.6 : 1.7) : 2.6, 0, 6.283); c.fill();
      }
    }
    c.globalAlpha = 1;
    for (const p of pts.filter(p => p.group === "reference")) {
      c.save(); c.translate(p._x, p._y); c.rotate(Math.PI / 4);
      c.fillStyle = "#0d1524"; c.fillRect(-6, -6, 12, 12);
      c.strokeStyle = HEX.reference; c.lineWidth = 2; c.strokeRect(-4.5, -4.5, 9, 9);
      c.restore();
      c.fillStyle = "#e8eef7"; c.font = `600 11.5px ${SANS}`; c.textAlign = "left";
      const nm = p.composition.split(" ")[0], off = { AMP: [8, -9], PZ: [10, 14] }[nm] || [10, 4];
      c.fillText(nm, p._x + off[0], p._y + off[1]);
    }
  }

  function drawHover() {
    const c = over.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    if (!hover) return;
    c.strokeStyle = "#e8eef7"; c.lineWidth = 2;
    c.beginPath(); c.arc(hover._x, hover._y, 6.5, 0, 6.283); c.stroke();
  }

  function nearest(mx, my) {
    let best = null, bd = 14 * 14;
    const gx = Math.floor(mx / 14), gy = Math.floor(my / 14);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
      for (const p of grid.get(`${gx + i},${gy + j}`) || []) {
        if (cheaperOnly && p.saving_vs_mea <= 0) continue;
        const dd = (p._x - mx) ** 2 + (p._y - my) ** 2;
        if (dd < bd || (dd === bd && p.group !== "blue")) { bd = dd; best = p; }
      }
    }
    return best;
  }

  over.addEventListener("mousemove", e => {
    const r = over.getBoundingClientRect();
    const p = nearest(e.clientX - r.left, e.clientY - r.top);
    if (p !== hover) { hover = p; drawHover(); }
    if (!p) { hideTip(); over.style.cursor = "default"; return; }
    const feat = d.featuredById[p.mixture_id];
    over.style.cursor = feat ? "pointer" : "default";
    showTip(tipRows(readable(p.composition, d.names), [
      ["Cyclic capacity", `${fmt.n(p.cyclic_cement_mol_per_kg)} mol/kg`], ["Reboiler duty", `${fmt.n(p.q_reb_cement_gj_per_t)} GJ/t`],
      ["Saving vs MEA", fmt.usdSigned(p.saving_vs_mea) + "/t"], ["Cost rank", `#${fmt.int(p.rank)}`], ["Capacity + energy rank", `#${fmt.int(p.capacity_energy_rank)}`]],
      feat ? "Click for details" : null, p.group), e.clientX, e.clientY);
  });
  over.addEventListener("mouseleave", () => { hover = null; drawHover(); hideTip(); });
  over.addEventListener("click", () => { if (hover && d.featuredById[hover.mixture_id]) openDetail(d.featuredById[hover.mixture_id]); });
  $("#sc-cheaper").addEventListener("change", e => { cheaperOnly = e.target.checked; draw(); });

  let lastW = 0;
  new ResizeObserver(() => { if (el.clientWidth !== lastW) { lastW = el.clientWidth; size(); draw(); drawHover(); } }).observe(el);
  if (!reduceMotion) { wrap.style.opacity = 0; wrap.style.transition = "opacity .8s"; onVisible(el, () => { wrap.style.opacity = 1; }); }
}

export function initAnalytics(d) {
  perf(d);
  cost(d);
  forest(d);
  sensitivity(d);
}
