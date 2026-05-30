"""
7 Days to Die – Telnet GUI Manager
====================================
Requirements: Python 3.6+  +  pip install PySide6 python-dotenv
Run:          python 7dtd_manager.py

Connection details entered at runtime or loaded from profiles.
Profiles saved to 7dtd_profiles.json next to this script.
.env file (optional) can pre-fill host/port/password.
"""

import socket
import threading
import queue
import json
import os
import re
import time
import sys
import itertools

from dotenv import load_dotenv
load_dotenv()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QTabWidget,
    QStatusBar, QComboBox, QDialog, QDialogButtonBox,
    QScrollArea, QGridLayout, QFrame, QSizePolicy, QMessageBox,
    QInputDialog, QSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, Slot, QTimer
from PySide6.QtGui import QFont, QTextCursor, QColor


# ─────────────────────────────────────────────────────────────
#  PROFILE STORAGE
# ─────────────────────────────────────────────────────────────
PROFILE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "7dtd_profiles.json")

def load_profiles():
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_profiles(profiles):
    with open(PROFILE_FILE, "w") as f:
        json.dump(profiles, f, indent=2)


# ─────────────────────────────────────────────────────────────
#  TELNET WORKER  (runs in QThread)
# ─────────────────────────────────────────────────────────────
class TelnetWorker(QObject):
    line_received  = Signal(str)
    connected_ok   = Signal()
    connect_failed = Signal(str)
    disconnected   = Signal()

    def __init__(self):
        super().__init__()
        self._sock = None
        self._running = False
        self._lock = threading.Lock()
        self._send_queue: queue.Queue = queue.Queue()

    def start_connect(self, host: str, port: int, password: str):
        self._host = host
        self._port = port
        self._password = password

    @Slot()
    def run(self):
        try:
            self._sock = socket.create_connection((self._host, self._port), timeout=10)
            self._sock.settimeout(0.5)
        except (ConnectionRefusedError, OSError) as e:
            self.connect_failed.emit(str(e))
            return

        self._running = True

        if not self._wait_for("password", timeout=15):
            self.connect_failed.emit("Timed out waiting for password prompt.")
            self._sock.close()
            return

        self._raw_send(self._password)

        result = self._wait_for_multi(
            ["logon successful", "wrong password", "password incorrect"],
            timeout=10
        )
        if result is None:
            self.connect_failed.emit("No authentication response received.")
            self._sock.close()
            return
        if "successful" not in result.lower():
            self.connect_failed.emit("Authentication failed — check your password.")
            self._sock.close()
            return

        self.connected_ok.emit()
        self._read_loop()

    def send(self, cmd: str):
        self._send_queue.put(cmd)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def _read_loop(self):
        buf = b""
        while self._running:
            while not self._send_queue.empty():
                try:
                    cmd = self._send_queue.get_nowait()
                    self._raw_send(cmd)
                except queue.Empty:
                    break
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                chunk = self._strip_iac(chunk)
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip("\r ")
                    if text:
                        self.line_received.emit(text)
            except socket.timeout:
                continue
            except OSError:
                break

        self._running = False
        self.disconnected.emit()

    def _raw_send(self, cmd: str):
        with self._lock:
            if self._sock:
                try:
                    self._sock.sendall((cmd.strip() + "\r\n").encode("utf-8"))
                except OSError:
                    pass

    def _wait_for(self, keyword: str, timeout: float) -> bool:
        deadline = time.time() + timeout
        stash = []
        found = False
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if chunk:
                    text = self._strip_iac(chunk).decode("utf-8", errors="replace")
                    stash.append(text)
                    if keyword.lower() in text.lower():
                        found = True
                        break
            except socket.timeout:
                continue
            except OSError:
                break
        for t in stash:
            for line in t.splitlines():
                if line.strip():
                    self.line_received.emit(line.strip())
        return found

    def _wait_for_multi(self, keywords: list, timeout: float):
        deadline = time.time() + timeout
        stash = []
        found = None
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if chunk:
                    text = self._strip_iac(chunk).decode("utf-8", errors="replace")
                    stash.append(text)
                    for kw in keywords:
                        if kw.lower() in text.lower():
                            found = text
                            break
                    if found:
                        break
            except socket.timeout:
                continue
            except OSError:
                break
        for t in stash:
            for line in t.splitlines():
                if line.strip():
                    self.line_received.emit(line.strip())
        return found

    @staticmethod
    def _strip_iac(data: bytes) -> bytes:
        out, i = bytearray(), 0
        while i < len(data):
            if data[i] == 0xFF and i + 1 < len(data):
                i += 3 if data[i + 1] in (0xFB, 0xFC, 0xFD, 0xFE) else 2
            else:
                out.append(data[i])
                i += 1
        return bytes(out)


