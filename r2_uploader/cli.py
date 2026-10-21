"""Command line interface for uploading objects to Cloudflare R2."""

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
        console.print("[yellow]Не указаны имена папок для создания.[/yellow]")
        sys.exit(0)

    header_text = (
        f"[bold]Бакет:[/bold] [cyan]{config.bucket_name}[/cyan]\n"
        f"[bold]Эндпоинт:[/bold] [dim]{config.endpoint_url}[/dim]\n"
        f"[bold]Папок к созданию:[/bold] {len(folder_keys)}"
    )
    if dry_run:
        header_text += "\n[bold yellow]РЕЖИМ ПРЕДПРОСМОТРА (DRY-RUN) — папки не создаются[/bold yellow]"

    console.print(Panel(header_text, title="[bold cyan]Создание папок в Cloudflare R2[/bold cyan]", border_style="cyan"))

    if dry_run:
        for k in folder_keys:
            console.print(f" [dim]•[/dim] [cyan]{k}[/cyan] (будет создана)")
        console.print("\n[yellow]Имитация завершена. Папки не были созданы.[/yellow]")
        return

    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]Ошибка подключения к R2:[/bold red] {e}")
        sys.exit(1)

    table = Table(title="Результат создания папок в R2", show_header=True, header_style="bold")
    table.add_column("Ключ папки в R2", style="cyan")
    table.add_column("Статус", justify="center")
    table.add_column("Детали / Ошибки", style="red")

    success_count = 0
    fail_count = 0

    for key in folder_keys:
        try:
            uploader.create_folder(key)
            table.add_row(key, "[bold green]✓ Создана[/bold green]", "")
            success_count += 1
        except Exception as e:
            table.add_row(key, "[bold red]✗ Ошибка[/bold red]", str(e))
            fail_count += 1

    console.print(table)
    summary_text = (
        f"[bold]Всего:[/bold] {len(folder_keys)} | "
        f"[green]Создано:[/green] {success_count} | "
        f"[red]Ошибок:[/red] {fail_count}"
    )
    console.print(Panel(summary_text, style="bold", title="Итог"))
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
        error_console.print(f"[bold red]Ошибка подключения к R2:[/bold red] {e}")
        sys.exit(1)

    clean_prefix = prefix.strip("/")
    display_prefix = f"/{clean_prefix}/" if clean_prefix else "/"

    header_text = (
        f"[bold]Бакет:[/bold] [cyan]{config.bucket_name}[/cyan]\n"
        f"[bold]Путь:[/bold] [yellow]{display_prefix}[/yellow]\n"
        f"[bold]Режим:[/bold] {'Рекурсивный' if recursive else 'Текущий каталог'}"
        f"{', только папки' if folders_only else ''}"
    )
    console.print(Panel(header_text, title="[bold cyan]Содержимое Cloudflare R2[/bold cyan]", border_style="cyan"))

    folders, files = uploader.list_items(prefix=prefix, recursive=recursive)

    if folders_only:
        files = []

    if not folders and not files:
        console.print("[yellow]В указанном пути ничего не найдено.[/yellow]")
        return

    table = Table(title=f"Содержимое {display_prefix}", show_header=True, header_style="bold magenta")
    table.add_column("Тип", justify="center", width=10)
    table.add_column("Имя / Ключ в R2", style="bold")
    table.add_column("Размер", justify="right", style="cyan")
    table.add_column("Дата изменения", style="dim")

    # Сначала выводим папки
    for folder in folders:
        table.add_row("📁 Папка", f"[bold cyan]{folder}[/bold cyan]", "-", "-")

    # Затем файлы
    total_file_bytes = 0
    for f in files:
        total_file_bytes += f["size"]
        mtime_str = f["last_modified"].strftime("%Y-%m-%d %H:%M:%S") if f.get("last_modified") else "-"
        table.add_row("📄 Файл", f["key"], format_bytes(f["size"]), mtime_str)

    console.print(table)

    summary = f"[bold]Папок:[/bold] {len(folders)}"
    if not folders_only:
        summary += f" | [bold]Файлов:[/bold] {len(files)} ({format_bytes(total_file_bytes)})"

    console.print(Panel(summary, style="bold", title="Итог"))


