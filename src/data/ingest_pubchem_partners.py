"""
Look up every partner amine on PubChem: real name, CID and how many chemical vendors list it.

Why: the library amines are known only by SMILES, so the practical stage needs to know which
of them can actually be bought. PubChem's "Chemical Vendors" source list is the open proxy
for that. A vendor count says a compound is on someone's catalogue, not that it is sold by
the tonne, so src/screening/practical.py uses it only to separate "can be purchased" from
"research curiosity"; library amines are still priced as specialty chemicals.

The result is cached in data/processed/practical/partner_availability.csv (tracked), so the
pipeline does not need the network; only amines missing from the cache are queried.

Run:  python -m src.data.ingest_pubchem_partners
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from src.screening.partners import build_pool
from src.thermo.chemistry import core_amines

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "practical" / "partner_availability.csv"

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
HEADERS = {"User-Agent": "amine-co2-uq/0.1 (research data ingestion)"}
PAUSE_S = 0.22          # PubChem asks for at most 5 requests per second
COLUMNS = ["smiles", "cid", "title", "iupac_name", "n_vendors"]


def _get(url: str, retries: int = 4):
    for attempt in range(retries):
        try:
            time.sleep(PAUSE_S)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
    return None


def lookup(smiles: str) -> dict:
    row = {"smiles": smiles, "cid": None, "title": None, "iupac_name": None, "n_vendors": 0}
    hit = _get(f"{PUG}/compound/smiles/cids/JSON?smiles={urllib.parse.quote(smiles)}")
    cids = (hit or {}).get("IdentifierList", {}).get("CID", [])
    if not cids or cids[0] == 0:
        return row
    cid = cids[0]
    row["cid"] = cid
    props = _get(f"{PUG}/compound/cid/{cid}/property/Title,IUPACName/JSON")
    if props:
        p = props["PropertyTable"]["Properties"][0]
        row["title"], row["iupac_name"] = p.get("Title"), p.get("IUPACName")
    cats = _get(f"{PUG_VIEW}/categories/compound/{cid}/JSON")
    for c in (cats or {}).get("SourceCategories", {}).get("Categories", []):
        if c.get("Category") == "Chemical Vendors":
            row["n_vendors"] = len(c.get("Sources", []))
    return row


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    core = core_amines()
    partners, _, _ = build_pool({k: v.smiles for k, v in core.items()}, verbose=False)
    wanted = [m.smiles for m in core.values()] + [p.smiles for p in partners]
    cached = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=COLUMNS)
    todo = [s for s in wanted if s not in set(cached["smiles"])]
    print(f"{len(wanted)} amines, {len(todo)} to query")
    rows = cached.to_dict("records")
    for i, smi in enumerate(todo, 1):
        rows.append(lookup(smi))
        if i % 50 == 0 or i == len(todo):
            pd.DataFrame(rows, columns=COLUMNS).to_csv(OUT, index=False)
            print(f"  {i}/{len(todo)}", flush=True)
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(OUT, index=False)
    print(f"-> {OUT.relative_to(ROOT)}: {df['cid'].notna().sum()} found on PubChem, "
          f"{(df['n_vendors'] > 0).sum()} with at least one vendor")


if __name__ == "__main__":
    main()
