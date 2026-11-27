import { fmt } from "../data.js";
import { $, esc, showTip, hideTip, tipRows } from "../ui.js";
import { s, linear, responsive, gridX, gridY, axisX, axisY, svgRoot } from "../chart.js";
import { icon } from "./common.js";

function checks(d) {
  const ch = d.checks, fr = d.calib.fit_report;
  const ratios = Object.values(ch.energy.measured_ratio);
  const [rlo, rhi] = [Math.min(...ratios), Math.max(...ratios)];
  const m = [ch.energy.model.cement.ratio_cesar1_to_mea, ch.energy.model.coal.ratio_cesar1_to_mea];
  const hl = fr.Hilliard2008_heldout;
  const dash = fr["AMP+PZ_heldout"];
  const heat = fr.Hilliard2008_heats.by_group.find(g => g.T_C === 120 && g.f_pz_N === 1);
  const cards = [
    { ok: m.every(v => v >= rlo && v <= rhi), t: "Energy against CESAR1 : MEA", big: `${fmt.n(Math.min(...m))}–${fmt.n(Math.max(...m))}`,
      p: `Model ratio, cement and coal. Published: ${fmt.n(rlo)}–${fmt.n(rhi)}. Ratios agree; absolute duty reads about 40 % low, so it is scaled to MEA.` },
    { ok: true, t: "Loading on data never fitted", big: `${fmt.n(hl["MEA+PZ"].mae_per_N, 3)} · ${fmt.n(hl.PZ.mae_per_N, 3)} · ${fmt.n(hl.MEA.mae_per_N, 3)}`,
      p: `Mean error, mol/mol N, for MEA+PZ, PZ and MEA in Hilliard (2008): ${hl["MEA+PZ"].n + hl.PZ.n + hl.MEA.n} points. MEA+PZ shows no bias (${fmt.signed(hl["MEA+PZ"].bias_per_N, 3)}).` },
    { ok: true, t: "Blend interval coverage", big: `${fmt.pct(dash.coverage90_param_only)} → ${fmt.pct(dash.coverage90_cqr_leave_group_out_mean)}`,
      p: `Held-out AMP + PZ data (Dash 2011, ${dash.n_points} points): share inside the 90 % interval, before and after the conformal margin.` },
    { ok: true, t: "Make-up anchor", big: "0.43 vs 0.45 kg/t",
      p: "CESAR1 solvent loss from the model against 0.45 kg/t measured over 400 days (Moser 2021). Good, but one measured point." },
    { ok: true, t: "Sensitivity of the lists", big: `${ch.sensitivity.worst_case.yellow} / ${ch.sensitivity.worst_case.blue} of ${ch.sensitivity.top_n}`,
      p: "Yellow / blue top-20 mixtures kept under the worst single change of a cost assumption." },
    { ok: false, t: "Beating MEA with 90 % confidence", big: "Not for the leaders",
      p: (() => {
        const c = d.siteData.counts, lo = c.cost_lo90_positive || [];
        const ex = lo[0];
        return `On capacity + energy, ${c.n_score_lo90_beats_mea_both} mixtures beat MEA at the 90 % lower bound in both scenarios. On cost, ` +
          (lo.length ? `only ${lo.length} MEA-rich blends (for example ${esc(ex.composition)}, rank #${ex.rank}) have a 5th-percentile saving above zero, at most ${fmt.usdSigned(ex.saving_lo90)}/t: small savings that are nearly certain because these blends are mostly MEA.` : "no mixture has a 5th-percentile saving above zero.") +
          ` The leaders' larger savings are probable, not proven.`;
      })() },
    { ok: false, t: "PZ heat at 120 °C", big: `${fmt.n(heat.measured, 1)} vs ${fmt.n(heat.measured + heat.bias, 1)} kJ/mol`,
      p: "Calorimetry (Hilliard 2008) against the model's VLE-based heat for PZ. The largest open question: see the stress test below." },
  ];
  $("#checks").innerHTML = cards.map(c => `<div class="check-card">
    <div class="st ${c.ok ? "ok" : "open"}">${icon(c.ok ? "check" : "alert", 13)}${c.ok ? "Passes" : "Open"}</div>
    <h4>${c.t}</h4><div class="big">${c.big}</div><p>${c.p}</p></div>`).join("");
}

