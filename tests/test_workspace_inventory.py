import hashlib
import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
INVENTORY = REPO / "tools" / "inventory_workspace.py"


class WorkspaceInventoryTests(unittest.TestCase):
    def run_inventory(self, root, output, check=False):
        command = [sys.executable, str(INVENTORY), "--root", str(root), "--output", str(output)]
        if check:
            command.append("--check")
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_inventory_covers_each_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            (root / "nested").mkdir(parents=True)
            (root / ".git").mkdir()
            (root / "alpha.py").write_bytes(b"alpha")
            (root / "nested" / "image.bin").write_bytes(b"\x00\xff")
            (root / ".git" / "config").write_text("repository metadata", encoding="utf-8")
            output = Path(temp_dir) / "inventory.json"

            result = self.run_inventory(root, output)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            rows = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual({"alpha.py", "nested/image.bin"}, {row["path"] for row in rows})

    def test_paths_are_relative_and_content_is_not_copied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            sample = b"do not put this text in the report"
            (root / "notes.txt").write_bytes(sample)
            output = Path(temp_dir) / "inventory.json"

            result = self.run_inventory(root, output)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            rows = json.loads(output.read_text(encoding="utf-8"))
            row = rows[0]
            self.assertEqual("notes.txt", row["path"])
            self.assertEqual(len(sample), row["size_bytes"])
            self.assertEqual(hashlib.sha256(sample).hexdigest(), row["sha256"])
            self.assertEqual("unclassified", row["classification"])
            self.assertNotIn("content", row)
            self.assertNotIn(sample.decode(), output.read_text(encoding="utf-8"))
            self.assertNotIn(str(root), output.read_text(encoding="utf-8"))

    def test_git_metadata_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            (root / "project" / ".git").mkdir(parents=True)
            (root / "project" / ".git" / "index").write_bytes(b"git index")
            (root / "project" / "readme.md").write_text("readme", encoding="utf-8")
            output = Path(temp_dir) / "inventory.json"

            result = self.run_inventory(root, output)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            rows = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(["project/readme.md"], [row["path"] for row in rows])

    def test_existing_classification_is_preserved_on_rescan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            (root / "main.py").write_text("print('ok')\r\n", encoding="utf-8")
            output = Path(temp_dir) / "inventory.json"

            first = self.run_inventory(root, output)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            rows = json.loads(output.read_text(encoding="utf-8"))
            rows[0]["classification"] = "source"
            output.write_text(json.dumps(rows), encoding="utf-8")

            second = self.run_inventory(root, output)

            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            rescanned = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("source", rescanned[0]["classification"])

    def test_check_rejects_unclassified_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            root.mkdir()
            (root / "main.py").write_text("print('ok')\r\n", encoding="utf-8")
            output = Path(temp_dir) / "inventory.json"

            pending = self.run_inventory(root, output, check=True)
            self.assertEqual(1, pending.returncode)

            rows = json.loads(output.read_text(encoding="utf-8"))
            rows[0]["classification"] = "source"
            output.write_text(json.dumps(rows), encoding="utf-8")
            reviewed = self.run_inventory(root, output, check=True)
            self.assertEqual(0, reviewed.returncode, reviewed.stdout + reviewed.stderr)

    def test_python_cache_files_are_classified_as_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            cache = root / "module" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "module.cpython-315.pyc").write_bytes(b"bytecode")
            output = Path(temp_dir) / "inventory.json"

            result = self.run_inventory(root, output)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            rows = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("cache", rows[0]["classification"])


    def test_symlinks_are_listed_without_reading_their_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "workspace"
            root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("private target content", encoding="utf-8")
            link = root / "external-link"
            try:
                os.symlink(outside, link)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            output = base / "inventory.json"

            result = self.run_inventory(root, output)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            report = output.read_text(encoding="utf-8")
            rows = json.loads(report)
            self.assertEqual("symlink", rows[0]["kind"])
            self.assertNotIn("private target content", report)


if __name__ == "__main__":
    unittest.main()
