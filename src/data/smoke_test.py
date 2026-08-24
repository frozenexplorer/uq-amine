"""
Week-0 RDKit smoke test.

Goal: prove SMILES -> mol -> descriptors works end to end before building
anything real on top of it. Uses the core pure amines from the plan's scope.

Run: python src/data/smoke_test.py
"""

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, rdFingerprintGenerator

_MORGAN_GEN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)

# Core pure amines (plan §3 — pure amines first)
AMINES = {
    "MEA":  "NCCO",                # monoethanolamine (1°)
    "DEA":  "OCCNCCO",             # diethanolamine (2°)
    "MDEA": "OCCN(C)CCO",          # methyldiethanolamine (3°)
    "PZ":   "C1CNCCN1",            # piperazine (cyclic, 2° x2)
    "AMP":  "CC(C)(CO)N",          # 2-amino-2-methyl-1-propanol (1°, hindered)
}


def featurize(smiles: str) -> dict:
    """Minimal descriptor set — expand in src/features/ once building for real."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit failed to parse/sanitize SMILES: {smiles}")
    return {
        "mol_wt": round(Descriptors.MolWt(mol), 2),
        "num_h_donors": rdMolDescriptors.CalcNumHBD(mol),
        "num_h_acceptors": rdMolDescriptors.CalcNumHBA(mol),
        "tpsa": round(Descriptors.TPSA(mol), 2),
        "num_amine_n": sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() == "N"),
        "morgan_fp_nbits_set": _MORGAN_GEN.GetFingerprint(mol).GetNumOnBits(),
    }


def main():
    print(f"{'Amine':<6} {'SMILES':<16} {'MolWt':>7} {'HBD':>4} {'HBA':>4} {'TPSA':>7} {'#N':>3} {'FP bits on':>11}")
    print("-" * 70)
    for name, smi in AMINES.items():
        feats = featurize(smi)
        print(
            f"{name:<6} {smi:<16} {feats['mol_wt']:>7} {feats['num_h_donors']:>4} "
            f"{feats['num_h_acceptors']:>4} {feats['tpsa']:>7} {feats['num_amine_n']:>3} "
            f"{feats['morgan_fp_nbits_set']:>11}"
        )
    print("\nSmoke test passed: SMILES -> mol -> descriptors pipeline works.")


if __name__ == "__main__":
    main()
