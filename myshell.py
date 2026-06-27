#!/usr/bin/env python3
"""
MyShell - una shell personalizzata, colorata, con monitoraggio processi
e navigazione del file system.

Comandi built-in:
    cd [path]            cambia cartella (cd senza argomenti = home)
    ls [path]            elenco file/cartelle colorato
    pwd                  mostra la cartella corrente
    tree [path] [n]      albero delle cartelle (n = profondita', default 2)
    mkdir <dir>          crea una cartella (anche annidata)
    rm [-r] <path>       elimina file (-r per le cartelle)
    copy/cp <src> <dst>  copia file o cartella
    move/mv <src> <dst>  sposta o rinomina
    cat/type <file>      mostra il contenuto di un file (colorato)
    find <nome|*.ext>    cerca file ricorsivamente nella cartella corrente
    open/start <path>    apre file/cartella col programma predefinito
    ps [n]               tabella dei processi (n = quanti, ordinati per CPU)
    top [n]              dashboard processi in tempo reale (Ctrl+C per uscire)
    sysinfo              stato di CPU / RAM / disco
    clear / cls          pulisce lo schermo
    help                 mostra questo aiuto
    exit / quit          esce dalla shell

Qualsiasi altro comando viene eseguito dal sistema operativo.
Pipe e redirect sono supportati: es.  ls | findstr .py   oppure   echo ciao > f.txt
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, cast

import psutil
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
    "cat", "type", "find", "open", "start",
    "clear", "cls", "help", "exit", "quit",
]


# --------------------------------------------------------------------------- #
# Utilita'
# --------------------------------------------------------------------------- #
def human_bytes(n: float) -> str:
    """Converte un numero di byte in formato leggibile (KB, MB, GB...)."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0:
            return f"{n:3.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} EB"


def color_for_percent(pct: float) -> str:
    """Verde/giallo/rosso in base alla percentuale di carico."""
    if pct < 50:
        return "green"
    if pct < 80:
        return "yellow"
    return "red"


# --------------------------------------------------------------------------- #
# Comandi: navigazione file system
# --------------------------------------------------------------------------- #
def cmd_cd(args: list[str]) -> None:
    target = args[0] if args else str(Path.home())
    try:
        os.chdir(os.path.expanduser(target))
    except FileNotFoundError:
        console.print(f"[red]cd: cartella non trovata:[/red] {target}")
    except NotADirectoryError:
        console.print(f"[red]cd: non e' una cartella:[/red] {target}")
    except PermissionError:
        console.print(f"[red]cd: permesso negato:[/red] {target}")


def cmd_pwd(_args: list[str]) -> None:
    console.print(f"[cyan]{Path.cwd()}[/cyan]")


def cmd_ls(args: list[str]) -> None:
    path = Path(args[0]) if args else Path.cwd()
    if not path.exists():
        console.print(f"[red]ls: percorso inesistente:[/red] {path}")
        return

    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Nome")
    table.add_column("Dimensione", justify="right")
    table.add_column("Modificato", justify="right")

    try:
        entries = sorted(
            path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),  # cartelle prima
        )
    except PermissionError:
        console.print(f"[red]ls: permesso negato:[/red] {path}")
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
# Comandi: monitoraggio processi e sistema
# --------------------------------------------------------------------------- #
def _process_table(limit: int) -> Table:
    table = Table(
        title=f"Processi (top {limit} per CPU) - {datetime.now():%H:%M:%S}",
        header_style="bold magenta",
    )
    table.add_column("PID", justify="right", style="dim")
    table.add_column("Nome")
    table.add_column("CPU %", justify="right")
    table.add_column("RAM %", justify="right")
    table.add_column("Memoria", justify="right")

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
    # Prima passata per "innescare" la misura cpu_percent di psutil.
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.3)
    console.print(_process_table(limit))


def _bar(pct: float, width: int = 30) -> str:
    """Barra di avanzamento testuale colorata, es. [#####-----] 50%."""
    filled = int(round(pct / 100 * width))
    color = color_for_percent(pct)
    bar = f"[{color}]{'#' * filled}[/][dim]{'-' * (width - filled)}[/]"
    return f"{bar} [{color}]{pct:5.1f}%[/]"