def handle_abort_multipart(prefix: str, config: R2Config):
    """Abort all unfinished/ongoing multipart uploads in bucket."""
    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]Ошибка подключения к R2:[/bold red] {e}")
        sys.exit(1)

    uploads = uploader.list_multipart_uploads(prefix=prefix)
    if not uploads:
        console.print("[green]✓ В бакете нет незавершенных (Ongoing) multipart-загрузок.[/green]")
        return

    console.print(f"[yellow]Найдено незавершенных multipart-загрузок: {len(uploads)}.[/yellow]")
    table = Table(title="Отмена Ongoing Multipart Uploads", show_header=True, header_style="bold red")
    table.add_column("Ключ объекта в R2", style="cyan")
    table.add_column("Upload ID", style="dim")
    table.add_column("Дата начала", style="dim")

    for u in uploads:
        table.add_row(
            u.get("Key", ""),
            (u.get("UploadId") or "")[:35] + "...",
            str(u.get("Initiated", "")),
        )
    console.print(table)

    count = uploader.abort_multipart_uploads(prefix=prefix)
    console.print(f"[bold green]✓ Успешно отменено {count} незавершенных multipart-загрузок. Место в R2 освобождено.[/bold green]")


@click.command(
    name="r2up",
    help="CLI-утилита для загрузки файлов и управления хранилищем Cloudflare R2.",
)
@click.argument("paths", nargs=-1, required=False)
@click.option(
    "-u",
    "--upload",
    is_flag=True,
    default=False,
    help="Загрузить файлы или папки в R2 (режим по умолчанию).",
)
@click.option(
    "-l",
    "--list",
    "--ls",
    "list_mode",
    is_flag=True,
    default=False,
    help="Показать список объектов и папок в R2 (--ls).",
)
@click.option(
    "-d",
    "--dirs-only",
    "--folders-only",
    "folders_only",
    is_flag=True,
    default=False,
    help="В режиме --ls показывать только папки (скрыть файлы).",
)
@click.option(
    "--abort-multipart",
    "--abort",
    is_flag=True,
    default=False,
    help="Очистить и отменить все незавершенные (Ongoing) multipart-загрузки в R2.",
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    default=False,
    help="Рекурсивная загрузка или вывод директорий.",
)
@click.option(
    "-p",
    "--prefix",
    default="",
    help="Префикс (папка) в бакете Cloudflare R2.",
)
@click.option(
    "-k",
    "--key",
    default=None,
    help="Пользовательский ключ объекта в R2 (только для одного файла).",
)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Переопределить имя бакета (по умолчанию из .env).",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Путь к файлу конфигурации .env.",
)
@click.option(
    "-e",
    "--exclude",
    multiple=True,
    help="Шаблон для исключения файлов (например, '*.tmp', '__pycache__/*'). Можно указывать несколько раз.",
)
@click.option(
    "--mkdir",
    is_flag=True,
    default=False,
    help="Создать указанные папки в бакете R2 вместо загрузки файлов.",
)
@click.option(
    "--content-only",
    is_flag=True,
    default=False,
    help="Загружать только содержимое папки напрямую в префикс (без создания подпапки с именем каталога).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Имитация загрузки: показать список файлов без отправки в R2.",
)
@click.option(
    "--no-clobber",
    is_flag=True,
    default=False,
    help="Не перезаписывать файлы, если они уже существуют в бакете.",
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
    """Загрузить указанные файлы или каталоги в Cloudflare R2."""
    # 1. Загрузка конфигурации
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Ошибка конфигурации:[/bold red] {e}")
        sys.exit(1)

    # Режим отмены незавершенных multipart-загрузок
    if abort_multipart:
        handle_abort_multipart(prefix=prefix, config=config)
        return

    # Режим просмотра списка объектов/папок
    if list_mode:
        prefix_arg = paths[0] if paths else prefix
        handle_ls(
            prefix=prefix_arg,
            folders_only=folders_only,
            recursive=recursive,
            config=config,
        )
        return

    # Если включен режим создания папок
    if mkdir:
        if not paths:
            error_console.print("[bold red]Ошибка:[/bold red] Укажите имена папок для создания: r2up --mkdir <папка1> ...")
            sys.exit(1)
        handle_mkdir(folders=paths, prefix=prefix, config=config, dry_run=dry_run)
        return

    if not paths:
        error_console.print(
            "[bold yellow]Не указаны файлы для загрузки или действие.[/bold yellow]\n\n"
            "Примеры использования:\n"
            "  • [cyan]r2up photo.jpg[/cyan]                — быстрая загрузка файла\n"
            "  • [cyan]r2up --upload file.txt[/cyan]        — явный режим загрузки\n"
            "  • [cyan]r2up -r ./my_folder/[/cyan]         — загрузить всю папку рекурсивно\n"
            "  • [cyan]r2up --ls[/cyan] (или [cyan]r2up ls[/cyan])       — список файлов и папок в R2\n"
            "  • [cyan]r2up --mkdir photos[/cyan]            — создать папку в бакете\n"
            "  • [cyan]r2up --abort[/cyan]                   — очистить зависшие multipart-загрузки\n"
            "  • [cyan]r2up --help[/cyan]                    — подробная справка"
        )
        sys.exit(1)

    # Режим загрузки файлов: проверяем существование путей
    target_paths = []
    for p in paths:
        path_obj = Path(p)
        if not path_obj.exists():
            error_console.print(f"[bold red]Ошибка:[/bold red] Файл или каталог не найден: {p}")
            sys.exit(1)
        target_paths.append(path_obj)

    # 2. Подготовка элементов загрузки
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
        error_console.print(f"[bold red]Ошибка формирования списка файлов:[/bold red] {e}")
        sys.exit(1)

    if not items:
        console.print("[yellow]Не найдено файлов для загрузки.[/yellow]")
        sys.exit(0)

    total_bytes = sum(item.size for item in items)

    # 3. Информационная панель
    header_text = (
        f"[bold]Бакет:[/bold] [cyan]{config.bucket_name}[/cyan]\n"
        f"[bold]Эндпоинт:[/bold] [dim]{config.endpoint_url}[/dim]\n"
        f"[bold]Файлов к отправке:[/bold] {len(items)} ({format_bytes(total_bytes)})"
    )
    if dry_run:
        header_text += "\n[bold yellow]РЕЖИМ ПРЕДПРОСМОТРА (DRY-RUN) — файлы не загружаются[/bold yellow]"

    console.print(Panel(header_text, title="[bold cyan]Cloudflare R2 Uploader[/bold cyan]", border_style="cyan"))

    # 4. Режим Dry-Run
    if dry_run:
        table = Table(title="Файлы для загрузки", show_header=True, header_style="bold magenta")
        table.add_column("Локальный файл", style="dim")
        table.add_column("Целевой ключ в R2", style="cyan")
        table.add_column("Размер", justify="right")
        table.add_column("MIME-тип", style="dim")

        for item in items:
            table.add_row(
                str(item.local_path),
                item.remote_key,
                format_bytes(item.size),
                item.content_type,
            )
        console.print(table)
        console.print("\n[yellow]Имитация завершена. Файлы не были загружены.[/yellow]")
        sys.exit(0)

    # 5. Выполнение загрузки
    try:
        uploader = R2Uploader(config)
    except Exception as e:
        error_console.print(f"[bold red]Ошибка подключения к R2:[/bold red] {e}")
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
                f"[green]Общий прогресс ({len(items)} файлов)",
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

                # Удаляем индивидуальный таск файла после окончания его загрузки
                progress.remove_task(file_task)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Загрузка прервана пользователем (Ctrl+C).[/bold yellow]")
        console.print("[dim]Очистка незавершенных multipart-загрузок в R2...[/dim]")
        uploader.abort_multipart_uploads()
        console.print("[bold green]✓ Все незавершенные части отменены. Место в R2 очищено.[/bold green]")
        sys.exit(130)

    # 6. Итоговый отчет
    console.print()
    report_table = Table(title="Отчет о загрузке в R2", show_header=True, header_style="bold")
    report_table.add_column("Ключ в R2", style="cyan")
    report_table.add_column("Размер", justify="right")
    report_table.add_column("Время", justify="right")
    report_table.add_column("Статус", justify="center")
    report_table.add_column("Детали / Ошибки", style="red")

    success_count = 0
    fail_count = 0
    skipped_count = 0
    uploaded_bytes = 0

    for res in results:
        if res.status == UploadStatus.SUCCESS:
            status_text = "[bold green]✓ Загружен[/bold green]"
            success_count += 1
            uploaded_bytes += res.item.size
        elif res.status == UploadStatus.SKIPPED:
            status_text = "[bold yellow]⚠ Пропущен[/bold yellow]"
            skipped_count += 1
        else:
            status_text = "[bold red]✗ Ошибка[/bold red]"
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
        f"[bold]Всего:[/bold] {len(results)} | "
        f"[green]Успешно:[/green] {success_count} | "
        f"[yellow]Пропущено:[/yellow] {skipped_count} | "
        f"[red]Ошибок:[/red] {fail_count} | "
        f"[cyan]Объем:[/cyan] {format_bytes(uploaded_bytes)}"
    )
    console.print(Panel(summary_text, style="bold", title="Итог"))

    if fail_count > 0:
        sys.exit(1)


