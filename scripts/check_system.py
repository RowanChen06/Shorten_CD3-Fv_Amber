"""Validate the topology and geometry of this specific 418-residue working construct."""
import csv
import sys
from pathlib import Path
import numpy as np
import parmed as pmd
from scipy.spatial import cKDTree

mode, top, restart = sys.argv[1:]
model = pmd.load_file(top, xyz=restart)
xyz = np.asarray(model.coordinates)
res = model.residues
mapping = list(csv.DictReader((Path(__file__).resolve().parents[1] / "input/residue_map.csv").open()))
if not np.isfinite(xyz).all():
    sys.exit("Non-finite coordinates.")
for i, row in enumerate(mapping):
    if res[i].name != row["amber_resname"]:
        sys.exit(f"Unexpected residue {i+1}: {res[i].name} != {row['amber_resname']}")
def atom(i, name):
    return next(a for a in res[i-1].atoms if a.name == name)
def distance(i, a, j, b):
    return float(np.linalg.norm(xyz[atom(i, a).idx] - xyz[atom(j, b).idx]))
def link(i, a, j, b):
    return atom(j, b) in atom(i, a).bond_partners
ends = {84,188,311}
for i in range(1,418):
    if link(i,"C",i+1,"N") != (i not in ends):
        sys.exit(f"Unexpected backbone connectivity at {i}/{i+1}.")
expected = {(16,52),(72,75),(111,160),(181,184),(210,284),(334,399)}
ss = {tuple(sorted([b.atom1.residue.idx+1,b.atom2.residue.idx+1])) for b in model.bonds
      if b.atom1.name == b.atom2.name == "SG"}
if ss != expected:
    sys.exit(f"Unexpected S-S bonds: {ss}")
charge = sum(a.charge for a in model.atoms)
print(f"{len(model.atoms)} atoms; net charge {charge:.4f} e")
if abs(charge)>0.02 or model.box is None:
    sys.exit("Check system charge and periodic box.")
problems = []
for i,j in sorted(ss):
    d = distance(i,"SG",j,"SG")
    print(f"S-S {i}-{j}: {d:.3f} A")
    if mode=="min" and not 1.85<=d<=2.25:
        problems.append(f"S-S {i}-{j} requires inspection")
print(f"A1 Arg32 NH2 / B2 Asp92 O: {distance(11,'NH2',403,'O'):.3f} A")
groups = []
for lo,hi in [(1,84),(85,188),(189,311),(312,418)]:
    ids=[a.idx for r in res[lo-1:hi] for a in r.atoms if a.atomic_number>1]
    groups.append(xyz[ids])
shortest=min(cKDTree(p).query(q)[0].min() for i,p in enumerate(groups) for q in groups[i+1:])
print(f"Shortest interchain heavy-atom distance: {shortest:.3f} A")
if mode=="min" and shortest<2.0:
    problems.append("Severe interchain overlap remains below 2.0 A")
if problems:
    sys.exit("\n".join(problems))
