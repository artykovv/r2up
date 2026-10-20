"""Upload logic for files and directories to Cloudflare R2."""

import mimetypes
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Generator, List, Optional
from botocore.exceptions import ClientError
from .config import R2Config
from .client import get_r2_client


class UploadStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class UploadItem:
    local_path: Path
    remote_key: str
    size: int
    content_type: str


@dataclass
class UploadResult:
    item: UploadItem
    status: UploadStatus
    elapsed_seconds: float = 0.0
    error_message: Optional[str] = None


class ProgressCallback:
    """Callback for tracking uploaded bytes."""

    def __init__(self, callback: Optional[Callable[[int], None]] = None):
        self.callback = callback

    def __call__(self, bytes_amount: int):
        if self.callback:
            self.callback(bytes_amount)


class R2Uploader:
    def __init__(self, config: R2Config):
        self.config = config
        self.client = get_r2_client(config)

    def object_exists(self, key: str) -> bool:
        """Check if an object already exists in the bucket."""
        try:
            self.client.head_object(Bucket=self.config.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            # If forbidden or other error, assume it doesn't or will fail on upload
            return False
    def create_folder(self, folder_path: str) -> str:
        """Create a directory marker (zero-byte object ending with /) in Cloudflare R2."""
        clean_path = folder_path.strip("/")
        if not clean_path:
            raise ValueError("Имя папки не может быть пустым.")
        folder_key = f"{clean_path}/"
        self.client.put_object(
            Bucket=self.config.bucket_name,
            Key=folder_key,
            Body=b"",
        )
        return folder_key

    def list_items(
        self,
        prefix: str = "",
        recursive: bool = False,
    ) -> tuple[List[str], List[dict]]:
        """
        List folders and files in the bucket.
        Returns a tuple of (folders_list, files_list).
        """
        clean_prefix = prefix.strip("/")
        if clean_prefix:
            clean_prefix += "/"

        paginator = self.client.get_paginator("list_objects_v2")
        folders_set = set()
        files_list = []

        pagination_args = {
            "Bucket": self.config.bucket_name,
            "Prefix": clean_prefix,
        }
        if not recursive:
            pagination_args["Delimiter"] = "/"

        for page in paginator.paginate(**pagination_args):
            if not recursive:
                for cp in page.get("CommonPrefixes", []):
                    folders_set.add(cp.get("Prefix"))

            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if key == clean_prefix:
                    # Skip the prefix folder marker itself if looking inside it
                    continue

                if key.endswith("/"):
                    folders_set.add(key)
                else:
                    if recursive:
                        parts = key.split("/")
                        for i in range(1, len(parts)):
                            subfolder = "/".join(parts[:i]) + "/"
                            if not clean_prefix or subfolder.startswith(clean_prefix):
                                folders_set.add(subfolder)

                    files_list.append({
                        "key": key,
                        "size": obj.get("Size", 0),
                        "last_modified": obj.get("LastModified"),
                    })

        return sorted(list(folders_set)), sorted(files_list, key=lambda x: x["key"])

    def list_multipart_uploads(self, prefix: str = "") -> List[dict]:
        """List active/abandoned multipart uploads."""
        clean_prefix = prefix.strip("/")
        res = self.client.list_multipart_uploads(
            Bucket=self.config.bucket_name,
            Prefix=clean_prefix if clean_prefix else "",
        )
        return res.get("Uploads", [])

    def abort_multipart_uploads(self, prefix: str = "") -> int:
        """Abort active/unfinished multipart uploads and free storage."""
        uploads = self.list_multipart_uploads(prefix=prefix)
        aborted = 0
        for u in uploads:
            self.client.abort_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=u["Key"],
                UploadId=u["UploadId"],
            )
            aborted += 1
        return aborted

    @staticmethod
    def detect_content_type(path: Path) -> str:
        """Detect MIME type from file extension."""
        mime, _ = mimetypes.guess_type(path)
        return mime or "application/octet-stream"


    @classmethod
    def prepare_items(
        cls,
        paths: List[Path],
        recursive: bool = False,
        prefix: str = "",
        custom_key: Optional[str] = None,
        excludes: Optional[List[str]] = None,
        preserve_dir_name: bool = True,
    ) -> List[UploadItem]:
        """Scan paths and build a list of UploadItem with calculated remote keys."""
        import fnmatch

        exclude_patterns = list(excludes or [])
        # Always ignore common system junk files by default unless explicitly wanted
        exclude_patterns.extend([".DS_Store", "Thumbs.db", ".git/*", "*__pycache__*", "*.pyc"])

        def is_excluded(p: Path) -> bool:
            name = p.name
            path_str = p.as_posix()
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path_str, pattern):
                    return True
            return False

        items: List[UploadItem] = []
        clean_prefix = prefix.strip("/")

        if len(paths) == 1 and custom_key and not paths[0].is_dir():
            path = paths[0]
            if not path.is_file():
                raise FileNotFoundError(f"Файл не найден: {path}")
            if is_excluded(path):
                return []
            items.append(
                UploadItem(
                    local_path=path,
                    remote_key=custom_key.lstrip("/"),
                    size=path.stat().st_size,
                    content_type=cls.detect_content_type(path),
                )
            )
            return items

        for base_path in paths:
            if not base_path.exists():
                raise FileNotFoundError(f"Путь не найден: {base_path}")

            if base_path.is_file():
                if is_excluded(base_path):
                    continue
                key = base_path.name
                if clean_prefix:
                    key = f"{clean_prefix}/{key}"
                items.append(
                    UploadItem(
                        local_path=base_path,
                        remote_key=key,
                        size=base_path.stat().st_size,
                        content_type=cls.detect_content_type(base_path),
                    )
                )
            elif base_path.is_dir():
                if not recursive:
                    raise IsADirectoryError(
                        f"'{base_path}' является каталогом. Используйте флаг -r / --recursive для загрузки папок."
                    )
                # Recursively walk directory
                for root, _, files in os.walk(base_path):
                    for file_name in sorted(files):
                        file_path = Path(root) / file_name
                        if is_excluded(file_path):
                            continue
                        rel_path = file_path.relative_to(base_path).as_posix()
                        
                        dir_prefix = base_path.name if preserve_dir_name else ""
                        if clean_prefix and dir_prefix:
                            key = f"{clean_prefix}/{dir_prefix}/{rel_path}"
                        elif clean_prefix:
                            key = f"{clean_prefix}/{rel_path}"
                        elif dir_prefix:
                            key = f"{dir_prefix}/{rel_path}"
                        else:
                            key = rel_path

                        items.append(
                            UploadItem(
                                local_path=file_path,
                                remote_key=key,
                                size=file_path.stat().st_size,
                                content_type=cls.detect_content_type(file_path),
                            )
                        )

        return items

    def upload_single_file(
        self,
        item: UploadItem,
        overwrite: bool = True,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> UploadResult:
        """Upload a single file to Cloudflare R2."""
        start_time = time.time()

        if not overwrite and self.object_exists(item.remote_key):
            return UploadResult(
                item=item,
                status=UploadStatus.SKIPPED,
                elapsed_seconds=time.time() - start_time,
                error_message="Файл уже существует в бакете (--no-clobber)",
            )

        extra_args = {"ContentType": item.content_type}
        callback = ProgressCallback(on_progress)

        try:
            self.client.upload_file(
                Filename=str(item.local_path),
                Bucket=self.config.bucket_name,
                Key=item.remote_key,
                ExtraArgs=extra_args,
                Callback=callback,
            )
            elapsed = time.time() - start_time
            return UploadResult(
                item=item,
                status=UploadStatus.SUCCESS,
                elapsed_seconds=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return UploadResult(
                item=item,
                status=UploadStatus.FAILED,
                elapsed_seconds=elapsed,
                error_message=str(e),
            )
