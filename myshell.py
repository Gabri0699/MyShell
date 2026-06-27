#!/usr/bin/env python3
"""
MyShell - a custom, colorful shell with process monitoring and file
system navigation.

Built-in commands:
    cd [path]            change directory (cd with no argument = home)
    ls [path]            colored file/folder listing
    pwd                  print the current directory
    tree [path] [n]      directory tree (n = depth, default 2)
    mkdir <dir>          create a folder (nested allowed)
    rm [-r] <path>       delete files (-r for folders)
    copy/cp <src> <dst>  copy a file or folder
    move/mv <src> <dst>  move or rename
    cat/type <file>      show file contents (syntax-highlighted)
    find <name|*.ext>    search files recursively in the current folder
    open/start <path>    open a file/folder with the default program
    ps [n]               process table (n = how many, sorted by CPU)
    top [n]              real-time process dashboard (Ctrl+C to exit)
    sysinfo              CPU / RAM / disk status
    pass <sub>           encrypted password manager (pass init/add/get/list/rm/gen/lock)
    clear / cls          clear the screen
    help                 show this help
    exit / quit          quit the shell

Any other command is executed by the operating system.
Pipes and redirects are supported, e.g.  ls | findstr .py   or   echo hi > f.txt
"""

from __future__ import annotations

import getpass
import os
import secrets
import shlex
import shutil
import string
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, cast

import psutil

import vault
from rich.console import Console, Group
from rich.table import Table
from rich.tree import Tree
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

console = Console()

