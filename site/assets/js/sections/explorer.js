import { fmt, parts } from "../data.js";
import { $, esc, seg } from "../ui.js";
import { ivlGlyph } from "./common.js";
import { openDetail } from "./detail.js";

const COLS = [
  { key: "pos", label: "#", cls: "l", sort: "pos" },
  { key: "composition", label: "Mixture", unit: "wt%, total 30", cls: "l" },
  { key: "saving_vs_mea", label: "Saving vs MEA", unit: "$/t CO₂ · 90 % interval", dir: -1 },
  { key: "p_cheaper_than_mea", label: "P(cheaper)", unit: "than MEA", dir: -1 },
  { key: "cyclic_cement_mol_per_kg", label: "Cyclic capacity", unit: "mol/kg", dir: -1 },
  { key: "q_reb_cement_gj_per_t", label: "Reboiler duty", unit: "GJ/t", dir: 1 },
  { key: "makeup_kg_per_t", label: "Make-up", unit: "kg/t", dir: 1 },
  { key: "corrosion_index", label: "Corrosion", unit: "MEA = 1", dir: 1 },
  { key: "pz_liquidus_C", label: "Solid below", unit: "°C, fresh", dir: 1 },
];

export function initExplorer(d) {
  const lists = {
    combined: d.combined.map((r, i) => ({ ...r, pos: i + 1 })),
    yellow: d.yellow.map((r, i) => ({ ...r, pos: i + 1 })),
    blue: d.blue.map((r, i) => ({ ...r, pos: i + 1 })),
  };
  for (const l of Object.values(lists)) for (const r of l) r._amines = parts(r.composition).map(p => p.name);

  const state = { list: "combined", q: "", solid: "", measured: false, pick: false, amines: new Set(), sort: "pos", dir: 1 };
  const table = $("#ex-table"), tbody = table.tBodies[0], thead = table.tHead;
  // shared glyph scale from typical intervals; wider ones are clipped at the ends
  const los = [], his = [];
  for (const l of Object.values(lists)) for (const r of l) { los.push(r.saving_lo90); his.push(r.saving_hi90); }
  los.sort((a, b) => a - b); his.sort((a, b) => a - b);
  const dom = [Math.min(-1, los[Math.floor(los.length * 0.1)]), Math.max(1, his[Math.floor(his.length * 0.9)])];

  // header
  thead.innerHTML = "<tr>" + COLS.map(c => `<th class="${c.cls || ""}" data-key="${c.key}" scope="col"><button type="button" aria-label="Sort by ${c.label}">${c.label}<span class="arrow">▲</span></button>${c.unit ? `<span class="u">${c.unit}</span>` : ""}</th>`).join("") + "</tr>";
  thead.addEventListener("click", e => {
    const th = e.target.closest("th"); if (!th) return;
    const col = COLS.find(c => c.key === th.dataset.key);
    if (state.sort === col.key) state.dir *= -1;
    else { state.sort = col.key; state.dir = col.dir ?? 1; }
    render(false);
  });

  function chips() {
    const counts = {};
    for (const r of lists[state.list]) for (const a of r._amines) counts[a] = (counts[a] || 0) + 1;
    const names = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b));
    for (const a of [...state.amines]) if (!counts[a]) state.amines.delete(a);
    const box = $("#ex-chips");
    box.innerHTML = `<span class="lbl">Contains</span>` + names.map(n =>
      `<button class="chip" data-a="${esc(n)}" aria-pressed="${state.amines.has(n)}">${esc(n)}<span class="n">${counts[n]}</span></button>`).join("") +
      (state.amines.size ? `<button class="chip clear" data-clear="1">Clear</button>` : "");
  }
  $("#ex-chips").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.clear) state.amines.clear();
    else state.amines.has(b.dataset.a) ? state.amines.delete(b.dataset.a) : state.amines.add(b.dataset.a);
    chips(); render(false);
  });

  function rows() {
    const q = state.q.trim().toLowerCase();
    let out = lists[state.list].filter(r => {
      if (q && !r.composition.toLowerCase().includes(q) && !r.group.includes(q)) return false;
      if (state.measured && r.data_basis !== "measured") return false;
      if (state.pick && !r.diverse_pick) return false;
      if (state.solid && r.pz_liquidus_C != null && r.pz_liquidus_C > Number(state.solid)) return false;
      for (const a of state.amines) if (!r._amines.includes(a)) return false;
      return true;
    });
    const k = state.sort, dir = state.dir;
    out = out.slice().sort((a, b) => {
      const va = a[k], vb = b[k];
      if (va == null && vb == null) return a.pos - b.pos;
      if (va == null) return 1;
      if (vb == null) return -1;
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * dir || a.pos - b.pos;
    });
    return out;
  }

  function render(animate) {
    for (const th of thead.querySelectorAll("th")) {
      const on = th.dataset.key === state.sort;
      th.toggleAttribute("aria-sort", on);
      if (on) th.setAttribute("aria-sort", state.dir > 0 ? "ascending" : "descending");
      th.querySelector(".arrow").textContent = on && state.dir < 0 ? "▼" : "▲";
    }
    const rs = rows();
    const total = lists[state.list].length;
    $("#ex-count").textContent = rs.length === total ? `${total} mixtures` : `${rs.length} of ${total} mixtures`;
    $("#ex-empty").hidden = rs.length > 0;
    tbody.innerHTML = rs.map((r, i) => {
      const sv = r.saving_vs_mea;
      const solid = r.pz_liquidus_C == null ? `<span class="faint">—</span>` : `${Math.round(r.pz_liquidus_C)}`;
      const corrFlag = r.corrosion_index >= d.siteData.counts.flag_corrosion_index;
      return `<tr tabindex="0" data-id="${r.mixture_id}" class="${animate ? "enter" : ""}" style="${animate ? `animation-delay:${Math.min(i, 24) * 14}ms` : ""}">
        <td class="rank l">${r.pos}</td>
        <td class="comp"><div class="comp-cell"><i class="dot ${r.group}" title="${r.group}"></i><span><span class="name">${esc(r.composition)}</span><span class="sub">${r.group === "reference" ? "single amine" : r.group} · overall #${r.rank}${r.data_basis !== "measured" ? " · partner estimated" : ""}</span></span></div></td>
        <td><span class="saving-cell">${ivlGlyph(r.saving_lo90, sv, r.saving_hi90, dom)}<span class="${sv >= 0 ? "pos" : "neg"}">${fmt.usdSigned(sv)}</span></span></td>
        <td>${fmt.pct(r.p_cheaper_than_mea)}</td>
        <td>${fmt.n(r.cyclic_cement_mol_per_kg)}</td>
        <td>${fmt.n(r.q_reb_cement_gj_per_t)}</td>
        <td>${fmt.n(r.makeup_kg_per_t)}</td>
        <td class="${corrFlag ? "cell-flag" : ""}">${fmt.n(r.corrosion_index, 1)}${corrFlag ? " ⚠" : ""}</td>
        <td>${solid}</td></tr>`;
    }).join("");
  }

  const open = tr => {
    const r = lists[state.list].find(x => x.mixture_id === tr.dataset.id);
    tbody.querySelectorAll("tr.selected").forEach(x => x.classList.remove("selected"));
    tr.classList.add("selected");
    openDetail(r);
  };
  tbody.addEventListener("click", e => { const tr = e.target.closest("tr"); if (tr) open(tr); });
  tbody.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { const tr = e.target.closest("tr"); if (tr) { e.preventDefault(); open(tr); } } });

  seg($("#ex-list"), v => { state.list = v; chips(); render(true); $(".table-wrap").scrollTop = 0; }, "list");
  let t;
  $("#ex-search").addEventListener("input", e => { clearTimeout(t); t = setTimeout(() => { state.q = e.target.value; render(false); }, 120); });
  $("#ex-solid").addEventListener("change", e => { state.solid = e.target.value; render(false); });
  $("#ex-measured").addEventListener("change", e => { state.measured = e.target.checked; render(false); });
  $("#ex-pick").addEventListener("change", e => { state.pick = e.target.checked; render(false); });
  $("#ex-reset").addEventListener("click", () => {
    Object.assign(state, { q: "", solid: "", measured: false, pick: false });
    state.amines.clear();
    $("#ex-search").value = ""; $("#ex-solid").value = ""; $("#ex-measured").checked = false; $("#ex-pick").checked = false;
    chips(); render(true);
  });
  chips();
  render(true);
}
