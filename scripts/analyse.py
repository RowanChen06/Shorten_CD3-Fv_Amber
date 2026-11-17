"""Trajectory analysis. All protein residue identifiers are traced to the input CIF."""
from collections import Counter
import csv
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.spatial import cKDTree

def table(path):
    with path.open() as f:
        return list(csv.DictReader(f))

def save(path, fields, rows):
    with path.open("w", newline="") as f:
        writer=csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)

def original(root):
    mapping=table(root/"input/residue_map.csv")
    ids={(r["cif_chain"],int(r["cif_resid"])):int(r["amber_resid"]) for r in mapping}
    lines=(root/"reference/output.cif").read_text().splitlines()
    cols=[s.strip().split(".")[1] for s in lines if s.startswith("_atom_site.")]
    keys=[]; coords=[]
    for line in lines:
        if line.startswith("ATOM "):
            d=dict(zip(cols,line.split()))
            key=(d["label_asym_id"],int(d["label_seq_id"]))
            if key in ids:
                keys.append((ids[key],d["label_atom_id"]))
                coords.append([float(d["Cartn_"+a]) for a in "xyz"])
    return keys,np.array(coords),mapping

def fit(moving,fixed):
    a=moving.mean(0); b=fixed.mean(0)
    u,_,vt=np.linalg.svd((moving-a).T@(fixed-b))
    u[:,-1]*=np.linalg.det(u@vt)
    return a,u@vt,b

def rmsd(a,b):
    return np.sqrt(((a-b)**2).sum(axis=1).mean())

def geometry(x,ref,ag,fv):
    a,r,b=fit(x[ag],ref[ag])
    placed=(x[fv]-a)@r+b
    f,q,g=fit(placed,ref[fv])
    angle=np.degrees(np.arccos(np.clip((np.trace(q)-1)/2,-1,1)))
    return [rmsd((x[ag]-a)@r+b,ref[ag]),rmsd(placed,ref[fv]),
            rmsd((placed-f)@q+g,ref[fv]),np.linalg.norm(f-g),angle]

def nearby(x,ids,a,b,radius):
    aa,bb=np.where(a)[0],np.where(b)[0]
    if not len(aa) or not len(bb): return set()
    neighbors=cKDTree(x[aa]).sparse_distance_matrix(cKDTree(x[bb]),radius,output_type="coo_matrix")
    return set(zip(ids[aa[neighbors.row]],ids[bb[neighbors.col]]))

def run_cpp(folder,name,commands):
    (folder/(name+".in")).write_text("\n".join(commands)+"\n")
    with (folder/(name+".log")).open("w") as log:
        subprocess.run(["cpptraj","-i",name+".in"],cwd=folder,stdout=log,stderr=subprocess.STDOUT,check=True)
    if re.search(r"^\s*Error:",(folder/(name+".log")).read_text(errors="replace"),re.M|re.I):
        raise RuntimeError(f"Inspect {name}.log in {folder}")

def bridge_pairs(text):
    waters=re.findall(r"(\d+)\(([\d+]+)\)",text)
    if not waters and text.strip().strip('"').lower() not in ("none",""):
        raise ValueError("Unrecognized CPPTRAJ water bridge IDs: "+text[:120])
    found=set()
    for _,members in waters:
        rs={int(x) for x in members.split("+") if x}
        found.update((i,j) for i in rs if i<=188 for j in rs if 188<j<=418)
    return found

def pair_rows(items,lookup):
    for (i,j),other in sorted(items.items()):
        a,b=lookup[i],lookup[j]
        yield [a["cif_chain"],a["cif_resid"],b["cif_chain"],b["cif_resid"],i,j,*other]

PAIR_FIELDS=["ag_chain","ag_cif_resid","fv_chain","fv_cif_resid","ag_amber_id","fv_amber_id"]

