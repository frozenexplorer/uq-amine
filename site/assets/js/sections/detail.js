// Mixture detail drawer, shared by the explorer, charts and lab cards.
import { fmt, parts, isCore } from "../data.js";
import { $, esc } from "../ui.js";
import { famTag, icon, COST_PARTS, liquidusNote } from "./common.js";

let D = null, lastFocus = null;
const SEG = ["#c9d3e0", "#8b9bb3", "#5c6d87"];

export function setDetailData(d) {
  D = d;
  $("#drawer-close").addEventListener("click", closeDetail);
  $("#scrim").addEventListener("click", closeDetail);
  addEventListener("keydown", e => { if (e.key === "Escape" && $("#drawer").classList.contains("open")) closeDetail(); });
}

export function closeDetail() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("open");
  document.body.style.overflow = "";
  lastFocus?.focus?.();
}

const VS = [
  ["Saving vs MEA", "saving_vs_mea", "$/t", null, 2],
  ["Running cost", "cost_usd_per_t", "$/t", true, 2],
  ["Cyclic capacity · cement", "cyclic_cement_mol_per_kg", "mol/kg", false, 2],
  ["Cyclic capacity · coal", "cyclic_coal_mol_per_kg", "mol/kg", false, 2],
  ["Reboiler duty · cement", "q_reb_cement_gj_per_t", "GJ/t", true, 2],
  ["Reboiler duty · coal", "q_reb_coal_gj_per_t", "GJ/t", true, 2],
  ["Amine make-up", "makeup_kg_per_t", "kg/t", true, 2],
  ["Corrosion index", "corrosion_index", "MEA = 1", true, 2],
  ["Rich viscosity, 40 °C", "rich_viscosity_mpas", "mPa s", true, 1],
  ["Amine price", "amine_price_usd_per_kg", "$/kg", true, 2],
];

function delta(v, ref, lowerBetter) {
  if (lowerBetter == null || v == null || ref == null || ref === 0) return "";
  const rel = (v - ref) / Math.abs(ref);
  if (Math.abs(rel) < 0.005) return `<span class="delta same">same</span>`;
  const better = lowerBetter ? rel < 0 : rel > 0;
  return `<span class="delta ${better ? "better" : "worse"}">${rel > 0 ? "↑" : "↓"} ${Math.abs(100 * rel).toFixed(0)}% ${better ? "better" : "worse"}</span>`;
}

function stackRow(name, r, max) {
  const segs = COST_PARTS.map(p => {
    const v = Math.max(0, r[p.key] ?? 0);
    return `<i style="width:${(100 * v / max).toFixed(2)}%;background:${p.color}" title="${p.label}: $${(r[p.key] ?? 0).toFixed(2)}/t"></i>`;
  }).join("");
  return `<div class="stack-row"><span class="nm">${esc(name)}</span><span class="stack">${segs}</span><span class="tot">$${r.cost_usd_per_t.toFixed(1)}</span></div>`;
}

