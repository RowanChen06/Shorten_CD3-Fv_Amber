"""CD3 模拟工作流：由 run.sh 调用"""
import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PROFILE = os.environ.get("PROFILE", "full")
CONFIG = json.loads((ROOT / "config/protocol.json").read_text())
SPEC = CONFIG[PROFILE]
RUN = Path(os.environ.get("RUN_ROOT", ROOT/"runs/manual")).resolve()/PROFILE
# 动力学引擎由 Bash 入口解析；禁止 Python 再次自动选择 CPU/GPU。
ENGINE = os.environ.get("ENGINE", "")
PYTHON = sys.executable
STAGES = ROOT/"mdin"

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def plan():
    for key, spec in CONFIG.items():
        print(f"{key}: {len(spec['seeds'])} replica(s) x {spec['segments']} segment(s) x "
              f"{spec['segment_ns']} ns; frames every {spec['frame_ps']} ps")
    print("Build -> minimization -> independent heat/NPT -> NVT production -> analysis")
    print("Run folder:", RUN)

def preflight(analysis_only=False):
    if not analysis_only and not ENGINE:
        raise SystemExit("请通过 run.sh 并显式指定 ENGINE，或使用提交模板。")
    programs=["cpptraj"] if analysis_only else list(dict.fromkeys(["tleap","sander","cpptraj",ENGINE]))
    missing=[n for n in programs if not shutil.which(n)]
    versions={}
    for n in ["numpy","scipy","parmed","netCDF4","matplotlib"]:
        try:
            m=importlib.import_module(n)
            versions[n]=getattr(m,"__version__","unknown")
        except (ImportError,OSError) as exc:
            missing.append(f"{n} ({exc})")
    if missing:
        raise SystemExit("Unavailable: "+", ".join(missing)+". See ENVIRONMENT.md.")
    info={"python":sys.version,"python_path":sys.executable,"host":platform.node(),
          "date_utc":datetime.now(timezone.utc).isoformat(),"packages":versions,
          "commands":{n:shutil.which(n) for n in programs},"engine":ENGINE,
          "job_id":os.getenv("SLURM_JOB_ID"),"loaded_modules":os.getenv("LOADEDMODULES"),
          # 保存真实引擎、MPI 与设备可见变量，避免日志里只剩包装脚本路径。
          "execution":{k:os.getenv(k) for k in (
              "AMBER_ENGINE_REQUESTED","AMBER_ENGINE_BIN","AMBER_ENGINE_FAMILY",
              "AMBER_USE_MPI","MPI_RANKS","MPI_LAUNCHER","MPI_TYPE",
              "AMBER_ALLOW_SMALL_BOX","SLURM_NTASKS","SLURM_CPUS_PER_TASK",
              "SLURM_JOB_GPUS","SLURM_GPUS_ON_NODE","CUDA_VISIBLE_DEVICES",
              "HIP_VISIBLE_DEVICES","ROCR_VISIBLE_DEVICES","HSA_FORCE_FINE_GRAIN_PCIE",
              "HIP_COMGR_ARCH","ROCBLAS_GPU_ARCHNAME","I_MPI_PMI_LIBRARY",
              "OMP_NUM_THREADS","JOB_VARIANT","SITE_ENV_LOADED")}}
    info["launcher_sha256"]={str(p.relative_to(ROOT)):sha(p) for p in
        [ROOT/"run.sh",*sorted((ROOT/"hpc").glob("*.sh"))]}
    env_file=os.getenv("SITE_ENV_LOADED")
    if env_file and Path(env_file).is_file():
        info["site_env_sha256"]=sha(Path(env_file))
    print("Programs:",info["commands"],flush=True)
    return info

def execute(args, cwd, log):
    print("+"," ".join(map(str,args)),flush=True)
    with (cwd/log).open("w") as out:
        proc=subprocess.run(list(map(str,args)),cwd=cwd,stdout=out,stderr=subprocess.STDOUT)
    if proc.returncode:
        raise RuntimeError(f"Command exited {proc.returncode}. See {cwd/log}")