function bench(d) {
  const ch = d.checks, st = d.siteData.pz_heat_stress;
  const SHORT = {
    "Verhaeghe et al. 2025 (PCCC-8), equal stripper pressure": ["Verhaeghe et al. 2025", "PCCC-8; pilot or model not stated"],
    "Mertdag thesis, ProMax simulation": ["Mertdag thesis", "ProMax process simulation"],
    "Frontiers in Energy Research 2024, biomass CHP": ["Salman et al. 2024", "techno-economic study, biomass CHP"],
  };
  const rows = [
    ...Object.entries(ch.energy.measured_ratio).map(([k, v]) => ({ k: SHORT[k]?.[0] || k, sub: SHORT[k]?.[1] || "", v, kind: "pub" })),
    { k: "This model, cement", sub: "short-cut process model", v: ch.energy.model.cement.ratio_cesar1_to_mea, kind: "model" },
    { k: "This model, coal", sub: "short-cut process model", v: ch.energy.model.coal.ratio_cesar1_to_mea, kind: "model" },
    { k: "With full calorimetric PZ heat", sub: "stress case, coal", v: ch.energy.cesar1_ratio_with_full_calorimetric_heat, kind: "stress" },
  ];
  const [lo, hi] = st.published_ratio_range;
  responsive($("#chart-bench"), w => {
    const narrow = w < 560;
    const L = narrow ? 8 : 230, R = 30, rowH = narrow ? 42 : 30, T = 8;
    const H = T + rows.length * rowH + 30;
    const x = linear([0.75, 1.05], [L, w - R]);
    const svg = svgRoot(w, H, "CESAR1 to MEA reboiler duty ratio: published values and the model");
    const g = s("g");
    g.append(s("rect", { x: x(lo), y: T, width: x(hi) - x(lo), height: H - 30 - T, fill: "rgba(92,200,224,.07)" }));
    g.append(s("text", { class: "axis-title", x: (x(lo) + x(hi)) / 2, y: H - 34, "text-anchor": "middle", text: "published range" }));
    gridX(g, x, [0.75, 0.8, 0.85, 0.9, 0.95, 1, 1.05], T, H - 30);
    rows.forEach((r, i) => {
      const y = T + i * rowH + (narrow ? 26 : 15);
      if (narrow) g.append(s("text", { class: "row-label", x: L, y: y - 12, text: r.k, "font-size": 11 }));
      else {
        g.append(s("text", { class: "row-label", x: L - 12, y: y - 1, "text-anchor": "end", text: r.k }));
        g.append(s("text", { x: L - 12, y: y + 11, "text-anchor": "end", "font-size": 10, fill: "#6f7f97", text: r.sub }));
      }
      const col = r.kind === "model" ? "#5cc8e0" : r.kind === "stress" ? "#eb6263" : "#c9d3e0";
      g.append(s("line", { x1: x(0.75), x2: x(r.v), y1: y, y2: y, stroke: "#1b2638", "stroke-width": 1 }));
      g.append(s("circle", { cx: x(r.v), cy: y, r: 5.5, fill: r.kind === "stress" ? "#0d1524" : col, stroke: r.kind === "stress" ? col : "#0d1524", "stroke-width": 2 }));
      g.append(s("text", { class: "val-label", x: x(r.v) + 10, y: y + 4, text: fmt.n(r.v, 3) }));
      g.append(s("rect", { class: "hit", x: 0, y: y - rowH / 2, width: w, height: rowH, onmousemove: e => showTip(tipRows(r.k, [["CESAR1 : MEA", fmt.n(r.v, 3)]], r.sub), e.clientX, e.clientY), onmouseleave: hideTip }));
    });
    axisX(g, x, [0.75, 0.8, 0.85, 0.9, 0.95, 1, 1.05], H - 30, v => v.toFixed(2));
    svg.append(g);
    $("#chart-bench").append(svg);
  });
}

