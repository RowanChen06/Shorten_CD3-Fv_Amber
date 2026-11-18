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
