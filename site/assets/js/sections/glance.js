import { fmt } from "../data.js";
import { $, h, esc, onVisible } from "../ui.js";
import { famTag, icon } from "./common.js";
import { openDetail } from "./detail.js";

function metric(k, v, d) {
  return `<div><div class="k">${k}</div><div class="v num">${v}</div>${d ? `<div class="d">${d}</div>` : ""}</div>`;
}

function rel(x, ref, lowerBetter, unit, digits = 2) {
  const diff = x - ref;
  const better = lowerBetter ? diff < 0 : diff > 0;
  return `<span class="${better ? "" : "faint"}">MEA ${fmt.n(ref, digits)}${unit}</span>`;
}

function leadIvl(r) {
  const span = Math.max(Math.abs(r.saving_lo90), Math.abs(r.saving_hi90)) * 1.12;
  const p = v => (50 + 50 * v / span).toFixed(2) + "%";
  return `<div class="lead-ivl" aria-label="Saving distribution: median ${fmt.usdSigned(r.saving_vs_mea)}, 90 % interval ${fmt.usdSigned(r.saving_lo90)} to ${fmt.usdSigned(r.saving_hi90)}">
    <div class="kicker" style="margin-bottom:4px">Saving distribution · 90 % interval</div>
    <div class="track"><span class="axis"></span><span class="zero" style="left:50%"></span><span style="position:absolute;left:50%;top:-6px;transform:translateX(-50%);font:500 10px var(--mono);color:var(--text-3)">MEA</span>
      <span class="rng" style="left:${p(r.saving_lo90)};width:calc(${p(r.saving_hi90)} - ${p(r.saving_lo90)})"></span>
      <span class="pt" style="left:${p(r.saving_vs_mea)}"></span></div>
    <div class="lbls" style="position:relative;height:16px"><span style="position:absolute;left:${p(r.saving_lo90)};transform:translateX(-100%)">${fmt.usdSigned(r.saving_lo90)}</span><span style="position:absolute;left:${p(r.saving_hi90)};transform:translateX(-100%)">${fmt.usdSigned(r.saving_hi90)}</span><span style="position:absolute;left:${p(r.saving_vs_mea)};transform:translateX(-50%);color:var(--text)">${fmt.usdSigned(r.saving_vs_mea)}</span></div>
    <p class="muted" style="font-size:12.5px;margin:10px 0 0">The interval still crosses zero: cheaper than MEA in ${fmt.pct(r.p_cheaper_than_mea)} of the uncertainty samples, not in all of them.</p>
  </div>`;
}

