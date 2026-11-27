import { loadCore, loadMixtures, fmt, getPath } from "./data.js";
import { $, $$, countUp, onVisible, initReveal, initNav } from "./ui.js";
import { initHero } from "./sections/hero.js";
import { initGlance } from "./sections/glance.js";
import { initExplorer } from "./sections/explorer.js";
import { initAnalytics, initScatter } from "./sections/analytics.js";
import { initDeta } from "./sections/deta.js";
import { initUncertainty } from "./sections/uncertainty.js";
import { initLab } from "./sections/lab.js";
import { initMethods } from "./sections/methods.js";
import { setDetailData } from "./sections/detail.js";

const note = $("#loading");

function bind(d) {
  const ctx = { counts: d.siteData.counts, deta: d.siteData.deta, ui: { n_combined: d.combined.length, n_lab_round: d.labRound.length } };
  for (const el of $$("[data-fmt]")) {
    const v = getPath(ctx, el.dataset.fmt);
    el.textContent = el.dataset.f ? fmt[el.dataset.f](v) : fmt.int(v);
  }
  for (const el of $$("[data-count]")) {
    const v = getPath(ctx, el.dataset.count);
    el.textContent = "0";
    onVisible(el, () => countUp(el, v), { threshold: 0.4 });
  }
}

function safe(name, fn) {
  try { fn(); }
  catch (e) {
    console.error(`[${name}]`, e);
    window.__siteErrors = (window.__siteErrors || []).concat(`${name}: ${e.message}`);
    document.documentElement.dataset.errors = window.__siteErrors.join(" | ");
  }
}

async function main() {
  initNav();
  initHero();
  let d;
  try {
    d = await loadCore();
  } catch (e) {
    console.error(e);
    note.classList.add("error");
    note.innerHTML = location.protocol === "file:"
      ? "This page loads the project's CSV files, which browsers block from <b>file://</b>. From the repository root run <span class='mono'>python -m http.server</span> and open <span class='mono'>http://localhost:8000/site/</span>."
      : `Could not load the project data (${e.message}). Run <span class='mono'>python run_all.py</span> to generate it.`;
    window.__siteErrors = [`load: ${e.message}`];
    return;
  }
  bind(d);
  setDetailData(d);
  safe("glance", () => initGlance(d));
  safe("explorer", () => initExplorer(d));
  safe("analytics", () => initAnalytics(d));
  safe("deta", () => initDeta(d));
  safe("uncertainty", () => initUncertainty(d));
  safe("lab", () => initLab(d));
  safe("methods", () => initMethods(d));
  initReveal();
  note.classList.add("done");
  try {
    const mixtures = await loadMixtures();
    safe("scatter", () => initScatter(d, mixtures));
  } catch (e) {
    console.error(e);
    $("#chart-scatter").innerHTML = `<div class="empty-state">The full mixture table (site/data/mixtures.csv) could not be loaded. Run <span class="mono">python -m src.viz.site_data</span>.</div>`;
  }
  document.documentElement.dataset.ready = "1";
}

main();