# ─────────────────────────────────────────────────────────────
#  HORDE RUNNER  (runs in QThread, uses existing worker)
# ─────────────────────────────────────────────────────────────
class HordeRunner(QObject):
    log       = Signal(str, str)   # message, colour
    finished  = Signal()

    NORMAL = {
        1: ('zombieArlene',   'zombieBoe'),
        2: ('zombieArlene',   'zombieBoe'),
        3: ('zombieBoeFeral', 'zombieSoldierFeral'),
    }
    MEAN = {
        1: ('zombieSoldier',     'zombieFatCop',     'zombieLumberjack'),
        2: ('zombieSoldier',     'zombieFatCop',     'zombieLumberjack'),
        3: ('zombieBoeFeral',    'zombieDemolition', 'zombieScreamer'),
    }

    def __init__(self, worker: TelnetWorker, level: int, bx: int, by: int, bz: int, D: int):
        super().__init__()
        self._worker  = worker
        self._level   = level
        self._bx, self._by, self._bz = bx, by, bz
        self._D       = D
        self._D14     = round(D * 0.714)
        self._stop    = False

    def stop(self):
        self._stop = True

    @Slot()
    def run(self):
        level  = self._level
        bx, by, bz = self._bx, self._by, self._bz
        D, D14 = self._D, self._D14

        WAVE_GAP   = 30 - (level - 1) * 5
        BREAK_LEAD = 10 - (level - 1) * 2
        BREAK_TAIL = 10 - (level - 1) * 2

        normal_cycle = itertools.cycle(self.NORMAL[level])
        mean_cycle   = itertools.cycle(self.MEAN[level])

        waves = [
            ('NORTH',     bx,    by, bz+D  ),
            ('NORTHWEST', bx-D14,by, bz+D14),
            ('WEST',      bx-D,  by, bz    ),
            ('SOUTHWEST', bx-D14,by, bz-D14),
            ('SOUTH',     bx,    by, bz-D  ),
            ('SOUTHEAST', bx+D14,by, bz-D14),
            ('EAST',      bx+D,  by, bz    ),
            ('NORTHEAST', bx+D14,by, bz+D14),
        ]

        def coord(x, y, z):
            return f"{x} {y} {z}"

        def send(cmd):
            if not self._stop:
                self._worker.send(cmd)
                time.sleep(0.9)

        def say(msg):
            send(f'say "[HORDE] {msg}"')

        def wait(secs):
            for _ in range(secs):
                if self._stop:
                    return
                time.sleep(1)

        self.log.emit(f"▶ HORDE LEVEL {level} — radius {D}, gap {WAVE_GAP}s", "#FFD700")
        say(f"HORDE INCOMING — LEVEL {level}! Good luck!")

        for i, (direction, x, y, z) in enumerate(waves):
            if self._stop:
                break

            normal = next(normal_cycle)
            mean   = next(mean_cycle)

            self.log.emit(f"  🧟 Wave {i+1}/8 — {direction}  ({normal} / {mean})", "#FF8C00")
            say(f"Wave {i+1}/8 from the {direction}!")
            send(f"sea {normal} {coord(x,y,z)} 3")
            send(f"sea {mean}   {coord(x,y,z)} 1")

            if i < len(waves) - 1:
                if level >= 2 and (i + 1) % 2 == 0:
                    wait(BREAK_LEAD)
                    if not self._stop:
                        self.log.emit("  🐕🦅 Dogs + Birds break!", "#00FFFF")
                        say("DOGS AND BIRDS! Watch the skies!")
                        send(f"sea animalZombieDog     {coord(bx,    by,    bz+D )} 2")
                        send(f"sea animalZombieDog     {coord(bx-D,  by,    bz   )} 2")
                        send(f"sea animalZombieDog     {coord(bx,    by,    bz-D )} 2")
                        send(f"sea animalZombieDog     {coord(bx+D,  by,    bz   )} 2")
                        send(f"sea animalZombieVulture {coord(bx,    by+20, bz   )} 5")
                    if level >= 3 and not self._stop:
                        wait(4)
                        if not self._stop:
                            self.log.emit("  💥 Ferals + Screamer + Demo!", "#FF5555")
                            say("SCREAMER! DEMOLISHER! RUN!!")
                            send(f"sea zombieScreamer   {coord(bx,    by, bz+D  )} 2")
                            send(f"sea zombieScreamer   {coord(bx,    by, bz-D  )} 2")
                            send(f"sea zombieDemolition {coord(bx-D14,by, bz+D14)} 1")
                            send(f"sea zombieDemolition {coord(bx+D14,by, bz-D14)} 1")
                            send(f"sea zombieBoeFeral   {coord(bx-D,  by, bz    )} 3")
                            send(f"sea zombieBoeFeral   {coord(bx+D,  by, bz    )} 3")
                    wait(BREAK_TAIL)
                else:
                    wait(WAVE_GAP)

        if not self._stop:
            say("All waves done! You survived... for now.")
            self.log.emit("✔ Horde complete.", "#88FF88")
        else:
            say("Horde aborted.")
            self.log.emit("⏹ Horde stopped.", "#FFD700")

        self.finished.emit()


# ─────────────────────────────────────────────────────────────
#  HELP PARSER
# ─────────────────────────────────────────────────────────────
PARAM_COMMANDS = {
    "kick", "ban", "say", "sayplayer", "settime", "teleport",
    "teleportplayer", "give", "giveselfxp", "spawnentity",
    "spawnsupplycrate", "setgamepref", "setgamstat", "admin",
    "whitelist", "weather", "resetplayer", "removequest",
    "chunkreset", "loglevel", "gfx", "debugshot",
}

TAB_HINTS = [
    ("General",  ["help", "version", "mem", "memcl", "loglevel", "debugshot",
                  "gfx", "switchview", "systeminformation", "ai"]),
    ("World",    ["saveworld", "chunkreset", "repairchunkdensity", "spawnentity",
                  "spawnsupplycrate", "updatelighton", "showchunkdata",
                  "showalbedo", "showspecular", "weather", "setspawnpoint",
                  "visitmap"]),
    ("Time",     ["settime", "gettime", "settimescale"]),
    ("Players",  ["listplayers", "lp", "kick", "ban", "say", "sayplayer",
                  "teleport", "teleportplayer", "give", "giveselfxp",
                  "resetplayer", "removequest", "whitelist", "starve",
                  "exhausted", "enablescopes"]),
    ("Admin",    ["admin", "shutdown", "getgamepref", "setgamepref",
                  "getgamstat", "setgamstat", "aiddebug"]),
]

