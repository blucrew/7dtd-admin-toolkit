# 7dtd admin toolkit

so this is the thing we use to run the server without having to type into a console like it's 1987 or whatever. PySide6 GUI that connects over telnet, auto-loads all the server commands, lets you run them without accidentally shutting the whole thing down because you typo'd.

also has a horde test tool built in. that part's kind of the whole point.

## what it does

- connects to your 7dtd server over telnet
- pulls all available commands automatically and puts them in tabs
- colour-coded terminal output so you can actually read what's happening
- save multiple server profiles, swap between them
- **horde test** — spawn zombie waves from all 8 directions at once, with dogs and birds and demolishers and all that, because sometimes you just want to see what happens you know

## setup

```bash
git clone https://github.com/blucrew/7dtd-admin-toolkit.git
cd 7dtd-admin-toolkit
pip install -r requirements.txt
copy .env.example .env
```

edit `.env` with your server ip, port, and telnet password. that's it.

## running it

```bash
python 7dtd_manager.py
```

connection fields auto-fill from `.env` on startup. save your servers as profiles so you can swap between them with one click.

## horde test

built into the GUI under the 🧟 horde tab. set your base coords, pick a level, launch it. uses the current connection so no separate setup needed.

or run it standalone from the command line if you want:

```bash
python horde_test.py 1   # regular zombies
python horde_test.py 2   # + dogs and vultures between waves
python horde_test.py 3   # + ferals, screamers, demolishers. good luck.
```

### levels

| | what's coming | break waves | gap |
|---|---|---|---|
| L1 | regular zombies from all 8 directions | none | 30s |
| L2 | soldiers, fat cops, lumberjacks | dogs + vultures every 2 waves | 25s |
| L3 | ferals only | dogs + vultures *then* screamers + demolishers | 20s |

demolishers have a bomb pack that explodes when they die. don't let them reach the walls. you'll find out why.

## .env

```
TDTD_HOST=your.server.ip
TDTD_PORT=8081
TDTD_PASS=yourpassword
```

never gets committed. neither do your profiles. sorted.

## license

MIT — do whatever with it