def _dashboard(limit: int) -> Group:
    """Pannello riepilogo (CPU/RAM/disco con barre) + tabella processi."""
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.cwd().anchor or "/"))

    header = Panel(
        "\n".join([
            f"CPU   {_bar(cpu)}  su {psutil.cpu_count()} core",
            f"RAM   {_bar(vm.percent)}  ({human_bytes(vm.used)} / {human_bytes(vm.total)})",
            f"Disco {_bar(disk.percent)}  ({human_bytes(disk.used)} / {human_bytes(disk.total)})",
        ]),
        title=f"[bold]Sistema[/bold] - {datetime.now():%H:%M:%S}  [dim](Ctrl+C per uscire)[/dim]",
        border_style="cyan",
    )
    return Group(header, _process_table(limit))


def cmd_top(args: list[str]) -> None:
    limit = int(args[0]) if args and args[0].isdigit() else 15
    # Prima passata per "innescare" la misura cpu_percent di psutil.
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
            screen=console.is_terminal,  # schermo intero solo in un vero terminale
        ) as live:
            while True:
                time.sleep(1.0)
                live.update(_dashboard(limit))
    except KeyboardInterrupt:
        console.print("[dim]Monitor chiuso.[/dim]")


def cmd_sysinfo(_args: list[str]) -> None:
    cpu = psutil.cpu_percent(interval=0.3)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.cwd().anchor or "/"))
    boot = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot

    lines = [
        f"CPU:    [{color_for_percent(cpu)}]{cpu:.1f}%[/] su {psutil.cpu_count()} core",
        f"RAM:    [{color_for_percent(vm.percent)}]{vm.percent:.1f}%[/] "
        f"({human_bytes(vm.used)} / {human_bytes(vm.total)})",
        f"Disco:  [{color_for_percent(disk.percent)}]{disk.percent:.1f}%[/] "
        f"({human_bytes(disk.used)} / {human_bytes(disk.total)})",
        f"Uptime: {str(uptime).split('.')[0]}",
    ]
    console.print(Panel("\n".join(lines), title="[bold]Stato sistema[/bold]", border_style="cyan"))


# --------------------------------------------------------------------------- #
# Comandi: utilita' shell
# --------------------------------------------------------------------------- #
def cmd_clear(_args: list[str]) -> None:
    console.clear()


def cmd_help(_args: list[str]) -> None:
    console.print(Panel(__doc__ or "", title="[bold]MyShell - aiuto[/bold]", border_style="green"))


def cmd_mkdir(args: list[str]) -> None:
    if not args:
        console.print("[red]mkdir: specifica almeno una cartella[/red]")
        return
    for a in args:
        try:
            Path(a).mkdir(parents=True, exist_ok=True)
            console.print(f"[green]creata[/green] {a}")
        except OSError as exc:
            console.print(f"[red]mkdir: {exc}[/red]")


def cmd_rm(args: list[str]) -> None:
    recursive = any(a in ("-r", "-rf", "-R") for a in args)
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        console.print("[red]rm: specifica un file o cartella (usa -r per le cartelle)[/red]")
        return
    for t in targets:
        p = Path(t)
        if not p.exists():
            console.print(f"[red]rm: non esiste:[/red] {t}")
            continue
        try:
            if p.is_dir():
                if not recursive:
                    console.print(f"[yellow]rm: '{t}' e' una cartella, usa 'rm -r {t}'[/yellow]")
                    continue
                shutil.rmtree(p)
            else:
                p.unlink()
            console.print(f"[green]rimosso[/green] {t}")
        except OSError as exc:
            console.print(f"[red]rm: {exc}[/red]")


def cmd_copy(args: list[str]) -> None:
    if len(args) < 2:
        console.print("[red]copy: uso: copy <sorgente> <destinazione>[/red]")
        return
    src, dst = Path(args[0]), Path(args[1])
    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        console.print(f"[green]copiato[/green] {args[0]} -> {args[1]}")
    except OSError as exc:
        console.print(f"[red]copy: {exc}[/red]")


