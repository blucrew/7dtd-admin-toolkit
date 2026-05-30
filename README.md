# 7 Days to Die — Admin Toolkit

A PySide6 telnet GUI manager for 7 Days to Die dedicated servers, with a built-in horde test tool.

## Features

- **Telnet GUI Manager** — connect to your server, browse and run all available commands, colour-coded server output terminal
- **Profile save/load** — store multiple server connection profiles locally
- **Quick bar** — one-click buttons for common commands (saveworld, shutdown, listplayers, etc.)
- **🧟 Horde Test** — spawn configurable zombie waves from all 8 directions around your base, with escalating difficulty levels

## Requirements

- Python 3.10+
- pip install -r requirements.txt

## Setup

```bash
# Clone the repo
git clone https://github.com/blucrew/7dtd-admin-toolkit.git
cd 7dtd-admin-toolkit

# Install dependencies
pip install -r requirements.txt

# Copy the env template and fill in your server details
copy .env.example .env
# Edit .env with your host, port, and telnet password
```

## Usage

### GUI Manager (main program)
```bash
python 7dtd_manager.py
```

Connection details auto-fill from `.env` on startup, or enter them manually and save as a profile.

### Horde Test (CLI standalone)
```bash
python horde_test.py 1   # Level 1 — regular zombies
python horde_test.py 2   # Level 2 — + dogs & vultures
python horde_test.py 3   # Level 3 — + ferals, screamers & demolishers
```

## Horde Test Levels

| Level | Waves | Breaks | Wave gap |
|-------|-------|--------|----------|
| 1 | 8 waves of regular zombies from all directions | None | 30s |
| 2 | Feral soldiers + fat cops + lumberjacks | Dogs + vultures every 2 waves | 25s |
| 3 | Feral zombies only | Dogs + vultures then screamers + demolishers every 2 waves | 20s |

Set your base coordinates and spawn radius in the Horde tab of the GUI, or edit `bx, by, bz` in `horde_test.py` for CLI use.

## .env format

```
TDTD_HOST=your.server.ip
TDTD_PORT=8081
TDTD_PASS=yourpassword
```

## License

MIT