def prepare():
    analysis_only=os.environ.get("ANALYSIS_ONLY")=="1"
    info=preflight(analysis_only)
    for profile,s in CONFIG.items():
        if not s["seeds"] or len(set(s["seeds"]))!=len(s["seeds"]) or s["segments"]<1:
            raise ValueError(f"Check replica seeds / segment count for {profile}")
        for value in (s["eq_ca_ps"],s["eq_free_ps"],s["segment_ns"],s["frame_ps"]):
            if value<=0: raise ValueError(f"Non-positive duration in {profile}")
        steps=round(s["segment_ns"]*500000)
        if steps%round(s["frame_ps"]*500) or steps%500 or round(s["eq_ca_ps"]*500)%1000 or round(s["eq_free_ps"]*500)%1000:
            raise ValueError("Lengths must give whole output intervals.")
    expected=(ROOT/"reference/SHA256SUMS").read_text().split()[0]
    if sha(ROOT/"reference/output.cif")!=expected:
        raise ValueError("Original CIF checksum mismatch.")
    files=[p for loc in ["reference","input","mdin"] for p in sorted((ROOT/loc).glob("*")) if p.is_file()]
    files.extend([ROOT/"scripts/workflow.py",ROOT/"scripts/check_system.py"])
    signature={"protocol":SPEC,"files":{str(p.relative_to(ROOT)):sha(p) for p in files}}
    manifest=RUN/"protocol.json"
    if manifest.exists() and json.loads(manifest.read_text())!=signature:
        raise ValueError("Simulation inputs changed. Set RUN_ROOT to a different directory for a new protocol.")
    RUN.mkdir(parents=True,exist_ok=True)
    if not manifest.exists():
        temp=manifest.with_suffix(".tmp")
        temp.write_text(json.dumps(signature,indent=2)); temp.replace(manifest)
    with (RUN/"environment.jsonl").open("a") as handle:
        handle.write(json.dumps(info)+"\n")

def verify(directory):
    marker=directory/"complete.json"
    if not marker.is_file(): raise RuntimeError(f"Incomplete published stage: {directory}")
    files=json.loads(marker.read_text())
    for name,meta in files.items():
        path=directory/name
        if not path.is_file() or path.stat().st_size!=meta["size"]:
            raise RuntimeError(f"Missing/truncated result {path}")
        if "sha256" in meta and sha(path)!=meta["sha256"]:
            raise RuntimeError(f"Changed checkpoint {path}")

# 只发布经过完整性检查的阶段；中断后的 .partial 会重算，已完成段逐项核验。
def stage(directory, worker, refresh=False):
    backup=directory.with_name(directory.name+".previous")
    if backup.exists() and not directory.exists(): backup.rename(directory)
    if directory.exists() and not refresh:
        verify(directory); print("Resume, verified:",directory,flush=True); return
    directory.parent.mkdir(parents=True,exist_ok=True)
    tmp=directory.with_name(directory.name+".partial")
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir()
    products=worker(tmp)
    files={}
    for name in products:
        path=tmp/name
        if not path.is_file() or path.stat().st_size==0: raise RuntimeError(f"Missing {path}")
        meta={"size":path.stat().st_size}
        if path.suffix in (".rst7",".parm7"): meta["sha256"]=sha(path)
        files[name]=meta
    (tmp/"complete.json").write_text(json.dumps(files,indent=2))
    if directory.exists():
        if backup.exists(): shutil.rmtree(backup)
        directory.rename(backup)
    tmp.rename(directory)
    if backup.exists(): shutil.rmtree(backup)

def check_geometry(folder,mode,top,coords):
    execute([PYTHON,ROOT/"scripts/check_system.py",mode,top,coords],folder,"geometry.txt")

