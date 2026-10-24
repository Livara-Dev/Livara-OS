import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('code_reuse', ROOT / 'scripts/validate-code-reuse.py')
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)


class CodeCandidateReuse(unittest.TestCase):
    def test_failed_runtime_can_reuse_successful_compilation_from_same_repository(self):
        run = {'head_repository': {'full_name': 'Livara-Dev/Livara-OS'}, 'head_sha': 'a' * 40}
        jobs = [{'steps': [{'name': 'Compile actual pinned Code source', 'conclusion': 'success'},
                           {'name': 'Preserve compiled candidate before runtime testing', 'conclusion': 'success'},
                           {'name': 'Test packaged CLI and native window', 'conclusion': 'failure'}]}]
        self.assertEqual(reuse.candidate_run(run, jobs, 'Livara-Dev/Livara-OS'), 'a' * 40)
        with self.assertRaisesRegex(ValueError, 'same repository'):
            reuse.candidate_run(run, jobs, 'someone/fork')
        jobs[0]['steps'][0]['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'successfully compile'):
            reuse.candidate_run(run, jobs, 'Livara-Dev/Livara-OS')

    @unittest.skipUnless(shutil.which('git'), 'Git required for source comparison')
    def test_docs_changes_reuse_but_controller_changes_recompile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Code reuse test')
            git('config', 'user.email', 'test@localhost')
            controller = root / 'forks/code/overlay/core/windowControls.ts'
            controller.parent.mkdir(parents=True)
            controller.write_text('original controller')
            git('add', '.')
            git('commit', '-qm', 'candidate')
            before = git('rev-parse', 'HEAD')
            (root / 'README.md').write_text('Updated documentation')
            git('add', '.')
            git('commit', '-qm', 'documentation')
            self.assertTrue(reuse.matching_inputs(before, git('rev-parse', 'HEAD'), root))
            controller.write_text('changed compiled behavior')
            git('add', '.')
            git('commit', '-qm', 'controller')
            self.assertFalse(reuse.matching_inputs(before, git('rev-parse', 'HEAD'), root))


if __name__ == '__main__':
    unittest.main()
