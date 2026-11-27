import { fmt } from "../data.js";
import { $, esc } from "../ui.js";
import { famTag, icon } from "./common.js";
import { openDetail } from "./detail.js";

const METRICS = [
  ["Saving vs MEA", "saving_vs_mea", r => fmt.usdSigned(r.saving_vs_mea) + "/t", "hi"],
  ["P(cheaper than MEA)", "p_cheaper_than_mea", r => (r.composition === "MEA 30%" ? "—" : fmt.pct(r.p_cheaper_than_mea)), "hi"],
  ["Running cost", "cost_usd_per_t", r => "$" + fmt.n(r.cost_usd_per_t, 1) + "/t", "lo"],
  ["Cost rank", "rank", r => "#" + fmt.int(r.rank), "lo"],
  ["Cyclic capacity", "cyclic_cement_mol_per_kg", r => fmt.n(r.cyclic_cement_mol_per_kg) + " mol/kg", "hi"],
  ["Reboiler duty", "q_reb_cement_gj_per_t", r => fmt.n(r.q_reb_cement_gj_per_t) + " GJ/t", "lo"],
  ["Amine make-up", "makeup_kg_per_t", r => fmt.n(r.makeup_kg_per_t) + " kg/t", "lo"],
  ["Corrosion index", "corrosion_index", r => fmt.n(r.corrosion_index, 1), "lo"],
  ["Solid below", "pz_liquidus_C", r => (r.pz_liquidus_C == null ? "no PZ" : Math.round(r.pz_liquidus_C) + " °C"), null],
  ["Amine price", "amine_price_usd_per_kg", r => "$" + fmt.n(r.amine_price_usd_per_kg) + "/kg", "lo"],
  ["CO₂ data", "data_basis", r => (r.data_basis === "measured" ? "measured" : "partner estimated"), null],
];

export function initLab(d) {
  const items = d.labRound.map(l => ({ ...l, r: d.featuredByComp[l.composition] }));
  const missing = items.filter(i => !i.r).map(i => i.composition);
  const sel = new Set(["MEA 30%", "PZ 30%", d.blue[0].composition, d.yellow[0].composition].filter(c => items.some(i => i.composition === c)));
  const groups = [["reference", "Reference"], ["yellow", "Yellow mixtures"], ["blue", "Blue mixtures"]];

  const box = $("#lab-groups");
  box.innerHTML = groups.map(([g, title]) => {
    const its = items.filter(i => i.group === g);
    return `<div class="lab-group ${g}"><h3><i class="dot ${g}"></i>${title} <span class="faint">· ${its.length}</span></h3><div class="lab-cards">${its.map(i => {
      const r = i.r || {};
      const bench = g === "reference";
      return `<button class="lab-card ${bench ? "bench" : ""}" data-c="${esc(i.composition)}" aria-pressed="${sel.has(i.composition)}">
        <span class="tick">${icon("check", 12)}</span>
        ${bench ? `<span class="tag reference" style="align-self:flex-start">Benchmark</span>` : ""}
        <span class="nm">${esc(i.composition)}</span>
        <span class="why">${esc(i.reason)}</span>
        <span class="meta"><span>saving <b>${i.composition === "MEA 30%" ? "—" : fmt.usdSigned(r.saving_vs_mea)}</b></span><span>rank <b>#${fmt.int(r.rank)}</b></span></span>
      </button>`;
    }).join("")}</div></div>`;
  }).join("");

  box.addEventListener("click", e => {
    const b = e.target.closest(".lab-card"); if (!b) return;
    const c = b.dataset.c;
    if (sel.has(c)) sel.delete(c);
    else { sel.add(c); if (sel.size > 5) sel.delete([...sel][0]); }
    box.querySelectorAll(".lab-card").forEach(x => x.setAttribute("aria-pressed", String(sel.has(x.dataset.c))));
    tray();
  });

  function tray() {
    const chosen = items.filter(i => sel.has(i.composition) && i.r);
    const el = $("#compare-tray");
    if (chosen.length < 2) {
      el.innerHTML = `<div class="kicker">Compare</div><p class="muted" style="margin:0">Select at least two solvents above to compare them side by side (up to five).</p>`;
      return;
    }
    const body = METRICS.map(([label, key, f, better]) => {
      const vals = chosen.map(i => i.r[key]);
      const nums = vals.filter(v => typeof v === "number");
      const max = nums.length ? Math.max(...nums.map(Math.abs)) : 0;
      const bestV = better && nums.length > 1 ? (better === "hi" ? Math.max(...nums) : Math.min(...nums)) : null;
      return `<tr><td>${label}</td>${chosen.map(i => {
        const v = i.r[key];
        const isBest = bestV != null && v === bestV && !(key === "p_cheaper_than_mea" && i.composition === "MEA 30%");
        const bar = typeof v === "number" && max > 0 && key !== "rank" ? `<span class="mini"><i style="width:${(100 * Math.abs(v) / max).toFixed(1)}%"></i></span>` : "";
        return `<td class="${isBest ? "best" : ""}">${f(i.r)}${isBest ? `<span class="star" aria-label="best">★</span>` : ""}${bar}</td>`;
      }).join("")}</tr>`;
    }).join("");
    el.innerHTML = `<div class="card-head" style="margin-bottom:8px"><div><div class="kicker">Compare ${chosen.length} solvents</div><p style="margin:0">Cement case for capacity and duty; cost is the mean of both cases. ★ marks the best value in each row.</p></div></div>
      <div style="overflow-x:auto"><table><thead><tr><th></th>${chosen.map(i => `<th><div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">${famTag(i.group)}<button class="chip" style="height:auto;min-height:26px;padding:4px 10px;white-space:normal;text-align:right;line-height:1.3" data-open="${esc(i.composition)}" title="Open details">${esc(i.composition)}</button></div></th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
  }
  $("#compare-tray").addEventListener("click", e => {
    const b = e.target.closest("[data-open]"); if (!b) return;
    const it = items.find(i => i.composition === b.dataset.open);
    if (it?.r) openDetail(it.r);
  });
  tray();
  if (missing.length) console.warn("first_lab_round.csv rows without results:", missing);
}
