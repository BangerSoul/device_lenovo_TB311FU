import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from partitions import strip_system_cellular as transformer


class StripSystemCellularSafetyTests(unittest.TestCase):
    def test_missing_ext4_is_failure(self):
        with patch.object(transformer, "ext4", None):
            ok, errors = transformer.verify_image_with_ext4("not-opened.img")

        self.assertFalse(ok)
        self.assertTrue(any("ext4" in error.lower() for error in errors))

    def test_ext4_parse_error_is_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "broken.img"
            image.write_bytes(b"not an ext4 image")
            fake_ext4 = SimpleNamespace(Volume=unittest.mock.Mock(side_effect=ValueError("bad superblock")))

            with patch.object(transformer, "ext4", fake_ext4):
                ok, errors = transformer.verify_image_with_ext4(str(image))

        self.assertFalse(ok)
        self.assertTrue(any("bad superblock" in error for error in errors))

    def test_ext4_directory_scan_error_is_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "system.img"
            image.write_bytes(b"image bytes")
            fake_volume = SimpleNamespace(
                inode_at=unittest.mock.Mock(side_effect=OSError("directory scan failed"))
            )
            fake_ext4 = SimpleNamespace(Volume=unittest.mock.Mock(return_value=fake_volume))

            with patch.object(transformer, "ext4", fake_ext4):
                ok, errors = transformer.verify_image_with_ext4(str(image))

        self.assertFalse(ok)
        self.assertTrue(any("directory scan failed" in error for error in errors))

    def test_missing_7z_is_failure(self):
        with (
            patch.object(transformer.os.path, "exists", return_value=False),
            patch.object(transformer.shutil, "which", return_value=None),
        ):
            ok, errors = transformer.verify_image_with_7z("system.img")

        self.assertFalse(ok)
        self.assertTrue(any("7z" in error.lower() for error in errors))

    def test_7z_nonzero_exit_is_failure(self):
        with (
            patch.object(transformer.os.path, "exists", return_value=False),
            patch.object(transformer.shutil, "which", return_value="/usr/bin/7z"),
            patch.object(
                transformer.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=2, stdout="", stderr="cannot open archive"),
            ),
        ):
            ok, errors = transformer.verify_image_with_7z("system.img")

        self.assertFalse(ok)
        self.assertTrue(any("cannot open archive" in error for error in errors))

    def test_7z_launch_error_is_failure(self):
        with (
            patch.object(transformer.os.path, "exists", return_value=False),
            patch.object(transformer.shutil, "which", return_value="/usr/bin/7z"),
            patch.object(transformer.subprocess, "run", side_effect=OSError("7z could not start")),
        ):
            ok, errors = transformer.verify_image_with_7z("system.img")

        self.assertFalse(ok)
        self.assertTrue(any("7z could not start" in error for error in errors))

    def test_dry_run_does_not_create_or_modify_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.img"
            output = Path(temp_dir) / "output.img"
            source.write_bytes(b"pristine image")
            before = source.read_bytes()
            argv = [
                "strip_system_cellular.py",
                "--image",
                str(source),
                "--output",
                str(output),
                "--dry-run",
            ]

            stderr = io.StringIO()
            with patch.object(transformer.sys, "argv", argv), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    transformer.main()
            self.assertEqual(2, raised.exception.code)
            self.assertIn("--dry-run cannot be combined with --output", stderr.getvalue())
            self.assertEqual(before, source.read_bytes())
            self.assertFalse(output.exists())

    def test_dry_run_scans_source_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.img"
            source.write_bytes(b"pristine image")
            before = source.read_bytes()
            argv = ["strip_system_cellular.py", "--image", str(source), "--dry-run"]
            surgery = SimpleNamespace(find_targets=unittest.mock.Mock(return_value=[]))
            stdout = io.StringIO()

            with (
                patch.object(transformer.sys, "argv", argv),
                patch.object(transformer, "Ext4DirectorySurgery", return_value=surgery),
                contextlib.redirect_stdout(stdout),
            ):
                transformer.main()

            self.assertEqual(before, source.read_bytes())
            self.assertIn('"dry_run": true', stdout.getvalue())

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.img"
            output = Path(temp_dir) / "output.img"
            source.write_bytes(b"source bytes")
            output.write_bytes(b"existing output bytes")

            with self.assertRaises(FileExistsError):
                transformer.strip_system_cellular(str(source), output_path=str(output))

            self.assertEqual(b"existing output bytes", output.read_bytes())

    def test_output_must_differ_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.img"
            source.write_bytes(b"source bytes")

            alias = str(source.parent) + transformer.os.sep + "." + transformer.os.sep + source.name
            with self.assertRaisesRegex(ValueError, "output path must differ from source"):
                transformer.strip_system_cellular(str(source), output_path=alias)

            self.assertEqual(b"source bytes", source.read_bytes())

    def test_failed_post_transform_verification_returns_nonzero(self):
        argv = [
            "strip_system_cellular.py",
            "--image",
            "source.img",
            "--output",
            "output.img",
        ]
        failed_result = {"verification": {"all_passed": False}}
        stdout = io.StringIO()

        with (
            patch.object(transformer.sys, "argv", argv),
            patch.object(transformer, "strip_system_cellular", return_value=failed_result),
            contextlib.redirect_stdout(stdout),
        ):
            with self.assertRaises(SystemExit) as raised:
                transformer.main()

        self.assertEqual(1, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
