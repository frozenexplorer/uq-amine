import { esc } from "../ui.js";

export const FAMILY = { yellow: "Yellow", blue: "Blue", reference: "Single amine" };
export const COLOR = { yellow: "var(--yellow)", blue: "var(--blue)", reference: "var(--ref)" };
export const HEX = { yellow: "#d28e05", blue: "#338ced", reference: "#c9d3e0" };

export const COST_PARTS = [
  { key: "cost_energy", label: "Energy", color: "#00a888" },
  { key: "cost_makeup", label: "Amine make-up", color: "#e76624" },
  { key: "cost_inventory", label: "First fill", color: "#9887ef" },
  { key: "cost_corrosion", label: "Corrosion", color: "#0aac23" },
  { key: "cost_viscosity", label: "Viscosity", color: "#e24d8b" },
];

export function famTag(group, extra = "") {
  return `<span class="tag ${group}"><i class="dot ${group}"></i>${FAMILY[group] ?? group}${extra}</span>`;
}

export function icon(id, size = 14, style = "") {
  return `<svg width="${size}" height="${size}" style="${style}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
}

/** Small inline interval glyph: 90 % interval bar, median dot, zero tick. */
export function ivlGlyph(lo, mid, hi, [d0, d1]) {
  const p = v => (100 * (v - d0) / (d1 - d0)).toFixed(2) + "%";
  const clamp = v => Math.max(d0, Math.min(d1, v));
  return `<span class="ivl" aria-hidden="true"><span class="zero" style="left:${p(0)}"></span>` +
    `<span class="rng" style="left:${p(clamp(lo))};width:calc(${p(clamp(hi))} - ${p(clamp(lo))})"></span>` +
    `<span class="pt" style="left:${p(clamp(mid))}"></span></span>`;
}

export function liquidusNote(r) {
  if (r.pz_liquidus_C == null) return "No PZ: no solidification risk from piperazine.";
  return `Fresh, unloaded solvent starts to solidify below about ${Math.round(r.pz_liquidus_C)} °C (measured for PZ + water; CO₂ loading lowers it).`;
}

export const escText = esc;
