"""
Partner-amine pool for BLUE mixtures (>= 1 core amine + >= 1 other amine).

Two sources:
  1. CURATED  - amines already used in published CO2-capture blends, with approximate
                literature pKa1 (sd 0.3; values marked "verify" until checked).
  2. LIBRARY  - the 945-compound Zenodo screening library, pKa1 from OPERA's predicted
                basic pKa (sd = OPERA's error measured on amines with known pKa).

Every partner is turned into an AmineModel by structure rules (RDKit):
  * each basic aliphatic N is one independent site (polyamine = several sites, each
    at the amine's molality)
  * site class: primary / secondary / secondary-ring / tertiary, hindered if an
    alpha-carbon carries >= 3 carbons (AMP-like)
  * strongest site gets pKa1; further sites are shifted down by an amount set by the
    bond distance to the nearest already-assigned site (EDA ~3, 1,3-diamines ~2, ...)
  * protonation dH and carbamate stability come from class priors, anchored on the
    calibrated core amines (MEA-like primary, PZ-like ring secondary, AMP-like hindered)

Physical feasibility filters, applied to BOTH sources (all configurable): CHNO only,
strongest pKa >= 8 (enough basicity to absorb at 40 C), boiling point >= 165 C (no more
volatile than AMP, the most volatile core amine; curated amines use literature boiling
points, library amines OPERA predictions), water solubility >= 1 mol/L (library only;
the curated amines are all water-miscible), MW <= 250. Rejected curated amines are
reported, not silently dropped.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors

from src.thermo.chemistry import AmineModel, Species

RDLogger.DisableLog("rdApp.*")
ROOT = Path(__file__).resolve().parents[2]
LIBRARY_CSV = ROOT / "data" / "processed" / "structured" / "candidate_amines_screening_library.csv"

FILTERS = dict(min_pka=8.0, min_bp_c=165.0, min_logws=0.0, max_mw=250.0)

# ---------------------------------------------------------------------------
# Class priors: (protonation dH, sd), (carbamate logK25, sd, dH, sd) or None
# ---------------------------------------------------------------------------
PROT_DH = {
    "primary": (-51.0, 6.0),
    "primary_hindered": (-58.0, 6.0),   # AMP calibrated -61
    "secondary": (-45.0, 6.0),
    "secondary_ring": (-44.0, 6.0),     # PZ calibrated -44.5
    "secondary_hindered": (-50.0, 7.0),
    "tertiary": (-37.0, 6.0),           # MDEA -34.9
}
CARBAMATE = {
    "primary": (1.4, 0.5, -22.0, 10.0),          # MEA-like
    "primary_hindered": (-1.5, 0.6, -18.0, 12.0),  # AMP calibrated -1.55
    "secondary": (0.6, 0.6, -18.0, 10.0),        # DEA-like, less stable than MEA
    "secondary_ring": (1.3, 0.5, -25.0, 10.0),   # PZ calibrated 1.34 / -26.8
    "secondary_hindered": (-1.2, 0.7, -18.0, 12.0),
    "tertiary": None,
}
PKA_SHIFT_BY_BONDS = {2: 4.5, 3: 3.5, 4: 2.0, 5: 1.2}   # >= 6 bonds -> 0.8
SUBSEQUENT_SITE_SD = 1.0

# Curated partners: name, SMILES, literature pKa1 at 25 C, normal boiling point (C).
# Approximate handbook values - verify before citing.
CURATED = [
    ("DEA", "OCCNCCO", 8.88, 269),
    ("MMEA", "CNCCO", 9.85, 158),
    ("EAE", "CCNCCO", 9.90, 169),
    ("DIPA", "CC(O)CNCC(C)O", 8.84, 249),
    ("DMEA", "CN(C)CCO", 9.23, 134),
    ("DEEA", "CCN(CC)CCO", 9.75, 162),
    ("TEA", "OCCN(CCO)CCO", 7.76, 335),
    ("MPA", "NCCCO", 9.96, 187),
    ("EDA", "NCCN", 9.93, 116),
    ("MAPA", "CNCCCN", 10.50, 140),
    ("DMAPA", "CN(C)CCCN", 10.10, 134),
    ("DETA", "NCCNCCN", 9.84, 207),
    ("AEP", "NCCN1CCNCC1", 9.48, 222),
    ("HEPZ", "OCCN1CCNCC1", 9.05, 246),
    ("1MPZ", "CN1CCNCC1", 9.14, 138),
    ("TMPDA", "CN(C)CCCN(C)C", 9.80, 145),
    ("HMPD", "CN1CCC(O)CC1", 9.40, 200),
]


def canon(smi: str) -> Optional[str]:
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else None


# ---------------------------------------------------------------------------
# Structure analysis
# ---------------------------------------------------------------------------
def _is_basic_n(atom) -> bool:
    if atom.GetAtomicNum() != 7 or atom.GetIsAromatic() or atom.GetFormalCharge() != 0:
        return False
    for b in atom.GetBonds():
        if b.GetBondType() != Chem.BondType.SINGLE:
            return False                                  # imine / nitrile
    for nb in atom.GetNeighbors():
        if nb.GetAtomicNum() not in (1, 6):
            return False                                  # N-N, N-O, N-S
        if nb.GetIsAromatic():
            return False                                  # aniline-type, weakly basic
        for b in nb.GetBonds():
            other = b.GetOtherAtom(nb)
            if b.GetBondType() == Chem.BondType.DOUBLE and other.GetAtomicNum() in (7, 8, 16):
                return False                              # amide / urea / amidine
    return True


def _site_class(atom) -> str:
    nH = atom.GetTotalNumHs()
    carbons = [nb for nb in atom.GetNeighbors() if nb.GetAtomicNum() == 6]
    hindered = any(sum(1 for x in c.GetNeighbors() if x.GetAtomicNum() == 6) >= 3 for c in carbons)
    if nH >= 2:
        return "primary_hindered" if hindered else "primary"
    if nH == 1:
        if hindered:
            return "secondary_hindered"
        return "secondary_ring" if atom.IsInRing() else "secondary"
    return "tertiary"


_BASICITY_ORDER = {"secondary_ring": 0, "secondary": 1, "primary": 2, "secondary_hindered": 3,
                   "primary_hindered": 4, "tertiary": 5}


@dataclass
class Partner:
    name: str
    smiles: str
    mw: float
    pka1: float
    pka1_sd: float
    origin: str               # curated | library
    site_classes: List[str]
    site_pkas: List[float]
    props: dict


def analyse(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    sites = [a for a in mol.GetAtoms() if _is_basic_n(a)]
    if not sites:
        return None
    classes = [_site_class(a) for a in sites]
    order = sorted(range(len(sites)), key=lambda i: _BASICITY_ORDER[classes[i]])
    dm = Chem.GetDistanceMatrix(mol)
    return mol, [sites[i].GetIdx() for i in order], [classes[i] for i in order], dm


def _pka_sequence(pka1: float, atom_idx, dm) -> List[float]:
    pkas = [pka1]
    for k in range(1, len(atom_idx)):
        d = int(min(dm[atom_idx[k], atom_idx[j]] for j in range(k)))
        pkas.append(pkas[-1] - PKA_SHIFT_BY_BONDS.get(d, 0.8) if d < 6 else pkas[-1] - 0.8)
    return pkas


def protonation_order(atom_idx: List[int], classes: List[str], pka1: float, dm):
    """
    Order in which a polyamine's sites protonate. Protons go first to sites that are
    far apart (least electrostatic repulsion), so choose the order that maximises the
    total of the site pKas; class basicity only breaks ties. Recovers e.g. DETA
    (terminal primaries 9.8 / 9.0, central secondary ~5; literature 9.84 / 9.02 / 4.23)
    and EDA (9.9 / 6.4; literature 9.93 / 6.85). Returns (atom_idx, classes, pkas).
    """
    if len(atom_idx) == 1:
        return atom_idx, classes, [pka1]
    best = None
    for perm in itertools.permutations(range(len(atom_idx))):
        idx = [atom_idx[i] for i in perm]
        pk = _pka_sequence(pka1, idx, dm)
        key = (round(sum(pk), 6), -sum(_BASICITY_ORDER[classes[i]] * (len(perm) - r)
                                       for r, i in enumerate(perm)))
        if best is None or key > best[0]:
            best = (key, perm, pk)
    _, perm, pk = best
    return [atom_idx[i] for i in perm], [classes[i] for i in perm], pk


def build_model(p: Partner) -> AmineModel:
    sites = []
    for k, (cls, pka) in enumerate(zip(p.site_classes, p.site_pkas)):
        dh, dh_sd = PROT_DH[cls]
        sd_pka = p.pka1_sd if k == 0 else float(np.hypot(p.pka1_sd, SUBSEQUENT_SITE_SD))
        sp = [Species(f"{p.name}#{k}", 0, 0, 0.0, 0.0),
              Species(f"{p.name}#{k}H+", 1, 0, pka, dh, sd_pka, dh_sd)]
        carb = CARBAMATE[cls]
        if carb is not None:
            lk, lk_sd, cdh, cdh_sd = carb
            sp.append(Species(f"{p.name}#{k}COO-", 0, 1, lk, cdh, lk_sd, cdh_sd))
        sites.append(AmineModel(f"{p.name}#{k}", p.smiles, p.mw, sp))
    model = AmineModel(p.name, p.smiles, p.mw, sites[0].species, sites=len(sites),
                       source=p.origin, site_models=sites,
                       note=f"{len(sites)} basic N: {', '.join(p.site_classes)}")
    return model


# ---------------------------------------------------------------------------
# Pool assembly
# ---------------------------------------------------------------------------
def opera_pka_error(lib: pd.DataFrame, known: dict) -> tuple:
    """Compare OPERA pKa_b_pred with literature pKa1 for amines present in the library."""
    rows = []
    for name, (smi, pka) in known.items():
        hit = lib[lib["canon"] == canon(smi)]
        if len(hit) and pd.notna(hit["pKa_b_pred"].iloc[0]):
            rows.append((name, pka, float(hit["pKa_b_pred"].iloc[0])))
    if not rows:
        return 0.8, pd.DataFrame()
    df = pd.DataFrame(rows, columns=["amine", "pka_literature", "pka_opera"])
    rmse = float(np.sqrt(np.mean((df.pka_opera - df.pka_literature) ** 2)))
    return max(rmse, 0.5), df


def build_pool(core_smiles: dict, filters: dict = FILTERS, verbose: bool = True):
    lib = pd.read_csv(LIBRARY_CSV)
    lib["canon"] = lib["std_smiles"].map(canon)

    known = {n: (s, p) for n, s, p, _ in CURATED}
    known.update({"MEA": ("NCCO", 9.50), "MDEA": ("CN(CCO)CCO", 8.56),
                  "AMP": ("CC(C)(N)CO", 9.68), "PZ": ("C1CNCCN1", 9.73)})
    opera_sd, opera_check = opera_pka_error(lib, known)

    exclude = {canon(s) for s in core_smiles.values()}
    partners: List[Partner] = []
    log = {"curated": 0, "library_total": len(lib)}

    curated_rejected = {}
    for name, smi, pka, bp in CURATED:
        a = analyse(smi)
        if a is None or canon(smi) in exclude:
            continue
        exclude.add(canon(smi))   # literature data wins: a rejected amine stays rejected
        if pka < filters["min_pka"]:
            curated_rejected[name] = f"pKa {pka} < {filters['min_pka']}"
            continue
        if bp < filters["min_bp_c"]:
            curated_rejected[name] = f"boiling point {bp} C < {filters['min_bp_c']} C"
            continue
        mol, idx, classes, dm = a
        idx, classes, pkas = protonation_order(idx, classes, pka, dm)
        partners.append(Partner(name, canon(smi), Descriptors.MolWt(mol), pka, 0.3, "curated",
                                classes, pkas,
                                {"pka_source": "literature (approx., verify)",
                                 "bp_lit_c": float(bp)}))
        exclude.add(canon(smi))
    log["curated"] = len(partners)
    log["curated_rejected"] = curated_rejected

    reasons = {"duplicate/core": 0, "not CHNO": 0, "no basic N": 0, "pKa": 0, "BP": 0,
               "solubility": 0, "MW": 0}
    for r in lib.itertuples(index=False):
        c = r.canon
        if c is None or c in exclude:
            reasons["duplicate/core"] += 1
            continue
        mol = Chem.MolFromSmiles(c)
        if any(a.GetSymbol() not in ("C", "N", "O") for a in mol.GetAtoms()):
            reasons["not CHNO"] += 1
            continue
        a = analyse(c)
        if a is None:
            reasons["no basic N"] += 1
            continue
        if not (pd.notna(r.pKa_b_pred) and r.pKa_b_pred >= filters["min_pka"]):
            reasons["pKa"] += 1
            continue
        if r.BP_pred < filters["min_bp_c"]:
            reasons["BP"] += 1
            continue
        if r.LogWS_pred < filters["min_logws"]:
            reasons["solubility"] += 1
            continue
        if r.MolWeight > filters["max_mw"]:
            reasons["MW"] += 1
            continue
        _, idx, classes, dm = a
        idx, classes, pkas = protonation_order(idx, classes, float(r.pKa_b_pred), dm)
        name = f"L{len(partners):04d}"
        cas = getattr(r, "cas", None)
        partners.append(Partner(
            name, c, float(r.MolWeight), float(r.pKa_b_pred), opera_sd, "library", classes,
            pkas,
            {"cas": cas if isinstance(cas, str) else None, "bp_pred_c": float(r.BP_pred),
             "logws_pred": float(r.LogWS_pred), "logvp_pred": float(r.LogVP_pred),
             "dg_md": float(r.dGMD) if pd.notna(r.dGMD) else None,
             "dg_pred": float(r.dg_avg_pred) if pd.notna(r.dg_avg_pred) else None,
             "pka_source": "OPERA prediction"}))
        exclude.add(c)
    log["library_kept"] = len(partners) - log["curated"]
    log["library_rejected"] = reasons
    log["opera_pka_sd"] = opera_sd
    if verbose:
        print(f"partners: {log['curated']} curated + {log['library_kept']} library "
              f"(of {log['library_total']}); OPERA pKa sd used = {opera_sd:.2f}")
        print("  curated rejected:", curated_rejected)
        print("  library rejections:", reasons)
        if len(opera_check):
            print(opera_check.to_string(index=False))
    return partners, log, opera_check


if __name__ == "__main__":
    from src.thermo.chemistry import core_amines
    ps, log, chk = build_pool({k: v.smiles for k, v in core_amines().items()})
    df = pd.DataFrame([{"name": p.name, "smiles": p.smiles, "origin": p.origin, "pka1": p.pka1,
                        "sites": len(p.site_classes), "classes": ",".join(p.site_classes)}
                       for p in ps])
    print(df.origin.value_counts().to_string())
    print(df.classes.value_counts().head(12).to_string())
    print(df[df.origin == "curated"].to_string(index=False))