ALWAYS_VISIBLE = ["saveworld", "shutdown", "listplayers", "gettime", "kick", "ban"]


def parse_help(help_text: str) -> dict:
    cmds = {}
    for line in help_text.splitlines():
        m = re.match(
            r"^\s*([a-zA-Z][a-zA-Z0-9_]*)"
            r"((?:\s+\S+)*?)"
            r"\s*(?:[-–]|=>)\s*(.+)",
            line
        )
        if not m:
            continue
        cmd  = m.group(1).lower()
        rest = m.group(2).strip()
        desc = m.group(3).strip()
        syntax_tokens = re.findall(r"[<\[][^>\]]+[>\]]", rest)
        syntax = " ".join(syntax_tokens)
        if not syntax:
            sm = re.search(r"usage[:\s]+\S+\s+([<\[][^)]+)", desc, re.I)
            if sm:
                syntax = sm.group(1).strip()
        needs_params = bool(syntax) or cmd in PARAM_COMMANDS
        cmds[cmd] = {"desc": desc, "syntax": syntax, "needs_params": needs_params}
    return cmds

def cmd_desc(cmds, cmd):
    v = cmds.get(cmd)
    return v["desc"] if isinstance(v, dict) else (v or "")

def cmd_syntax(cmds, cmd):
    v = cmds.get(cmd)
    return v["syntax"] if isinstance(v, dict) else ""

def cmd_needs_params(cmds, cmd):
    v = cmds.get(cmd)
    if isinstance(v, dict):
        return v["needs_params"]
    return cmd in PARAM_COMMANDS

def categorise_commands(cmds: dict) -> dict:
    assigned = set()
    tabs = {}
    for tab_label, hints in TAB_HINTS:
        tab_cmds = [c for c in sorted(cmds)
                    if c in hints or any(c.startswith(h) for h in hints)]
        if tab_cmds:
            tabs[tab_label] = tab_cmds
            assigned.update(tab_cmds)
    other = [c for c in sorted(cmds) if c not in assigned]
    if other:
        tabs["Other"] = other
    return tabs


