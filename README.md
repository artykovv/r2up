# r2up — Cloudflare R2 Storage CLI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**English** | [Русский](README.ru.md)

A fast, reliable, and user-friendly command-line utility for uploading files and directories to **Cloudflare R2** object storage (S3-compatible API).

> [!NOTE]
> Designed specifically for **upload-only** and management workflows: it focuses on high-speed transfers, live progress visualization, directory structure preservation, and clean summary reports without public URL generation overhead.

---

## 🚀 Features

- ⚡ **High Performance**: Built on top of `boto3` with automatic multipart upload for large files.
- 📊 **Rich Terminal UI**: Beautiful real-time progress bars powered by `rich`, showing upload speed (MB/s), ETA, and percentages.
- 📁 **Recursive Directory Uploads**: Upload entire folders (`-r` / `--recursive`) preserving directory structure.
- 🎯 **Key & Prefix Control**: Customize destination path with `--prefix` or specify an exact object key with `--key`.
- 🔍 **Dry Run Mode**: Inspect files, keys, and destinations before uploading anything with `--dry-run`.
- 🛡️ **Overwrite Protection**: Skip existing files in the bucket using `--no-clobber`.
- 📂 **Directory Markers**: Create remote folder markers using `r2-mkdir` (or `r2-upload --mkdir`).
- 📋 **Bucket Explorer**: List files and folders with `r2-ls` in a neat terminal table.
- 🧹 **Multipart Cleanup**: Easily abort unfinished/dangling multipart uploads with `r2-abort`.
- ⚙️ **Smart Endpoint Normalization**: Automatically trims accidental bucket names or paths from `R2_ENDPOINT_URL`.

---

## 📦 Installation

Clone the repository and install dependencies using [Poetry](https://python-poetry.org/):

```bash
git clone https://github.com/artykovv/r2up.git
cd r2up
poetry install
```

To make commands accessible globally across your system:
```bash
poetry run pip install -e .
```

---

## 🛠️ Configuration (`.env`)

Create a `.env` file in the project root or configure your shell environment:

```env
R2_ENDPOINT_URL="https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
R2_ACCESS_KEY_ID="your_access_key_id"
R2_SECRET_ACCESS_KEY="your_secret_access_key"
R2_BUCKET_NAME="your_bucket_name"
```

---

## 💻 Usage

### 1. Upload a Single File
```bash
r2-upload photo.jpg
```

Upload into a specific folder/prefix:
```bash
r2-upload photo.jpg --prefix uploads/2026
```

Upload with an explicit target key:
```bash
r2-upload photo.jpg --key avatars/admin.jpg
```

### 2. Upload Multiple Files
```bash
r2-upload file1.txt file2.pdf archive.zip
```

### 3. Recursive Folder Upload
Use `-r` (or `--recursive`) and `--prefix` (or `-p`):

```bash
# Option A: Folder "my_folder" is placed inside the target prefix
# Result: live/2026/my_folder/file.txt
r2-upload -r ./my_folder/ --prefix live/2026

# Option B: Upload folder contents directly into the prefix
# Result: live/2026/file.txt
r2-upload -r ./my_folder/ --prefix live/2026 --content-only

# Option C: If already inside the directory (use dot .)
# Result: live/2026/file.txt
r2-upload -r . --prefix live/2026
```

### 4. Preview Changes (Dry Run)
Inspect the files and destination keys without actually transferring data:
```bash
r2-upload -r ./my_folder/ --dry-run
```

### 5. Skip Existing Files (No Clobber)
Avoid re-uploading and overwriting objects that already exist in the bucket:
```bash
r2-upload -r ./my_folder/ --no-clobber
```

### 6. Create Remote Folders (`r2-mkdir`)
Create directory markers (keys ending with `/`) directly in the bucket:

```bash
# Create a single folder
r2-mkdir photos

# Create multiple folders at once
r2-mkdir documents archive logs

# Create nested directory hierarchy
r2-mkdir 2026/backups/database

# Inside a specific prefix
r2-mkdir albums --prefix user_101

# Preview before creating
r2-mkdir new_folder --dry-run
```

*(You can also use `r2-upload --mkdir <folder_name>`)*

---

### 7. List Files and Directories (`r2-ls`)
Explore bucket contents in formatted tables:

```bash
# List items in bucket root
r2-ls

# List items inside a specific prefix/folder
r2-ls live

# List folders only (hide files)
r2-ls -d
r2-ls -d live

# Recursively list all nested files and folders
r2-ls -r

# Or via the -l flag in r2-upload
r2-upload -l
r2-upload -l live
```

---

### 8. Clean Up Incomplete Multipart Uploads (`r2-abort`)
If an upload was interrupted (e.g. `Ctrl+C` during large file transfer), Cloudflare R2 may store unfinished parts that occupy storage space:

```bash
# Abort all dangling multipart uploads in the bucket
r2-abort

# Or using the flag in r2-upload
r2-upload --abort-multipart
```

---

### 9. CLI Reference & Help
```bash
r2-upload --help
r2-mkdir --help
r2-ls --help
r2-abort --help
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).