export function openDetail(row) {
  if (!D) return;
  const r = { ...(D.featuredById[row.mixture_id] || D.featuredByComp[row.composition] || {}), ...row };
  const mea = D.mea;
  lastFocus = document.activeElement;
  $("#drawer-title").textContent = r.composition;
  const tags = [famTag(r.group), `<span class="tag">#${fmt.int(r.rank)} of ${fmt.int(D.siteData.counts.n_practical)}</span>`,
    r.data_basis === "measured" ? `<span class="tag ok">${icon("check", 11)}measured CO₂ data</span>` : `<span class="tag est">${icon("alert", 11)}partner estimated</span>`];
  $("#drawer-tags").innerHTML = tags.join("");

  const ps = parts(r.composition);
  const compBar = ps.map((p, i) => {
    const w = 100 * p.wt / 30;
    return `<div style="width:${w}%;background:${SEG[i % 3]};color:${i === 2 ? "#fff" : "#0b0b0b"}" title="${esc(p.name)} ${p.wt}%">${w >= 9 ? p.wt + "%" : ""}</div>`;
  }).join("");
  const compLegend = ps.map((p, i) => {
    const role = isCore(p.name) ? "benchmark amine" : "partner amine";
    return `<div><span><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${SEG[i % 3]};margin-right:8px"></i><b>${esc(p.name)}</b> <span class="faint">· ${role}</span></span><span class="num">${p.wt} wt%</span></div>`;
  }).join("") + `<div><span>Water</span><span class="num">70 wt%</span></div>`;

  const sMax = Math.max(Math.abs(r.saving_lo90), Math.abs(r.saving_hi90), 1) * 1.1;
  const pos = v => (50 + 50 * v / sMax).toFixed(2) + "%";

  const vsRows = VS.map(([label, key, unit, lb, dg]) => {
    const v = r[key], ref = mea[key];
    return `<tr><td>${label} <span class="faint mono" style="font-size:11px">${unit}</span></td><td>${key === "saving_vs_mea" ? fmt.usdSigned(v) : fmt.n(v, dg)}</td><td class="faint">${key === "saving_vs_mea" ? "0" : fmt.n(ref, dg)}</td><td>${key === "saving_vs_mea" ? "" : delta(v, ref, lb)}</td></tr>`;
  }).join("");

  const hasCost = r.cost_energy != null;
  const maxCost = Math.max(r.cost_usd_per_t, mea.cost_usd_per_t);
  const costTable = hasCost ? COST_PARTS.map(p => `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${p.color};margin-right:8px"></i>${p.label}</td><td>${fmt.n(r[p.key])}</td><td class="faint">${fmt.n(mea[p.key])}</td><td>${delta(r[p.key], mea[p.key], true)}</td></tr>`).join("") : "";

  const notes = [];
  notes.push([r.pz_liquidus_C != null && r.pz_liquidus_C >= D.siteData.counts.flag_liquidus_C ? "alert" : "info", liquidusNote(r) + (r.pz_liquidus_C >= D.siteData.counts.flag_liquidus_C ? " Prepare and store warm." : "")]);
  notes.push([r.corrosion_index >= D.siteData.counts.flag_corrosion_index ? "alert" : "check",
    r.corrosion_index >= D.siteData.counts.flag_corrosion_index ? `Corrosion index ${fmt.n(r.corrosion_index, 1)}: corrosive to carbon steel, needs inhibitor or stainless.` : `Corrosion index ${fmt.n(r.corrosion_index, 1)} (MEA = 1): no corrosion flag.`]);
  notes.push(["info", `Rich-solvent viscosity about ${fmt.n(r.rich_viscosity_mpas, 1)} mPa s at 40 °C (MEA ${fmt.n(mea.rich_viscosity_mpas, 1)}); the practical filter drops anything above ${D.siteData.counts.max_rich_viscosity_mpas} mPa s.`]);
  notes.push([r.data_basis === "measured" ? "check" : "alert", r.data_basis === "measured"
    ? "Every amine in this mixture is calibrated on measured CO₂ loading data."
    : "A partner amine uses structure-based estimates. Those estimates were wrong for DETA, DEA and MPA: treat this rank as provisional."]);
  notes.push(["info", `Capacity + energy rank before cost: #${fmt.int(r.capacity_energy_rank)}.`]);
  const noteHtml = notes.map(([ic, t]) => `<li>${icon(ic, 14, `color:${ic === "alert" ? "#f1c578" : ic === "check" ? "var(--good)" : "var(--accent)"}`)}<span>${esc(t)}</span></li>`).join("");

  $("#drawer-body").innerHTML = `
    <div class="d-sec"><div class="kicker">Composition · 30 wt% total amine</div>
      <div class="comp-bar">${compBar}</div><div class="comp-legend">${compLegend}</div></div>
    <div class="d-sec"><div class="kicker">Predicted saving against 30 wt% MEA</div>
      <div class="saving" style="margin:0"><span class="v">${fmt.usdSigned(r.saving_vs_mea)}</span><span class="u">per tonne CO₂ · ${fmt.pct(r.p_cheaper_than_mea)} chance cheaper</span></div>
      <div style="position:relative;height:30px;margin:16px 0 4px">
        <div style="position:absolute;left:0;right:0;top:14px;height:1px;background:var(--grid)"></div>
        <div style="position:absolute;left:50%;top:4px;bottom:4px;width:1px;background:var(--axis)"></div>
        <div style="position:absolute;top:13px;height:3px;border-radius:2px;background:var(--text-3);left:${pos(r.saving_lo90)};width:calc(${pos(r.saving_hi90)} - ${pos(r.saving_lo90)})"></div>
        <div style="position:absolute;top:9px;width:11px;height:11px;margin-left:-5.5px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 2px var(--bg-2);left:${pos(r.saving_vs_mea)}"></div>
      </div>
      <div style="display:flex;justify-content:space-between" class="faint mono"><span style="font-size:11px">${fmt.usdSigned(r.saving_lo90)} (5th pct)</span><span style="font-size:11px">0 = MEA</span><span style="font-size:11px">${fmt.usdSigned(r.saving_hi90)} (95th pct)</span></div></div>
    <div class="d-sec"><div class="kicker">Against 30 wt% MEA</div>
      <table class="vs-table"><thead><tr><th>Metric</th><th>This</th><th>MEA</th><th></th></tr></thead><tbody>${vsRows}</tbody></table></div>
    <div class="d-sec"><div class="kicker">Cost breakdown · $ per tonne CO₂, mean of cement and coal</div>
      ${hasCost ? `${stackRow("This mixture", r, maxCost)}${stackRow("MEA 30%", mea, maxCost)}
      <table class="vs-table" style="margin-top:10px"><thead><tr><th>Component</th><th>This</th><th>MEA</th><th></th></tr></thead><tbody>${costTable}</tbody></table>
      <p class="faint" style="font-size:12px;margin:8px 0 0">Negative viscosity cost means a thinner solvent than MEA; bars show it as zero.</p>` : `<p class="muted">Cost split not available for this mixture.</p>`}</div>
    <div class="d-sec"><div class="kicker">Physical and handling considerations</div><ul class="notes-list">${noteHtml}</ul></div>`;

  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("open");
  document.body.style.overflow = "hidden";
  $("#drawer-body").scrollTop = 0;
  setTimeout(() => $("#drawer-close").focus(), 50);
}
