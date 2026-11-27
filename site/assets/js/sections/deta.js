import { fmt } from "../data.js";
import { $, $$, esc, seg, showTip, hideTip, tipRows, reduceMotion } from "../ui.js";
import { s, linear, log, responsive, gridX, gridY, axisX, axisY, svgRoot, barPath } from "../chart.js";
import { HEX } from "./common.js";

const TCOL = { 40: "#00a888", 80: "#e76624", 120: "#9887ef" };

function interpLog(px, py, p) {
  const lp = Math.log10(p);
  for (let i = 1; i < px.length; i++) {
    if (px[i] >= p) {
      const a = Math.log10(px[i - 1]), b = Math.log10(px[i]);
      return py[i - 1] + (py[i] - py[i - 1]) * (lp - a) / (b - a);
    }
  }
  return py[py.length - 1];
}

export function initDeta(d) {
  const D = d.siteData.deta;
  const meas = d.detaMeasured.filter(r => r.amine === "DETA").map(r => ({ ...r, T_C: Math.round(r.T - 273.15) }));
  const state = { w: 0.3, model: "old", showData: false, hot: false };
  const el = $("#chart-deta");
  let disp = null, anim = 0;

  const curvesFor = w => D.curves.filter(c => Math.abs(c.w - w) < 1e-6);
  const temps = () => (state.hot ? [40, 80, 120] : [40, 80]);

  function legend() {
    const items = temps().map(t => `<span><i class="line" style="background:${TCOL[t]}"></i>${t} °C${t === 120 ? " (extrapolated)" : ""}</span>`);
    if (state.model !== "calibrated") items.push(`<span style="color:var(--text-2)"><i class="dash"></i>October model</span>`);
    if (state.model !== "old") items.push(`<span><i class="line" style="background:var(--text-2)"></i>Calibrated model</span>`);
    if (state.showData) items.push(`<span><i class="circ" style="background:var(--text-2)"></i>Measured, Chang 2013</span>`);
    $("#deta-legend").innerHTML = items.join("");
  }

  function readouts() {
    const e = D.error, c = D.capacity_30wt_cement;
    $("#deta-readouts").innerHTML = `
      <div><div class="k">Mean error, all ${D.n_points} points</div><div class="v">${fmt.n(e.old.mae, 3)} → ${fmt.n(e.calibrated.mae, 3)} <small>mol/mol</small></div></div>
      <div><div class="k">Worst error at 80 °C</div><div class="v">${fmt.n(e.old.max_abs_80C, 2)} → ${fmt.n(e.calibrated.max_abs_80C, 2)} <small>mol/mol</small></div></div>
      <div><div class="k">30 wt% DETA cyclic capacity</div><div class="v">${fmt.n(c.old.cyclic_mol_per_kg)} → ${fmt.n(c.calibrated.cyclic_mol_per_kg)} <small>mol/kg</small></div><div class="k">MEA: ${fmt.n(c.MEA.cyclic_mol_per_kg)} mol/kg</div></div>`;
  }

  function target(model) {
    return Object.fromEntries(curvesFor(state.w).map(c => [c.T_C, (model === "calibrated" ? c.calibrated : c.old).slice()]));
  }

  function draw(w, from, to, t) {
    const cur = curvesFor(state.w);
    const p = cur[0].p_kpa;
    const T = 10, B = 40, L = 58, R = 70, H = Math.round(Math.min(420, Math.max(300, w * 0.52)));
    const vis = cur.filter(c => temps().includes(c.T_C));
    const ys = vis.flatMap(c => [...c.old, ...c.calibrated]).concat(meas.filter(m => Math.abs(m.w_amine - state.w) < 0.005).map(m => m.loading));
    const ymax = Math.ceil(Math.max(...ys) * 10 + 0.5) / 10;
    const x = log([p[0], p[p.length - 1]], [L, w - R]);
    const y = linear([0, ymax], [H - B, T]);
    const svg = svgRoot(w, H, "DETA CO2 loading against partial pressure: October model, calibrated model and measurements");
    const g = s("g");
    gridY(g, y, y.ticks(5), L, w - R);
    gridX(g, x, x.ticks(), T, H - B);
    axisX(g, x, x.ticks(), H - B, v => (v >= 1 ? String(v) : String(v)));
    axisY(g, y, y.ticks(5), L, v => v.toFixed(1));
    g.append(s("text", { class: "axis-title", x: (L + w - R) / 2, y: H - 6, "text-anchor": "middle", text: "CO₂ partial pressure, kPa (log scale)" }));
    g.append(s("text", { class: "axis-title", x: 12, y: (T + H - B) / 2, transform: `rotate(-90 12 ${(T + H - B) / 2})`, "text-anchor": "middle", text: "loading, mol CO₂ / mol DETA" }));
    const line = arr => arr.map((v, i) => `${i ? "L" : "M"}${x(p[i]).toFixed(1)},${y(v).toFixed(1)}`).join("");
    for (const c of vis) {
      const col = TCOL[c.T_C];
      if (state.model === "both") {
        g.append(s("path", { d: line(c.old), fill: "none", stroke: col, "stroke-width": 2, "stroke-dasharray": "5 4", opacity: 0.7 }));
        g.append(s("path", { d: line(c.calibrated), fill: "none", stroke: col, "stroke-width": 2 }));
      } else {
        const arr = to[c.T_C].map((v, i) => from[c.T_C][i] + (v - from[c.T_C][i]) * t);
        g.append(s("path", { d: line(arr), fill: "none", stroke: col, "stroke-width": 2, "stroke-dasharray": state.model === "old" ? "5 4" : null }));
      }
      const endArr = state.model === "old" ? c.old : c.calibrated;
      g.append(s("text", { x: w - R + 6, y: y(endArr[endArr.length - 1]) + 4, fill: col, "font-size": 11.5, "font-weight": 600, text: `${c.T_C} °C` }));
    }
    if (state.showData) {
      const pts = meas.filter(m => Math.abs(m.w_amine - state.w) < 0.005 && m.pCO2_kPa >= p[0] && m.pCO2_kPa <= p[p.length - 1]);
      // annotation: hot solvent at low pressure, the stripper-like corner
      const hot = pts.filter(m => m.T_C === 80).sort((a, b) => Math.abs(Math.log(a.pCO2_kPa / 2)) - Math.abs(Math.log(b.pCO2_kPa / 2)))[0];
      if (hot && state.model !== "calibrated") {
        const c80 = cur.find(c => c.T_C === 80);
        const ov = interpLog(p, c80.old, hot.pCO2_kPa);
        const xa = x(hot.pCO2_kPa);
        g.append(s("line", { x1: xa - 14, x2: xa - 14, y1: y(ov), y2: y(hot.loading), stroke: "#e8eef7", "stroke-width": 1.2 }));
        g.append(s("line", { x1: xa - 18, x2: xa - 10, y1: y(ov), y2: y(ov), stroke: "#e8eef7", "stroke-width": 1.2 }));
        g.append(s("line", { x1: xa - 18, x2: xa - 10, y1: y(hot.loading), y2: y(hot.loading), stroke: "#e8eef7", "stroke-width": 1.2 }));
        const ax = L + 14, ay = T + 22, my = (y(ov) + y(hot.loading)) / 2;
        g.append(s("path", { d: `M${xa - 18},${my}L${ax + 60},${ay + 22}`, stroke: "#6f7f97", "stroke-width": 1, fill: "none" }));
        const tx = s("text", { x: ax, y: ay, fill: "#e8eef7", "font-size": 11.5 });
        tx.append(s("tspan", { x: ax, dy: 0, "font-weight": 600, text: `Hot solvent, 80 °C and ${fmt.n(hot.pCO2_kPa, 1)} kPa` }));
        tx.append(s("tspan", { x: ax, dy: 15, fill: "#a3b1c6", text: `measured ${fmt.n(hot.loading)} vs October ${fmt.n(ov)} mol/mol` }));
        g.append(tx);
      }
      for (const m of pts) {
        if (!temps().includes(m.T_C)) continue;
        g.append(s("circle", { class: "mark", cx: x(m.pCO2_kPa), cy: y(m.loading), r: 4.5, fill: TCOL[m.T_C], stroke: "#0d1524", "stroke-width": 2 }));
      }
      const hit = s("rect", { class: "hit", x: L, y: T, width: w - R - L, height: H - B - T });
      hit.addEventListener("mousemove", e => {
        const r = hit.getBoundingClientRect(), sx = (w / r.width);
        const mx = (e.clientX - r.left) * sx + L, my = (e.clientY - r.top) * sx + T;
        let best = null, bd = 16 * 16;
        for (const m of pts) { const dd = (x(m.pCO2_kPa) - mx) ** 2 + (y(m.loading) - my) ** 2; if (dd < bd) { bd = dd; best = m; } }
        if (!best) return hideTip();
        const c = cur.find(c => c.T_C === best.T_C);
        showTip(tipRows(`${Math.round(state.w * 100)} wt% DETA · ${best.T_C} °C`, [
          ["CO₂ partial pressure", `${fmt.n(best.pCO2_kPa, 1)} kPa`], ["Measured", `${fmt.n(best.loading)} mol/mol`],
          ["October model", fmt.n(interpLog(p, c.old, best.pCO2_kPa))], ["Calibrated model", fmt.n(interpLog(p, c.calibrated, best.pCO2_kPa))]], "Chang et al. (2013), via NIST ThermoML"), e.clientX, e.clientY);
      });
      hit.addEventListener("mouseleave", hideTip);
      g.append(hit);
    }
    if (state.hot) g.append(s("text", { class: "axis-title", x: w - R, y: T + 12, "text-anchor": "end", text: "120 °C: no data, model extrapolation" }));
    svg.append(g);
    return svg;
  }

  let width = 0;
  function render(animate) {
    legend();
    const to = target(state.model === "both" ? "calibrated" : state.model);
    const from = disp && animate && !reduceMotion && state.model !== "both" ? disp : to;
    cancelAnimationFrame(anim);
    const t0 = performance.now();
    const frame = now => {
      const t = Math.min(1, (now - t0) / 700), e = 1 - Math.pow(1 - t, 3);
      el.replaceChildren(draw(width, from, to, from === to ? 1 : e));
      if (t < 1 && from !== to) anim = requestAnimationFrame(frame);
    };
    anim = requestAnimationFrame(frame);
    disp = to;
  }
  responsive(el, w => { width = w; disp = null; render(false); });

  const modelBtns = $$("#deta-model button");
  const setModelUI = m => modelBtns.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.m === m)));
  seg($("#deta-w"), v => { state.w = Number(v); disp = null; render(false); }, "w");
  seg($("#deta-model"), v => { state.model = v; state.showData = state.showData || v !== "old"; render(true); }, "m");
  $("#deta-hot").addEventListener("change", e => { state.hot = e.target.checked; disp = null; render(false); });

  const steps = $$("#deta-steps .step");
  const chartPanel = $("#deta-chart-panel"), impactPanel = $("#deta-impact-panel");
  let impactBuilt = false;
  steps.forEach(b => b.addEventListener("click", () => {
    steps.forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    const k = Number(b.dataset.step);
    if (k === 3) {
      chartPanel.hidden = true; impactPanel.hidden = false;
      if (!impactBuilt) { buildImpact(d, impactPanel); impactBuilt = true; }
      return;
    }
    chartPanel.hidden = false; impactPanel.hidden = true;
    const conf = [{ model: "old", showData: false }, { model: "old", showData: true }, { model: "calibrated", showData: true }][k];
    Object.assign(state, conf);
    setModelUI(state.model);
    render(true);
  }));
  readouts();
  partnerTable(d);
}

