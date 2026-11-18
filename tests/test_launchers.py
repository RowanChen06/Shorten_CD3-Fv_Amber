"""无需 Amber/Slurm 的启动回归测试；使用临时替身程序，不生成科学模拟结果。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="amber launch test ")
        self.base = Path(self.tmp.name)
        self.bin = self.base / "bin with spaces"
        self.bin.mkdir()
        self.log = self.base / "calls.jsonl"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith((
            "AMBER_", "SLURM_", "MPI_", "EXPECTED_", "ENGINE", "SITE_ENV", "RUN_ROOT", "PROFILE", "JOB_VARIANT"))}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ["PATH"], TEST_LOG=str(self.log))
        for name in ["sander", "sander.MPI", "pmemd", "pmemd.MPI", "pmemd.cuda", "pmemd.cuda.MPI",
                     "pmemd.hip", "pmemd.hip.MPI", "pmemd.cuda_DPFP.MPI"]:
            self.write_exe(name, '''import json, os, sys
from pathlib import Path
with open(os.environ["TEST_LOG"], "a") as f:
    f.write(json.dumps({"kind":"engine", "name":Path(sys.argv[0]).name,"args":sys.argv[1:]})+"\\n")
sys.exit(int(os.environ.get("TEST_ENGINE_EXIT", "0")))
''')
        for name in ["srun", "mpiexec", "mpirun"]:
            self.write_exe(name, '''import json, os, subprocess, sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ["TEST_LOG"], "a") as f:
    f.write(json.dumps({"kind":"launcher","name":Path(sys.argv[0]).name,"args":args})+"\\n")
i=0
while i<len(args) and args[i].startswith("-"):
    i += 2 if args[i] in ("-n", "-np") else 1
sys.exit(subprocess.run(args[i:]).returncode)
''')

    def tearDown(self):
        self.tmp.cleanup()

    def write_exe(self, name, body):
        p = self.bin / name
        p.write_text(f"#!{sys.executable}\n" + body)
        p.chmod(0o755)

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def launch(self, engine=None, extra=None, args=None):
        env = self.env.copy()
        if engine is not None:
            env["ENGINE"] = engine
        env.update(extra or {})
        script = 'set -euo pipefail; source hpc/configure_engine.sh; configure_engine; "$ENGINE" "$@"'
        return subprocess.run(["bash", "-c", script, "test", *(args or ["-O", "-i", "input with space.in"])],
                              cwd=ROOT, env=env, text=True, capture_output=True)

    def test_serial_engines_preserve_arguments(self):
        for engine in ["sander", "pmemd", "pmemd.cuda", "pmemd.hip"]:
            with self.subTest(engine=engine):
                self.log.unlink(missing_ok=True)
                args = ["-i", "a b.in", "-p", "model;echo nope.parm7", "-x", "trajectory $raw.nc"]
                p = self.launch(engine, args=args)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(self.calls(), [{"kind": "engine", "name": engine, "args": args}])

    def test_mpi_cpu_cuda_hip_exactly_one_launch(self):
        for engine in ["sander.MPI", "pmemd.MPI", "pmemd.cuda.MPI", "pmemd.hip.MPI", "pmemd.cuda_DPFP.MPI"]:
            with self.subTest(engine=engine):
                self.log.unlink(missing_ok=True)
                p = self.launch(engine, {"SLURM_JOB_ID": "123", "SLURM_NTASKS": "4",
                    "SLURM_CPUS_PER_TASK": "16", "MPI_TYPE": "pmix_v4"})
                self.assertEqual(p.returncode, 0, p.stderr)
                calls = self.calls()
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["name"], "srun")
                for flag in ["--ntasks=4", "--cpus-per-task=16", "--mpi=pmix_v4", "--kill-on-bad-exit=1"]:
                    self.assertIn(flag, calls[0]["args"])
                self.assertEqual(calls[1]["args"], ["-O", "-i", "input with space.in"])

    def test_missing_engine_fails_without_cpu_fallback(self):
        for engine in [None, "auto", "not-installed", "srun -n 4 pmemd.hip.MPI"]:
            with self.subTest(engine=engine):
                p = self.launch(engine)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_mpi_requires_ranks_and_respects_allocation(self):
        for extra in [{}, {"MPI_RANKS": "0"}, {"MPI_RANKS": "9", "SLURM_NTASKS": "4"},
                      {"MPI_RANKS": "2", "SLURM_NTASKS": "4", "EXPECTED_ACCELERATORS": "4"}]:
            with self.subTest(extra=extra):
                self.assertNotEqual(self.launch("pmemd.hip.MPI", extra).returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_non_slurm_mpiexec(self):
        p = self.launch("pmemd.MPI", {"MPI_RANKS": "2"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls()[0]["name"], "mpiexec")
        self.assertEqual(self.calls()[0]["args"][:2], ["-n", "2"])

    def test_explicit_launcher_and_absolute_engine_path(self):
        p = self.launch(str(self.bin / "pmemd.hip.MPI"),
                        {"MPI_RANKS": "2", "MPI_LAUNCHER": str(self.bin / "mpirun")})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls()[0]["name"], "mpirun")

    def test_engine_failure_is_propagated(self):
        for name in ["pmemd.hip", "pmemd.hip.MPI"]:
            with self.subTest(engine=name):
                self.assertEqual(self.launch(name, {"TEST_ENGINE_EXIT": "17", "MPI_RANKS": "2"}).returncode, 17)

    def test_small_box_is_explicit_gpu_only(self):
        p = self.launch("pmemd.hip", {"AMBER_ALLOW_SMALL_BOX": "1"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls()[-1]["args"][0], "-AllowSmallBox")
        self.assertNotEqual(self.launch("sander", {"AMBER_ALLOW_SMALL_BOX": "1"}).returncode, 0)

    def test_template_engine_mismatch_rejected(self):
        self.assertNotEqual(self.launch("sander", {"EXPECTED_ENGINE_FAMILY": "hip"}).returncode, 0)
        self.assertNotEqual(self.launch("pmemd.hip", {"EXPECTED_MPI_MODE": "1"}).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_preflight_does_not_launch_engine(self):
        p = self.launch("pmemd.hip.MPI", {"MPI_RANKS": "4"}, args=["--check"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls(), [])

    def test_real_main_loop_and_analysis_alias(self):
        import shutil
        project = self.base / 'main loop project'
        shutil.copytree(ROOT / 'hpc', project / 'hpc')
        shutil.copyfile(ROOT / 'run.sh', project / 'run.sh')
        self.write_exe('python3', '''import json, os, sys
with open(os.environ['TEST_LOG'],'a') as f:
    f.write(json.dumps({'kind':'python','args':sys.argv[1:]})+'\\n')
if len(sys.argv)>2 and sys.argv[2]=='replicas': print(3)
''')
        env = {**self.env, 'ENGINE':'pmemd.hip.MPI', 'MPI_RANKS':'4'}
        p = subprocess.run(['bash','run.sh','full'], cwd=project, env=env, text=True, capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([x['args'][1:] for x in self.calls()],
            [['prepare'],['build'],['minimize'],['replicas'],['equilibrate','1'],['produce','1'],
             ['equilibrate','2'],['produce','2'],['equilibrate','3'],['produce','3'],['analyse']])
        self.log.unlink()
        # 单独分析不要求动力学引擎；美式 analyze 和英式 analyse 均可。
        p = subprocess.run(['bash','run.sh','analyze'],cwd=project,env=self.env,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([x['args'][1:] for x in self.calls()],[['prepare'],['analyse']])

    def test_active_output_lock_blocks_second_writer(self):
        import fcntl
        import shutil
        project = self.base / 'lock project'
        shutil.copytree(ROOT / 'hpc',project / 'hpc')
        shutil.copyfile(ROOT / 'run.sh',project / 'run.sh')
        out = project / 'runs/manual/full'
        out.mkdir(parents=True)
        with (out / '.writer.lock').open('w') as f:
            fcntl.flock(f,fcntl.LOCK_EX | fcntl.LOCK_NB)
            p = subprocess.run(['bash','run.sh','full'],cwd=project,
                env={**self.env,'ENGINE':'sander'},text=True,capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('已有作业',p.stderr)
        self.assertEqual(self.calls(),[])

    def test_all_submission_templates_select_expected_backend(self):
        # 复制真实提交脚本/配置器，替换最外层 run.sh 以只记录入口调用。
        import shutil
        project = self.base / "project with spaces"
        shutil.copytree(ROOT / "hpc", project / "hpc")
        (project / "config").mkdir()
        (project / "config/protocol.json").write_text("{}")
        site = self.base / "site env.sh"
        site.write_text('export SITE_WAS_LOADED=yes\nexport MPI_TYPE=pmix_v4\ncd /\n')
        (project / "run.sh").write_text('''#!/bin/bash
set -euo pipefail
if [[ $1 != analyse && $1 != analyze ]]; then source hpc/configure_engine.sh; configure_engine; fi
"$REAL_TEST_PYTHON" - "$1" <<'PYCODE'
import json, os, sys
with open(os.environ['TEST_LOG'],'a') as f:
    f.write(json.dumps({'kind':'workflow','mode':sys.argv[1],
       'engine':os.getenv('AMBER_ENGINE_REQUESTED'), 'root':os.getenv('RUN_ROOT'),
       'site':os.getenv('SITE_WAS_LOADED'), 'profile':os.getenv('PROFILE')})+'\\n')
PYCODE
''')
        matrix = {"cpu_serial": (1, "sander"), "cpu_mpi": (8, "sander.MPI"),
                  "nvidia_single": (1, "pmemd.cuda"), "nvidia_multi": (4, "pmemd.cuda.MPI"),
                  "dcu_single": (1, "pmemd.hip"), "dcu_multi": (4, "pmemd.hip.MPI"),
                  "hip_single": (1, "pmemd.hip"), "hip_multi": (4, "pmemd.hip.MPI")}
        for variant, (n, engine) in matrix.items():
            with self.subTest(variant=variant):
                self.log.unlink(missing_ok=True)
                env = {**self.env, "SLURM_JOB_ID": "321", "SLURM_NTASKS": str(n),
                       "SLURM_CPUS_PER_TASK": "16", "SLURM_SUBMIT_DIR": str(project),
                       "SITE_ENV": str(site), "REAL_TEST_PYTHON": sys.executable,
                       "ENGINE": "stale-engine-must-not-be-used"}
                proc = subprocess.run(["bash", str(project / f"hpc/submit_{variant}.slurm"), "pilot"],
                                      env=env, text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                calls = self.calls()
                self.assertEqual([x['mode'] for x in calls], ['check', 'pilot'])
                self.assertTrue(all(x['engine'] == engine and x['site'] == 'yes' for x in calls))
                self.assertEqual(calls[-1]['root'], str(project / f"runs/{variant}-{n}r"))


if __name__ == "__main__":
    unittest.main()
