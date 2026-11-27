import { fmt } from "../data.js";
import { $, esc } from "../ui.js";
import { COST_PARTS } from "./common.js";

const doi = d => `<a href="https://doi.org/${d}" target="_blank" rel="noopener">doi:${d}</a>`;
const link = (u, t = "open copy") => `<a href="${u}" target="_blank" rel="noopener">${t}</a>`;

// Citations as recorded in docs/data_sources.md and the final report. DOIs only where the ledger has one.
const REFS = [
  ["Chang, Y.-C.; Leron, R. B.; Li, M.-H.", "2013", "Equilibrium solubility of carbon dioxide in aqueous solutions of (diethylenetriamine + piperazine).", "J. Chem. Thermodyn. 64, 106–113.", doi("10.1016/j.jct.2013.05.005"), "DETA calibration"],
  ["Ghalib, L.; Ali, B. S.; Ashri, W. M.; Mazari, S.", "2016", "Effect of piperazine on solubility of carbon dioxide using aqueous diethanolamine.", "Fluid Phase Equilib. 414, 1–13.", doi("10.1016/j.fluid.2015.12.056"), "DEA calibration"],
  ["Arcis, H.; Ballerat-Busserolles, K.; Rodier, L.; Coxam, J.-Y.", "2012", "Measurement and modeling of enthalpy of solution of carbon dioxide in aqueous solutions of diethanolamine at temperatures of (322.5 and 372.9) K and pressures up to 3 MPa.", "J. Chem. Eng. Data 57, 840–855.", doi("10.1021/je201012e"), "DEA heat of absorption"],
  ["Leontiadis, K.; Tzimpilis, E.; Aslanidou, D.; Tsivintzelis, I.", "2019", "Solubility of CO₂ in 3-amino-1-propanol and in N-methyldiethanolamine aqueous solutions: experimental investigation and correlation using the CPA equation of state.", "Fluid Phase Equilib. 500, 112254.", doi("10.1016/j.fluid.2019.112254"), "MDEA and MPA calibration"],
  ["Wagner, M.; von Harbou, I.; Kim, J.; Ermatchkova, I.; Maurer, G.; Hasse, H.", "2013", "Solubility of carbon dioxide in aqueous solutions of monoethanolamine in the low and high gas loading regions.", "J. Chem. Eng. Data 58, 883–895.", doi("10.1021/je301030z"), "MEA calibration"],
  ["Aronu, U. E. et al.", "2011", "Solubility of CO₂ in 15, 30, 45 and 60 mass% MEA from 40 to 120 °C and model representation using the extended UNIQUAC framework.", "Chem. Eng. Sci. 66, 6393–6406.", doi("10.1016/j.ces.2011.08.042"), "MEA calibration"],
  ["Ermatchkov, V.; Kamps, Á. P.-S.; Speyer, D.; Maurer, G.", "2006", "Solubility of carbon dioxide in aqueous solutions of piperazine in the low gas loading region.", "J. Chem. Eng. Data.", doi("10.1021/je0601917"), "PZ calibration"],
  ["Hartono, A.; Ahmad, R.; Usman, M.; Asif, N.; Svendsen, H. F.", "2020", "Solubility of CO₂ in 0.1M, 1M and 3M of 2-amino-2-methyl-1-propanol (AMP) from 313 to 393K and model representation using the eNRTL framework.", "Fluid Phase Equilib. 511, 112485.", doi("10.1016/j.fluid.2020.112485"), "AMP calibration"],
  ["Dash, S. K.; Samanta, A. N.; Bandyopadhyay, S. S.", "2011", "Solubility of carbon dioxide in aqueous solution of 2-amino-2-methyl-1-propanol and piperazine.", "Fluid Phase Equilib. 307, 166–174.", doi("10.1016/j.fluid.2011.05.009"), "Held out; sets the conformal margin"],
  ["Dey, A.; Dash, S. K.; Mandal, B.", "2018", "Equilibrium CO₂ solubility and thermophysical properties of aqueous blends of 1-(2-aminoethyl) piperazine and N-methyldiethanolamine.", "Fluid Phase Equilib. 463, 91–105.", doi("10.1016/j.fluid.2018.01.030"), "MDEA calibration"],
  ["Arcis, H.; Rodier, L.; Ballerat-Busserolles, K.; Coxam, J.-Y.", "2008", "Enthalpy of solution of CO₂ in aqueous solutions of methyldiethanolamine at T = 322.5 K and pressure up to 5 MPa.", "J. Chem. Thermodyn. 40, 1022–1029.", doi("10.1016/j.jct.2008.01.028"), "MDEA heat of absorption"],
  ["Xu, Q.", "2011", "Thermodynamics of CO₂ loaded aqueous amines.", "PhD dissertation, The University of Texas at Austin.", link("https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/Xu-2011-Thermodynamics-of-CO2-Loaded-Aqueous-Amines.pdf"), "MDEA + PZ at stripper temperatures"],
  ["Dugas, R. E.", "2009", "Carbon dioxide absorption, desorption, and diffusion in aqueous piperazine and monoethanolamine.", "PhD dissertation, The University of Texas at Austin.", link("https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/Dugas-2009-Carbon-Dioxide-Absorption-Desorption-and-Diffusion-in-Aqueous-Piperazine-and-Monoethanolamine.pdf"), "Held out: MEA, PZ, MEA + PZ"],
  ["Hilliard, M. D.", "2008", "A predictive thermodynamic model for an aqueous blend of potassium carbonate, piperazine, and monoethanolamine for carbon dioxide capture from flue gas.", "PhD dissertation, The University of Texas at Austin.", link("https://sites.utexas.edu/rochelle/wp-content/uploads/sites/3310/2015/02/Hilliard-2008-A-Predictive-Thermodynamic-Model-for-an-Aqueous-Blend-of-Potassium-Carbonate-Piperazine-and-Monoethanolamine-for-Car.pdf"), "Held-out loading, calorimetric heats, volatility, PZ solid solubility"],
  ["Wang, L.; He, L.; Liu, X.; Wang, R.", "2026", "High-cyclic-capacity ternary amine blends containing TMPDA and DETA for CO₂ capture: kinetics, stability, and corrosion analysis.", "Sep. Purif. Technol. 393, 137264.", "", "DETA blend check and corrosion"],
  ["Chen, X.; Cui, Y.; Wang, S.", "2024", "Corrosion behavior of carbon steel in diethylenetriamine solution for post-combustion CO₂ capture.", "ACS Omega 9, 13067–13080.", doi("10.1021/acsomega.3c09540"), "DETA corrosion"],
  ["Obute, J.; Onomura, T.; Rochelle, G.", "2025", "Amine screening for oxidation by bench-scale experiments.", "PCCC-8 (IEAGHG slides).", link("https://airdrive.eventsair.com/eventsairwesteuprod/production-ieaghg-public/cbe16b9807b74faea861b57fe6ac3d47", "slides"), "Oxidation indices"],
  ["Moser, P. et al.", "2021", "[ALIGN-CCUS, 18-month test of aqueous AMP/PZ (CESAR1) at Niederaussem]", "Int. J. Greenh. Gas Control 109, 103381.", link("https://researchportal.hw.ac.uk/en/publications/align-ccus-results-of-the-18-month-test-with-aqueous-amppz-solven/", "record"), "CESAR1 solvent loss, 0.45 kg/t over 400 days"],
  ["Salman, M.; Beguin, B.; Nyssen, T.; Léonard, G.", "2024", "Techno-economic analysis of AMP/PZ solvent for CO₂ capture in a biomass CHP plant: towards net negative emissions.", "Front. Energy Res. 12, 1325212.", doi("10.3389/fenrg.2024.1325212"), "CESAR1 : MEA energy benchmark"],
  ["Verhaeghe, A. et al.", "2025", "[Minimum reboiler duty of CESAR1 and MEA at equal stripper pressure]", "PCCC-8 (IEAGHG slides).", link("https://airdrive.eventsair.com/eventsairwesteuprod/production-ieaghg-public/874fd8f67f0d4351911b7e00a573f7e9", "slides"), "CESAR1 : MEA energy benchmark"],
  ["Jones, D. A.", "2018", "Technoeconomic evaluation of MEA versus mixed amines and a catalyst system for CO₂ removal at near-commercial scale at Duke Energy Gibson 3 plant and Duke Energy Buck NGCC plant.", "LLNL-TR-758732.", link("https://www.osti.gov/servlets/purl/1476188", "OSTI"), "Amine prices, steam value"],
  ["Amundsen, T. G.; Øi, L. E.; Eimer, D. A.", "2009", "[Viscosity data: MEA, CO₂-loaded]", "J. Chem. Eng. Data.", doi("10.1021/je900188m"), "Viscosity"],
  ["Freeman, S. A.; Rochelle, G. T.", "2011", "[Viscosity data: PZ, CO₂-loaded]", "J. Chem. Eng. Data.", doi("10.1021/je1012263"), "Viscosity"],
  ["Paul, S.; Mandal, B.", "2006", "[Viscosity data: MDEA, MDEA + PZ, AMP + PZ]", "J. Chem. Eng. Data.", doi("10.1021/je060195b"), "Viscosity"],
  ["Hartono, A.; Svendsen, H. F.", "2009", "[Viscosity data: DETA, unloaded]", "J. Chem. Thermodyn. 41, 973–979.", doi("10.1016/j.jct.2008.11.012"), "Viscosity"],
  ["Cho, Kim, No & Lim", "2025", "[HQNN-Amine code repository]", "Project starting point.", link("https://github.com/hclim0213/HQNN-Amine", "GitHub"), "Origin of the project"],
];