BUILTIN_COMMANDS = [
    "cd", "ls", "dir", "pwd", "tree", "ps", "top", "sysinfo",
    "mkdir", "rm", "del", "copy", "cp", "move", "mv",
    "cat", "type", "find", "open", "start", "pass",
    "clear", "cls", "help", "exit", "quit",
]


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #
def human_bytes(n: float) -> str:
    """Convert a number of bytes into a readable format (KB, MB, GB...)."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0:
            return f"{n:3.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} EB"


def color_for_percent(pct: float) -> str:
    """Green/yellow/red depending on the load percentage."""
    if pct < 50:
        return "green"
    if pct < 80:
        return "yellow"
    return "red"


# --------------------------------------------------------------------------- #
# Commands: file system navigation
# --------------------------------------------------------------------------- #
def cmd_cd(args: list[str]) -> None:
    target = args[0] if args else str(Path.home())
    try:
        os.chdir(os.path.expanduser(target))
    except FileNotFoundError:
        console.print(f"[red]cd: directory not found:[/red] {target}")
    except NotADirectoryError:
        console.print(f"[red]cd: not a directory:[/red] {target}")
    except PermissionError:
        console.print(f"[red]cd: permission denied:[/red] {target}")


def cmd_pwd(_args: list[str]) -> None:
    console.print(f"[cyan]{Path.cwd()}[/cyan]")


def cmd_ls(args: list[str]) -> None:
    path = Path(args[0]) if args else Path.cwd()
    if not path.exists():
        console.print(f"[red]ls: path does not exist:[/red] {path}")
        return

    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Name")
    table.add_column("Size", justify="right")
    table.add_column("Modified", justify="right")

    try:
        entries = sorted(
            path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),  # folders first
        )
    except PermissionError:
        console.print(f"[red]ls: permission denied:[/red] {path}")
        return

    for entry in entries:
        try:
            stat = entry.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            if entry.is_dir():
                name = Text(f"[DIR] {entry.name}", style="bold blue")
                size = "-"
            else:
                name = Text(entry.name, style="white")
                size = human_bytes(stat.st_size)
            table.add_row(name, size, mtime)
        except (PermissionError, OSError):
            table.add_row(Text(entry.name, style="dim red"), "?", "?")

    console.print(table)


def _build_tree(node: Tree, path: Path, depth: int, max_depth: int) -> None:
    if depth >= max_depth:
        return
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except (PermissionError, OSError):
        return
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            branch = node.add(f"[bold blue][DIR] {entry.name}[/bold blue]")
            _build_tree(branch, entry, depth + 1, max_depth)
        else:
            node.add(f"[white]{entry.name}[/white]")


def cmd_tree(args: list[str]) -> None:
    path = Path(args[0]) if args and not args[0].isdigit() else Path.cwd()
    depth_arg = args[-1] if args and args[-1].isdigit() else "2"
    max_depth = int(depth_arg)
    root = Tree(f"[bold cyan]{path}[/bold cyan]")
    _build_tree(root, path, 0, max_depth)
    console.print(root)


# --------------------------------------------------------------------------- #
# Commands: process and system monitoring
# --------------------------------------------------------------------------- #
def _process_table(limit: int) -> Table:
    table = Table(
        title=f"Processes (top {limit} by CPU) - {datetime.now():%H:%M:%S}",
        header_style="bold magenta",
    )
    table.add_column("PID", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("CPU %", justify="right")
    table.add_column("RAM %", justify="right")
    table.add_column("Memory", justify="right")

    procs: list[dict[str, Any]] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: float(x.get("cpu_percent") or 0.0), reverse=True)

    for info in procs[:limit]:
        cpu = float(info.get("cpu_percent") or 0.0)
        mem = float(info.get("memory_percent") or 0.0)
        meminfo = info.get("memory_info")
        rss = int(meminfo.rss) if meminfo else 0
        name = str(info.get("name") or "?")[:30]
        table.add_row(
            str(info.get("pid", "?")),
            name,
            f"[{color_for_percent(cpu)}]{cpu:.1f}[/]",
            f"[{color_for_percent(mem)}]{mem:.1f}[/]",
            human_bytes(rss),
        )
    return table


def cmd_ps(args: list[str]) -> None:
    limit = int(args[0]) if args and args[0].isdigit() else 15
    # First pass to "prime" psutil's cpu_percent measurement.
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.3)
    console.print(_process_table(limit))


def _bar(pct: float, width: int = 30) -> str:
    """Colored text progress bar, e.g. [#####-----] 50%."""
    filled = int(round(pct / 100 * width))
    color = color_for_percent(pct)
    bar = f"[{color}]{'#' * filled}[/][dim]{'-' * (width - filled)}[/]"
    return f"{bar} [{color}]{pct:5.1f}%[/]"


def _dashboard(limit: int) -> Group:
    """Summary panel (CPU/RAM/disk bars) + process table."""
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.cwd().anchor or "/"))

    header = Panel(
        "\n".join([
            f"CPU  {_bar(cpu)}  on {psutil.cpu_count()} cores",
            f"RAM  {_bar(vm.percent)}  ({human_bytes(vm.used)} / {human_bytes(vm.total)})",
            f"Disk {_bar(disk.percent)}  ({human_bytes(disk.used)} / {human_bytes(disk.total)})",
        ]),
        title=f"[bold]System[/bold] - {datetime.now():%H:%M:%S}  [dim](Ctrl+C to exit)[/dim]",
        border_style="cyan",
    )
    return Group(header, _process_table(limit))


def cmd_top(args: list[str]) -> None:
    limit = int(args[0]) if args and args[0].isdigit() else 15
    # First pass to "prime" psutil's cpu_percent measurement.
    psutil.cpu_percent(None)
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    try:
        with Live(
            _dashboard(limit),
            refresh_per_second=1,
            console=console,
            screen=console.is_terminal,  # full screen only in a real terminal
        ) as live:
            while True:
                time.sleep(1.0)
                live.update(_dashboard(limit))
    except KeyboardInterrupt:
        console.print("[dim]Monitor closed.[/dim]")


def cmd_sysinfo(_args: list[str]) -> None:
    cpu = psutil.cpu_percent(interval=0.3)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.cwd().anchor or "/"))
    boot = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot

    lines = [
        f"CPU:    [{color_for_percent(cpu)}]{cpu:.1f}%[/] on {psutil.cpu_count()} cores",
        f"RAM:    [{color_for_percent(vm.percent)}]{vm.percent:.1f}%[/] "
        f"({human_bytes(vm.used)} / {human_bytes(vm.total)})",
        f"Disk:   [{color_for_percent(disk.percent)}]{disk.percent:.1f}%[/] "
        f"({human_bytes(disk.used)} / {human_bytes(disk.total)})",
        f"Uptime: {str(uptime).split('.')[0]}",
    ]
    console.print(Panel("\n".join(lines), title="[bold]System status[/bold]", border_style="cyan"))