def build(folder):
    import parmed as pmd
    shutil.copyfile(ROOT/"input/ecto.pdb",folder/"ecto.pdb")
    base=(STAGES/"build.leap").read_text().replace("input/ecto.pdb","ecto.pdb")
    def leap(tag,tail):
        (folder/(tag+".leap")).write_text(base+tail+"\nquit\n")
        execute(["tleap","-f",tag+".leap"],folder,tag+".log")
        body=(folder/(tag+".log")).read_text(errors="replace")
        if not re.search(r"Errors\s*=\s*0\b",body):
            raise RuntimeError(f"Inspect {folder}/{tag}.log")
    leap("count","saveAmberParm mol count.parm7 count.rst7")
    count=sum(r.name in ("WAT","HOH") for r in pmd.load_file(str(folder/"count.parm7")).residues)
    if count<=0: raise ValueError("Solvation produced no water")
    salt=round(count*.15/55.5)
    leap("build",f"addIonsRand mol Na+ 0\naddIonsRand mol Na+ {salt} Cl- {salt}\ncheck mol\ncharge mol\nsaveAmberParm mol system.parm7 system.rst7")
    check_geometry(folder,"build",folder/"system.parm7",folder/"system.rst7")
    for name in ["count.rst7","count.parm7","ecto.pdb"]: (folder/name).unlink()
    return ["system.parm7","system.rst7","build.log","build.leap","geometry.txt","count.log","count.leap"]

def restart_header(path):
    with path.open() as handle:
        next(handle); row=next(handle).split()
    return int(row[0]), float(row[1]) if len(row)>1 else 0.0

def check_restart_payload(path, natom, needs_velocity):
    import numpy as np
    from parmed.amber import Rst7
    rst=Rst7.open(str(path))
    xyz=np.asarray(rst.coordinates)
    if xyz.size!=3*natom or not np.isfinite(xyz).all() or not rst.hasbox:
        raise ValueError(f"Incomplete coordinates/periodic box: {path}")
    if needs_velocity and (not rst.hasvels or not np.isfinite(rst.velocities).all()):
        raise ValueError(f"Missing or invalid velocities: {path}")

