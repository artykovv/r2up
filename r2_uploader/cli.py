"""Command line interface for Cloudflare R2 storage management and uploads."""

import sys
from pathlib import Path
from typing import List, Optional
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from .config import R2Config
from .uploader import R2Uploader, UploadItem, UploadResult, UploadStatus

console = Console()
error_console = Console(stderr=True)


def format_bytes(size: float) -> str:
    """Format bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} B"


def handle_mkdir(
    folders: tuple[str, ...],
    prefix: str,
    config: R2Config,
    dry_run: bool,
):
    """Handle creation of folder markers in Cloudflare R2."""
    clean_prefix = prefix.strip("/")
    folder_keys = []
    for f in folders:
        f_clean = f.strip("/")
        if not f_clean:
            continue
        key = f"{clean_prefix}/{f_clean}/" if clean_prefix else f"{f_clean}/"
        folder_keys.append(key)

    if not folder_keys:
        console.print("[yellow]No folder names specified.[/yellow]")
        sys.exit(0)

    header_text = (
        f"[bold]Bucket:[/bold] [cyan]{config.bucket_name}[/cyan]\n"
        f"[bold]Endpoint:[/bold] [dim]{config.endpoint_url}[/dim]\n"
        f"[bold]Folders to create:[/bold] {len(folder_keys)}"
    )
    if dry_run:
        header_text += "\n[bold yellow]DRY-RUN MODE — no folders will be created[/bold yellow]"

    console.print(Panel(header_text, title="[bold cyan]Create Folders in Cloudflare R2[/bold cyan]", border_style="cyan"))

    if dry_run:
        for k in folder_keys:
            console.print(f" [dim]•[/dim] [cyan]{k}[/cyan] (will be created)")
        console.print("\n[yellow]Dry-run complete. No folders were created.[/yellow]")
        return

    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]R2 connection error:[/bold red] {e}")
        sys.exit(1)

    table = Table(title="Folder Creation Results", show_header=True, header_style="bold")
    table.add_column("Remote Folder Key", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details / Errors", style="red")

    success_count = 0
    fail_count = 0

    for key in folder_keys:
        try:
            uploader.create_folder(key)
            table.add_row(key, "[bold green]✓ Created[/bold green]", "")
            success_count += 1
        except Exception as e:
            table.add_row(key, "[bold red]✗ Failed[/bold red]", str(e))
            fail_count += 1

    console.print(table)
    summary_text = (
        f"[bold]Total:[/bold] {len(folder_keys)} | "
        f"[green]Created:[/green] {success_count} | "
        f"[red]Failed:[/red] {fail_count}"
    )
    console.print(Panel(summary_text, style="bold", title="Summary"))
    if fail_count > 0:
        sys.exit(1)


def handle_ls(
    prefix: str,
    folders_only: bool,
    recursive: bool,
    config: R2Config,
):
    """Handle listing of folders and files in Cloudflare R2."""
    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]R2 connection error:[/bold red] {e}")
        sys.exit(1)

    clean_prefix = prefix.strip("/")
    display_prefix = f"/{clean_prefix}/" if clean_prefix else "/"

    header_text = (
        f"[bold]Bucket:[/bold] [cyan]{config.bucket_name}[/cyan]\n"
        f"[bold]Path:[/bold] [yellow]{display_prefix}[/yellow]\n"
        f"[bold]Mode:[/bold] {'Recursive' if recursive else 'Current directory'}"
        f"{', folders only' if folders_only else ''}"
    )
    console.print(Panel(header_text, title="[bold cyan]Cloudflare R2 Contents[/bold cyan]", border_style="cyan"))

    folders, files = uploader.list_items(prefix=prefix, recursive=recursive)

    if folders_only:
        files = []

    if not folders and not files:
        console.print("[yellow]No items found in the specified path.[/yellow]")
        return

    table = Table(title=f"Contents of {display_prefix}", show_header=True, header_style="bold magenta")
    table.add_column("Type", justify="center", width=10)
    table.add_column("Name / Key in R2", style="bold")
    table.add_column("Size", justify="right", style="cyan")
    table.add_column("Last Modified", style="dim")

    for folder in folders:
        table.add_row("📁 Dir", f"[bold cyan]{folder}[/bold cyan]", "-", "-")

    total_file_bytes = 0
    for f in files:
        total_file_bytes += f["size"]
        mtime_str = f["last_modified"].strftime("%Y-%m-%d %H:%M:%S") if f.get("last_modified") else "-"
        table.add_row("📄 File", f["key"], format_bytes(f["size"]), mtime_str)

    console.print(table)

    summary = f"[bold]Folders:[/bold] {len(folders)}"
    if not folders_only:
        summary += f" | [bold]Files:[/bold] {len(files)} ({format_bytes(total_file_bytes)})"

    console.print(Panel(summary, style="bold", title="Summary"))


def handle_abort_multipart(prefix: str, config: R2Config):
    """Abort all unfinished/ongoing multipart uploads in bucket."""
    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]R2 connection error:[/bold red] {e}")
        sys.exit(1)

    uploads = uploader.list_multipart_uploads(prefix=prefix)
    if not uploads:
        console.print("[green]✓ No ongoing multipart uploads found in bucket.[/green]")
        return

    console.print(f"[yellow]Found ongoing multipart uploads: {len(uploads)}.[/yellow]")
    table = Table(title="Abort Ongoing Multipart Uploads", show_header=True, header_style="bold red")
    table.add_column("Object Key in R2", style="cyan")
    table.add_column("Upload ID", style="dim")
    table.add_column("Initiated", style="dim")

    for u in uploads:
        table.add_row(
            u.get("Key", ""),
            (u.get("UploadId") or "")[:35] + "...",
            str(u.get("Initiated", "")),
        )
    console.print(table)

    count = uploader.abort_multipart_uploads(prefix=prefix)
    console.print(f"[bold green]✓ Successfully aborted {count} multipart upload(s). Storage reclaimed.[/bold green]")


@click.command(
    name="r2up",
    help="Fast and reliable CLI tool for Cloudflare R2 object storage.",
)
@click.argument("paths", nargs=-1, required=False)
@click.option(
    "-u",
    "--upload",
    is_flag=True,
    default=False,
    help="Upload files or directories to R2 (default mode).",
)
@click.option(
    "-l",
    "--list",
    "--ls",
    "list_mode",
    is_flag=True,
    default=False,
    help="List files and directories in R2.",
)
@click.option(
    "-d",
    "--dirs-only",
    "--folders-only",
    "folders_only",
    is_flag=True,
    default=False,
    help="In list mode, show only folders (hide files).",
)
@click.option(
    "--abort-multipart",
    "--abort",
    is_flag=True,
    default=False,
    help="Abort and clean up ongoing multipart uploads in R2.",
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    default=False,
    help="Recursively upload or list directories.",
)
@click.option(
    "-p",
    "--prefix",
    default="",
    help="Destination prefix (folder) in Cloudflare R2 bucket.",
)
@click.option(
    "-k",
    "--key",
    default=None,
    help="Custom remote key (single file upload only).",
)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Override bucket name (defaults to R2_BUCKET_NAME from config).",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to custom .env configuration file.",
)
@click.option(
    "-e",
    "--exclude",
    multiple=True,
    help="Pattern to exclude files (e.g. '*.tmp', '__pycache__/*'). Can be used multiple times.",
)
@click.option(
    "--mkdir",
    is_flag=True,
    default=False,
    help="Create specified folders in R2 instead of uploading files.",
)
@click.option(
    "--content-only",
    is_flag=True,
    default=False,
    help="Upload folder contents directly into prefix without directory name.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Dry-run: inspect files and destination keys without uploading.",
)
@click.option(
    "--no-clobber",
    is_flag=True,
    default=False,
    help="Skip files that already exist in the bucket.",
)
def cli(
    paths: tuple[str, ...],
    upload: bool,
    list_mode: bool,
    folders_only: bool,
    abort_multipart: bool,
    recursive: bool,
    prefix: str,
    key: Optional[str],
    bucket: Optional[str],
    env_file: Optional[str],
    exclude: tuple[str, ...],
    mkdir: bool,
    content_only: bool,
    dry_run: bool,
    no_clobber: bool,
):
    """Upload files/directories or manage Cloudflare R2 storage."""
    # 1. Load configuration
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    # Abort ongoing multipart uploads
    if abort_multipart:
        handle_abort_multipart(prefix=prefix, config=config)
        return

    # List mode
    if list_mode:
        prefix_arg = paths[0] if paths else prefix
        handle_ls(
            prefix=prefix_arg,
            folders_only=folders_only,
            recursive=recursive,
            config=config,
        )
        return

    # Mkdir mode
    if mkdir:
        if not paths:
            error_console.print("[bold red]Error:[/bold red] Specify folder name(s) to create: r2up --mkdir <folder1> ...")
            sys.exit(1)
        handle_mkdir(folders=paths, prefix=prefix, config=config, dry_run=dry_run)
        return

    if not paths:
        error_console.print(
            "[bold yellow]No files or action specified.[/bold yellow]\n\n"
            "Usage examples:\n"
            "  • [cyan]r2up photo.jpg[/cyan]                — upload single file\n"
            "  • [cyan]r2up -r ./my_folder/[/cyan]         — upload directory recursively\n"
            "  • [cyan]r2up --upload file.txt[/cyan]        — explicit upload mode\n"
            "  • [cyan]r2up --ls[/cyan] (or [cyan]r2up ls[/cyan])       — list bucket contents\n"
            "  • [cyan]r2up --mkdir photos[/cyan]            — create folder in bucket\n"
            "  • [cyan]r2up --abort[/cyan]                   — abort unfinished multipart uploads\n"
            "  • [cyan]r2up --help[/cyan]                    — view all options"
        )
        sys.exit(1)

    # Validate target paths
    target_paths = []
    for p in paths:
        path_obj = Path(p)
        if not path_obj.exists():
            error_console.print(f"[bold red]Error:[/bold red] File or directory not found: {p}")
            sys.exit(1)
        target_paths.append(path_obj)

    # 2. Prepare items for upload
    try:
        items = R2Uploader.prepare_items(
            paths=target_paths,
            recursive=recursive,
            prefix=prefix,
            custom_key=key,
            excludes=list(exclude),
            preserve_dir_name=not content_only,
        )
    except Exception as e:
        error_console.print(f"[bold red]Failed to prepare files:[/bold red] {e}")
        sys.exit(1)

    if not items:
        console.print("[yellow]No files to upload.[/yellow]")
        sys.exit(0)

    total_bytes = sum(item.size for item in items)

    # 3. Header panel
    header_text = (
        f"[bold]Bucket:[/bold] [cyan]{config.bucket_name}[/cyan]\n"
        f"[bold]Endpoint:[/bold] [dim]{config.endpoint_url}[/dim]\n"
        f"[bold]Files to upload:[/bold] {len(items)} ({format_bytes(total_bytes)})"
    )
    if dry_run:
        header_text += "\n[bold yellow]DRY-RUN MODE — no files will be uploaded[/bold yellow]"

    console.print(Panel(header_text, title="[bold cyan]Cloudflare R2 Uploader[/bold cyan]", border_style="cyan"))

    # 4. Dry-Run mode
    if dry_run:
        table = Table(title="Files to Upload", show_header=True, header_style="bold magenta")
        table.add_column("Local File", style="dim")
        table.add_column("Target Key in R2", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Content Type", style="dim")

        for item in items:
            table.add_row(
                str(item.local_path),
                item.remote_key,
                format_bytes(item.size),
                item.content_type,
            )
        console.print(table)
        console.print("\n[yellow]Dry-run complete. No files were uploaded.[/yellow]")
        sys.exit(0)

    # 5. Execute upload
    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]R2 connection error:[/bold red] {e}")
        sys.exit(1)

    results: List[UploadResult] = []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            overall_task = progress.add_task(
                f"[green]Total progress ({len(items)} files)",
                total=total_bytes,
            )

            for item in items:
                file_task = progress.add_task(
                    f"[cyan]{item.remote_key}[/cyan]",
                    total=item.size,
                )

                def make_progress_handler(f_task):
                    def handler(chunk_bytes: int):
                        progress.update(f_task, advance=chunk_bytes)
                        progress.update(overall_task, advance=chunk_bytes)
                    return handler

                result = uploader.upload_single_file(
                    item=item,
                    overwrite=not no_clobber,
                    on_progress=make_progress_handler(file_task),
                )
                results.append(result)
                progress.remove_task(file_task)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Upload interrupted by user (Ctrl+C).[/bold yellow]")
        console.print("[dim]Cleaning up incomplete multipart uploads in R2...[/dim]")
        uploader.abort_multipart_uploads()
        console.print("[bold green]✓ Incomplete parts aborted. Storage cleaned.[/bold green]")
        sys.exit(130)

    # 6. Summary report
    console.print()
    report_table = Table(title="Upload Report", show_header=True, header_style="bold")
    report_table.add_column("Key in R2", style="cyan")
    report_table.add_column("Size", justify="right")
    report_table.add_column("Time", justify="right")
    report_table.add_column("Status", justify="center")
    report_table.add_column("Details / Errors", style="red")

    success_count = 0
    fail_count = 0
    skipped_count = 0
    uploaded_bytes = 0

    for res in results:
        if res.status == UploadStatus.SUCCESS:
            status_text = "[bold green]✓ Uploaded[/bold green]"
            success_count += 1
            uploaded_bytes += res.item.size
        elif res.status == UploadStatus.SKIPPED:
            status_text = "[bold yellow]⚠ Skipped[/bold yellow]"
            skipped_count += 1
        else:
            status_text = "[bold red]✗ Failed[/bold red]"
            fail_count += 1

        report_table.add_row(
            res.item.remote_key,
            format_bytes(res.item.size),
            f"{res.elapsed_seconds:.2f}s",
            status_text,
            res.error_message or "",
        )

    console.print(report_table)

    summary_text = (
        f"[bold]Total:[/bold] {len(results)} | "
        f"[green]Success:[/green] {success_count} | "
        f"[yellow]Skipped:[/yellow] {skipped_count} | "
        f"[red]Failed:[/red] {fail_count} | "
        f"[cyan]Transferred:[/cyan] {format_bytes(uploaded_bytes)}"
    )
    console.print(Panel(summary_text, style="bold", title="Summary"))

    if fail_count > 0:
        sys.exit(1)


@click.command(
    name="mkdir",
    help="Create folders in Cloudflare R2 bucket.",
)
@click.argument("folders", nargs=-1, required=True)
@click.option(
    "-p",
    "--prefix",
    default="",
    help="Parent prefix/directory in R2 bucket.",
)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Override bucket name.",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to custom .env file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Simulate creation without sending request.",
)
def mkdir_cli(
    folders: tuple[str, ...],
    prefix: str,
    bucket: Optional[str],
    env_file: Optional[str],
    dry_run: bool,
):
    """Create one or more folders in Cloudflare R2 bucket."""
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    handle_mkdir(folders=folders, prefix=prefix, config=config, dry_run=dry_run)


@click.command(
    name="ls",
    help="List files and directories in Cloudflare R2 bucket.",
)
@click.argument("prefix", default="", required=False)
@click.option(
    "-d",
    "--folders-only",
    is_flag=True,
    default=False,
    help="Show only directories.",
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    default=False,
    help="Recursively list all nested files and folders.",
)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Override bucket name.",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to custom .env file.",
)
def ls_cli(
    prefix: str,
    folders_only: bool,
    recursive: bool,
    bucket: Optional[str],
    env_file: Optional[str],
):
    """List folders and files in Cloudflare R2."""
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    handle_ls(
        prefix=prefix,
        folders_only=folders_only,
        recursive=recursive,
        config=config,
    )


@click.command(
    name="abort",
    help="Abort ongoing multipart uploads in Cloudflare R2.",
)
@click.argument("prefix", default="", required=False)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Override bucket name.",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to custom .env file.",
)
def abort_cli(
    prefix: str,
    bucket: Optional[str],
    env_file: Optional[str],
):
    """Abort all unfinished ongoing multipart uploads."""
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    handle_abort_multipart(prefix=prefix, config=config)


def main():
    """Universal CLI dispatcher for r2up supporting both subcommands and flags."""
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "upload":
            sys.argv.pop(1)
            cli()
            return
        elif cmd in ("ls", "list"):
            sys.argv.pop(1)
            ls_cli()
            return
        elif cmd == "mkdir":
            sys.argv.pop(1)
            mkdir_cli()
            return
        elif cmd in ("abort", "abort-multipart"):
            sys.argv.pop(1)
            abort_cli()
            return

    cli()


if __name__ == "__main__":
    main()