function buildImpact(d, box) {
  const D = d.siteData.deta, O = d.siteData.october;
  const c = D.capacity_30wt_cement;
  const first = O.rows[0];
  const sc = D.scenario;
  box.innerHTML = `
    <div class="kicker">Impact on the ranking</div>
    <div class="readouts" style="margin:0 0 20px">
      <div><div class="k">DETA mixtures in the capacity + energy top 100</div><div class="v">${O.deta_in_top100_october} → ${O.deta_in_top100_now}</div></div>
      <div><div class="k">October #1, ${esc(first.composition)}</div><div class="v">#${first.rank_october} → #${fmt.int(first.rank_now)} <small>of ${fmt.int(O.n_mixtures_now)}</small></div></div>
      <div><div class="k">30 wt% DETA cyclic capacity</div><div class="v">${fmt.n(c.old.cyclic_mol_per_kg)} → ${fmt.n(c.calibrated.cyclic_mol_per_kg)} <small>mol/kg</small></div></div>
    </div>
    <div class="twocol">
      <div><div class="sm-title">Why: hot DETA keeps its CO₂</div><div class="sm-sub">30 wt% DETA loading, lean (${sc.T_strip_C} °C, ${sc.p_lean_kpa} kPa) → rich (${sc.T_abs_C} °C, ${sc.p_feed_kpa} kPa)</div><div class="chart" id="deta-swing"></div>
        <p class="muted" style="font-size:13px;margin-top:10px">The rich end barely moves. The lean end rises from ${fmt.n(c.old.lean_loading)} to ${fmt.n(c.calibrated.lean_loading)} mol/mol: regenerated DETA still holds much of its CO₂, so each cycle carries less. Capacity falls below MEA's ${fmt.n(c.MEA.cyclic_mol_per_kg)} mol/kg.</p></div>
      <div><div class="sm-title">October rank → today's rank</div><div class="sm-sub">capacity + energy, October's top 100 still in today's screen (log scale)</div><div class="chart" id="deta-slope"></div></div>
    </div>
    <p class="faint" style="font-size:12.5px;margin:14px 0 0" id="deta-missing"></p>`;

  responsive($("#deta-swing"), w => {
    const rows = [{ k: "October model", lean: c.old.lean_loading, rich: c.old.rich_loading, cap: c.old.cyclic_mol_per_kg, dash: true },
      { k: "Calibrated", lean: c.calibrated.lean_loading, rich: c.calibrated.rich_loading, cap: c.calibrated.cyclic_mol_per_kg }];
    const L = 96, R = 16, H = 2 * 46 + 52;
    const x = linear([0, 1.3], [L, w - R]);
    const svg = svgRoot(w, H, "Lean and rich loading of 30 wt% DETA, October model and calibrated");
    const g = s("g");
    gridX(g, x, [0, 0.25, 0.5, 0.75, 1, 1.25], 4, H - 48);
    rows.forEach((r, i) => {
      const y = 22 + i * 46;
      g.append(s("text", { class: "row-label", x: L - 10, y: y + 4, "text-anchor": "end", text: r.k }));
      g.append(s("line", { x1: x(r.lean), x2: x(r.rich), y1: y, y2: y, stroke: "#00a888", "stroke-width": 6, opacity: 0.35, "stroke-linecap": "round" }));
      g.append(s("circle", { cx: x(r.lean), cy: y, r: 5.5, fill: "#9887ef", stroke: "#0d1524", "stroke-width": 2 }));
      g.append(s("circle", { cx: x(r.rich), cy: y, r: 5.5, fill: "#00a888", stroke: "#0d1524", "stroke-width": 2 }));
      g.append(s("text", { class: "val-label", x: x(r.lean), y: y - 11, "text-anchor": "middle", text: fmt.n(r.lean) }));
      g.append(s("text", { class: "val-label", x: x(r.rich), y: y - 11, "text-anchor": "middle", text: fmt.n(r.rich) }));
      g.append(s("rect", { class: "hit", x: 0, y: y - 20, width: w, height: 40, onmousemove: e => showTip(tipRows(`30 wt% DETA · ${r.k}`, [["Lean loading", fmt.n(r.lean)], ["Rich loading", fmt.n(r.rich)], ["Swing", fmt.n(r.rich - r.lean)], ["Cyclic capacity", `${fmt.n(r.cap)} mol/kg`]]), e.clientX, e.clientY), onmouseleave: hideTip }));
    });
    axisX(g, x, [0, 0.25, 0.5, 0.75, 1, 1.25], H - 48, v => v.toFixed(2));
    g.append(s("text", { class: "axis-title", x: L - 10, y: H - 32, "text-anchor": "end", text: "mol/mol" }));
    g.append(s("circle", { cx: L, cy: H - 6, r: 4, fill: "#9887ef" }));
    g.append(s("text", { x: L + 8, y: H - 2, "font-size": 11, text: "lean (stripper)" }));
    g.append(s("circle", { cx: L + 110, cy: H - 6, r: 4, fill: "#00a888" }));
    g.append(s("text", { x: L + 118, y: H - 2, "font-size": 11, text: "rich (absorber)" }));
    svg.append(g);
    $("#deta-swing").append(svg);
  });

  const present = O.rows.filter(r => r.rank_now != null);
  const missing = O.rows.filter(r => r.rank_now == null);
  $("#deta-missing").textContent = `${missing.length} of October's top 100 are not in today's screen; ${missing.filter(r => r.composition.includes("DETA")).length} of them are three-amine DETA blends. Three-amine blends are built only from the best partners, and DETA is no longer one of them, so those blends were not re-screened.`;
  const label = new Set([present[0]?.composition, present.find(r => r.color === "yellow")?.composition]);
  responsive($("#deta-slope"), w => {
    const H = 300, T = 22, B = 18, Lx = 64, Rx = w - Math.min(170, w * 0.42);
    const y = log([1, 25000], [T, H - B]);
    const svg = svgRoot(w, H, "October rank against today's rank");
    const g = s("g");
    for (const t of [1, 10, 100, 1000, 10000]) {
      g.append(s("line", { x1: Lx, x2: Rx, y1: y(t), y2: y(t), stroke: "#1b2638" }));
      g.append(s("text", { class: "tick", x: Lx - 8, y: y(t) + 3.5, "text-anchor": "end", text: "#" + fmt.int(t), "font-size": 10, fill: "#6f7f97" }));
    }
    g.append(s("text", { x: Lx, y: 12, "text-anchor": "middle", class: "axis-title", text: "October" }));
    g.append(s("text", { x: Rx, y: 12, "text-anchor": "middle", class: "axis-title", text: "Today" }));
    const sorted = present.slice().sort((a, b) => (label.has(a.composition) - label.has(b.composition)) || ((a.color === "yellow") - (b.color === "yellow")));
    for (const r of sorted) {
      const isDeta = r.composition.includes("DETA");
      const col = r.color === "yellow" ? HEX.yellow : HEX.blue;
      const on = label.has(r.composition);
      const ln = s("line", { class: "mark", x1: Lx, x2: Rx, y1: y(r.rank_october), y2: y(r.rank_now), stroke: col, "stroke-width": on ? 2.2 : 1.2, opacity: on ? 1 : isDeta ? 0.55 : 0.75 });
      g.append(ln);
      g.append(s("line", { class: "hit", x1: Lx, x2: Rx, y1: y(r.rank_october), y2: y(r.rank_now), stroke: "transparent", "stroke-width": 8,
        onmousemove: e => { ln.setAttribute("stroke-width", 3); showTip(tipRows(r.composition, [["October rank", "#" + r.rank_october], ["Today's rank", "#" + fmt.int(r.rank_now)], ["Today's cost rank", r.rank_practical_now ? "#" + fmt.int(r.rank_practical_now) : "—"]], null, r.color), e.clientX, e.clientY); },
        onmouseleave: () => { ln.setAttribute("stroke-width", on ? 2.2 : 1.2); hideTip(); } }));
      if (on) {
        const lt = s("text", { x: Rx + 8, y: y(r.rank_now) - 2, "font-size": 11, fill: "#e8eef7" });
        lt.append(s("tspan", { x: Rx + 8, "font-weight": 600, text: `#${fmt.int(r.rank_now)}` }));
        lt.append(s("tspan", { x: Rx + 8, dy: 13, fill: "#a3b1c6", text: r.composition }));
        g.append(lt);
      }
    }
    svg.append(g);
    $("#deta-slope").append(svg);
  });
}