def write_thermo(folder, body):
    """Keep regular MD records; exclude Amber's average and RMS summaries."""
    samples = []
    stop = re.split(r"A V E R A G E S|R M S  F L U C T U A T I O N S", body, maxsplit=1)[0]
    for record in re.split(r"(?=^\s*NSTEP\s*=)", stop, flags=re.M):
        if not re.match(r"\s*NSTEP\s*=",record):
            continue
        row=[]
        for field in ("NSTEP","TIME(PS)","TEMP(K)","EPtot","VOLUME","Density"):
            m = re.search(re.escape(field)+r"\s*=\s*([-+0-9.Ee]+)", record)
            row.append(m.group(1) if m else "")
        samples.append(row)
    if not samples or not any(r[2] for r in samples):
        raise ValueError("No temperature records in md.out")
    with (folder/"thermo.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["step","time_ps","temperature_K","potential_kcal_mol","volume_A3","density_g_cm3"])
        w.writerows(samples)

def md(directory, template, start, seed=0, reference=None, steps=0):
    from netCDF4 import Dataset
    def run(folder):
        top=RUN/"build/system.parm7"
        text=(STAGES/(template+".in")).read_text()
        stride=round(SPEC["frame_ps"]*500) if template=="production" else 1000
        for key,value in [("SEED",seed),("STEPS",steps),("STRIDE",stride)]:
            text=text.replace(key,str(value))
        (folder/"md.in").write_text(text)
        minim=template.startswith("min")
        # 最小化保持 CPU sander；升温/平衡/生产交给统一 CPU/CUDA/HIP 启动器。
        args=["sander" if minim else ENGINE,"-O","-i","md.in","-p",top,"-c",start,
              "-r","end.rst7","-o","md.out","-inf","md.info"]
        if reference: args+=["-ref",reference]
        if not minim: args+=["-x","wet.nc"]
        execute(args,folder,"console.log")
        body=(folder/"md.out").read_text(errors="replace")
        if not re.search("TIMINGS|Total wall time",body,re.I):
            raise RuntimeError(f"Missing Amber completion footer: {folder}")
        natom,t0=restart_header(start)
        nend,t1=restart_header(folder/"end.rst7")
        if nend!=natom: raise ValueError("Checkpoint atom count differs")
        check_restart_payload(folder/"end.rst7",nend,not minim)
        files=["end.rst7","md.out","md.in"]
        if not minim:
            dt=0.001 if template=="heat" else .002
            if not math.isclose(t1,(0 if template=="heat" else t0)+steps*dt,abs_tol=.02):
                raise ValueError(f"Checkpoint time {t1} inconsistent with {steps} steps")
            with Dataset(folder/"wet.nc") as nc:
                shape=nc.variables["coordinates"].shape
                if shape!=(steps//stride,natom,3): raise ValueError(f"Unexpected trajectory shape {shape}")
            write_thermo(folder,body)
            files.extend(["wet.nc","thermo.csv"])
        if minim:
            if "FINAL RESULTS" not in body: raise RuntimeError("Missing minimization results")
            # The local relaxation is recorded, full geometry is checked after free minimization.
            check_geometry(folder,"min" if template=="min_free" else "intermediate",top,folder/"end.rst7")
            files.append("geometry.txt")
        return files
    stage(directory,run)
    return directory/"end.rst7"

def minimize():
    start=RUN/"build/system.rst7"
    first=md(RUN/"min_ca","min_ca",start,reference=start)
    md(RUN/"min_free","min_free",first)

# 每个重复使用独立种子；多卡共同推进该重复，不会增加统计重复数。
def equilibrate(rep):
    base=RUN/f"rep{rep:02d}"
    seed=SPEC["seeds"][rep-1]
    start=RUN/"min_free/end.rst7"
    hot=md(base/"heat","heat",start,seed,start,50000)
    relax=md(base/"eq_ca","eq_ca",hot,seed+1,start,round(500*SPEC["eq_ca_ps"]))
    md(base/"eq_free","eq_free",relax,seed+2,steps=round(500*SPEC["eq_free_ps"]))

def produce(rep):
    base=RUN/f"rep{rep:02d}"
    start=base/"eq_free/end.rst7"
    steps=round(500000*SPEC["segment_ns"])
    seed=SPEC["seeds"][rep-1]
    for i in range(1,SPEC["segments"]+1):
        start=md(base/f"prod{i:03d}","production",start,seed+100+i,steps=steps)

def analyse():
    from analyse import analyse_replica, summarize
    top=RUN/"build/system.parm7"
    for rep in range(1,len(SPEC["seeds"])+1):
        base=RUN/f"rep{rep:02d}"
        parts=[base/f"prod{i:03d}" for i in range(1,SPEC["segments"]+1)]
        for part in [base/"eq_free",*parts]: verify(part)
        def process(folder):
            return analyse_replica(ROOT,folder,top,base,parts,SPEC)
        stage(base/"analysis",process,refresh=os.environ.get("ANALYSIS_ONLY")=="1")
    stage(RUN/"summary",lambda folder:summarize(folder,RUN,len(SPEC["seeds"])),refresh=os.environ.get("ANALYSIS_ONLY")=="1")

if __name__=="__main__":
    action=sys.argv[1]
    if action=="plan": plan()
    elif action=="check": preflight()
    elif action=="prepare": prepare()
    elif action=="replicas": print(len(SPEC["seeds"]))
    elif action=="build": stage(RUN/"build",build)
    elif action=="minimize": minimize()
    elif action=="equilibrate": equilibrate(int(sys.argv[2]))
    elif action=="produce": produce(int(sys.argv[2]))
    elif action=="analyse": analyse()
    else: raise SystemExit(f"Unknown step {action}")
