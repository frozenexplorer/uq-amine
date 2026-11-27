// Data loading. The repository files are the source of truth; the site never re-types a dataset.
// Paths are relative to site/index.html, so the site must be served from the repository root
// (python -m http.server, then open /site/).

const ROOT = "..";
export const SOURCES = {
  combined: `${ROOT}/reports/results/lab_list_combined.csv`,
  yellow: `${ROOT}/reports/results/lab_list_yellow.csv`,
  blue: `${ROOT}/reports/results/lab_list_blue.csv`,
  labRound: `${ROOT}/reports/results/first_lab_round.csv`,
  amines: `${ROOT}/data/processed/screening/amines_practical.csv`,
  checks: `${ROOT}/data/processed/practical/checks.json`,
  calib: `${ROOT}/data/processed/thermo/calibrated_core_amines.json`,
  runMeta: `${ROOT}/data/processed/screening/run_meta.json`,
  detaMeasured: `${ROOT}/data/interim/deta_chang2013.csv`,
  featured: "data/featured.csv",
  siteData: "data/site_data.json",
  mixtures: "data/mixtures.csv",
};

const NUM = /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/;

export function parseCSV(text) {
  const rows = [];
  let row = [], field = "", i = 0, q = false;
  while (i < text.length) {
    const c = text[i];
    if (q) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        q = false; i++; continue;
      }
      field += c; i++; continue;
    }
    if (c === '"') { q = true; i++; continue; }
    if (c === ",") { row.push(field); field = ""; i++; continue; }
    if (c === "\r") { i++; continue; }
    if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
    field += c; i++;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const head = rows.shift();
  return rows.filter(r => r.length > 1 || r[0] !== "").map(r => {
    const o = {};
    head.forEach((h, j) => {
      const v = r[j] ?? "";
      o[h] = v === "" ? null : NUM.test(v) ? Number(v) : v === "True" ? true : v === "False" ? false : v;
    });
    return o;
  });
}

async function get(url, kind) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return kind === "json" ? res.json() : parseCSV(await res.text());
}

export async function loadCore() {
  const keys = ["combined", "yellow", "blue", "labRound", "amines", "checks", "calib", "runMeta", "detaMeasured", "featured", "siteData"];
  const vals = await Promise.all(keys.map(k => get(SOURCES[k], SOURCES[k].endsWith(".json") ? "json" : "csv")));
  const d = Object.fromEntries(keys.map((k, i) => [k, vals[i]]));
  d.names = {};
  for (const a of d.amines) if (a.chem_name) d.names[a.name] = a.chem_name;
  d.amineInfo = Object.fromEntries(d.amines.map(a => [a.name, a]));
  d.featuredById = Object.fromEntries(d.featured.map(r => [r.mixture_id, r]));
  d.featuredByComp = Object.fromEntries(d.featured.map(r => [r.composition, r]));
  d.mea = d.featuredByComp["MEA 30%"];
  d.pz = d.featuredByComp["PZ 30%"];
  return d;
}

export const loadMixtures = () => get(SOURCES.mixtures, "csv");

// ---------------------------------------------------------------- composition helpers
const CORE = ["MEA", "MDEA", "AMP", "PZ"];
export function parts(composition) {
  return composition.split(" + ").map(s => {
    const m = s.match(/^(.*) ([\d.]+)%$/);
    return m ? { name: m[1], wt: Number(m[2]) } : { name: s, wt: NaN };
  });
}
export const isCore = n => CORE.includes(n);
/** Replace library codes (L0255) with chemical names, as the lab lists do. */
export function readable(composition, names) {
  return composition.replace(/\bL\d{4}\b/g, c => names[c] || c);
}

// ---------------------------------------------------------------- formatting
export const fmt = {
  int: x => (x == null || Number.isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US")),
  n: (x, d = 2) => (x == null || Number.isNaN(x) ? "—" : Number(x).toFixed(d)),
  signed: (x, d = 2) => (x == null || Number.isNaN(x) ? "—" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d)),
  usd: (x, d = 2) => (x == null ? "—" : (x < 0 ? "−$" : "$") + Math.abs(x).toFixed(d)),
  usdSigned: (x, d = 2) => (x == null ? "—" : (x > 0 ? "+$" : x < 0 ? "−$" : "$") + Math.abs(x).toFixed(d)),
  pct: (x, d = 0) => (x == null ? "—" : (100 * x).toFixed(d) + "%"),
  usd1: x => (x == null ? "—" : "$" + x.toFixed(1)),
};

export function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}