# ─────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    HELP_TIMEOUT_MS = 8000
    KEEPALIVE_MS    = 60000

    def __init__(self):
        super().__init__()
        self.setWindowTitle("7 Days to Die — Telnet Manager")
        self.resize(1150, 780)
        self.setMinimumSize(850, 550)

        self._profiles = load_profiles()
        self._command_map: dict = {}
        self._help_lines: list = []
        self._collecting_help = False
        self._thread: QThread | None = None
        self._worker: TelnetWorker | None = None
        self._horde_thread: QThread | None = None
        self._horde_runner: HordeRunner | None = None
        self._keepalive_timer = QTimer(self)
        self._keepalive_timer.timeout.connect(self._do_keepalive)
        self._help_timer = QTimer(self)
        self._help_timer.setSingleShot(True)
        self._help_timer.timeout.connect(self._finish_help)

        self._build_ui()
        self._apply_styles()
        self._prefill_from_env()

    # ── .env prefill ─────────────────────────────────────────

    def _prefill_from_env(self):
        host = os.getenv("TDTD_HOST", "")
        port = os.getenv("TDTD_PORT", "")
        pw   = os.getenv("TDTD_PASS", "")
        if host: self._host_input.setText(host)
        if port: self._port_input.setText(port)
        if pw:   self._pass_input.setText(pw)

    # ── UI construction ──────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 6)
        root.setSpacing(8)

        self._build_topbar(root)
        self._build_quick_bar(root)
        self._build_main_area(root)
        self._build_input_bar(root)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Not connected.")

    def _build_topbar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("topbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        title = QLabel("🧟 7DTD Telnet Manager")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addSpacing(20)

        for label_text, attr, width, placeholder, echo in [
            ("Host",     "_host_input",  160, "192.168.x.x",    None),
            ("Port",     "_port_input",   70, "8081",            None),
            ("Password", "_pass_input",  140, "telnet password", QLineEdit.Password),
        ]:
            lbl = QLabel(label_text)
            lbl.setObjectName("field_label")
            layout.addWidget(lbl)
            inp = QLineEdit()
            inp.setFixedWidth(width)
            inp.setPlaceholderText(placeholder)
            inp.setObjectName("field_input")
            if echo:
                inp.setEchoMode(echo)
            setattr(self, attr, inp)
            layout.addWidget(inp)
            layout.addSpacing(4)

        lbl = QLabel("Profile")
        lbl.setObjectName("field_label")
        layout.addWidget(lbl)
        self._profile_combo = QComboBox()
        self._profile_combo.setFixedWidth(130)
        self._profile_combo.setObjectName("field_input")
        self._profile_combo.addItems([""] + list(self._profiles.keys()))
        self._profile_combo.currentTextChanged.connect(self._on_profile_selected)
        layout.addWidget(self._profile_combo)

        btn_save = QPushButton("💾")
        btn_save.setToolTip("Save profile")
        btn_save.setObjectName("btn_icon")
        btn_save.setFixedWidth(32)
        btn_save.clicked.connect(self._save_profile)
        layout.addWidget(btn_save)

        btn_del = QPushButton("🗑")
        btn_del.setToolTip("Delete profile")
        btn_del.setObjectName("btn_icon")
        btn_del.setFixedWidth(32)
        btn_del.clicked.connect(self._delete_profile)
        layout.addWidget(btn_del)

        layout.addSpacing(12)

        self._btn_connect = QPushButton("⚡  Connect")
        self._btn_connect.setObjectName("btn_connect")
        self._btn_connect.setMinimumHeight(36)
        self._btn_connect.setMinimumWidth(110)
        self._btn_connect.clicked.connect(self._do_connect)
        layout.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("✖  Disconnect")
        self._btn_disconnect.setObjectName("btn_disconnect")
        self._btn_disconnect.setMinimumHeight(36)
        self._btn_disconnect.setMinimumWidth(120)
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.clicked.connect(self._do_disconnect)
        layout.addWidget(self._btn_disconnect)

        self._dot = QLabel("●")
        self._dot.setObjectName("dot_off")
        self._dot.setFixedWidth(20)
        layout.addWidget(self._dot)

        parent_layout.addWidget(bar)

    def _build_quick_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("quickbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        lbl = QLabel("Quick:")
        lbl.setObjectName("field_label")
        layout.addWidget(lbl)

        for cmd in ALWAYS_VISIBLE:
            btn = QPushButton(cmd)
            btn.setObjectName("btn_quick")
            btn.setMinimumHeight(30)
            btn.clicked.connect(lambda checked, c=cmd: self._confirm_command(c))
            layout.addWidget(btn)

        layout.addStretch()
        parent_layout.addWidget(bar)

    def _build_main_area(self, parent_layout):
        splitter_layout = QHBoxLayout()
        splitter_layout.setSpacing(8)

        # ── Terminal (left) ──────────────────────────────────
        term_frame = QFrame()
        term_frame.setObjectName("panel")
        term_layout = QVBoxLayout(term_frame)
        term_layout.setContentsMargins(0, 0, 0, 0)
        term_layout.setSpacing(0)

        term_header = QLabel("  Server Output")
        term_header.setObjectName("panel_header")
        term_layout.addWidget(term_header)

        self._terminal = QTextEdit()
        self._terminal.setReadOnly(True)
        self._terminal.setObjectName("terminal")
        self._terminal.setPlaceholderText("Connect to a server to see output here...")
        term_layout.addWidget(self._terminal)

        splitter_layout.addWidget(term_frame, stretch=3)

        # ── Command + Horde tabs (right) ─────────────────────
        cmd_frame = QFrame()
        cmd_frame.setObjectName("panel")
        cmd_layout = QVBoxLayout(cmd_frame)
        cmd_layout.setContentsMargins(0, 0, 0, 0)
        cmd_layout.setSpacing(0)

        cmd_header = QLabel("  Commands")
        cmd_header.setObjectName("panel_header")
        cmd_layout.addWidget(cmd_header)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setObjectName("cmd_tabs")
        cmd_layout.addWidget(self._tabs)

        # Placeholder tab
        ph = QWidget()
        ph_layout = QVBoxLayout(ph)
        ph_lbl = QLabel("Connect to a server\nto auto-load commands.")
        ph_lbl.setAlignment(Qt.AlignCenter)
        ph_lbl.setObjectName("placeholder_label")
        ph_layout.addWidget(ph_lbl)
        self._tabs.addTab(ph, "  Commands  ")

        # Horde tab — always present
        self._tabs.addTab(self._build_horde_tab(), "  🧟 Horde  ")

        splitter_layout.addWidget(cmd_frame, stretch=2)
        parent_layout.addLayout(splitter_layout)

    def _build_horde_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("tab_container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("🧟 Horde Test")
        title.setObjectName("desc_title")
        layout.addWidget(title)

        desc = QLabel("Spawn waves of zombies from all 8 directions.\nUses the current server connection.")
        desc.setObjectName("desc_body")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ── Base coords ──────────────────────────────────────
        coords_frame = QFrame()
        coords_frame.setObjectName("horde_section")
        coords_layout = QHBoxLayout(coords_frame)
        coords_layout.setContentsMargins(0, 0, 0, 0)
        coords_layout.setSpacing(8)

        coords_layout.addWidget(QLabel("Base X:"))
        self._horde_bx = QLineEdit("-189")
        self._horde_bx.setFixedWidth(70)
        self._horde_bx.setObjectName("field_input")
        coords_layout.addWidget(self._horde_bx)

        coords_layout.addWidget(QLabel("Y:"))
        self._horde_by = QLineEdit("70")
        self._horde_by.setFixedWidth(60)
        self._horde_by.setObjectName("field_input")
        coords_layout.addWidget(self._horde_by)

        coords_layout.addWidget(QLabel("Z:"))
        self._horde_bz = QLineEdit("879")
        self._horde_bz.setFixedWidth(70)
        self._horde_bz.setObjectName("field_input")
        coords_layout.addWidget(self._horde_bz)

        coords_layout.addSpacing(12)

        coords_layout.addWidget(QLabel("Radius:"))
        self._horde_radius = QLineEdit("35")
        self._horde_radius.setFixedWidth(50)
        self._horde_radius.setObjectName("field_input")
        coords_layout.addWidget(self._horde_radius)

        coords_layout.addStretch()
        layout.addWidget(coords_frame)

        # ── Level buttons ─────────────────────────────────────
        lvl_lbl = QLabel("Level:")
        lvl_lbl.setObjectName("field_label")
        layout.addWidget(lvl_lbl)

        lvl_row = QHBoxLayout()
        lvl_row.setSpacing(8)
        self._horde_level = 1
        self._horde_lvl_btns = []

        level_info = [
            ("L1 — Zombies",            "8 waves of regular zombies.\n30s between waves."),
            ("L2 — + Dogs & Birds",     "Zombie waves + dog/vulture breaks every 2 waves.\n25s between waves."),
            ("L3 — + Ferals & Demos",   "Feral zombies, screamers, demolishers.\nDogs, birds AND demo breaks every 2 waves.\n20s between waves."),
        ]

        for i, (label, tooltip) in enumerate(level_info, start=1):
            btn = QPushButton(label)
            btn.setObjectName("btn_lvl_selected" if i == 1 else "btn_lvl")
            btn.setMinimumHeight(36)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked, lvl=i: self._select_horde_level(lvl))
            self._horde_lvl_btns.append(btn)
            lvl_row.addWidget(btn)

        layout.addLayout(lvl_row)

        # ── Status label ──────────────────────────────────────
        self._horde_status = QLabel("Ready.")
        self._horde_status.setObjectName("syntax_lbl")
        layout.addWidget(self._horde_status)

        # ── Start / Stop ──────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._btn_horde_start = QPushButton("⚡  Launch Horde")
        self._btn_horde_start.setObjectName("btn_initiate")
        self._btn_horde_start.setMinimumHeight(40)
        self._btn_horde_start.clicked.connect(self._launch_horde)
        action_row.addWidget(self._btn_horde_start)

        self._btn_horde_stop = QPushButton("⏹  Stop")
        self._btn_horde_stop.setObjectName("btn_disconnect")
        self._btn_horde_stop.setMinimumHeight(40)
        self._btn_horde_stop.setEnabled(False)
        self._btn_horde_stop.clicked.connect(self._stop_horde)
        action_row.addWidget(self._btn_horde_stop)

        action_row.addStretch()
        layout.addLayout(action_row)

        layout.addStretch()
        return container

    def _build_input_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("inputbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        prompt = QLabel(">")
        prompt.setObjectName("prompt")
        layout.addWidget(prompt)

        self._cmd_input = QLineEdit()
        self._cmd_input.setObjectName("cmd_input")
        self._cmd_input.setPlaceholderText("Type a raw command and press Enter...")
        self._cmd_input.returnPressed.connect(self._send_raw)
        layout.addWidget(self._cmd_input)

        btn_send = QPushButton("Send")
        btn_send.setObjectName("btn_send")
        btn_send.setMinimumHeight(30)
        btn_send.clicked.connect(self._send_raw)
        layout.addWidget(btn_send)

        parent_layout.addWidget(bar)

    # ── Horde logic ──────────────────────────────────────────

    def _select_horde_level(self, level: int):
        self._horde_level = level
        for i, btn in enumerate(self._horde_lvl_btns, start=1):
            btn.setObjectName("btn_lvl_selected" if i == level else "btn_lvl")
            btn.setStyleSheet(
                "background-color: #7c3aed; color: #ffffff; border-color: #7c3aed;"
                if i == level else ""
            )

    def _launch_horde(self):
        if not self._worker or not self._worker._running:
            QMessageBox.warning(self, "Not connected", "Connect to a server first.")
            return

        try:
            bx = int(self._horde_bx.text())
            by = int(self._horde_by.text())
            bz = int(self._horde_bz.text())
            D  = int(self._horde_radius.text())
        except ValueError:
            QMessageBox.warning(self, "Bad input", "Coords and radius must be integers.")
            return

        level = self._horde_level
        reply = QMessageBox.question(
            self, "Launch Horde?",
            f"Start Level {level} horde at ({bx}, {by}, {bz}) radius {D}?\n\nThis will spawn waves of zombies on the server.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._btn_horde_start.setEnabled(False)
        self._btn_horde_stop.setEnabled(True)
        self._horde_status.setText(f"Running Level {level}…")

        self._horde_runner = HordeRunner(self._worker, level, bx, by, bz, D)
        self._horde_runner.log.connect(self._on_horde_log)
        self._horde_runner.finished.connect(self._on_horde_finished)

        self._horde_thread = QThread()
        self._horde_runner.moveToThread(self._horde_thread)
        self._horde_thread.started.connect(self._horde_runner.run)
        self._horde_thread.start()

    def _stop_horde(self):
        if self._horde_runner:
            self._horde_runner.stop()

    @Slot(str, str)
    def _on_horde_log(self, msg: str, colour: str):
        self._term_print(msg, colour)
        self._horde_status.setText(msg.strip())

    @Slot()
    def _on_horde_finished(self):
        self._btn_horde_start.setEnabled(True)
        self._btn_horde_stop.setEnabled(False)
        self._horde_status.setText("Ready.")
        if self._horde_thread:
            self._horde_thread.quit()

    # ── Connection logic ─────────────────────────────────────

    def _do_connect(self):
        host     = self._host_input.text().strip()
        port_str = self._port_input.text().strip()
        password = self._pass_input.text().strip()

        if not host or not port_str:
            QMessageBox.warning(self, "Missing info", "Host and Port are required.")
            return
        try:
            port = int(port_str)
        except ValueError:
            QMessageBox.warning(self, "Bad port", "Port must be a number.")
            return

        self._term_print(f"[INFO] Connecting to {host}:{port}…", "#64748b")
        self._set_status("Connecting…", "#FFD700")
        self._btn_connect.setEnabled(False)

        self._worker = TelnetWorker()
        self._worker.start_connect(host, port, password)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.line_received.connect(self._on_line)
        self._worker.connected_ok.connect(self._on_connected)
        self._worker.connect_failed.connect(self._on_connect_failed)
        self._worker.disconnected.connect(self._on_disconnected)
        self._thread.start()

    @Slot()
    def _on_connected(self):
        self._set_status(
            f"Connected  •  {self._host_input.text()}:{self._port_input.text()}",
            "#00ff88"
        )
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)
        self._dot.setObjectName("dot_on")
        self._dot.setStyleSheet("color: #00ff88; font-size: 18px;")
        self._term_print("[INFO] Authenticated. Fetching command list…", "#64748b")
        self._fetch_help()
        self._keepalive_timer.start(self.KEEPALIVE_MS)

    @Slot(str)
    def _on_connect_failed(self, reason: str):
        self._term_print(f"[ERROR] {reason}", "#FF5555")
        self._set_status("Connection failed.", "#FF5555")
        self._btn_connect.setEnabled(True)
        self._dot.setStyleSheet("color: #FF5555; font-size: 18px;")
        if self._thread:
            self._thread.quit()

    @Slot()
    def _on_disconnected(self):
        self._term_print("[DISCONNECTED] Connection closed.", "#64748b")
        self._set_status("Disconnected.", "#888888")
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._dot.setStyleSheet("color: #555555; font-size: 18px;")
        self._keepalive_timer.stop()

    def _do_disconnect(self):
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
        self._keepalive_timer.stop()

    # ── Incoming lines ───────────────────────────────────────

    @Slot(str)
    def _on_line(self, line: str):
        if self._collecting_help:
            self._help_lines.append(line)
        colour = self._classify(line)
        self._term_print(line, colour)

    def _classify(self, line: str) -> str:
        l = line.lower()
        if re.search(r"\b(err|error|exception|critical)\b", l):
            return "#FF5555"
        if re.search(r"\b(wrn|warn|warning)\b", l):
            return "#FFD700"
        if re.search(r"(from chat|chat:)", l):
            return "#00FFFF"
        if re.search(r"\b(player|joined|left|spawned)\b", l):
            return "#88FF88"
        return "#c0c0c0"

    # ── Help / tab building ──────────────────────────────────

    def _fetch_help(self):
        self._help_lines = []
        self._collecting_help = True
        self._worker.send("help")
        self._help_timer.start(self.HELP_TIMEOUT_MS)

    def _finish_help(self):
        self._collecting_help = False
        raw = "\n".join(self._help_lines)
        self._command_map = parse_help(raw)
        if self._command_map:
            self._term_print(f"[INFO] {len(self._command_map)} commands loaded.", "#64748b")
            self._build_command_tabs(self._command_map)
        else:
            self._term_print("[WARN] Could not parse help output — try the raw input bar.", "#FFD700")

    def _build_command_tabs(self, cmds: dict):
        # Keep the horde tab widget reference before clearing
        horde_tab = self._tabs.widget(self._tabs.count() - 1)
        self._tabs.clear()

        tabs = categorise_commands(cmds)
        all_tab_cmds = sorted(cmds.keys())
        tab_order = [("All", all_tab_cmds)] + list(tabs.items())

        for tab_label, tab_cmds in tab_order:
            self._tabs.addTab(
                self._make_command_tab(tab_cmds, cmds),
                f"  {tab_label}  "
            )

        # Re-add horde tab
        self._tabs.addTab(horde_tab, "  🧟 Horde  ")

    def _make_command_tab(self, tab_cmds: list, cmds: dict) -> QWidget:
        container = QWidget()
        container.setObjectName("tab_container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        desc_panel = QFrame()
        desc_panel.setObjectName("desc_panel")
        desc_panel.setMinimumHeight(160)
        desc_layout = QVBoxLayout(desc_panel)
        desc_layout.setContentsMargins(16, 14, 16, 10)
        desc_layout.setSpacing(8)

        cmd_title = QLabel("Select a command below")
        cmd_title.setObjectName("desc_title")
        desc_layout.addWidget(cmd_title)

        cmd_desc_lbl = QLabel("Click any command button to see what it does before running it.")
        cmd_desc_lbl.setObjectName("desc_body")
        cmd_desc_lbl.setWordWrap(True)
        desc_layout.addWidget(cmd_desc_lbl)

        syntax_lbl = QLabel("")
        syntax_lbl.setObjectName("syntax_lbl")
        syntax_lbl.setVisible(False)
        desc_layout.addWidget(syntax_lbl)

        cmd_input = QLineEdit()
        cmd_input.setObjectName("cmd_param_input")
        cmd_input.setVisible(False)
        cmd_input.setMinimumHeight(30)
        desc_layout.addWidget(cmd_input)

        desc_layout.addStretch()

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        btn_initiate = QPushButton("⚡  Initiate")
        btn_initiate.setObjectName("btn_initiate")
        btn_initiate.setMinimumHeight(34)
        btn_initiate.setMinimumWidth(110)
        btn_initiate.setVisible(False)

        btn_back = QPushButton("← Back")
        btn_back.setObjectName("btn_back")
        btn_back.setMinimumHeight(34)
        btn_back.setMinimumWidth(80)
        btn_back.setVisible(False)

        action_row.addWidget(btn_initiate)
        action_row.addWidget(btn_back)
        action_row.addStretch()
        desc_layout.addLayout(action_row)
        layout.addWidget(desc_panel)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("divider")
        layout.addWidget(divider)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("cmd_scroll")

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(6)

        for col in range(3):
            grid.setColumnStretch(col, 1)

        selected_btn = [None]

        def on_cmd_clicked(cmd, btn):
            if selected_btn[0] and selected_btn[0] is not btn:
                selected_btn[0].setObjectName("btn_cmd")
                selected_btn[0].setStyleSheet("")
            selected_btn[0] = btn
            btn.setObjectName("btn_cmd_selected")
            btn.setStyleSheet(
                "background-color: #1d4ed8; color: #ffffff; border-color: #1d4ed8;"
            )
            desc  = cmd_desc(cmds, cmd) or "No description available."
            syn   = cmd_syntax(cmds, cmd)
            needs = cmd_needs_params(cmds, cmd)

            cmd_title.setText(f"  {cmd}")
            cmd_desc_lbl.setText(desc)

            if needs:
                placeholder = syn if syn else "enter parameters..."
                cmd_input.setPlaceholderText(placeholder)
                cmd_input.clear()
                cmd_input.setVisible(True)
                syntax_lbl.setText(f"syntax:  {cmd} {syn}" if syn else f"syntax:  {cmd} <params>")
                syntax_lbl.setVisible(True)
            else:
                cmd_input.setVisible(False)
                syntax_lbl.setVisible(False)

            btn_initiate.setVisible(True)
            btn_back.setVisible(True)

            try:
                btn_initiate.clicked.disconnect()
            except RuntimeError:
                pass
            btn_initiate.clicked.connect(
                lambda: self._confirm_command(cmd, cmd_input.text().strip() if needs else "")
            )

        def on_back():
            cmd_title.setText("Select a command below")
            cmd_desc_lbl.setText("Click any command button to see what it does before running it.")
            cmd_input.setVisible(False)
            syntax_lbl.setVisible(False)
            btn_initiate.setVisible(False)
            btn_back.setVisible(False)
            if selected_btn[0]:
                selected_btn[0].setObjectName("btn_cmd")
                selected_btn[0].setStyleSheet("")
                selected_btn[0] = None

        btn_back.clicked.connect(on_back)

        for i, cmd in enumerate(sorted(tab_cmds)):
            btn = QPushButton(cmd)
            btn.setObjectName("btn_cmd")
            btn.setMinimumHeight(32)
            btn.clicked.connect(lambda checked, c=cmd, b=btn: on_cmd_clicked(c, b))
            grid.addWidget(btn, i // 3, i % 3)

        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return container

    # ── Command execution ────────────────────────────────────

    def _confirm_command(self, cmd: str, params: str = ""):
        if not self._worker or not self._worker._running:
            QMessageBox.warning(self, "Not connected", "Connect to a server first.")
            return
        full = f"{cmd} {params}".strip()
        reply = QMessageBox.question(
            self, "Are you sure?",
            f"Run command:\n\n  {full}\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._term_print(f"> {full}", "#1d8348")
        self._worker.send(full)

    def _send_raw(self):
        cmd = self._cmd_input.text().strip()
        if not cmd:
            return
        if not self._worker or not self._worker._running:
            QMessageBox.warning(self, "Not connected", "Connect to a server first.")
            return
        self._term_print(f"> {cmd}", "#1d8348")
        self._worker.send(cmd)
        self._cmd_input.clear()

    # ── Keepalive ────────────────────────────────────────────

    def _do_keepalive(self):
        if self._worker and self._worker._running:
            self._worker.send("gettime")

    # ── Terminal ─────────────────────────────────────────────

    def _term_print(self, text: str, colour: str = "#c0c0c0"):
        ts = time.strftime("%H:%M:%S")
        cursor = self._terminal.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._terminal.setTextCursor(cursor)
        self._terminal.setTextColor(QColor("#475569"))
        self._terminal.insertPlainText(f"[{ts}] ")
        self._terminal.setTextColor(QColor(colour))
        self._terminal.insertPlainText(f"{text}\n")
        self._terminal.ensureCursorVisible()

    def _set_status(self, msg: str, colour: str = "#888888"):
        self._status_bar.showMessage(msg)
        self._status_bar.setStyleSheet(f"color: {colour}; background: #080b11;")

    # ── Profiles ─────────────────────────────────────────────

    def _save_profile(self):
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name:
            return
        self._profiles[name] = {
            "host":     self._host_input.text(),
            "port":     self._port_input.text(),
            "password": self._pass_input.text(),
        }
        save_profiles(self._profiles)
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItems([""] + list(self._profiles.keys()))
        self._profile_combo.setCurrentText(name)
        self._profile_combo.blockSignals(False)

    def _delete_profile(self):
        name = self._profile_combo.currentText()
        if name and name in self._profiles:
            del self._profiles[name]
            save_profiles(self._profiles)
            self._profile_combo.blockSignals(True)
            self._profile_combo.clear()
            self._profile_combo.addItems([""] + list(self._profiles.keys()))
            self._profile_combo.blockSignals(False)

    def _on_profile_selected(self, name: str):
        p = self._profiles.get(name, {})
        self._host_input.setText(p.get("host", ""))
        self._port_input.setText(p.get("port", ""))
        self._pass_input.setText(p.get("password", ""))

    # ── Styles ───────────────────────────────────────────────

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0f1117;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Consolas', monospace;
                font-size: 14px;
            }
            #title {
                font-size: 18px; font-weight: 700;
                color: #f8fafc; letter-spacing: 0.5px;
            }
            #topbar, #quickbar, #inputbar {
                background-color: #141820;
                border-bottom: 1px solid #1e293b;
            }
            #inputbar { border-top: 1px solid #1e293b; border-bottom: none; }
            #field_label { color: #64748b; font-size: 13px; }
            #field_input, QLineEdit {
                background-color: #1e293b; color: #e2e8f0;
                border: 1px solid #334155; border-radius: 5px; padding: 4px 8px;
                selection-background-color: #1d4ed8;
            }
            #field_input:focus, QLineEdit:focus { border-color: #1d4ed8; }
            QComboBox {
                background-color: #1e293b; color: #e2e8f0;
                border: 1px solid #334155; border-radius: 5px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e293b; color: #e2e8f0;
                selection-background-color: #1d4ed8;
            }
            #btn_connect {
                background-color: #166534; color: #f0fdf4;
                border: none; border-radius: 6px; font-weight: 700; font-size: 14px;
            }
            #btn_connect:hover    { background-color: #15803d; }
            #btn_connect:pressed  { background-color: #14532d; }
            #btn_connect:disabled { background-color: #1e293b; color: #475569; }
            #btn_disconnect {
                background-color: #7f1d1d; color: #fef2f2;
                border: none; border-radius: 6px; font-weight: 700; font-size: 14px;
            }
            #btn_disconnect:hover    { background-color: #991b1b; }
            #btn_disconnect:pressed  { background-color: #450a0a; }
            #btn_disconnect:disabled { background-color: #1e293b; color: #475569; }
            #btn_quick {
                background-color: #1e3a5f; color: #bfdbfe;
                border: 1px solid #1d4ed8; border-radius: 5px;
                font-size: 13px; font-weight: 600; padding: 4px 10px;
            }
            #btn_quick:hover   { background-color: #1d4ed8; color: #ffffff; }
            #btn_quick:pressed { background-color: #1e40af; }
            #btn_icon {
                background-color: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-radius: 5px; font-size: 13px;
            }
            #btn_icon:hover { background-color: #334155; }
            #btn_cmd {
                background-color: #1e293b; color: #cbd5e1;
                border: 1px solid #2d3f55; border-radius: 5px;
                font-size: 13px; font-family: 'Consolas', monospace; padding: 6px;
            }
            #btn_cmd:hover   { background-color: #1d4ed8; color: #ffffff; border-color: #1d4ed8; }
            #btn_cmd:pressed { background-color: #1e40af; }
            #btn_send {
                background-color: #1d4ed8; color: #ffffff;
                border: none; border-radius: 5px; font-weight: 600; padding: 4px 16px;
            }
            #btn_send:hover   { background-color: #2563eb; }
            #btn_send:pressed { background-color: #1e40af; }
            #btn_initiate {
                background-color: #166534; color: #f0fdf4;
                border: none; border-radius: 6px; font-weight: 700; font-size: 14px;
            }
            #btn_initiate:hover   { background-color: #15803d; }
            #btn_initiate:pressed { background-color: #14532d; }
            #btn_back {
                background-color: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-radius: 6px; font-size: 14px;
            }
            #btn_back:hover   { background-color: #334155; color: #e2e8f0; }
            #btn_back:pressed { background-color: #0f172a; }
            #btn_lvl {
                background-color: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-radius: 6px;
                font-size: 13px; font-weight: 600; padding: 6px 12px;
            }
            #btn_lvl:hover { background-color: #4c1d95; color: #e9d5ff; border-color: #7c3aed; }
            #btn_lvl_selected {
                background-color: #7c3aed; color: #ffffff;
                border: 1px solid #7c3aed; border-radius: 6px;
                font-size: 13px; font-weight: 700; padding: 6px 12px;
            }
            #panel {
                background-color: #0f1117;
                border: 1px solid #1e293b; border-radius: 8px;
            }
            #panel_header {
                background-color: #141820; color: #475569;
                font-size: 14px; font-weight: 600; letter-spacing: 1px;
                padding: 6px 12px; border-bottom: 1px solid #1e293b;
                border-radius: 8px 8px 0 0;
            }
            #terminal {
                background-color: #080b11; color: #94a3b8;
                border: none; border-radius: 0 0 8px 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px; padding: 8px;
                selection-background-color: #1d4ed8;
            }
            #placeholder_label { color: #334155; font-size: 13px; }
            #prompt {
                color: #00ff88; font-size: 16px;
                font-family: 'Consolas', monospace; font-weight: 700;
            }
            #cmd_input {
                background-color: #080b11; color: #00ff88;
                border: 1px solid #1e293b; border-radius: 5px;
                padding: 5px 10px; font-family: 'Consolas', monospace; font-size: 14px;
            }
            #cmd_input:focus { border-color: #00ff88; }
            QTabWidget#cmd_tabs::pane { border: none; background-color: #0f1117; }
            QTabWidget#cmd_tabs QTabBar::tab {
                background: #141820; color: #64748b;
                padding: 7px 14px; margin-right: 2px;
                border-radius: 5px 5px 0 0; font-size: 13px; font-weight: 500;
                border: 1px solid #1e293b; border-bottom: none;
            }
            QTabWidget#cmd_tabs QTabBar::tab:selected {
                background: #1d4ed8; color: #f8fafc; font-weight: 700;
            }
            QTabWidget#cmd_tabs QTabBar::tab:hover:!selected {
                background: #1e293b; color: #cbd5e1;
            }
            #cmd_scroll { background-color: #0f1117; border: none; }
            QScrollBar:vertical {
                background: #0f1117; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #334155; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QStatusBar {
                background-color: #080b11; color: #475569;
                font-size: 14px; border-top: 1px solid #1e293b;
            }
            QMessageBox, QInputDialog { background-color: #0f1117; color: #e2e8f0; }
            QToolTip {
                background-color: #1e293b; color: #cbd5e1;
                border: 1px solid #334155; font-size: 13px; padding: 4px 8px;
            }
            #desc_panel { background-color: #0d1117; border-bottom: 1px solid #1e293b; }
            #desc_title { font-size: 17px; font-weight: 700; color: #f1f5f9; letter-spacing: 0.3px; }
            #desc_body  { font-size: 14px; color: #94a3b8; line-height: 1.5; }
            #divider    { color: #1e293b; background-color: #1e293b; max-height: 1px; }
            #tab_container { background-color: #0f1117; }
            #syntax_lbl {
                font-family: 'Consolas', monospace; font-size: 13px;
                color: #475569; padding: 2px 0px;
            }
            #cmd_param_input {
                background-color: #0d1117; color: #e2e8f0;
                border: 1px solid #1d4ed8; border-radius: 5px;
                padding: 5px 10px; font-family: 'Consolas', monospace; font-size: 14px;
            }
            #cmd_param_input:focus { border-color: #3b82f6; }
            #horde_section { background: transparent; }
        """)


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
