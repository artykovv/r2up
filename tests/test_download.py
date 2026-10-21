import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from r2_uploader.uploader import R2Uploader


class DownloadTransferTests(unittest.TestCase):
    def setUp(self):
        self.uploader = R2Uploader.__new__(R2Uploader)
        self.uploader.config = SimpleNamespace(bucket_name="test-bucket")
        self.uploader.client = Mock()

    def test_download_writes_object_to_destination(self):
        def write_download(bucket, key, filename, **kwargs):
            Path(filename).write_bytes(b"file contents")
            if kwargs.get("Callback"):
                kwargs["Callback"](13)

        self.uploader.client.download_file.side_effect = write_download

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "nested" / "download.txt"
            progress = Mock()
            result = self.uploader.download_file("folder/item.txt", destination, callback=progress)

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"file contents")
            progress.assert_called_once_with(13)
            self.assertEqual(list(destination.parent.iterdir()), [destination])

    def test_download_does_not_overwrite_existing_file_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "download.txt"
            destination.write_text("keep me", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                self.uploader.download_file("item.txt", destination)

            self.uploader.client.download_file.assert_not_called()
            self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")

    def test_download_force_replaces_existing_file(self):
        self.uploader.client.download_file.side_effect = (
            lambda bucket, key, filename, **kwargs: Path(filename).write_bytes(b"new contents")
        )

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "download.txt"
            destination.write_text("old contents", encoding="utf-8")

            self.uploader.download_file("item.txt", destination, overwrite=True)

            self.assertEqual(destination.read_bytes(), b"new contents")
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_failed_download_leaves_no_partial_file(self):
        def fail_download(bucket, key, filename, **kwargs):
            Path(filename).write_bytes(b"partial")
            raise RuntimeError("interrupted")

        self.uploader.client.download_file.side_effect = fail_download

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "download.txt"
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.uploader.download_file("item.txt", destination)

            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])



if __name__ == "__main__":
    unittest.main()
