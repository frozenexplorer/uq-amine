"""
Check the NotebookLM-extracted literature tables against the text of their source PDFs.

literature_blend_performance.csv came out of an AI summariser, not from hand transcription.
This script looks for every numeric value in the pdftotext output of the PDF named in
`source_reference` and adds `verified_in_pdf`:

    yes    every number in `raw_text` occurs in the PDF text
    no     at least one number does not occur
    n/a    the row has no number, or its source PDF is not available

A "yes" means the number exists in the paper, not that it belongs to that blend and metric.
The PDFs are in `our data/` (gitignored); the result is stored in the tracked CSV.

Run:  python -m src.data.verify_literature_tables
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

from src.data.ingest_aronu2011_mea import _pdftotext

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data" / "processed" / "structured" / "literature_blend_performance.csv"
PDF_DIR = ROOT / "our data" / "Amine_Earlier work" / "Amine Blends_Computations_NotebookLM" / "References_Amine"

NUMBER = re.compile(r"\d+(?:\.\d+)?")


def pdf_text(pdf: Path, exe: str) -> str:
    out = subprocess.run([exe, "-layout", str(pdf), "-"], capture_output=True)
    return out.stdout.decode("utf-8", errors="ignore")


def main():
    exe = _pdftotext()
    if exe is None or not PDF_DIR.exists():
        print("skipped: needs pdftotext and the PDFs in our data/")
        return
    df = pd.read_csv(CSV)
    texts = {}
    for ref in df["source_reference"].dropna().unique():
        hits = [p for p in PDF_DIR.glob("*.pdf") if p.name[:40] == str(ref)[:40]]
        if hits:
            texts[ref] = pdf_text(hits[0], exe)
    status = []
    for r in df.itertuples():
        nums = NUMBER.findall(str(r.raw_text)) if pd.notna(r.raw_text) else []
        if not nums or r.source_reference not in texts:
            status.append("n/a")
        else:
            status.append("yes" if all(n in texts[r.source_reference] for n in nums) else "no")
    df["verified_in_pdf"] = status
    df.to_csv(CSV, index=False)
    print(df["verified_in_pdf"].value_counts().to_string())
    print(df.groupby("source_reference")["verified_in_pdf"].value_counts().unstack(fill_value=0).to_string())
    print("not found:")
    print(df[df["verified_in_pdf"] == "no"][["blend_label", "metric", "raw_text"]].to_string(max_colwidth=46))


if __name__ == "__main__":
    main()
