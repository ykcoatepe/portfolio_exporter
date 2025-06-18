import unittest
import unittest.mock
from pathlib import Path
import tempfile

import orchestrate_dataset as od


class OrchestrateTests(unittest.TestCase):
    def test_run_script_collects_new_files(self):
        tmp = Path("./tmp_test_run")
        tmp.mkdir(exist_ok=True)
        self.addCleanup(lambda: [p.unlink() for p in tmp.iterdir()])
        od.OUTPUT_DIR = str(tmp)

        def dummy_run(cmd, check, stdout=None, stderr=None, timeout=None, stdin=None):
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

    def test_main_cleans_up_files(self):
        with tempfile.TemporaryDirectory() as td:
            od.OUTPUT_DIR = td
            created: list[Path] = []

            def fake_run_script(cmd):
                path = Path(td) / f"{cmd[0]}.csv"
                path.write_text("x")
                created.append(path)
                return [str(path)]

            with unittest.mock.patch.object(
                od, "run_script", side_effect=fake_run_script
            ):
                with unittest.mock.patch("builtins.input", return_value=""):
                    od.main()

            zips = list(Path(td).glob("dataset_*.zip"))
            self.assertEqual(len(zips), 1)
            for p in created:
                self.assertFalse(p.exists())


if __name__ == "__main__":
    unittest.main()
