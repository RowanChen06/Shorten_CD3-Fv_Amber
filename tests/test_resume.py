"""用临时文本文件检查阶段发布/恢复；不执行 Amber，不代表轨迹数值验证。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workflow_under_test", ROOT / "scripts/workflow.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class ResumeTests(unittest.TestCase):
    def test_complete_reused_and_truncation_detected(self):
        with tempfile.TemporaryDirectory() as d:
            stage = Path(d) / "prod001"
            def worker(p):
                (p / 'end.rst7').write_text('checkpoint\n')
                return ['end.rst7']
            workflow.stage(stage, worker)
            workflow.stage(stage, lambda p: self.fail('已完成阶段不应重算'))
            (stage / 'end.rst7').write_text('bad\n')
            with self.assertRaises(RuntimeError):
                workflow.stage(stage, worker)

    def test_failed_partial_is_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            stage = Path(d) / 'prod002'
            def fail(p):
                (p / 'partial.txt').write_text('interrupted')
                raise RuntimeError('simulated engine error')
            with self.assertRaises(RuntimeError):
                workflow.stage(stage, fail)
            self.assertFalse(stage.exists())
            def complete(p):
                self.assertFalse((p / 'partial.txt').exists())
                (p / 'end.rst7').write_text('finished\n')
                return ['end.rst7']
            workflow.stage(stage, complete)
            workflow.verify(stage)

    def test_checkpoint_same_length_change_detected(self):
        with tempfile.TemporaryDirectory() as d:
            stage = Path(d) / 'prod003'
            def worker(p):
                (p / 'end.rst7').write_text('abc')
                return ['end.rst7']
            workflow.stage(stage, worker)
            (stage / 'end.rst7').write_text('xyz')
            with self.assertRaises(RuntimeError):
                workflow.verify(stage)


if __name__ == '__main__':
    unittest.main()