def water_and_hbonds(folder,parts,spec,site,lookup):
    # All production frames are screened for distances <= 7 A before this subset is built.
    mask=":"+",".join(map(str,sorted(site)))
    stride=max(1,round(100/spec["frame_ps"])) if len(parts)>1 else 1
    # If no near-interface residues exist, evaluate the entire protein instead.
    if not site: mask=":1-418"
    commands=["parm ../../build/system.parm7"]
    commands.extend(f"trajin ../{part.name}/wet.nc 1 last {stride}" for part in parts)
    commands+=["autoimage anchor :1-84",
        f"hbond HB {mask} nointramol image dist 3.2 angle 135 solventdonor :WAT solventacceptor :WAT@O avgout direct_all.dat out bridge_trace.dat",
        "run","writedata bridge_ids.dat HB[ID]"]
    run_cpp(folder,"hbond",commands)
    hb=[]
    for line in (folder/"direct_all.dat").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"): continue
        row=line.split()
        nums=[int(re.search(r"_(\d+)@",atom).group(1)) for atom in (row[0],row[2])]
        if (nums[0]<=188)!=(nums[1]<=188):
            hb.append([*row[:3],row[3],row[4],row[5],row[6]])
    save(folder/"interface_hbonds.csv",["acceptor","donor_H","donor","n_frames","fraction","mean_distance_A","mean_angle_deg"],hb)
    counts=Counter(); n=0
    for line in (folder/"bridge_ids.dat").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"): continue
        fields=line.strip().split(None,1)
        states=bridge_pairs(fields[1] if len(fields)>1 else "")
        counts.update(states); n+=1
    frames_per_part=round(spec["segment_ns"]*1000/spec["frame_ps"])
    if n!=len(parts)*((frames_per_part-1)//stride+1):
        raise ValueError(f"Unexpected H-bond analysis frame count: {n}")
    save(folder/"water_bridges.csv",PAIR_FIELDS+["n_frames","fraction","n_sampled_frames"],
         pair_rows({k:[v,v/n,n] for k,v in counts.items()},lookup))

def analyse_replica(root,folder,top_path,base,parts,spec):
    import parmed as pmd
    from netCDF4 import Dataset
    run_cpp(folder,"view",["parm ../../build/system.parm7","trajin ../eq_free/end.rst7",
        *[f"trajin ../{part.name}/wet.nc" for part in parts],"autoimage anchor :1-84",
        "rms first :1-188@CA","strip !:1-418 parmout protein.parm7 nobox",
        "trajout protein.nc netcdf nobox","run"])
    top=pmd.load_file(str(folder/"protein.parm7"))
    keys,ref,mapping=original(root)
    lookup={int(r["amber_resid"]):r for r in mapping}
    atoms={(a.residue.idx+1,a.name):a.idx for a in top.atoms}
    indices=[atoms[k] for k in keys]
    ids=np.array([i for i,a in keys])
    ag=ids<=188; fv=~ag; ca=np.array([a=="CA" for i,a in keys])
    names=[(lookup[i]["cif_resname"],a) for i,a in keys]
    acid=np.array([res in ("ASP","GLU") and a in ("OD1","OD2","OE1","OE2") for res,a in names])
    basic=np.array([res in ("ARG","LYS") and a in ("NZ","NE","NH1","NH2") for res,a in names])
    native=nearby(ref,ids,ag,fv,4.)
    baseline={(int(r["antigen_amber_resid"]),int(r["antibody_amber_resid"])) for r in table(root/"input/original_contacts.csv")}
    if native!=baseline or len(native)!=44: raise ValueError("Original 44-contact baseline differs")
    labels=["A1_B1","A1_B2","A2_B1","A2_B2"]
    groups={k:{p for p in native if lookup[p[0]]["cif_chain"]+"_"+lookup[p[1]]["cif_chain"]==k} for k in labels}
    counts=Counter(); salt=Counter(); site=set()
    geo=["ag_RMSD_A","Fv_pose_RMSD_A","Fv_self_RMSD_A","Fv_center_shift_A","Fv_rotation_deg"]
    fields=["frame","prod_ns",*geo,*["eq_"+s for s in geo],"Q_original","Q_eq","new_contacts","salt_pairs",*["Q_"+s for s in labels]]
    with Dataset(folder/"protein.nc") as nc, (folder/"metrics.csv").open("w",newline="") as f:
        xyz=nc.variables["coordinates"]
        n=xyz.shape[0]-1
        if n!=round(len(parts)*spec["segment_ns"]*1000/spec["frame_ps"]): raise ValueError("Unexpected imaged frame count")
        eq=np.asarray(xyz[0],float)[indices]; eqpairs=nearby(eq,ids,ag,fv,4.)
        writer=csv.writer(f);writer.writerow(fields)
        path_metrics=[]
        for i in range(1,n+1):
            x=np.asarray(xyz[i],float)[indices]
            c=nearby(x,ids,ag,fv,4.)
            close=nearby(x,ids,ag,fv,7.)
            for aa,bb in close: site.update((aa,bb))
            salts=nearby(x,ids,ag&acid,fv&basic,4.)|nearby(x,ids,ag&basic,fv&acid,4.)
            counts.update(c);salt.update(salts)
            g=geometry(x,ref,ag&ca,fv&ca)
            q=len(c&native)/len(native)
            path_metrics.append([g[1],q])
            vals=[i,i*spec["frame_ps"]/1000,*g,*geometry(x,eq,ag&ca,fv&ca),
                  q,len(c&eqpairs)/len(eqpairs) if eqpairs else np.nan,len(c-native),len(salts),
                  *[len(c&groups[k])/len(groups[k]) for k in labels]]
            writer.writerow([f"{v:.8g}" for v in vals])
        # Actual frame closest to the mean in two standardized observables.
        data=np.array(path_metrics); sd=data.std(0); sd[sd<1.e-8]=1
        med=int(np.argmin((((data-data.mean(0))/sd)**2).sum(1)))+1
        top.coordinates=np.asarray(xyz[med],float)
        top.save(str(folder/"representative.pdb"),overwrite=True)
        (folder/"representative.txt").write_text(f"Production frame {med}, {med*spec['frame_ps']/1000:g} ns\n")
    save(folder/"contacts.csv",PAIR_FIELDS+["in_original","in_eq","frames","fraction"],
        pair_rows({p:[int(p in native),int(p in eqpairs),counts[p],counts[p]/n] for p in set(counts)|native|eqpairs},lookup))
    save(folder/"salt_bridges.csv",PAIR_FIELDS+["frames","fraction"],pair_rows({p:[v,v/n] for p,v in salt.items()},lookup))
    water_and_hbonds(folder,parts,spec,site,lookup)
    return ["view.in","view.log","protein.parm7","protein.nc","metrics.csv","contacts.csv",
            "salt_bridges.csv","representative.pdb","representative.txt","hbond.in","hbond.log",
            "direct_all.dat","interface_hbonds.csv","bridge_trace.dat","bridge_ids.dat","water_bridges.csv"]

def summarize(folder,run,replicas):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    measures=["Fv_pose_RMSD_A","Fv_self_RMSD_A","Q_original","new_contacts"]
    statrows=[]; blockrows=[]; means=[]
    fig,axes=plt.subplots(2,2,figsize=(10,6),layout="constrained")
    for r in range(1,replicas+1):
        vals=np.genfromtxt(run/f"rep{r:02d}/analysis/metrics.csv",delimiter=",",names=True)
        series=[]
        for ax,m in zip(axes.flat,measures):
            v=vals[m]; t=vals["prod_ns"]
            ax.plot(t,v,lw=.65,alpha=.8,label=f"rep {r}")
            ax.set(xlabel="Production time (ns)",ylabel=m.replace("_"," "))
            statrows.append([r,m,v.mean(),np.median(v),v.std()]);series.append(v.mean())
            for i,block in enumerate(np.array_split(np.arange(len(v)),4),1):
                blockrows.append([r,m,i,t[block[0]],t[block[-1]],v[block].mean()])
        means.append(series)
    axes.flat[0].legend()
    fig.savefig(folder/"traces.png",dpi=160);plt.close(fig)
    save(folder/"replica_stats.csv",["replica","metric","mean","median","within_replica_sd"],statrows)
    save(folder/"blocks.csv",["replica","metric","block","start_ns","end_ns","mean"],blockrows)
    x=np.array(means)
    save(folder/"across_replicas.csv",["metric","n_replicas","mean_of_replica_means","sd_of_replica_means"],
         ([m,replicas,x[:,i].mean(),x[:,i].std(ddof=1) if replicas>1 else ""] for i,m in enumerate(measures)))
    all_pairs={}
    for r in range(1,replicas+1):
        for row in table(run/f"rep{r:02d}/analysis/contacts.csv"):
            key=tuple(row[k] for k in PAIR_FIELDS)
            if key not in all_pairs:
                all_pairs[key]=(int(row["in_original"]),np.zeros(replicas))
            all_pairs[key][1][r-1]=float(row["fraction"])
    save(folder/"cross_replica_contacts.csv",
         [*PAIR_FIELDS,"in_original",*[f"rep{r:02d}_fraction" for r in range(1,replicas+1)],"mean","replica_sd"],
         ([*k,native,*vals,vals.mean(),vals.std(ddof=1) if replicas>1 else ""]
          for k,(native,vals) in sorted(all_pairs.items(),key=lambda item:-item[1][1].mean())))
    return ["traces.png","replica_stats.csv","blocks.csv","across_replicas.csv","cross_replica_contacts.csv"]