function partnerTable(d) {
  const fr = d.calib.fit_report, e = d.siteData.deta.error;
  const rows = [
    ["DETA", "Chang 2013", fr.DETA.n_points, e.old.mae, fr.DETA.mae_loading, `30 wt% capacity ${fmt.n(d.siteData.deta.capacity_30wt_cement.old.cyclic_mol_per_kg)} → ${fmt.n(d.siteData.deta.capacity_30wt_cement.calibrated.cyclic_mol_per_kg)} mol/kg, below MEA's ${fmt.n(d.siteData.deta.capacity_30wt_cement.MEA.cyclic_mol_per_kg)}`],
    ["DEA", "Ghalib 2016 + Arcis 2012 heats", fr.DEA.n_points, fr.DEA.mae_prior, fr.DEA.mae_loading, "Heat 71–80 kJ/mol against 77 measured (Arcis 2012)"],
    ["MPA", "Leontiadis 2019", fr.MPA.n_points, fr.MPA.mae_prior, fr.MPA.mae_loading, "Moderate correction"],
  ];
  $("#partner-table").innerHTML = `<div class="kicker">Partner amines checked against data</div>
    <div style="overflow-x:auto"><table class="plain"><thead><tr><th>Partner</th><th>Measured data</th><th class="n">Points</th><th class="n">Estimate error</th><th class="n">Calibrated error</th><th>Effect</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td style="color:var(--text);font-weight:600">${r[0]}</td><td>${r[1]}</td><td class="n">${r[2]}</td><td class="n">${fmt.n(r[3], 3)}</td><td class="n" style="color:var(--good)">${fmt.n(r[4], 3)}</td><td>${r[5]}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="faint" style="font-size:12px;margin:10px 0 0">Mean absolute error in CO₂ loading, mol CO₂ per mol amine. DIPA, AEP and the library amines have no direct data and remain on structure-based estimates: the lists mark them "partner estimated".</p>`;
}