# --------------------------------------------------------------------------- #
# Commands: shell utilities
# --------------------------------------------------------------------------- #
def cmd_clear(_args: list[str]) -> None:
    console.clear()


def cmd_help(_args: list[str]) -> None:
    console.print(Panel(__doc__ or "", title="[bold]MyShell - help[/bold]", border_style="green"))


def cmd_mkdir(args: list[str]) -> None:
    if not args:
        console.print("[red]mkdir: specify at least one folder[/red]")
        return
    for a in args:
        try:
            Path(a).mkdir(parents=True, exist_ok=True)
            console.print(f"[green]created[/green] {a}")
        except OSError as exc:
            console.print(f"[red]mkdir: {exc}[/red]")


def cmd_rm(args: list[str]) -> None:
    recursive = any(a in ("-r", "-rf", "-R") for a in args)
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        console.print("[red]rm: specify a file or folder (use -r for folders)[/red]")
        return
    for t in targets:
        p = Path(t)
        if not p.exists():
            console.print(f"[red]rm: does not exist:[/red] {t}")
            continue
        try:
            if p.is_dir():
                if not recursive:
                    console.print(f"[yellow]rm: '{t}' is a folder, use 'rm -r {t}'[/yellow]")
                    continue
                shutil.rmtree(p)
            else:
                p.unlink()
            console.print(f"[green]removed[/green] {t}")
        except OSError as exc:
            console.print(f"[red]rm: {exc}[/red]")


def cmd_copy(args: list[str]) -> None:
    if len(args) < 2:
        console.print("[red]copy: usage: copy <source> <destination>[/red]")
        return
    src, dst = Path(args[0]), Path(args[1])
    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        console.print(f"[green]copied[/green] {args[0]} -> {args[1]}")
    except OSError as exc:
        console.print(f"[red]copy: {exc}[/red]")


def cmd_move(args: list[str]) -> None:
    if len(args) < 2:
        console.print("[red]move: usage: move <source> <destination>[/red]")
        return
    try:
        shutil.move(args[0], args[1])
        console.print(f"[green]moved[/green] {args[0]} -> {args[1]}")
    except OSError as exc:
        console.print(f"[red]move: {exc}[/red]")


def cmd_cat(args: list[str]) -> None:
    if not args:
        console.print("[red]cat: specify a file[/red]")
        return
    p = Path(args[0])
    if not p.is_file():
        console.print(f"[red]cat: file not found:[/red] {args[0]}")
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        console.print(f"[red]cat: {exc}[/red]")
        return
    # Syntax highlighting based on the file extension.
    syntax = Syntax(text, Syntax.guess_lexer(str(p), text), line_numbers=True, theme="ansi_dark")
    console.print(syntax)


def cmd_find(args: list[str]) -> None:
    if not args:
        console.print("[red]find: specify a name or pattern (e.g. *.py)[/red]")
        return
    pattern = args[0]
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"  # "contains" search when it is not a glob
    base = Path.cwd()
    count = 0
    for match in base.rglob(pattern):
        rel = match.relative_to(base)
        style = "bold blue" if match.is_dir() else "white"
        console.print(f"[{style}]{rel}[/]")
        count += 1
    console.print(f"[dim]{count} results[/dim]")


def cmd_open(args: list[str]) -> None:
    target = args[0] if args else "."
    p = Path(target)
    if not p.exists():
        console.print(f"[red]open: path does not exist:[/red] {target}")
        return
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(p.resolve()))  # type: ignore[attr-defined]  # Windows
        else:
            subprocess.run(["xdg-open", str(p.resolve())])  # Linux fallback
    except OSError as exc:
        console.print(f"[red]open: {exc}[/red]")


# --------------------------------------------------------------------------- #
# Commands: password manager (encrypted vault)
# --------------------------------------------------------------------------- #
# Key and data stay in memory for the session only (never on disk).
_vault_key: bytes | None = None
_vault_data: dict[str, dict[str, str]] | None = None


def _ensure_unlocked() -> bool:
    """Unlock the vault (prompting for the master password) if not already open."""
    global _vault_key, _vault_data
    if _vault_key is not None:
        return True
    if not vault.vault_exists():
        console.print("[yellow]No vault yet. Create one with:[/yellow] pass init")
        return False
    try:
        pw = getpass.getpass("Master password: ")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    try:
        _vault_key, _vault_data = vault.unlock(pw)
    except vault.InvalidToken:
        console.print("[red]Wrong master password.[/red]")
        return False
    return True