export function initMethods(d) {
  const c = d.siteData.counts, fr = d.calib.fit_report, rm = d.runMeta;
  const fitted = ["MEA", "AMP", "PZ", "MDEA", "DETA", "DEA", "MPA"];
  const nPts = fitted.reduce((a, k) => a + (fr[k]?.n_points || 0), 0);
  const stages = [
    ["01", "Measured data", "CO₂ loading and heat data from the literature, mostly via NIST ThermoML.", `${fmt.int(nPts)}`, `fitted points · ${fitted.length} amines`],
    ["02", "Calibrated model", "Aqueous-amine equilibrium model, Monte Carlo over its parameters, plus a conformal margin for blend error.", `±${fmt.n(rm.loading_discrepancy_q90, 3)}`, "mol/mol blend margin (90 %)"],
    ["03", "Screen", `Every yellow and blue mixture at ${rm.total_wt_pct} wt% total amine, both flue gases.`, fmt.int(c.n_screened), `mixtures × ${rm.mc_samples} samples × 2 cases`],
    ["04", "Practical stage", "Energy, make-up, first fill, corrosion and viscosity as one $/t, plus a practical filter.", fmt.int(c.n_practical), "pass the filter"],
    ["05", "Lab lists", "Ranked by saving against 30 wt% MEA; a 12-solvent first round.", `${d.combined.length} · ${d.yellow.length} · ${d.blue.length}`, "combined · yellow · blue"],
  ];
  $("#pipeline").innerHTML = stages.map(s => `<div class="pipe"><div class="n">${s[0]}</div><h4>${s[1]}</h4><p>${s[2]}</p><div class="stat">${s[3]}<small>${s[4]}</small></div></div>`).join("");

  const cem = rm.scenarios.cement, coal = rm.scenarios.coal;
  $("#m-screen").innerHTML = `<ul>
    <li><b>Yellow:</b> every mixture of two or more of MEA, MDEA, PZ and AMP on a ${rm.yellow_step} wt% grid (${fmt.int(rm.counts.yellow)} mixtures), plus the four single amines as references.</li>
    <li><b>Blue, stage 1:</b> one benchmark amine plus one partner at 5–25 wt% in ${rm.blue_step} wt% steps. Partners: ${rm.partner_pool.curated} curated amines and ${fmt.int(rm.partner_pool.library_kept)} of ${fmt.int(rm.partner_pool.library_total)} library amines that pass the boiling-point, pKa and solubility filters.</li>
    <li><b>Blue, stage 2:</b> three-amine blends built from the ${rm.stage2_partners.length} best purchasable partners of stage 1, every component at least 5 wt%. In total ${fmt.int(rm.counts.blue)} blue mixtures.</li>
    <li><b>Process cases:</b> absorber at ${Math.round(cem.T_abs - 273.15)} °C with ${cem.p_feed} kPa CO₂ (cement) or ${coal.p_feed} kPa (coal); stripper at ${Math.round(cem.T_strip - 273.15)} °C and ${cem.p_lean} kPa. Cyclic capacity is the rich-minus-lean CO₂ per kg of solvent. Reboiler duty is a short-cut sum of desorption heat, sensible heat and stripping steam (after Oexmann &amp; Kather, 2010).</li>
    <li><b>Uncertainty:</b> ${rm.mc_samples} Monte Carlo samples of the model parameters with common random numbers, so every mixture sees the same draw and differences between mixtures stay meaningful. Seed ${rm.seed}.</li></ul>`;

  $("#m-filter").innerHTML = `<p>A mixture leaves the list, with the reason recorded, if:</p><ul>
    <li>a partner has a reactive group such as an epoxide, aziridine, nitrile or ester (<b>${fmt.int(c.n_excluded_reactive)}</b> mixtures);</li>
    <li>a library partner has fewer than ${c.min_vendors} vendors on PubChem (<b>${fmt.int(c.n_excluded_vendors)}</b> mixtures; some fail both);</li>
    <li>its rich solvent is thicker than ${c.max_rich_viscosity_mpas} mPa s at 40 °C.</li></ul>
    <p><b>${fmt.int(c.n_practical)}</b> of ${fmt.int(c.n_screened)} remain. Two things are <b>flagged, not removed</b>: fresh solvent that solidifies above ${c.flag_liquidus_C} °C (PZ-rich mixtures), and a corrosion index of ${c.flag_corrosion_index} or more.</p>`;

  const mea = d.mea;
  const amineRows = ["MEA", "MDEA", "AMP", "PZ", "DETA", "DEA", "MPA", "DIPA", "AEP"].map(n => {
    const a = d.amineInfo[n];
    const measured = ["MEA", "MDEA", "AMP", "PZ"].includes(n) || n in d.calib.partners;
    return a ? `<tr><td style="color:var(--text)">${n}</td><td class="n">$${fmt.n(a.price_med)}</td><td class="n">${fmt.n(a.oxidation_med)}</td><td class="n">${fmt.n(a.corrosion_med, 1)} <span class="faint">(${fmt.n(a.corrosion_low, 1)}–${fmt.n(a.corrosion_high, 1)})</span></td><td>${measured ? "measured" : "estimated"}</td></tr>` : "";
  }).join("");
  $("#m-cost").innerHTML = `<div class="formula">cost [$/t CO₂] = energy + amine make-up + first fill + corrosion + viscosity</div>
    <ul>
      <li><b>Energy:</b> reboiler duty × heat price. The model is scaled so that 30 wt% MEA needs ${fmt.n(d.siteData.scalars.q_mea_pilot[1], 1)} GJ/t; heat costs $${d.siteData.scalars.heat_cement[1]}/GJ for cement (assumed) and $${d.siteData.scalars.heat_coal[1]}/GJ for coal (LLNL).</li>
      <li><b>Make-up:</b> oxidative and fixed losses plus vapour after the water wash, × price, anchored on MEA ${fmt.n(d.siteData.scalars.makeup_floor[1] + d.siteData.scalars.makeup_ox_mea[1], 1)} kg/t and the measured CESAR1 loss.</li>
      <li><b>Corrosion:</b> mass-weighted index (MEA = 1) × $${d.siteData.scalars.corrosion_mea[1]}/t. <b>Viscosity:</b> extra packing and exchanger area for thicker solvent. <b>First fill:</b> solvent inventory, annualised.</li>
      <li>Every input has a low–central–high range. The saving against MEA is computed sample by sample, so uncertainty shared by every mixture (heat price, MEA duty) cancels.</li>
    </ul>
    <table class="plain"><thead><tr><th>30 wt% MEA</th>${COST_PARTS.map(p => `<th class="n">${p.label}</th>`).join("")}<th class="n">Total</th></tr></thead>
      <tbody><tr><td>$ per t CO₂</td>${COST_PARTS.map(p => `<td class="n">${fmt.n(mea[p.key], 2)}</td>`).join("")}<td class="n">${fmt.n(mea.cost_usd_per_t, 2)}</td></tr></tbody></table>
    <table class="plain" style="margin-top:16px"><thead><tr><th>Amine</th><th class="n">Bulk price, $/kg</th><th class="n">Oxidation (MEA = 1)</th><th class="n">Corrosion (range)</th><th>CO₂ model</th></tr></thead><tbody>${amineRows}</tbody></table>
    <p class="faint" style="font-size:12.5px;margin-top:8px">Library amines are priced at $${d.amineInfo.L0255?.price_med ?? 30}/kg by assumption. Every value and its basis: data/processed/practical/amine_inputs.csv.</p>`;

  const SRC = { MEA: "Wagner 2013 + Aronu 2011", AMP: "Hartono 2020", PZ: "Ermatchkov 2006", MDEA: "Leontiadis 2019 + Dey 2018 + Xu 2011, Arcis 2008 heats", DETA: "Chang 2013", DEA: "Ghalib 2016, Arcis 2012 heats", MPA: "Leontiadis 2019" };
  const fitRows = fitted.map(k => `<tr><td style="color:var(--text)">${k}</td><td>${SRC[k]}</td><td class="n">${fr[k].n_points}</td><td class="n">${fmt.n(fr[k].mae_loading, 3)}</td></tr>`).join("");
  const dg = fr.Dugas2009_heldout.by_system, hl = fr.Hilliard2008_heldout, xu = fr["MDEA+PZ_Xu2011"].leave_one_blend_out, ap = fr["AMP+PZ_heldout"];
  $("#m-calib").innerHTML = `<p>Each amine's equilibrium constants were fitted to measured CO₂ loading (and heats where available), then tested on data the fit never saw.</p>
    <table class="plain"><thead><tr><th>Amine</th><th>Fitted to</th><th class="n">Points</th><th class="n">MAE, mol/mol</th></tr></thead><tbody>${fitRows}</tbody></table>
    <table class="plain" style="margin-top:16px"><thead><tr><th>Held-out test</th><th>System</th><th class="n">Points</th><th class="n">MAE</th></tr></thead><tbody>
      ${Object.entries(dg).map(([k, v]) => `<tr><td>Dugas 2009</td><td>${k}</td><td class="n">${v.n}</td><td class="n">${fmt.n(v.mae_loading_per_alkalinity, 3)}</td></tr>`).join("")}
      ${Object.entries(hl).map(([k, v]) => `<tr><td>Hilliard 2008</td><td>${k}</td><td class="n">${v.n}</td><td class="n">${fmt.n(v.mae_per_N, 3)}</td></tr>`).join("")}
      ${Object.entries(xu).map(([k, v]) => `<tr><td>Xu 2011, leave one blend out</td><td>${k}</td><td class="n">${v.n}</td><td class="n">${fmt.n(v.mae_loading_per_alkalinity, 3)}</td></tr>`).join("")}
      <tr><td>Dash 2011</td><td>AMP + PZ</td><td class="n">${ap.n_points}</td><td class="n">${fmt.n(ap.mae_loading_calibrated, 3)}</td></tr>
    </tbody></table>
    <p class="faint" style="font-size:12.5px;margin-top:8px">MAE per mol amine for fits; per mol alkalinity (Dugas, Xu) or per mol N (Hilliard) for held-out tests. The MEA uncertainty is widened ×${fr.MEA.interlab_sd_inflation.factor} so held-out coverage reaches ${fmt.pct(fr.MEA.interlab_sd_inflation.dugas_coverage90_inflated)}.</p>`;

  $("#m-limits").innerHTML = `<ul>
    <li><b>Absolute reboiler duty reads about 40 % low.</b> The cost stage scales it to MEA and keeps the ratios between solvents.</li>
    <li><b>No loading data above 80 °C for DETA, DEA and MPA.</b> The 120 °C stripper end is extrapolated for these amines.</li>
    <li><b>Some partners are provisional.</b> DIPA, AEP and the library amines use structure-based estimates, which were wrong for DETA, DEA and MPA.</li>
    <li><b>Many prices are indicative.</b> Several prices, and the corrosion and viscosity cost scales, are assumptions with ranges.</li>
    <li><b>Blend bias.</b> AMP + PZ keeps a ${fmt.n(ap.bias_loading_calibrated, 2)} mol/mol bias, covered by the conformal margin. Wang (2026) reports DETA blend capacities about 30 % above the model, but also above Chang's pure-DETA data.</li>
    <li><b>Not a plant design.</b> Absorption rate, foaming and nitrosamine formation are not costed.</li>
    <li><b>PZ heat at 120 °C</b> is the largest open question (see Uncertainty).</li></ul>`;

  $("#refs").innerHTML = REFS.map(([a, y, t, j, l, use]) => `<li><b>${esc(a)}</b> (${y}). ${esc(t)} <i>${esc(j)}</i> ${l}<span class="use">${esc(use)}</span></li>`).join("");
  $("#foot-data").textContent = `Data: ${d.combined.length + d.yellow.length + d.blue.length} list rows, ${fmt.int(c.n_practical)} mixtures, calibration and checks from the repository`;
}
