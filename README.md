# MyShell

A custom, colorful and interactive shell written in Python: it monitors
processes in real time, helps you navigate the file system, and includes an
encrypted password manager.

## Features

- 🎨 **Colorful output** (tables, trees, panels) powered by [rich](https://github.com/Textualize/rich)
- 📊 **Real-time process monitor** with CPU/RAM/disk bars (`top`)
- 🗂️ **File navigation & management**: `ls`, `cd`, `tree`, `mkdir`, `rm`, `copy`, `move`, `cat`, `find`, `open`
- 🔐 **Encrypted password manager** (`pass`) — credentials encrypted with a master password
- ⌨️ **Command history** and **autocompletion** (Tab) via [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit)
- 🔗 **Pipes and redirects** (`|`, `>`, `>>`) forwarded to the system shell
- 🚀 Runs any external command (e.g. `git`, `python`, `ping`)

## Requirements

- Python 3.10+
- Dependencies listed in [requirements.txt](requirements.txt)

## Installation

```bash
git clone https://github.com/<user>/MyShell.git
cd MyShell
pip install -r requirements.txt
python myshell.py
```

## Commands

| Command | Description |
|---|---|
| `cd [path]` | change directory (no argument goes to home) |
| `ls [path]` | colored file/folder listing |
| `pwd` | print the current directory |
| `tree [path] [n]` | directory tree (depth `n`, default 2) |
| `mkdir <dir>` | create a folder (nested allowed) |
| `rm [-r] <path>` | delete files (`-r` for folders) |
| `copy` / `cp <src> <dst>` | copy a file or folder |
| `move` / `mv <src> <dst>` | move or rename |
| `cat` / `type <file>` | show file contents (syntax-highlighted) |
| `find <name\|*.ext>` | search files recursively |
| `open` / `start <path>` | open with the default program |
| `ps [n]` | process table (top N by CPU) |
| `top [n]` | real-time process dashboard (`Ctrl+C` to exit) |
| `sysinfo` | CPU / RAM / disk status |
| `pass <sub>` | encrypted password manager (see below) |
| `clear` / `cls` | clear the screen |
| `help` | show help |
| `exit` / `quit` | quit the shell |

Pipes and redirects are supported, e.g. `dir | findstr .py` or `echo hello > f.txt`.

## Password manager

The `pass` command stores credentials in an **encrypted** vault. The data is
encrypted with [Fernet](https://cryptography.io/en/latest/fernet/)
(AES-128-CBC + HMAC) using a key derived from your master password via
PBKDF2-HMAC-SHA256 (600,000 iterations).

| Subcommand | Description |
|---|---|
| `pass init` | create the vault and set the master password |
| `pass add <name>` | add a credential (asks for username, password, note) |
| `pass get <name>` | show a stored credential |
| `pass list` | list stored credentials |
| `pass rm <name>` | remove a credential |
| `pass gen [n]` | generate a random password (length `n`, default 20) |
| `pass lock` | lock the vault (master password required again) |

**Security notes**

- The master password is **never stored** anywhere. If you forget it, the data
  cannot be recovered.
- The vault is **per user**: it lives in your home directory
  (`~/.myshell_vault.dat`). Nothing is hardcoded in the source, so every user
  has their own independent, separately encrypted vault.
- A wrong master password is rejected because the encryption is authenticated.

## Building a standalone executable (Windows)

```bash
pip install pyinstaller
python -m PyInstaller --onefile --console --name MyShell --clean myshell.py
```

The standalone executable is generated at `dist/MyShell.exe`.

## License

MIT