def _pass_init(_args: list[str]) -> None:
    global _vault_key, _vault_data
    if vault.vault_exists():
        console.print("[yellow]A vault already exists.[/yellow] Delete it manually to recreate it: "
                      f"{vault.VAULT_PATH}")
        return
    pw1 = getpass.getpass("New master password: ")
    if not pw1:
        console.print("[red]Empty password, cancelled.[/red]")
        return
    pw2 = getpass.getpass("Confirm master password: ")
    if pw1 != pw2:
        console.print("[red]Passwords do not match, cancelled.[/red]")
        return
    _vault_key = vault.create_vault(pw1)
    _vault_data = {}
    console.print(f"[green]Vault created:[/green] {vault.VAULT_PATH}")


def _pass_add(args: list[str]) -> None:
    if not args:
        console.print("[red]usage: pass add <name>[/red]")
        return
    if not _ensure_unlocked():
        return
    assert _vault_data is not None and _vault_key is not None
    name = args[0]
    if name in _vault_data:
        console.print(f"[yellow]'{name}' already exists. Use 'pass rm {name}' before redoing it.[/yellow]")
        return
    username = input("Username: ").strip()
    pwd = getpass.getpass("Password (empty = generate): ")
    if not pwd:
        pwd = _generate_password(20)
        console.print("[dim]Password generated automatically.[/dim]")
    note = input("Note (optional): ").strip()
    _vault_data[name] = {"username": username, "password": pwd, "note": note}
    vault.save(_vault_key, _vault_data)
    console.print(f"[green]Saved credential[/green] '{name}'")


def _pass_get(args: list[str]) -> None:
    if not args:
        console.print("[red]usage: pass get <name>[/red]")
        return
    if not _ensure_unlocked():
        return
    assert _vault_data is not None
    name = args[0]
    entry = _vault_data.get(name)
    if not entry:
        console.print(f"[red]No credential with name:[/red] {name}")
        return
    table = Table(show_header=False, box=None)
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row("Name", name)
    table.add_row("Username", entry.get("username", ""))
    table.add_row("Password", f"[bold yellow]{entry.get('password', '')}[/bold yellow]")
    if entry.get("note"):
        table.add_row("Note", entry["note"])
    console.print(table)


