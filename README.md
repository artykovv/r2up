# r2up — Cloudflare R2 Storage CLI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**English** | [Русский](README.ru.md)

A fast, reliable, and user-friendly command-line utility for uploading files and managing objects in **Cloudflare R2** storage (S3-compatible API).

> [!NOTE]
> Designed specifically for **upload-only** and storage management workflows: high-speed transfers, live progress visualization, directory structure preservation, and clean summary reports without public URL generation overhead.

---

## 🚀 Features

- ⚡ **High Performance**: Built on top of `boto3` with automatic multipart upload for large files.
- 📊 **Rich Terminal UI**: Beautiful real-time progress bars powered by `rich`, showing upload speed (MB/s), ETA, and percentages.
- 📁 **Recursive Directory Uploads**: Upload entire folders (`-r` / `--recursive`) preserving directory hierarchy.
- 🎯 **Key & Prefix Control**: Customize destination path with `--prefix` or specify an exact object key with `--key`.
- 🔍 **Dry Run Mode**: Inspect files, keys, and destinations before uploading anything with `--dry-run`.
- 🛡️ **Overwrite Protection**: Skip existing files in the bucket using `--no-clobber`.
- 📂 **Directory Markers**: Create remote folder markers using `r2up --mkdir` (or `r2up mkdir`).
- 📋 **Bucket Explorer**: List files and folders with `r2up --ls` (or `r2up ls`) in a neat terminal table.
- 🧹 **Multipart Cleanup**: Easily abort unfinished/dangling multipart uploads with `r2up --abort` (or `r2up abort`).
- ⚙️ **Smart Endpoint Normalization**: Automatically trims accidental bucket names or paths from `R2_ENDPOINT_URL`.

---

## 📦 Installation

### 1. Recommended: Global CLI via `pipx`
[pipx](https://pypa.github.io/pipx/) installs the CLI in an isolated environment and makes the `r2up` command globally available in your terminal from any folder:

```bash
# Install directly from GitHub
pipx install git+https://github.com/artykovv/r2up.git
```

Or from a local cloned directory:
```bash
git clone https://github.com/artykovv/r2up.git
cd r2up
pipx install .
```

*(You can also use standard `pip install .`)*

### 2. For Development (Poetry)
```bash
git clone https://github.com/artykovv/r2up.git
cd r2up
poetry install
poetry run r2up --help
```

---

## 🛠️ Configuration (`.env`)

`r2up` looks for credentials in the following order:

1. **Global User Config (Recommended for global CLI use)**:
   Place your credentials in `~/.config/r2up/.env` (or `~/.r2up.env`) to use `r2up` seamlessly from any directory:
   ```bash
   mkdir -p ~/.config/r2up
   cat << 'EOF' > ~/.config/r2up/.env
   R2_ENDPOINT_URL="https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
   R2_ACCESS_KEY_ID="your_access_key_id"
   R2_SECRET_ACCESS_KEY="your_secret_access_key"
   R2_BUCKET_NAME="your_bucket_name"
   EOF
   ```

2. **Current Directory**:
   A `.env` file located in your current working directory.

3. **Shell Environment Variables**:
   Exported variables in your shell (`export R2_ACCESS_KEY_ID=...`).

---

## 💻 Usage

`r2up` supports both **flags** (`r2up --upload`, `r2up --mkdir`, `r2up --ls`, `r2up --abort`) and **subcommands** (`r2up upload`, `r2up mkdir`, `r2up ls`, `r2up abort`).

### 1. Upload a Single File
```bash
# Direct / default upload mode
r2up photo.jpg

# Or explicit flag
r2up --upload photo.jpg

# Or subcommand
r2up upload photo.jpg
```

Upload into a specific folder/prefix:
```bash
r2up photo.jpg --prefix uploads/2026
```

Upload with an explicit target key:
```bash
r2up photo.jpg --key avatars/admin.jpg
```

### 2. Upload Multiple Files
```bash
r2up file1.txt file2.pdf archive.zip
```

### 3. Recursive Folder Upload
Use `-r` (or `--recursive`) and `--prefix` (or `-p`):

```bash
# Option A: Folder "my_folder" is placed inside the target prefix
# Result: live/2026/my_folder/file.txt
r2up -r ./my_folder/ --prefix live/2026

# Option B: Upload folder contents directly into the prefix
# Result: live/2026/file.txt
r2up -r ./my_folder/ --prefix live/2026 --content-only

# Option C: If already inside the directory (use dot .)
# Result: live/2026/file.txt
r2up -r . --prefix live/2026
```

### 4. Preview Changes (Dry Run)
Inspect files and destination keys without uploading data:
```bash
r2up -r ./my_folder/ --dry-run
```

### 5. Skip Existing Files (No Clobber)
Avoid re-uploading and overwriting objects that already exist in the bucket:
```bash
r2up -r ./my_folder/ --no-clobber
```

---

### 6. Create Remote Folders (`--mkdir`)
Create directory markers (keys ending with `/`) directly in the bucket:

```bash
# Using flag
r2up --mkdir photos

# Or using subcommand
r2up mkdir photos

# Create multiple folders at once
r2up --mkdir documents archive logs

# Create nested directory hierarchy
r2up --mkdir 2026/backups/database

# Inside a specific prefix
r2up --mkdir albums --prefix user_101

# Preview before creating
r2up --mkdir new_folder --dry-run
```

---

### 7. List Files and Directories (`--ls`)
Explore bucket contents in formatted tables:

```bash
# List items in bucket root
r2up --ls
# (or: r2up ls)

# List items inside a specific prefix/folder
r2up --ls live
# (or: r2up ls live)

# List folders only (hide files)
r2up --ls live -d

# Recursively list all nested files and folders
r2up --ls -r
```

---

### 8. Clean Up Incomplete Multipart Uploads (`--abort`)
If an upload was interrupted (e.g. `Ctrl+C` during large file transfer), Cloudflare R2 may store unfinished parts that occupy storage space:

```bash
# Abort all dangling multipart uploads in the bucket
r2up --abort
# (or: r2up abort)
```

---

### 9. CLI Reference & Help
```bash
r2up --help
r2up mkdir --help
r2up ls --help
r2up abort --help
```

> [!TIP]
> **Backwards Compatibility**: Dedicated commands `r2-upload`, `r2-mkdir`, `r2-ls`, and `r2-abort` remain available as aliases.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).