import unittest
from pathlib import Path
import tempfile

import orchestrate_dataset as od


class OrchestrateTests(unittest.TestCase):
    def test_run_script_collects_new_files(self):
        tmp = Path("./tmp_test_run")
        tmp.mkdir(exist_ok=True)
        self.addCleanup(lambda: [p.unlink() for p in tmp.iterdir()])
        od.OUTPUT_DIR = str(tmp)

        def dummy_run(cmd, check):
            (tmp / "new.csv").write_text("x")

        prev = od.subprocess.run
        od.subprocess.run = dummy_run
        try:
            created = od.run_script(["dummy.py"])
        finally:
            od.subprocess.run = prev
        self.assertEqual(len(created), 1)
        self.assertTrue((tmp / "new.csv") in map(Path, created))

    def test_create_zip(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            f1 = td_path / "a.txt"
            f2 = td_path / "b.txt"
            f1.write_text("1")
            f2.write_text("2")
            zip_path = td_path / "out.zip"
            od.create_zip([str(f1), str(f2)], str(zip_path))
            self.assertTrue(zip_path.exists())
            import zipfile

            with zipfile.ZipFile(zip_path) as zf:
                self.assertEqual(set(zf.namelist()), {"a.txt", "b.txt"})


if __name__ == "__main__":
    unittest.main()