def _pass_list(_args: list[str]) -> None:
    if not _ensure_unlocked():
        return
    assert _vault_data is not None
    if not _vault_data:
        console.print("[dim]Vault is empty.[/dim]")
        return
    table = Table(header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Username")
    for name, entry in sorted(_vault_data.items()):
        table.add_row(name, entry.get("username", ""))
    console.print(table)


def _pass_rm(args: list[str]) -> None:
    if not args:
        console.print("[red]usage: pass rm <name>[/red]")
        return
    if not _ensure_unlocked():
        return
    assert _vault_data is not None and _vault_key is not None
    name = args[0]
    if name not in _vault_data:
        console.print(f"[red]No credential with name:[/red] {name}")
        return
    del _vault_data[name]
    vault.save(_vault_key, _vault_data)
    console.print(f"[green]Removed[/green] '{name}'")


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _pass_gen(args: list[str]) -> None:
    length = int(args[0]) if args and args[0].isdigit() else 20
    console.print(f"[bold yellow]{_generate_password(length)}[/bold yellow]")


def _pass_lock(_args: list[str]) -> None:
    global _vault_key, _vault_data
    _vault_key = None
    _vault_data = None
    console.print("[green]Vault locked.[/green]")


_PASS_SUB: dict[str, Callable[[list[str]], None]] = {
    "init": _pass_init,
    "add": _pass_add,
    "get": _pass_get,
    "list": _pass_list,
    "ls": _pass_list,
    "rm": _pass_rm,
    "del": _pass_rm,
    "gen": _pass_gen,
    "lock": _pass_lock,
}


def cmd_pass(args: list[str]) -> None:
    if not args:
        console.print(
            "Password manager. Subcommands:\n"
            "  [cyan]pass init[/cyan]          create the vault (master password)\n"
            "  [cyan]pass add <name>[/cyan]    add a credential\n"
            "  [cyan]pass get <name>[/cyan]    show a credential\n"
            "  [cyan]pass list[/cyan]          list credentials\n"
            "  [cyan]pass rm <name>[/cyan]     remove a credential\n"
            "  [cyan]pass gen [n][/cyan]       generate a random password\n"
            "  [cyan]pass lock[/cyan]          lock the vault (master password required again)"
        )
        return
    sub = _PASS_SUB.get(args[0].lower())
    if sub is None:
        console.print(f"[red]pass: unknown subcommand:[/red] {args[0]}")
        return
    sub(args[1:])


def has_shell_operators(line: str) -> bool:
    """True if the line contains pipes/redirects (| < > &) outside of quotes."""
    in_quote: str | None = None
    for ch in line:
        if ch in ("'", '"'):
            if in_quote == ch:
                in_quote = None
            elif in_quote is None:
                in_quote = ch
        elif in_quote is None and ch in "|<>&":
            return True
    return False


def run_external(command: str) -> None:
    """Run a system command (with pipe and redirect support via the shell)."""
    try:
        subprocess.run(command, shell=True)
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
DISPATCH: dict[str, Callable[[list[str]], None]] = {
    "cd": cmd_cd,
    "ls": cmd_ls,
    "dir": cmd_ls,
    "pwd": cmd_pwd,
    "tree": cmd_tree,
    "ps": cmd_ps,
    "top": cmd_top,
    "sysinfo": cmd_sysinfo,
    "clear": cmd_clear,
    "cls": cmd_clear,
    "help": cmd_help,
    "mkdir": cmd_mkdir,
    "rm": cmd_rm,
    "del": cmd_rm,
    "copy": cmd_copy,
    "cp": cmd_copy,
    "move": cmd_move,
    "mv": cmd_move,
    "cat": cmd_cat,
    "type": cmd_cat,
    "find": cmd_find,
    "open": cmd_open,
    "start": cmd_open,
    "pass": cmd_pass,
}


def make_prompt() -> str:
    """Plain-text prompt; styling is added by prompt_toolkit/rich."""
    return f"{Path.cwd()} > "


def make_session() -> Any | None:
    """Create a PromptSession (history + autocompletion).

    Returns None if prompt_toolkit is not installed or the console is not
    compatible (e.g. running through a pipe): in that case input() is used.
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import (
            PathCompleter,
            WordCompleter,
            merge_completers,
        )
        from prompt_toolkit.history import FileHistory
    except ImportError:
        return None

    try:
        completer = merge_completers([
            WordCompleter(BUILTIN_COMMANDS, ignore_case=True),
            PathCompleter(expanduser=True),
        ])
        history_file = Path.home() / ".myshell_history"
        return cast(Any, PromptSession(history=FileHistory(str(history_file)), completer=completer))
    except Exception:
        return None


def get_input(session: Any | None) -> str:
    if session is not None:
        return cast(str, session.prompt(make_prompt()))
    # fallback without prompt_toolkit
    console.print(f"[bold green]{Path.cwd()}[/bold green] [bold cyan]>[/bold cyan] ", end="")
    return input()


def main() -> None:
    console.print(
        Panel(
            "[bold cyan]MyShell[/bold cyan] - type [bold]help[/bold] for commands, "
            "[bold]exit[/bold] to quit.",
            border_style="cyan",
        )
    )

    session = make_session()

    while True:
        try:
            line = get_input(session).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Exiting.[/dim]")
            break

        if not line:
            continue

        # With pipes/redirects (| > < &) pass the whole line to the system shell.
        if has_shell_operators(line):
            run_external(line)
            continue

        try:
            parts = shlex.split(line, posix=False)
        except ValueError:
            parts = line.split()

        cmd, args = parts[0].lower(), parts[1:]

        if cmd in ("exit", "quit"):
            console.print("[dim]Bye![/dim]")
            break

        handler = DISPATCH.get(cmd)
        if handler:
            try:
                handler(args)
            except Exception as exc:  # do not let the shell die on a command error
                console.print(f"[red]error:[/red] {exc}")
        else:
            run_external(line)


if __name__ == "__main__":
    main()
