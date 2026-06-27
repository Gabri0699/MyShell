# MyShell

Una shell personalizzata, colorata e interattiva scritta in Python: monitora i
processi in tempo reale e offre comandi comodi per navigare il file system.

## Funzionalità

- 🎨 **Output colorato** (tabelle, alberi e pannelli) tramite [rich](https://github.com/Textualize/rich)
- 📊 **Monitoraggio processi** in tempo reale con barre CPU/RAM/disco (`top`)
- 🗂️ **Navigazione e gestione file**: `ls`, `cd`, `tree`, `mkdir`, `rm`, `copy`, `move`, `cat`, `find`, `open`
- ⌨️ **Cronologia comandi** e **autocompletamento** (Tab) tramite [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit)
- 🔗 **Pipe e redirect** (`|`, `>`, `>>`) inoltrati alla shell di sistema
- 🚀 Esegue qualsiasi comando esterno (es. `git`, `python`, `ping`)

## Requisiti

- Python 3.10+
- Le dipendenze in [requirements.txt](requirements.txt)

## Installazione

```bash
git clone https://github.com/<utente>/MyShell.git
cd MyShell
pip install -r requirements.txt
python myshell.py
```

## Comandi

| Comando | Descrizione |
|---|---|
| `cd [path]` | cambia cartella (senza argomenti va alla home) |
| `ls [path]` | elenco file/cartelle colorato |
| `pwd` | mostra la cartella corrente |
| `tree [path] [n]` | albero delle cartelle (profondità `n`, default 2) |
| `mkdir <dir>` | crea una cartella (anche annidata) |
| `rm [-r] <path>` | elimina file (`-r` per le cartelle) |
| `copy` / `cp <src> <dst>` | copia file o cartelle |
| `move` / `mv <src> <dst>` | sposta o rinomina |
| `cat` / `type <file>` | mostra il contenuto di un file (colorato) |
| `find <nome\|*.ext>` | cerca file ricorsivamente |
| `open` / `start <path>` | apre col programma predefinito |
| `ps [n]` | tabella dei processi (top N per CPU) |
| `top [n]` | dashboard processi in tempo reale (`Ctrl+C` per uscire) |
| `sysinfo` | stato di CPU / RAM / disco |
| `clear` / `cls` | pulisce lo schermo |
| `help` | mostra l'aiuto |
| `exit` / `quit` | esce dalla shell |

Pipe e redirect sono supportati, es. `dir | findstr .py` oppure `echo ciao > f.txt`.

## Creare l'eseguibile (Windows)

```bash
pip install pyinstaller
python -m PyInstaller --onefile --console --name MyShell --clean myshell.py
```

L'eseguibile autonomo viene generato in `dist/MyShell.exe`.

## Licenza

MIT