def cmd_move(args: list[str]) -> None:
    if len(args) < 2:
        console.print("[red]move: uso: move <sorgente> <destinazione>[/red]")
        return
    try:
        shutil.move(args[0], args[1])
        console.print(f"[green]spostato[/green] {args[0]} -> {args[1]}")
    except OSError as exc:
        console.print(f"[red]move: {exc}[/red]")


def cmd_cat(args: list[str]) -> None:
    if not args:
        console.print("[red]cat: specifica un file[/red]")
        return
    p = Path(args[0])
    if not p.is_file():
        console.print(f"[red]cat: file non trovato:[/red] {args[0]}")
        return
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        console.print(f"[red]cat: {exc}[/red]")
        return
    # Colorazione della sintassi in base all'estensione del file.
    syntax = Syntax(text, Syntax.guess_lexer(str(p), text), line_numbers=True, theme="ansi_dark")
    console.print(syntax)


def cmd_find(args: list[str]) -> None:
    if not args:
        console.print("[red]find: specifica un nome o pattern (es. *.py)[/red]")
        return
    pattern = args[0]
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"  # ricerca "contiene" se non e' un glob
    base = Path.cwd()
    count = 0
    for match in base.rglob(pattern):
        rel = match.relative_to(base)
        style = "bold blue" if match.is_dir() else "white"
        console.print(f"[{style}]{rel}[/]")
        count += 1
    console.print(f"[dim]{count} risultati[/dim]")


def cmd_open(args: list[str]) -> None:
    target = args[0] if args else "."
    p = Path(target)
    if not p.exists():
        console.print(f"[red]open: percorso inesistente:[/red] {target}")
        return
    try:
        if hasattr(os, "startfile"):
            os.startfile(str(p.resolve()))  # type: ignore[attr-defined]  # Windows
        else:
            subprocess.run(["xdg-open", str(p.resolve())])  # Linux fallback
    except OSError as exc:
        console.print(f"[red]open: {exc}[/red]")


def has_shell_operators(line: str) -> bool:
    """True se la riga contiene pipe/redirect (| < > &) fuori dalle virgolette."""
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
    """Esegue un comando di sistema (con supporto a pipe e redirect via shell)."""
    try:
        subprocess.run(command, shell=True)
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------- #
# Loop principale
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
}


def make_prompt() -> str:
    """Prompt colorato (testo semplice; lo stile lo aggiunge prompt_toolkit/rich)."""
    return f"{Path.cwd()} > "


def make_session() -> Any | None:
    """Crea una PromptSession (cronologia + autocompletamento).

    Ritorna None se prompt_toolkit non e' installato o se la console non e'
    compatibile (es. esecuzione tramite pipe): in tal caso si usa input().
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
    # fallback senza prompt_toolkit
    console.print(f"[bold green]{Path.cwd()}[/bold green] [bold cyan]>[/bold cyan] ", end="")
    return input()


def main() -> None:
    console.print(
        Panel(
            "[bold cyan]MyShell[/bold cyan] - scrivi [bold]help[/bold] per i comandi, "
            "[bold]exit[/bold] per uscire.",
            border_style="cyan",
        )
    )

    session = make_session()

    while True:
        try:
            line = get_input(session).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Uscita.[/dim]")
            break

        if not line:
            continue

        # Con pipe/redirect (| > < &) passa l'intera riga alla shell di sistema.
        if has_shell_operators(line):
            run_external(line)
            continue

        try:
            parts = shlex.split(line, posix=False)
        except ValueError:
            parts = line.split()

        cmd, args = parts[0].lower(), parts[1:]

        if cmd in ("exit", "quit"):
            console.print("[dim]Ciao![/dim]")
            break

        handler = DISPATCH.get(cmd)
        if handler:
            try:
                handler(args)
            except Exception as exc:  # non far morire la shell per un errore di comando
                console.print(f"[red]errore:[/red] {exc}")
        else:
            run_external(line)


if __name__ == "__main__":
    main()