function stress(d) {
  const st = d.siteData.pz_heat_stress, pts = st.points, nOk = d.siteData.counts.n_practical;
  const slider = $("#stress-slider");
  slider.max = pts.length - 1;
  const idxOf = u => pts.reduce((b, p, i) => (Math.abs(p.uplift - u) < Math.abs(pts[b].uplift - u) ? i : b), 0);
  const iAllowed = idxOf(st.allowed_by_benchmarks), iFull = idxOf(st.full_calorimetry);
  const [rlo, rhi] = st.published_ratio_range;
  let cur = 0;

  $("#stress-presets").innerHTML = [[0, "No extra heat"], [iAllowed, `+${fmt.n(pts[iAllowed].uplift, 1)} · benchmark limit`], [iFull, `+${fmt.n(pts[iFull].uplift, 1)} · full calorimetry`]]
    .map(([i, t]) => `<button class="chip" data-i="${i}">${t}</button>`).join("");
  $("#stress-presets").addEventListener("click", e => { const b = e.target.closest("button"); if (b) set(Number(b.dataset.i)); });
  slider.addEventListener("input", () => set(Number(slider.value)));

  $("#stress-note").innerHTML = `<b>A stress case, not an established operating result.</b> The ranking itself keeps the VLE-based heat. These curves set every uncertain input to its central value, so with no extra heat PZ 30% saves ${fmt.usdSigned(pts[0].pz30_saving)}/t here; the median over all inputs, used in the lists, is ${fmt.usdSigned(d.pz.saving_vs_mea)}/t. Full calorimetry would push CESAR1 : MEA to ${fmt.n(d.checks.energy.cesar1_ratio_with_full_calorimetric_heat)}, outside the published ${fmt.n(rlo)}–${fmt.n(rhi)}, so the published ratios argue against it. They come from AMP + PZ, not PZ alone, and none is a confirmed pilot measurement.`;

  const charts = [];
  function lineChart(el, key, yfmt, label) {
    let hoverI = null;
    const redraw = responsive(el, w => {
      const H = 170, L = 48, R = 16, T = 10, B = 28;
      const vals = pts.map(p => p[key]);
      const lo = key === "n_cheaper" ? 0 : Math.min(...vals) - 0.3, hi = Math.max(...vals) * (key === "n_cheaper" ? 1.08 : 1) + (key === "n_cheaper" ? 0 : 0.3);
      const x = linear([0, pts[pts.length - 1].uplift], [L, w - R]);
      const y = linear([lo, hi], [H - B, T]);
      const svg = svgRoot(w, H, label);
      const g = s("g");
      g.append(s("rect", { x: x(st.allowed_by_benchmarks), y: T, width: w - R - x(st.allowed_by_benchmarks), height: H - B - T, fill: "rgba(235,98,99,.06)" }));
      gridY(g, y, y.ticks(4), L, w - R);
      if (lo < 0) g.append(s("line", { x1: L, x2: w - R, y1: y(0), y2: y(0), stroke: "#c9d3e0", "stroke-width": 1, opacity: 0.6 }));
      axisY(g, y, y.ticks(4), L, yfmt);
      axisX(g, x, [0, 5, 10, 15, 20, 25], H - B, v => `+${v}`);
      g.append(s("text", { class: "axis-title", x: w - R, y: H - 2, "text-anchor": "end", text: "extra PZ heat, kJ/mol →" }));
      g.append(s("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(p.uplift).toFixed(1)},${y(p[key]).toFixed(1)}`).join(""), fill: "none", stroke: "#5cc8e0", "stroke-width": 2 }));
      for (const i of [iAllowed, iFull]) {
        g.append(s("circle", { cx: x(pts[i].uplift), cy: y(pts[i][key]), r: 3.5, fill: "#0d1524", stroke: "#a3b1c6", "stroke-width": 1.5 }));
      }
      const c = pts[cur];
      g.append(s("line", { x1: x(c.uplift), x2: x(c.uplift), y1: T, y2: H - B, stroke: "#e8eef7", "stroke-width": 1, opacity: 0.5 }));
      g.append(s("circle", { cx: x(c.uplift), cy: y(c[key]), r: 5.5, fill: "#5cc8e0", stroke: "#0d1524", "stroke-width": 2 }));
      const tx = x(c.uplift) > w - R - 90;
      g.append(s("text", { class: "val-label", x: x(c.uplift) + (tx ? -10 : 10), y: y(c[key]) - 9, "text-anchor": tx ? "end" : "start", text: yfmt(c[key]) }));
      if (hoverI != null && hoverI !== cur) {
        const hp = pts[hoverI];
        g.append(s("line", { x1: x(hp.uplift), x2: x(hp.uplift), y1: T, y2: H - B, stroke: "#6f7f97", "stroke-width": 1 }));
      }
      const hit = s("rect", { class: "hit", x: L, y: T, width: w - R - L, height: H - B - T });
      const pick = e => { const r = hit.getBoundingClientRect(); const u = x.invert((e.clientX - r.left) * (w / svg.getBoundingClientRect().width) + L); return idxOf(u); };
      hit.addEventListener("mousemove", e => {
        const i = pick(e), p = pts[i];
        if (i !== hoverI) { hoverI = i; charts.forEach(f => f()); }
        showTip(tipRows(`+${fmt.n(p.uplift, 1)} kJ/mol extra PZ heat`, [["PZ 30% saving", fmt.usdSigned(p.pz30_saving) + "/t"], ["Cheaper than MEA", `${fmt.int(p.n_cheaper)} of ${fmt.int(nOk)}`], ["CESAR1 : MEA", fmt.n(p.cesar1_mea_ratio, 3)]], "Click to set the slider"), e.clientX, e.clientY);
      });
      hit.addEventListener("mouseleave", () => { hoverI = null; hideTip(); charts.forEach(f => f()); });
      hit.addEventListener("click", e => set(pick(e)));
      g.append(hit);
      svg.append(g);
      el.append(svg);
    });
    charts.push(redraw);
  }
  lineChart($("#chart-stress-saving"), "pz30_saving", v => fmt.usdSigned(v), "PZ 30% saving against extra PZ heat");
  lineChart($("#chart-stress-count"), "n_cheaper", v => fmt.int(v), "Mixtures cheaper than MEA against extra PZ heat");

  function set(i) {
    cur = Math.max(0, Math.min(pts.length - 1, i));
    slider.value = cur;
    const p = pts[cur];
    $("#stress-val").textContent = `+${fmt.n(p.uplift, 1)} kJ/mol`;
    slider.setAttribute("aria-valuetext", `${fmt.n(p.uplift, 1)} kilojoules per mole extra; PZ 30% saving ${fmt.usdSigned(p.pz30_saving)} per tonne`);
    $("#stress-kv").innerHTML = `
      <div><span>PZ 30% saving vs MEA</span><b style="color:${p.pz30_saving >= 0 ? "var(--text)" : "var(--critical)"}">${fmt.usdSigned(p.pz30_saving)}/t</b></div>
      <div><span>Mixtures cheaper than MEA</span><b>${fmt.int(p.n_cheaper)}</b></div>
      <div><span>Best yellow</span><b style="font-size:12.5px">${esc(p.best_yellow.composition)} · ${fmt.usdSigned(p.best_yellow.saving)}</b></div>
      <div><span>Best blue</span><b style="font-size:12.5px">${esc(p.best_blue.composition)} · ${fmt.usdSigned(p.best_blue.saving)}</b></div>
      <div><span>Top 20 kept, yellow / blue</span><b>${p.kept_top20.yellow} / ${p.kept_top20.blue}</b></div>`;
    const gx = v => (100 * (v - 0.75) / 0.3).toFixed(2) + "%";
    const ok = p.cesar1_mea_ratio <= rhi + 1e-6;
    $("#stress-gauge").innerHTML = `<div class="lbl"><span>CESAR1 : MEA energy ratio implied</span><b class="mono" style="color:var(--text)">${fmt.n(p.cesar1_mea_ratio, 3)}</b></div>
      <div style="position:relative;height:14px;border-radius:7px;background:var(--surface-3)">
        <div style="position:absolute;top:0;bottom:0;left:${gx(rlo)};width:calc(${gx(rhi)} - ${gx(rlo)});background:rgba(92,200,224,.25);border-radius:7px"></div>
        <div style="position:absolute;top:-3px;width:4px;height:20px;border-radius:2px;margin-left:-2px;background:${ok ? "var(--accent)" : "var(--critical)"};left:${gx(Math.min(1.05, p.cesar1_mea_ratio))};transition:left .3s"></div>
      </div>
      <div class="lbl" style="margin-top:4px"><span>0.75</span><span>published ${fmt.n(rlo)}–${fmt.n(rhi)}</span><span>1.05</span></div>`;
    const v = $("#stress-verdict");
    v.className = "verdict " + (ok ? "ok" : "bad");
    v.innerHTML = ok
      ? `${icon("check", 15, "color:var(--good)")}<span><b>Consistent with the published ratios.</b> ${p.uplift > 0 ? "This much extra heat cannot be ruled out by the benchmarks." : "The ranking's own assumption."}</span>`
      : `${icon("alert", 15, "color:var(--critical)")}<span><b>Outside the published range.</b> The CESAR1 : MEA benchmarks argue against this much extra heat. Treat it as a stress case.</span>`;
    charts.forEach(f => f());
  }
  set(0);
}

export function initUncertainty(d) {
  checks(d);
  bench(d);
  stress(d);
}