@click.command(
    name="r2-mkdir",
    help="CLI-утилита для создания папок в хранилище Cloudflare R2.",
)
@click.argument("folders", nargs=-1, required=True)
@click.option(
    "-p",
    "--prefix",
    default="",
    help="Префикс (родительская папка) в бакете Cloudflare R2.",
)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Переопределить имя бакета (по умолчанию из .env).",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Путь к файлу конфигурации .env.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Имитация создания без обращения к R2.",
)
def mkdir_cli(
    folders: tuple[str, ...],
    prefix: str,
    bucket: Optional[str],
    env_file: Optional[str],
    dry_run: bool,
):
    """Создать одну или несколько папок в бакете Cloudflare R2."""
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Ошибка конфигурации:[/bold red] {e}")
        sys.exit(1)

    handle_mkdir(folders=folders, prefix=prefix, config=config, dry_run=dry_run)


@click.command(
    name="r2-ls",
    help="CLI-утилита для просмотра папок и файлов в Cloudflare R2.",
)
@click.argument("prefix", default="", required=False)
@click.option(
    "-d",
    "--folders-only",
    is_flag=True,
    default=False,
    help="Показать только папки.",
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    default=False,
    help="Рекурсивный вывод всех вложенных папок и файлов.",
)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Переопределить имя бакета (по умолчанию из .env).",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Путь к файлу конфигурации .env.",
)
def ls_cli(
    prefix: str,
    folders_only: bool,
    recursive: bool,
    bucket: Optional[str],
    env_file: Optional[str],
):
    """Показать список папок и файлов в Cloudflare R2."""
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Ошибка конфигурации:[/bold red] {e}")
        sys.exit(1)

    handle_ls(
        prefix=prefix,
        folders_only=folders_only,
        recursive=recursive,
        config=config,
    )


@click.command(
    name="r2-abort",
    help="CLI-утилита для отмены незавершенных (Ongoing) multipart-загрузок в Cloudflare R2.",
)
@click.argument("prefix", default="", required=False)
@click.option(
    "-b",
    "--bucket",
    default=None,
    help="Переопределить имя бакета (по умолчанию из .env).",
)
@click.option(
    "--env-file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Путь к файлу конфигурации .env.",
)
def abort_cli(
    prefix: str,
    bucket: Optional[str],
    env_file: Optional[str],
):
    """Отменить все незавершенные (Ongoing) multipart-загрузки."""
    try:
        config = R2Config.load(env_path=env_file)
        if bucket:
            config.bucket_name = bucket
    except Exception as e:
        error_console.print(f"[bold red]Ошибка конфигурации:[/bold red] {e}")
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



