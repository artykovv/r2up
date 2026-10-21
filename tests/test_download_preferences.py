import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from r2_uploader.cli import download_cli
from r2_uploader.preferences import ensure_download_dir, load_download_dir, save_download_dir


class DownloadPreferenceTests(unittest.TestCase):
    def test_download_directory_is_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_file = root / "config" / "settings.json"
            selected_dir = root / "downloads"

            saved = save_download_dir(selected_dir, settings_file=settings_file)

            self.assertTrue(selected_dir.is_dir())
            self.assertEqual(saved, selected_dir.resolve())
            self.assertEqual(load_download_dir(settings_file=settings_file), selected_dir.resolve())

    def test_download_directory_cannot_be_an_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "not-a-folder"
            file_path.write_text("file", encoding="utf-8")

            with self.assertRaises(NotADirectoryError):
                ensure_download_dir(file_path)

    def test_first_download_prompts_and_remembers_directory(self):
        selected_dir = Path("/tmp/r2up-test-downloads")
        config = SimpleNamespace(bucket_name="test-bucket")

        with (
            patch("r2_uploader.cli.R2Config.load", return_value=config),
            patch("r2_uploader.cli.load_download_dir", return_value=None),
            patch("r2_uploader.cli.save_download_dir", return_value=selected_dir) as save_dir,
            patch("r2_uploader.cli.click.prompt", return_value=str(selected_dir)) as prompt,
            patch("r2_uploader.cli.sys.stdin", new=SimpleNamespace(isatty=lambda: True)),
            patch("r2_uploader.cli.handle_download") as handle_download,
        ):
            download_cli.callback("folder/report.pdf", None, False, None, None, None)

        prompt.assert_called_once()
        save_dir.assert_called_once_with(str(selected_dir))
        handle_download.assert_called_once_with(
            key="folder/report.pdf",
            output=None,
            force=False,
            download_dir=selected_dir,
            config=config,
        )

    def test_directory_can_be_changed_without_r2_credentials(self):
        new_dir = Path("/tmp/r2up-new-downloads")
        with patch("r2_uploader.cli.save_download_dir", return_value=new_dir), patch(
            "r2_uploader.cli.R2Config.load"
        ) as load_config:
            download_cli.callback(None, None, False, new_dir, None, None)

        load_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