function mixCard(el, r, mea, { label, lead = false, n }) {
  el.innerHTML = `
    <div class="kicker">${label}</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">${famTag(r.group)}${r.rank === 1 ? `<span class="tag ok">${icon("check", 11)}#1 of ${fmt.int(n)}</span>` : `<span class="tag">#${r.rank} overall</span>`}</div>
    <div class="mix-name">${esc(r.composition)}</div>
    <div class="saving"><span class="v">${fmt.usdSigned(r.saving_vs_mea)}</span><span class="u">per tonne CO₂ saved against 30 wt% MEA</span></div>
    <div class="interval-line">90 % interval ${fmt.usdSigned(r.saving_lo90)} to ${fmt.usdSigned(r.saving_hi90)}</div>
    <div class="prob"><span>Chance cheaper than MEA</span><span class="bar"><i data-w="${100 * r.p_cheaper_than_mea}"></i></span><b class="num">${fmt.pct(r.p_cheaper_than_mea)}</b></div>
    ${lead ? `${leadIvl(r)}<div class="metric-row push">
      ${metric("Cyclic capacity", fmt.n(r.cyclic_cement_mol_per_kg) + ' <small class="muted">mol/kg</small>', rel(r.cyclic_cement_mol_per_kg, mea.cyclic_cement_mol_per_kg, false, ""))}
      ${metric("Reboiler duty", fmt.n(r.q_reb_cement_gj_per_t) + ' <small class="muted">GJ/t</small>', rel(r.q_reb_cement_gj_per_t, mea.q_reb_cement_gj_per_t, true, ""))}
      ${metric("Amine make-up", fmt.n(r.makeup_kg_per_t) + ' <small class="muted">kg/t</small>', rel(r.makeup_kg_per_t, mea.makeup_kg_per_t, true, ""))}
    </div>
    <div class="metric-row" style="margin-top:0;border-top:0;padding-top:14px">
      ${metric("Corrosion index", fmt.n(r.corrosion_index, 1), `<span>MEA = 1.0</span>`)}
      ${metric("Solid below", r.pz_liquidus_C == null ? "—" : Math.round(r.pz_liquidus_C) + " °C", "fresh solvent")}
      ${metric("Data basis", r.data_basis === "measured" ? "Measured" : "Estimated", "CO₂ model")}
    </div>` : `<div class="metric-row">
      ${metric("Capacity", fmt.n(r.cyclic_cement_mol_per_kg), "mol/kg")}
      ${metric("Duty", fmt.n(r.q_reb_cement_gj_per_t), "GJ/t")}
      ${metric("Solid below", r.pz_liquidus_C == null ? "—" : Math.round(r.pz_liquidus_C) + " °C", "fresh solvent")}
    </div>`}`;
  el.style.cursor = "pointer";
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `Open details for ${r.composition}`);
  el.addEventListener("click", () => openDetail(r));
  el.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(r); } });
}

export function initGlance(d) {
  const { mea, pz } = d;
  const bestBlue = d.blue[0], bestYellow = d.yellow[0], best = d.combined[0];
  mixCard($("#g-blue"), bestBlue, mea, { label: best.composition === bestBlue.composition ? "Best overall · best blue" : "Best blue", lead: true, n: d.siteData.counts.n_practical });
  mixCard($("#g-yellow"), bestYellow, mea, { label: "Best yellow", n: d.siteData.counts.n_practical });
  mixCard($("#g-pz"), pz, mea, { label: "Benchmark · pure PZ 30 wt%", n: d.siteData.counts.n_practical });

  const c = d.siteData.counts;
  $("#g-mea").innerHTML = `
    <div class="kicker">Reference · 30 wt% MEA</div>
    <div style="display:flex;gap:6px">${famTag("reference")}</div>
    <div class="mix-name">MEA 30%</div>
    <div class="saving"><span class="v">${fmt.usd(c.mea_cost_usd_per_t, 1)}</span><span class="u">per tonne CO₂, running cost</span></div>
    <div class="interval-line">the zero point every saving is measured from</div>
    <div class="metric-row">
      ${metric("Capacity", fmt.n(mea.cyclic_cement_mol_per_kg), "mol/kg")}
      ${metric("Duty", fmt.n(mea.q_reb_cement_gj_per_t), "GJ/t")}
      ${metric("Make-up", fmt.n(mea.makeup_kg_per_t), "kg/t")}
    </div>`;
  $("#g-count").innerHTML = `
    <div class="kicker">How many beat MEA</div>
    <div class="saving" style="margin-top:6px"><span class="v num">${fmt.int(c.n_cheaper_median)}</span><span class="u">of ${fmt.int(c.n_practical)} mixtures</span></div>
    <p class="muted" style="font-size:13.5px;margin-top:10px">are cheaper than 30 wt% MEA on their median saving. MEA itself ranks #${c.mea_rank}.</p>
    <p class="muted" style="font-size:13.5px;margin:0">For the leaders, the 90 % interval of the saving still includes zero: they are probably cheaper than MEA, not certainly.</p>`;

  // why PZ: MEA vs PZ on capacity, duty, make-up + oxidation
  const ox = n => d.amineInfo[n]?.oxidation_med;
  const items = [
    { k: "Cyclic capacity", u: "mol/kg", a: mea.cyclic_cement_mol_per_kg, b: pz.cyclic_cement_mol_per_kg, hi: true,
      txt: "Two amine nitrogens per molecule carry more CO₂ per kilogram of solvent through each absorb–strip cycle." },
    { k: "Reboiler duty", u: "GJ/t", a: mea.q_reb_cement_gj_per_t, b: pz.q_reb_cement_gj_per_t, hi: false,
      txt: `More CO₂ per kilogram means less solvent to heat and less stripping steam per tonne. Energy is ${fmt.pct(mea.cost_energy / mea.cost_usd_per_t)} of MEA's running cost.` },
    { k: "Oxidation index", u: "MEA = 1", a: ox("MEA"), b: ox("PZ"), hi: false, dg: 2,
      txt: `PZ oxidises far more slowly (measured, Obute 2025), so make-up falls from ${fmt.n(mea.makeup_kg_per_t)} to ${fmt.n(pz.makeup_kg_per_t)} kg of amine per tonne CO₂.` },
  ];
  const grid = $("#why-grid");
  for (const it of items) {
    const ch = it.hi ? (it.b / it.a - 1) : (1 - it.b / it.a);
    const max = Math.max(it.a, it.b) * 1.08;
    const card = h("div", { class: "card reveal" });
    card.innerHTML = `
      <div class="kicker">${it.k}</div>
      <div class="why-num">${it.hi ? "+" : "−"}${Math.round(100 * Math.abs(ch))}%<small>${it.hi ? "higher" : "lower"} for PZ</small></div>
      <div class="compare-bars">
        <div class="cbar"><span>MEA 30%</span><span class="track"><i style="background:var(--text-3)" data-w="${100 * it.a / max}"></i></span><span class="val">${fmt.n(it.a, it.dg ?? 2)}</span></div>
        <div class="cbar"><span>PZ 30%</span><span class="track"><i style="background:var(--accent)" data-w="${100 * it.b / max}"></i></span><span class="val">${fmt.n(it.b, it.dg ?? 2)}</span></div>
      </div>
      <p class="muted" style="font-size:13.3px;margin:0">${it.txt}</p>
      <div class="faint mono" style="font-size:11px;margin-top:10px">${it.u}</div>`;
    grid.append(card);
  }
  // animate bars when visible
  for (const el of document.querySelectorAll("#glance [data-w]")) {
    onVisible(el, x => { x.style.width = x.dataset.w + "%"; }, { threshold: 0.3 });
  }
}
