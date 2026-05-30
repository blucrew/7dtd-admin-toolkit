"""
7 Days to Die — Admin Toolkit
Requirements: pip install PySide6 python-dotenv
Run:          python 7dtd_manager.py
"""

import socket, threading, queue, json, os, re, time, sys, itertools
from dotenv import load_dotenv
load_dotenv()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QTabWidget,
    QStatusBar, QComboBox, QScrollArea, QGridLayout, QFrame,
    QMessageBox, QInputDialog, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, Slot, QTimer, QPoint
from PySide6.QtGui import QTextCursor, QColor, QAction

# ─────────────────────────────────────────────────────────────
#  FILE PATHS
# ─────────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_FILE     = os.path.join(_DIR, "7dtd_profiles.json")
WAVE_CONFIG_FILE = os.path.join(_DIR, "horde_waves.json")
PRESETS_FILE     = os.path.join(_DIR, "horde_presets.json")
FAVOURITES_FILE  = os.path.join(_DIR, "favourites.json")

# ─────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────
DIRECTIONS = ['NORTH','NORTHWEST','WEST','SOUTHWEST','SOUTH','SOUTHEAST','EAST','NORTHEAST','CENTER','ABOVE']

def direction_offset(direction, D, D14):
    return {
        'NORTH':     ( 0,   0,  D  ),
        'NORTHWEST': (-D14, 0,  D14),
        'WEST':      (-D,   0,  0  ),
        'SOUTHWEST': (-D14, 0, -D14),
        'SOUTH':     ( 0,   0, -D  ),
        'SOUTHEAST': ( D14, 0, -D14),
        'EAST':      ( D,   0,  0  ),
        'NORTHEAST': ( D14, 0,  D14),
        'CENTER':    ( 0,   0,  0  ),
        'ABOVE':     ( 0,   20, 0  ),
    }.get(direction, (0, 0, 0))

DEFAULT_WAVES = [
    {'name': 'Wave 1', 'direction': 'NORTH',     'spawns': [('zombieArlene', 3), ('zombieSoldier',    1)]},
    {'name': 'Wave 2', 'direction': 'NORTHWEST', 'spawns': [('zombieBoe',    3), ('zombieFatCop',     1)]},
    {'name': 'Wave 3', 'direction': 'WEST',      'spawns': [('zombieArlene', 3), ('zombieLumberjack', 1)]},
    {'name': 'Wave 4', 'direction': 'SOUTHWEST', 'spawns': [('zombieBoe',    3), ('zombieSoldier',    1)]},
    {'name': 'Wave 5', 'direction': 'SOUTH',     'spawns': [('zombieArlene', 3), ('zombieFatCop',     1)]},
    {'name': 'Wave 6', 'direction': 'SOUTHEAST', 'spawns': [('zombieBoe',    3), ('zombieLumberjack', 1)]},
    {'name': 'Wave 7', 'direction': 'EAST',      'spawns': [('zombieArlene', 3), ('zombieSoldier',    1)]},
    {'name': 'Wave 8', 'direction': 'NORTHEAST', 'spawns': [('zombieBoe',    3), ('zombieFatCop',     1)]},
]
DEFAULT_BREAK_SPAWNS = [
    ('animalZombieDog',     2, 'NORTH'), ('animalZombieDog',     2, 'SOUTH'),
    ('animalZombieDog',     2, 'EAST'),  ('animalZombieDog',     2, 'WEST'),
    ('animalZombieVulture', 5, 'ABOVE'),
]
DEFAULT_L3_BREAK_SPAWNS = [
    ('zombieScreamer',   2, 'NORTH'), ('zombieScreamer',   2, 'SOUTH'),
    ('zombieDemolition', 1, 'NORTHWEST'), ('zombieDemolition', 1, 'SOUTHEAST'),
    ('zombieBoeFeral',   3, 'WEST'),  ('zombieBoeFeral',   3, 'EAST'),
]

ALWAYS_VISIBLE = ["saveworld", "shutdown", "listplayers", "gettime", "kick", "ban"]
PARAM_COMMANDS = {
    "kick","ban","say","sayplayer","settime","teleport","teleportplayer",
    "give","giveselfxp","spawnentity","spawnsupplycrate","setgamepref",
    "setgamstat","admin","whitelist","weather","resetplayer","removequest",
    "chunkreset","loglevel","gfx","debugshot",
}
TAB_HINTS = [
    ("General", ["help","version","mem","memcl","loglevel","debugshot","gfx","switchview","systeminformation","ai"]),
    ("World",   ["saveworld","chunkreset","repairchunkdensity","spawnentity","spawnsupplycrate",
                 "updatelighton","showchunkdata","showalbedo","showspecular","weather","setspawnpoint","visitmap"]),
    ("Time",    ["settime","gettime","settimescale"]),
    ("Players", ["listplayers","lp","kick","ban","say","sayplayer","teleport","teleportplayer",
                 "give","giveselfxp","resetplayer","removequest","whitelist","starve","exhausted","enablescopes"]),
    ("Admin",   ["admin","shutdown","getgamepref","setgamepref","getgamstat","setgamstat","aiddebug"]),
]

# ─────────────────────────────────────────────────────────────
#  PERSISTENCE HELPERS
# ─────────────────────────────────────────────────────────────
def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except: pass
    return default

def _save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

load_profiles   = lambda: _load_json(PROFILE_FILE, {})
save_profiles   = lambda p: _save_json(PROFILE_FILE, p)
load_favourites = lambda: set(_load_json(FAVOURITES_FILE, []))
save_favourites = lambda f: _save_json(FAVOURITES_FILE, list(f))
load_presets    = lambda: _load_json(PRESETS_FILE, {})
save_presets    = lambda p: _save_json(PRESETS_FILE, p)

# ─────────────────────────────────────────────────────────────
#  HISTORY LINE EDIT
# ─────────────────────────────────────────────────────────────
class HistoryLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history = []
        self._idx = -1
        self._saved = ""

    def push(self, cmd):
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._idx = -1

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            if not self._history: return
            if self._idx == -1: self._saved = self.text(); self._idx = len(self._history) - 1
            elif self._idx > 0: self._idx -= 1
            self.setText(self._history[self._idx])
        elif event.key() == Qt.Key_Down:
            if self._idx == -1: return
            if self._idx < len(self._history) - 1:
                self._idx += 1; self.setText(self._history[self._idx])
            else:
                self._idx = -1; self.setText(self._saved)
        else:
            self._idx = -1
            super().keyPressEvent(event)

# ─────────────────────────────────────────────────────────────
#  TELNET WORKER
# ─────────────────────────────────────────────────────────────
class TelnetWorker(QObject):
    line_received  = Signal(str)
    connected_ok   = Signal()
    connect_failed = Signal(str)
    disconnected   = Signal()

    def __init__(self):
        super().__init__()
        self._sock = None; self._running = False
        self._lock = threading.Lock(); self._send_queue = queue.Queue()

    def start_connect(self, host, port, password):
        self._host, self._port, self._password = host, port, password

    @Slot()
    def run(self):
        try:
            self._sock = socket.create_connection((self._host, self._port), timeout=10)
            self._sock.settimeout(0.5)
        except (ConnectionRefusedError, OSError) as e:
            self.connect_failed.emit(str(e)); return
        self._running = True
        if not self._wait_for("password", 15):
            self.connect_failed.emit("Timed out waiting for password prompt.")
            self._sock.close(); return
        self._raw_send(self._password)
        result = self._wait_for_multi(["logon successful","wrong password","password incorrect"], 10)
        if result is None:
            self.connect_failed.emit("No authentication response."); self._sock.close(); return
        if "successful" not in result.lower():
            self.connect_failed.emit("Authentication failed."); self._sock.close(); return
        self.connected_ok.emit(); self._read_loop()

    def send(self, cmd): self._send_queue.put(cmd)

    def stop(self):
        self._running = False
        if self._sock:
            try: self._sock.close()
            except OSError: pass

    def _read_loop(self):
        buf = b""
        while self._running:
            while not self._send_queue.empty():
                try: self._raw_send(self._send_queue.get_nowait())
                except queue.Empty: break
            try:
                chunk = self._sock.recv(4096)
                if not chunk: break
                buf += self._strip_iac(chunk)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip("\r ")
                    if text: self.line_received.emit(text)
            except socket.timeout: continue
            except OSError: break
        self._running = False; self.disconnected.emit()

    def _raw_send(self, cmd):
        with self._lock:
            if self._sock:
                try: self._sock.sendall((cmd.strip()+"\r\n").encode("utf-8"))
                except OSError: pass

    def _wait_for(self, keyword, timeout):
        deadline = time.time()+timeout; stash = []; found = False
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if chunk:
                    text = self._strip_iac(chunk).decode("utf-8", errors="replace")
                    stash.append(text)
                    if keyword.lower() in text.lower(): found = True; break
            except socket.timeout: continue
            except OSError: break
        for t in stash:
            for line in t.splitlines():
                if line.strip(): self.line_received.emit(line.strip())
        return found

    def _wait_for_multi(self, keywords, timeout):
        deadline = time.time()+timeout; stash = []; found = None
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(4096)
                if chunk:
                    text = self._strip_iac(chunk).decode("utf-8", errors="replace")
                    stash.append(text)
                    for kw in keywords:
                        if kw.lower() in text.lower(): found = text; break
                    if found: break
            except socket.timeout: continue
            except OSError: break
        for t in stash:
            for line in t.splitlines():
                if line.strip(): self.line_received.emit(line.strip())
        return found

    @staticmethod
    def _strip_iac(data):
        out, i = bytearray(), 0
        while i < len(data):
            if data[i] == 0xFF and i+1 < len(data):
                i += 3 if data[i+1] in (0xFB,0xFC,0xFD,0xFE) else 2
            else: out.append(data[i]); i += 1
        return bytes(out)

# ─────────────────────────────────────────────────────────────
#  HORDE RUNNER
# ─────────────────────────────────────────────────────────────
class HordeRunner(QObject):
    log           = Signal(str, str)
    finished      = Signal()
    wave_progress = Signal(int, int)   # current, total
    countdown     = Signal(int, str)   # seconds, label

    def __init__(self, worker, level, bx, by, bz, D, config):
        super().__init__()
        self._worker = worker; self._level = level
        self._bx, self._by, self._bz = bx, by, bz
        self._D = D; self._D14 = round(D*0.714)
        self._config = config; self._stop = False

    def stop(self): self._stop = True

    @Slot()
    def run(self):
        level = self._level
        bx, by, bz, D, D14 = self._bx, self._by, self._bz, self._D, self._D14
        WAVE_GAP   = 30-(level-1)*5
        BREAK_LEAD = 10-(level-1)*2
        BREAK_TAIL = 10-(level-1)*2

        waves           = self._config.get('waves', DEFAULT_WAVES)
        break_spawns    = self._config.get('break_spawns', DEFAULT_BREAK_SPAWNS)
        l3_break_spawns = self._config.get('l3_break_spawns', DEFAULT_L3_BREAK_SPAWNS)

        def pos(direction):
            dx,dy,dz = direction_offset(direction, D, D14)
            return bx+dx, by+dy, bz+dz

        def send(cmd):
            if not self._stop: self._worker.send(cmd); time.sleep(0.9)

        def say(msg): send(f'say "[HORDE] {msg}"')

        def wait(secs, label=""):
            for remaining in range(secs, 0, -1):
                if self._stop: return
                self.countdown.emit(remaining, label); time.sleep(1)
            self.countdown.emit(0, "")

        total = len(waves)
        self.log.emit(f"▶ HORDE LEVEL {level}  |  {total} waves  |  radius {D}  |  gap {WAVE_GAP}s", "#FFD700")
        say(f"HORDE INCOMING — LEVEL {level}! Good luck!")

        for i, wave in enumerate(waves):
            if self._stop: break
            self.wave_progress.emit(i+1, total)
            x, y, z = pos(wave['direction'])
            name = wave.get('name', f'Wave {i+1}')
            self.log.emit(f"  🧟 {name}  [{wave['direction']}]", "#FF8C00")
            say(f"{name} from the {wave['direction']}!")
            for etype, count in wave['spawns']:
                if etype.strip(): send(f"sea {etype.strip()} {x} {y} {z} {count}")

            if i < len(waves)-1:
                if level >= 2 and (i+1) % 2 == 0:
                    wait(BREAK_LEAD, "Break incoming…")
                    if not self._stop:
                        self.log.emit("  🐕🦅 Break wave!", "#00FFFF")
                        say("Dogs and birds! Watch the skies!")
                        for etype, count, direction in break_spawns:
                            if etype.strip():
                                bpx,bpy,bpz = pos(direction)
                                send(f"sea {etype.strip()} {bpx} {bpy} {bpz} {count}")
                    if level >= 3 and not self._stop:
                        wait(4, "Ferals incoming…")
                        if not self._stop:
                            self.log.emit("  💥 Ferals + Screamers + Demos!", "#FF5555")
                            say("SCREAMER! DEMOLISHER! RUN!!")
                            for etype, count, direction in l3_break_spawns:
                                if etype.strip():
                                    bpx,bpy,bpz = pos(direction)
                                    send(f"sea {etype.strip()} {bpx} {bpy} {bpz} {count}")
                    wait(BREAK_TAIL, "")
                else:
                    wait(WAVE_GAP, f"Next wave in")

        if not self._stop:
            self.wave_progress.emit(total, total)
            say("All waves done! You survived... for now.")
            self.log.emit("✔ Horde complete.", "#88FF88")
        else:
            say("Horde aborted.")
            self.log.emit("⏹ Horde stopped.", "#FFD700")

        self.countdown.emit(0, "")
        self.finished.emit()

# ─────────────────────────────────────────────────────────────
#  HELP PARSER
# ─────────────────────────────────────────────────────────────
def parse_help(help_text):
    cmds = {}
    for line in help_text.splitlines():
        m = re.match(r"^\s*([a-zA-Z][a-zA-Z0-9_]*)((?:\s+\S+)*?)\s*(?:[-–]|=>)\s*(.+)", line)
        if not m: continue
        cmd = m.group(1).lower(); rest = m.group(2).strip(); desc = m.group(3).strip()
        syntax_tokens = re.findall(r"[<\[][^>\]]+[>\]]", rest)
        syntax = " ".join(syntax_tokens)
        if not syntax:
            sm = re.search(r"usage[:\s]+\S+\s+([<\[][^)]+)", desc, re.I)
            if sm: syntax = sm.group(1).strip()
        cmds[cmd] = {"desc": desc, "syntax": syntax, "needs_params": bool(syntax) or cmd in PARAM_COMMANDS}
    return cmds

def categorise_commands(cmds):
    assigned, tabs = set(), {}
    for label, hints in TAB_HINTS:
        tc = [c for c in sorted(cmds) if c in hints or any(c.startswith(h) for h in hints)]
        if tc: tabs[label] = tc; assigned.update(tc)
    other = [c for c in sorted(cmds) if c not in assigned]
    if other: tabs["Other"] = other
    return tabs

# ─────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    HELP_TIMEOUT_MS    = 8000
    KEEPALIVE_MS       = 60000
    PLAYER_POLL_MS     = 10000
    RECONNECT_DELAY_S  = 10

    def __init__(self):
        super().__init__()
        self.setWindowTitle("7 Days to Die — Admin Toolkit")
        self.resize(1250, 860); self.setMinimumSize(950, 600)

        # Core state
        self._profiles    = load_profiles()
        self._favourites  = load_favourites()
        self._presets     = load_presets()
        self._command_map = {}
        self._help_lines  = []; self._collecting_help = False
        self._thread = None; self._worker = None
        self._horde_thread = None; self._horde_runner = None

        # Terminal filter
        self._term_lines  = []   # list of (text, colour)
        self._filter_text = ""

        # Players
        self._players_data        = {}   # id -> dict
        self._selected_player_id  = None
        self._parsing_players     = False
        self._player_lines_buf    = []

        # Auto-reconnect
        self._intentional_disconnect = False
        self._reconnect_credentials  = None
        self._reconnect_countdown    = 0

        # Wave editor state
        self._wave_records       = []
        self._break_records      = []
        self._l3_break_records   = []
        self._waves_container    = None
        self._break_container    = None
        self._l3_break_container = None

        # Timers
        self._keepalive_timer   = QTimer(self); self._keepalive_timer.timeout.connect(self._do_keepalive)
        self._help_timer        = QTimer(self); self._help_timer.setSingleShot(True); self._help_timer.timeout.connect(self._finish_help)
        self._player_poll_timer = QTimer(self); self._player_poll_timer.timeout.connect(self._poll_players)
        self._reconnect_timer   = QTimer(self); self._reconnect_timer.timeout.connect(self._reconnect_tick)

        self._build_ui()
        self._apply_styles()
        self._prefill_from_env()
        self._load_wave_config()

    # ── Prefill ──────────────────────────────────────────────
    def _prefill_from_env(self):
        h = os.getenv("TDTD_HOST",""); p = os.getenv("TDTD_PORT",""); pw = os.getenv("TDTD_PASS","")
        if h:  self._host_input.setText(h)
        if p:  self._port_input.setText(p)
        if pw: self._pass_input.setText(pw)

    # ─────────────────────────────────────────────────────────
    #  UI BUILD
    # ─────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(12,12,12,6); root.setSpacing(8)
        self._build_topbar(root)
        self._build_quick_bar(root)
        self._build_main_area(root)
        self._build_input_bar(root)
        self._status_bar = QStatusBar(); self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Not connected.")

    def _build_topbar(self, parent):
        bar = QFrame(); bar.setObjectName("topbar")
        lay = QHBoxLayout(bar); lay.setContentsMargins(10,8,10,8); lay.setSpacing(8)
        title = QLabel("🧟 7DTD Admin Toolkit"); title.setObjectName("title"); lay.addWidget(title)
        lay.addSpacing(20)
        for lbl_txt, attr, w, ph, echo in [
            ("Host","_host_input",160,"192.168.x.x",None),
            ("Port","_port_input",70,"8081",None),
            ("Password","_pass_input",140,"telnet password",QLineEdit.Password),
        ]:
            lbl = QLabel(lbl_txt); lbl.setObjectName("field_label"); lay.addWidget(lbl)
            inp = QLineEdit(); inp.setFixedWidth(w); inp.setPlaceholderText(ph); inp.setObjectName("field_input")
            if echo: inp.setEchoMode(echo)
            setattr(self, attr, inp); lay.addWidget(inp); lay.addSpacing(4)

        lbl = QLabel("Profile"); lbl.setObjectName("field_label"); lay.addWidget(lbl)
        self._profile_combo = QComboBox(); self._profile_combo.setFixedWidth(130); self._profile_combo.setObjectName("field_input")
        self._profile_combo.addItems([""] + list(self._profiles.keys()))
        self._profile_combo.currentTextChanged.connect(self._on_profile_selected); lay.addWidget(self._profile_combo)
        for icon, tip, slot in [("💾","Save profile",self._save_profile),("🗑","Delete profile",self._delete_profile)]:
            b = QPushButton(icon); b.setToolTip(tip); b.setObjectName("btn_icon"); b.setFixedWidth(32)
            b.clicked.connect(slot); lay.addWidget(b)
        lay.addSpacing(12)

        self._btn_connect = QPushButton("⚡  Connect"); self._btn_connect.setObjectName("btn_connect")
        self._btn_connect.setMinimumHeight(36); self._btn_connect.setMinimumWidth(110)
        self._btn_connect.clicked.connect(self._do_connect); lay.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("✖  Disconnect"); self._btn_disconnect.setObjectName("btn_disconnect")
        self._btn_disconnect.setMinimumHeight(36); self._btn_disconnect.setMinimumWidth(120)
        self._btn_disconnect.setEnabled(False); self._btn_disconnect.clicked.connect(self._do_disconnect_manual)
        lay.addWidget(self._btn_disconnect)

        self._dot = QLabel("●"); self._dot.setObjectName("dot_off"); self._dot.setFixedWidth(20); lay.addWidget(self._dot)
        parent.addWidget(bar)

    def _build_quick_bar(self, parent):
        bar = QFrame(); bar.setObjectName("quickbar")
        self._quick_bar_outer = QHBoxLayout(bar); self._quick_bar_outer.setContentsMargins(10,6,10,6); self._quick_bar_outer.setSpacing(8)
        lbl = QLabel("Quick:"); lbl.setObjectName("field_label"); self._quick_bar_outer.addWidget(lbl)
        self._quick_bar_layout = QHBoxLayout(); self._quick_bar_layout.setSpacing(6)
        self._quick_bar_outer.addLayout(self._quick_bar_layout)
        self._quick_bar_outer.addStretch()
        self._rebuild_quick_bar()
        parent.addWidget(bar)

    def _rebuild_quick_bar(self):
        while self._quick_bar_layout.count():
            item = self._quick_bar_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for cmd in ALWAYS_VISIBLE:
            btn = QPushButton(cmd); btn.setObjectName("btn_quick"); btn.setMinimumHeight(30)
            btn.clicked.connect(lambda checked, c=cmd: self._confirm_command(c))
            self._quick_bar_layout.addWidget(btn)
        if self._favourites:
            div = QFrame(); div.setFrameShape(QFrame.VLine); div.setObjectName("vdivider")
            self._quick_bar_layout.addWidget(div)
            for cmd in sorted(self._favourites):
                btn = QPushButton(f"⭐ {cmd}"); btn.setObjectName("btn_fav"); btn.setMinimumHeight(30)
                btn.clicked.connect(lambda checked, c=cmd: self._confirm_command(c))
                self._quick_bar_layout.addWidget(btn)

    def _build_main_area(self, parent):
        row = QHBoxLayout(); row.setSpacing(8)

        # ── Left: terminal + filter + players ────────────────
        left = QVBoxLayout(); left.setSpacing(4)

        # Filter bar
        filter_row = QHBoxLayout(); filter_row.setSpacing(6)
        filter_icon = QLabel("🔍"); filter_icon.setObjectName("field_label"); filter_row.addWidget(filter_icon)
        self._filter_input = QLineEdit(); self._filter_input.setObjectName("filter_input")
        self._filter_input.setPlaceholderText("Filter output…"); self._filter_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_input)
        clear_btn = QPushButton("✕"); clear_btn.setObjectName("btn_icon"); clear_btn.setFixedWidth(28)
        clear_btn.clicked.connect(lambda: self._filter_input.clear()); filter_row.addWidget(clear_btn)
        left.addLayout(filter_row)

        # Terminal
        term_frame = QFrame(); term_frame.setObjectName("panel")
        tl = QVBoxLayout(term_frame); tl.setContentsMargins(0,0,0,0); tl.setSpacing(0)
        th = QLabel("  Server Output"); th.setObjectName("panel_header"); tl.addWidget(th)
        self._terminal = QTextEdit(); self._terminal.setReadOnly(True); self._terminal.setObjectName("terminal")
        self._terminal.setPlaceholderText("Connect to a server to see output here…")
        tl.addWidget(self._terminal); left.addWidget(term_frame, stretch=3)

        # Players panel
        self._players_panel = QFrame(); self._players_panel.setObjectName("panel")
        self._players_panel.setMaximumHeight(160)
        pl = QVBoxLayout(self._players_panel); pl.setContentsMargins(0,0,0,0); pl.setSpacing(0)
        ph_row = QHBoxLayout()
        ph = QLabel("  👥 Players"); ph.setObjectName("panel_header"); ph_row.addWidget(ph)
        ph_row.addStretch()
        refresh_btn = QPushButton("↺"); refresh_btn.setObjectName("btn_icon"); refresh_btn.setFixedSize(28,24)
        refresh_btn.setToolTip("Refresh player list"); refresh_btn.clicked.connect(self._poll_players)
        ph_row.addWidget(refresh_btn)
        ph_spacer = QWidget(); ph_spacer.setFixedWidth(6); ph_row.addWidget(ph_spacer)
        header_w = QWidget(); header_w.setObjectName("topbar"); header_w.setLayout(ph_row)
        pl.addWidget(header_w)

        self._player_table = QTableWidget(0, 4)
        self._player_table.setHorizontalHeaderLabels(["Name","HP","Position","Deaths"])
        self._player_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._player_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed); self._player_table.setColumnWidth(1, 50)
        self._player_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._player_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed); self._player_table.setColumnWidth(3, 60)
        self._player_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._player_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._player_table.setObjectName("player_table")
        self._player_table.verticalHeader().setVisible(False)
        self._player_table.cellClicked.connect(self._on_player_clicked)
        self._player_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._player_table.customContextMenuRequested.connect(self._on_player_right_click)
        pl.addWidget(self._player_table)
        self._players_panel.setVisible(False)
        left.addWidget(self._players_panel, stretch=1)

        left_w = QWidget(); left_w.setLayout(left); row.addWidget(left_w, stretch=3)

        # ── Right: tabs ───────────────────────────────────────
        cf = QFrame(); cf.setObjectName("panel")
        cl = QVBoxLayout(cf); cl.setContentsMargins(0,0,0,0); cl.setSpacing(0)
        ch = QLabel("  Commands"); ch.setObjectName("panel_header"); cl.addWidget(ch)
        self._tabs = QTabWidget(); self._tabs.setDocumentMode(True); self._tabs.setObjectName("cmd_tabs")
        cl.addWidget(self._tabs)
        ph_w = QWidget(); phl = QVBoxLayout(ph_w)
        phl_lbl = QLabel("Connect to a server\nto auto-load commands."); phl_lbl.setAlignment(Qt.AlignCenter)
        phl_lbl.setObjectName("placeholder_label"); phl.addWidget(phl_lbl)
        self._tabs.addTab(ph_w, "  Commands  ")
        self._tabs.addTab(self._build_horde_tab(), "  🧟 Horde  ")
        row.addWidget(cf, stretch=2); parent.addLayout(row)

    def _build_input_bar(self, parent):
        bar = QFrame(); bar.setObjectName("inputbar")
        lay = QHBoxLayout(bar); lay.setContentsMargins(10,6,10,6); lay.setSpacing(8)
        prompt = QLabel(">"); prompt.setObjectName("prompt"); lay.addWidget(prompt)
        self._cmd_input = HistoryLineEdit(); self._cmd_input.setObjectName("cmd_input")
        self._cmd_input.setPlaceholderText("Type a raw command and press Enter… (↑↓ for history)")
        self._cmd_input.returnPressed.connect(self._send_raw); lay.addWidget(self._cmd_input)
        btn = QPushButton("Send"); btn.setObjectName("btn_send"); btn.setMinimumHeight(30)
        btn.clicked.connect(self._send_raw); lay.addWidget(btn); parent.addWidget(bar)

    # ─────────────────────────────────────────────────────────
    #  HORDE TAB
    # ─────────────────────────────────────────────────────────
    def _build_horde_tab(self):
        outer = QWidget(); outer.setObjectName("tab_container")
        ol = QVBoxLayout(outer); ol.setContentsMargins(0,0,0,0)
        sub = QTabWidget(); sub.setDocumentMode(True); sub.setObjectName("cmd_tabs")
        sub.addTab(self._build_horde_launch_tab(), "  🚀 Launch  ")
        sub.addTab(self._build_horde_config_tab(), "  ⚙ Configure  ")
        ol.addWidget(sub); return outer

    def _build_horde_launch_tab(self):
        w = QWidget(); w.setObjectName("tab_container")
        lay = QVBoxLayout(w); lay.setContentsMargins(16,16,16,16); lay.setSpacing(12)

        title = QLabel("🧟 Horde Test"); title.setObjectName("desc_title"); lay.addWidget(title)
        desc = QLabel("Spawn waves of zombies from all directions. Configure in ⚙ Configure tab.")
        desc.setObjectName("desc_body"); desc.setWordWrap(True); lay.addWidget(desc)

        # Presets row
        preset_row = QHBoxLayout(); preset_row.setSpacing(8)
        preset_row.addWidget(self._make_label("Preset:"))
        self._preset_combo = QComboBox(); self._preset_combo.setFixedWidth(160); self._preset_combo.setObjectName("field_input")
        self._preset_combo.addItem("— select preset —"); self._preset_combo.addItems(list(self._presets.keys()))
        preset_row.addWidget(self._preset_combo)
        load_p = QPushButton("Load"); load_p.setObjectName("btn_add"); load_p.setMinimumHeight(28)
        load_p.clicked.connect(self._load_preset); preset_row.addWidget(load_p)
        save_p = QPushButton("Save As…"); save_p.setObjectName("btn_add"); save_p.setMinimumHeight(28)
        save_p.clicked.connect(self._save_preset_as); preset_row.addWidget(save_p)
        del_p = QPushButton("🗑"); del_p.setObjectName("btn_del"); del_p.setFixedWidth(28)
        del_p.clicked.connect(self._delete_preset); preset_row.addWidget(del_p)
        preset_row.addStretch(); lay.addLayout(preset_row)

        # Coords + radius
        cr = QHBoxLayout(); cr.setSpacing(8)
        for lbl_txt, attr, default, w_ in [
            ("Base X:","_horde_bx","-189",70),("Y:","_horde_by","70",55),
            ("Z:","_horde_bz","879",70),("Radius:","_horde_radius","35",50),
        ]:
            cr.addWidget(self._make_label(lbl_txt))
            inp = QLineEdit(default); inp.setFixedWidth(w_); inp.setObjectName("field_input")
            setattr(self, attr, inp); cr.addWidget(inp); cr.addSpacing(4)
        cr.addStretch(); lay.addLayout(cr)

        # Level buttons
        lay.addWidget(self._make_label("Level:"))
        lvl_row = QHBoxLayout(); lvl_row.setSpacing(8)
        self._horde_level = 1; self._horde_lvl_btns = []
        for i, (lbl, tip) in enumerate([
            ("L1 — Zombies",        "Regular zombie waves. 30s gaps."),
            ("L2 — + Dogs & Birds", "Zombie waves + dog/vulture breaks every 2 waves. 25s gaps."),
            ("L3 — + Ferals & Demos","Feral zombies + screamer/demo/dog/bird breaks. 20s gaps."),
        ], start=1):
            btn = QPushButton(lbl); btn.setObjectName("btn_lvl_selected" if i==1 else "btn_lvl")
            btn.setMinimumHeight(36); btn.setToolTip(tip)
            btn.clicked.connect(lambda checked, lvl=i: self._select_horde_level(lvl))
            self._horde_lvl_btns.append(btn); lvl_row.addWidget(btn)
        lay.addLayout(lvl_row)

        # Progress + countdown
        self._horde_progress = QLabel(""); self._horde_progress.setObjectName("horde_progress"); lay.addWidget(self._horde_progress)
        self._horde_countdown = QLabel(""); self._horde_countdown.setObjectName("syntax_lbl"); lay.addWidget(self._horde_countdown)
        self._horde_status = QLabel("Ready."); self._horde_status.setObjectName("syntax_lbl"); lay.addWidget(self._horde_status)

        ar = QHBoxLayout(); ar.setSpacing(10)
        self._btn_horde_start = QPushButton("⚡  Launch Horde"); self._btn_horde_start.setObjectName("btn_initiate")
        self._btn_horde_start.setMinimumHeight(40); self._btn_horde_start.clicked.connect(self._launch_horde)
        ar.addWidget(self._btn_horde_start)
        self._btn_horde_stop = QPushButton("⏹  Stop"); self._btn_horde_stop.setObjectName("btn_disconnect")
        self._btn_horde_stop.setMinimumHeight(40); self._btn_horde_stop.setEnabled(False)
        self._btn_horde_stop.clicked.connect(self._stop_horde); ar.addWidget(self._btn_horde_stop)
        ar.addStretch(); lay.addLayout(ar); lay.addStretch()
        return w

    def _build_horde_config_tab(self):
        outer = QWidget(); outer.setObjectName("tab_container")
        ol = QVBoxLayout(outer); ol.setContentsMargins(0,0,0,0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setObjectName("cmd_scroll")
        inner = QWidget(); inner.setObjectName("tab_container")
        il = QVBoxLayout(inner); il.setContentsMargins(12,12,12,12); il.setSpacing(16)

        # Waves
        wave_hdr = QHBoxLayout()
        wave_hdr.addWidget(self._make_label("Waves", "section_label")); wave_hdr.addStretch()
        add_wave_btn = QPushButton("+ Add Wave"); add_wave_btn.setObjectName("btn_add"); add_wave_btn.setMinimumHeight(28)
        add_wave_btn.clicked.connect(self._add_wave); wave_hdr.addWidget(add_wave_btn); il.addLayout(wave_hdr)
        waves_w = QWidget(); waves_w.setObjectName("tab_container")
        self._waves_container = QVBoxLayout(waves_w); self._waves_container.setContentsMargins(0,0,0,0)
        self._waves_container.setSpacing(6); self._waves_container.addStretch(); il.addWidget(waves_w)

        div = QFrame(); div.setFrameShape(QFrame.HLine); div.setObjectName("divider"); il.addWidget(div)

        # Break waves
        il.addWidget(self._make_label("Break Waves (L2+) — every 2 waves", "section_label"))
        bc = QWidget(); bc.setObjectName("tab_container")
        self._break_container = QVBoxLayout(bc); self._break_container.setContentsMargins(0,0,0,0); self._break_container.setSpacing(4)
        add_b = QPushButton("+ Add Spawn"); add_b.setObjectName("btn_add"); add_b.setMaximumWidth(120)
        add_b.clicked.connect(lambda: self._add_break_row(self._break_container, self._break_records))
        self._break_container.addWidget(add_b); il.addWidget(bc)

        div2 = QFrame(); div2.setFrameShape(QFrame.HLine); div2.setObjectName("divider"); il.addWidget(div2)

        # L3 break
        il.addWidget(self._make_label("L3 Extra Break — 4s after dogs/birds", "section_label"))
        l3c = QWidget(); l3c.setObjectName("tab_container")
        self._l3_break_container = QVBoxLayout(l3c); self._l3_break_container.setContentsMargins(0,0,0,0); self._l3_break_container.setSpacing(4)
        add_l3 = QPushButton("+ Add Spawn"); add_l3.setObjectName("btn_add"); add_l3.setMaximumWidth(120)
        add_l3.clicked.connect(lambda: self._add_break_row(self._l3_break_container, self._l3_break_records))
        self._l3_break_container.addWidget(add_l3); il.addWidget(l3c)

        il.addStretch()
        save_row = QHBoxLayout(); save_row.setSpacing(8)
        save_btn = QPushButton("💾  Save Config"); save_btn.setObjectName("btn_quick"); save_btn.setMinimumHeight(32)
        save_btn.clicked.connect(self._save_wave_config); save_row.addWidget(save_btn)
        reset_btn = QPushButton("↺  Reset to Defaults"); reset_btn.setObjectName("btn_back"); reset_btn.setMinimumHeight(32)
        reset_btn.clicked.connect(self._reset_wave_config); save_row.addWidget(reset_btn)
        save_row.addStretch(); il.addLayout(save_row)
        scroll.setWidget(inner); ol.addWidget(scroll)
        return outer

    # ─────────────────────────────────────────────────────────
    #  WAVE EDITOR
    # ─────────────────────────────────────────────────────────
    def _make_label(self, text, obj="field_label"):
        lbl = QLabel(text); lbl.setObjectName(obj); return lbl

    def _make_spinbox(self, value=1):
        sb = QSpinBox(); sb.setMinimum(1); sb.setMaximum(999); sb.setValue(value)
        sb.setFixedWidth(70); sb.setObjectName("spinbox"); return sb

    def _make_dir_combo(self, current='NORTH'):
        cb = QComboBox(); cb.addItems(DIRECTIONS); cb.setCurrentText(current)
        cb.setFixedWidth(115); cb.setObjectName("field_input"); return cb

    def _populate_waves(self, wave_data_list):
        self._wave_records = []
        while self._waves_container.count() > 1:
            item = self._waves_container.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for wave in wave_data_list: self._add_wave(wave)

    def _add_wave(self, wave_data=None):
        if wave_data is None:
            wave_data = {'name': f'Wave {len(self._wave_records)+1}', 'direction': 'NORTH', 'spawns': [('zombieArlene', 3)]}
        frame = QFrame(); frame.setObjectName("wave_frame")
        fl = QVBoxLayout(frame); fl.setContentsMargins(10,8,10,8); fl.setSpacing(6)
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        name_inp = QLineEdit(wave_data.get('name','')); name_inp.setObjectName("field_input"); name_inp.setFixedWidth(140)
        name_inp.setPlaceholderText("Wave name")
        dir_cb = self._make_dir_combo(wave_data.get('direction','NORTH'))
        hdr.addWidget(name_inp); hdr.addWidget(dir_cb); hdr.addStretch()
        up_btn = QPushButton("↑"); up_btn.setObjectName("btn_icon"); up_btn.setFixedWidth(28)
        dn_btn = QPushButton("↓"); dn_btn.setObjectName("btn_icon"); dn_btn.setFixedWidth(28)
        del_btn = QPushButton("🗑"); del_btn.setObjectName("btn_del"); del_btn.setFixedWidth(28)
        for b in (up_btn, dn_btn, del_btn): hdr.addWidget(b)
        fl.addLayout(hdr)
        spawns_w = QWidget(); spawns_w.setObjectName("tab_container")
        sl = QVBoxLayout(spawns_w); sl.setContentsMargins(0,0,0,0); sl.setSpacing(4)
        fl.addWidget(spawns_w)
        spawn_records = []

        def add_spawn(etype='', count=1):
            rw = QWidget(); rw.setObjectName("tab_container")
            rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)
            ti = QLineEdit(etype); ti.setObjectName("field_input"); ti.setFixedWidth(200)
            ti.setPlaceholderText("entity type e.g. zombieArlene")
            cs = self._make_spinbox(count)
            ds = QPushButton("🗑"); ds.setObjectName("btn_del"); ds.setFixedWidth(28)
            rl.addWidget(ti); rl.addWidget(cs); rl.addWidget(ds); rl.addStretch()
            rec = {'widget': rw, 'type': ti, 'count': cs}; spawn_records.append(rec); sl.addWidget(rw)
            ds.clicked.connect(lambda: (rw.deleteLater(), spawn_records.remove(rec)) if rec in spawn_records else None)

        add_spawn_btn = QPushButton("+ Add Spawn"); add_spawn_btn.setObjectName("btn_add"); add_spawn_btn.setMaximumWidth(110)
        add_spawn_btn.clicked.connect(lambda: add_spawn()); fl.addWidget(add_spawn_btn)
        for etype, count in wave_data.get('spawns',[]): add_spawn(etype, count)

        rec = {'frame': frame, 'name': name_inp, 'dir': dir_cb, 'spawns': spawn_records}
        self._wave_records.append(rec)

        def move_up():
            i = self._wave_records.index(rec)
            if i > 0:
                self._wave_records[i], self._wave_records[i-1] = self._wave_records[i-1], self._wave_records[i]
                self._rebuild_wave_frames()

        def move_down():
            i = self._wave_records.index(rec)
            if i < len(self._wave_records)-1:
                self._wave_records[i], self._wave_records[i+1] = self._wave_records[i+1], self._wave_records[i]
                self._rebuild_wave_frames()

        up_btn.clicked.connect(move_up); dn_btn.clicked.connect(move_down)
        del_btn.clicked.connect(lambda: (self._wave_records.remove(rec) if rec in self._wave_records else None, frame.deleteLater()))
        self._waves_container.insertWidget(self._waves_container.count()-1, frame)

    def _rebuild_wave_frames(self):
        for rec in self._wave_records:
            self._waves_container.removeWidget(rec['frame']); rec['frame'].setParent(None)
        while self._waves_container.count() > 1:
            item = self._waves_container.takeAt(0)
            if item.widget(): item.widget().setParent(None)
        for rec in self._wave_records:
            self._waves_container.insertWidget(self._waves_container.count()-1, rec['frame']); rec['frame'].show()

    def _add_break_row(self, container, records, etype='', count=1, direction='CENTER'):
        rw = QWidget(); rw.setObjectName("tab_container")
        rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)
        ti = QLineEdit(etype); ti.setObjectName("field_input"); ti.setFixedWidth(200); ti.setPlaceholderText("entity type")
        cs = self._make_spinbox(count)
        dc = self._make_dir_combo(direction)
        db = QPushButton("🗑"); db.setObjectName("btn_del"); db.setFixedWidth(28)
        rl.addWidget(ti); rl.addWidget(cs); rl.addWidget(dc); rl.addWidget(db); rl.addStretch()
        rec = {'widget': rw, 'type': ti, 'count': cs, 'dir': dc}; records.append(rec)
        container.insertWidget(container.count()-1, rw)
        db.clicked.connect(lambda: (rw.deleteLater(), records.remove(rec)) if rec in records else None)

    def _populate_break_rows(self, container, records, defaults):
        while records:
            r = records.pop(); r['widget'].deleteLater()
        for etype, count, direction in defaults:
            self._add_break_row(container, records, etype, count, direction)

    # ── Wave config persistence ──────────────────────────────
    def _collect_horde_config(self):
        waves = []
        for rec in self._wave_records:
            spawns = [(sr['type'].text().strip(), sr['count'].value()) for sr in rec['spawns'] if sr['type'].text().strip()]
            if spawns: waves.append({'name': rec['name'].text().strip() or f'Wave {len(waves)+1}',
                                      'direction': rec['dir'].currentText(), 'spawns': spawns})
        break_spawns = [(r['type'].text().strip(), r['count'].value(), r['dir'].currentText())
                        for r in self._break_records if r['type'].text().strip()]
        l3_spawns    = [(r['type'].text().strip(), r['count'].value(), r['dir'].currentText())
                        for r in self._l3_break_records if r['type'].text().strip()]
        return {'waves': waves, 'break_spawns': break_spawns, 'l3_break_spawns': l3_spawns}

    def _save_wave_config(self):
        _save_json(WAVE_CONFIG_FILE, self._collect_horde_config())
        self._term_print("[HORDE] Wave config saved.", "#64748b")

    def _load_wave_config(self):
        config = _load_json(WAVE_CONFIG_FILE, None)
        if config:
            self._populate_waves(config.get('waves', DEFAULT_WAVES))
            self._populate_break_rows(self._break_container, self._break_records, config.get('break_spawns', DEFAULT_BREAK_SPAWNS))
            self._populate_break_rows(self._l3_break_container, self._l3_break_records, config.get('l3_break_spawns', DEFAULT_L3_BREAK_SPAWNS))
        else:
            self._populate_waves(DEFAULT_WAVES)
            self._populate_break_rows(self._break_container, self._break_records, DEFAULT_BREAK_SPAWNS)
            self._populate_break_rows(self._l3_break_container, self._l3_break_records, DEFAULT_L3_BREAK_SPAWNS)

    def _reset_wave_config(self):
        if QMessageBox.question(self,"Reset?","Reset all waves to defaults?",
                                QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        self._populate_waves(DEFAULT_WAVES)
        self._populate_break_rows(self._break_container, self._break_records, DEFAULT_BREAK_SPAWNS)
        self._populate_break_rows(self._l3_break_container, self._l3_break_records, DEFAULT_L3_BREAK_SPAWNS)

    # ── Presets ──────────────────────────────────────────────
    def _save_preset_as(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name: return
        self._presets[name] = self._collect_horde_config()
        save_presets(self._presets)
        self._preset_combo.blockSignals(True); self._preset_combo.clear()
        self._preset_combo.addItem("— select preset —"); self._preset_combo.addItems(list(self._presets.keys()))
        self._preset_combo.setCurrentText(name); self._preset_combo.blockSignals(False)
        self._term_print(f"[HORDE] Preset '{name}' saved.", "#64748b")

    def _load_preset(self):
        name = self._preset_combo.currentText()
        if name not in self._presets: return
        config = self._presets[name]
        self._populate_waves(config.get('waves', DEFAULT_WAVES))
        self._populate_break_rows(self._break_container, self._break_records, config.get('break_spawns', DEFAULT_BREAK_SPAWNS))
        self._populate_break_rows(self._l3_break_container, self._l3_break_records, config.get('l3_break_spawns', DEFAULT_L3_BREAK_SPAWNS))
        self._term_print(f"[HORDE] Preset '{name}' loaded.", "#64748b")

    def _delete_preset(self):
        name = self._preset_combo.currentText()
        if name not in self._presets: return
        del self._presets[name]; save_presets(self._presets)
        self._preset_combo.blockSignals(True); self._preset_combo.clear()
        self._preset_combo.addItem("— select preset —"); self._preset_combo.addItems(list(self._presets.keys()))
        self._preset_combo.blockSignals(False)

    # ── Horde launch ─────────────────────────────────────────
    def _select_horde_level(self, level):
        self._horde_level = level
        for i, btn in enumerate(self._horde_lvl_btns, start=1):
            btn.setObjectName("btn_lvl_selected" if i==level else "btn_lvl")
            btn.setStyleSheet("background-color:#7c3aed;color:#fff;border-color:#7c3aed;" if i==level else "")

    def _launch_horde(self):
        if not self._worker or not self._worker._running:
            QMessageBox.warning(self,"Not connected","Connect to a server first."); return
        try:
            bx=int(self._horde_bx.text()); by=int(self._horde_by.text())
            bz=int(self._horde_bz.text()); D=int(self._horde_radius.text())
        except ValueError:
            QMessageBox.warning(self,"Bad input","Coords and radius must be integers."); return
        config = self._collect_horde_config(); level = self._horde_level; wc = len(config['waves'])
        if QMessageBox.question(self,"Launch Horde?",f"Start Level {level} horde?\n{wc} waves at ({bx},{by},{bz}) radius {D}.",
                                QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        self._btn_horde_start.setEnabled(False); self._btn_horde_stop.setEnabled(True)
        self._horde_progress.setText("Wave 0 / " + str(wc) + "  " + "░"*10)
        self._horde_status.setText(f"Running Level {level}…")
        self._horde_runner = HordeRunner(self._worker, level, bx, by, bz, D, config)
        self._horde_runner.log.connect(self._on_horde_log)
        self._horde_runner.finished.connect(self._on_horde_finished)
        self._horde_runner.wave_progress.connect(self._on_wave_progress)
        self._horde_runner.countdown.connect(self._on_horde_countdown)
        self._horde_thread = QThread(); self._horde_runner.moveToThread(self._horde_thread)
        self._horde_thread.started.connect(self._horde_runner.run); self._horde_thread.start()

    def _stop_horde(self):
        if self._horde_runner: self._horde_runner.stop()

    @Slot(str, str)
    def _on_horde_log(self, msg, colour):
        self._term_print(msg, colour); self._horde_status.setText(msg.strip())

    @Slot()
    def _on_horde_finished(self):
        self._btn_horde_start.setEnabled(True); self._btn_horde_stop.setEnabled(False)
        self._horde_status.setText("Ready."); self._horde_countdown.setText("")
        if self._horde_thread: self._horde_thread.quit()

    @Slot(int, int)
    def _on_wave_progress(self, current, total):
        filled = int(current/total*10) if total else 0
        bar = "█"*filled + "░"*(10-filled)
        self._horde_progress.setText(f"Wave {current} / {total}  {bar}")

    @Slot(int, str)
    def _on_horde_countdown(self, seconds, label):
        if seconds > 0: self._horde_countdown.setText(f"{label} {seconds}s…")
        else:           self._horde_countdown.setText("")

    # ─────────────────────────────────────────────────────────
    #  PLAYERS PANEL
    # ─────────────────────────────────────────────────────────
    def _poll_players(self):
        if self._worker and self._worker._running:
            self._parsing_players = True; self._player_lines_buf = []
            self._worker.send("listplayers")

    def _try_parse_player_output(self, line):
        if not self._parsing_players: return
        self._player_lines_buf.append(line)
        if "total of" in line.lower():
            self._parsing_players = False
            self._update_players_display()

    def _update_players_display(self):
        players = {}
        for line in self._player_lines_buf:
            m = re.search(
                r"id=(\d+),\s*(\S+),\s*pos=\(([^)]+)\).*?health=(\d+).*?deaths=(\d+)",
                line, re.I
            )
            if m:
                players[m.group(1)] = {
                    'id': m.group(1), 'name': m.group(2),
                    'pos': m.group(3), 'health': m.group(4), 'deaths': m.group(5)
                }
        self._players_data = players
        self._player_table.setRowCount(0)
        for pid, p in players.items():
            row = self._player_table.rowCount(); self._player_table.insertRow(row)
            name_item = QTableWidgetItem(("● " if pid == self._selected_player_id else "") + p['name'])
            self._player_table.setItem(row, 0, name_item)
            self._player_table.setItem(row, 1, QTableWidgetItem(p['health']))
            self._player_table.setItem(row, 2, QTableWidgetItem(p['pos']))
            self._player_table.setItem(row, 3, QTableWidgetItem(p['deaths']))
            for col in range(4):
                item = self._player_table.item(row, col)
                if item: item.setData(Qt.UserRole, pid)
        self._players_panel.setVisible(bool(players))

    def _on_player_clicked(self, row, col):
        item = self._player_table.item(row, 0)
        if not item: return
        pid = item.data(Qt.UserRole)
        self._selected_player_id = pid
        p = self._players_data.get(pid, {})
        self._term_print(f"[PLAYER] Selected: {p.get('name','?')} (id={pid})", "#64748b")
        self._update_players_display()

    def _on_player_right_click(self, pos: QPoint):
        item = self._player_table.itemAt(pos)
        if not item: return
        pid = item.data(Qt.UserRole)
        p = self._players_data.get(pid, {})
        name = p.get('name','?')
        menu = QMenu(self)
        menu.addAction(f"📍 TP to {name}",   lambda: self._worker.send(f"teleportplayer 584 {pid}") if self._worker else None)
        menu.addAction(f"⬅ TP {name} to me", lambda: self._worker.send(f"teleportplayer {pid} 584") if self._worker else None)
        menu.addAction(f"💊 Heal {name}",     lambda: self._worker.send(f"buffplayer {pid} buffHealthRegenLarge") if self._worker else None)
        menu.addAction(f"🎁 Give item…",      lambda: self._give_to_player(pid, name))
        menu.addAction(f"👢 Kick {name}",     lambda: self._kick_player(pid, name))
        menu.exec(self._player_table.viewport().mapToGlobal(pos))

    def _give_to_player(self, pid, name):
        item, ok = QInputDialog.getText(self, f"Give to {name}", "item count quality (e.g. ammoRocketHE 10 6):")
        if ok and item and self._worker: self._worker.send(f"give {pid} {item}")

    def _kick_player(self, pid, name):
        if QMessageBox.question(self,"Kick?",f"Kick {name}?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No) == QMessageBox.Yes:
            if self._worker: self._worker.send(f"kick {pid}")

    # ─────────────────────────────────────────────────────────
    #  CONNECTION
    # ─────────────────────────────────────────────────────────
    def _do_connect(self):
        host=self._host_input.text().strip(); port_str=self._port_input.text().strip(); password=self._pass_input.text().strip()
        if not host or not port_str:
            QMessageBox.warning(self,"Missing info","Host and Port are required."); return
        try: port=int(port_str)
        except ValueError:
            QMessageBox.warning(self,"Bad port","Port must be a number."); return
        self._reconnect_credentials = (host, port, password)
        self._intentional_disconnect = False
        self._connect_to(host, port, password)

    def _connect_to(self, host, port, password):
        self._term_print(f"[INFO] Connecting to {host}:{port}…", "#64748b")
        self._set_status("Connecting…", "#FFD700"); self._btn_connect.setEnabled(False)
        self._worker = TelnetWorker(); self._worker.start_connect(host, port, password)
        self._thread = QThread(); self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.line_received.connect(self._on_line)
        self._worker.connected_ok.connect(self._on_connected)
        self._worker.connect_failed.connect(self._on_connect_failed)
        self._worker.disconnected.connect(self._on_disconnected)
        self._thread.start()

    def _do_disconnect_manual(self):
        self._intentional_disconnect = True
        self._reconnect_timer.stop()
        if self._worker: self._worker.stop()
        if self._thread: self._thread.quit()
        self._keepalive_timer.stop(); self._player_poll_timer.stop()

    @Slot()
    def _on_connected(self):
        self._set_status(f"Connected  •  {self._host_input.text()}:{self._port_input.text()}", "#00ff88")
        self._btn_connect.setEnabled(False); self._btn_disconnect.setEnabled(True)
        self._dot.setStyleSheet("color:#00ff88;font-size:18px;")
        self._term_print("[INFO] Authenticated. Fetching command list…", "#64748b")
        self._reconnect_timer.stop()
        self._fetch_help()
        self._keepalive_timer.start(self.KEEPALIVE_MS)
        self._player_poll_timer.start(self.PLAYER_POLL_MS)
        QTimer.singleShot(1000, self._poll_players)

    @Slot(str)
    def _on_connect_failed(self, reason):
        self._term_print(f"[ERROR] {reason}", "#FF5555"); self._set_status("Connection failed.", "#FF5555")
        self._btn_connect.setEnabled(True); self._dot.setStyleSheet("color:#FF5555;font-size:18px;")
        if self._thread: self._thread.quit()
        if not self._intentional_disconnect: self._start_auto_reconnect()

    @Slot()
    def _on_disconnected(self):
        self._term_print("[DISCONNECTED] Connection closed.", "#64748b")
        self._btn_connect.setEnabled(True); self._btn_disconnect.setEnabled(False)
        self._dot.setStyleSheet("color:#555555;font-size:18px;")
        self._keepalive_timer.stop(); self._player_poll_timer.stop()
        self._players_panel.setVisible(False)
        if not self._intentional_disconnect:
            self._start_auto_reconnect()
        else:
            self._set_status("Disconnected.", "#888888")

    def _start_auto_reconnect(self):
        if not self._reconnect_credentials: return
        self._reconnect_countdown = self.RECONNECT_DELAY_S
        self._reconnect_timer.start(1000)
        self._set_status(f"Reconnecting in {self._reconnect_countdown}s…", "#FFD700")

    def _reconnect_tick(self):
        self._reconnect_countdown -= 1
        if self._reconnect_countdown <= 0:
            self._reconnect_timer.stop()
            host, port, password = self._reconnect_credentials
            self._term_print("[INFO] Auto-reconnecting…", "#64748b")
            self._connect_to(host, port, password)
        else:
            self._set_status(f"Reconnecting in {self._reconnect_countdown}s…", "#FFD700")

    # ─────────────────────────────────────────────────────────
    #  TERMINAL
    # ─────────────────────────────────────────────────────────
    @Slot(str)
    def _on_line(self, line):
        if self._collecting_help: self._help_lines.append(line)
        self._try_parse_player_output(line)
        colour = self._classify(line)
        self._term_lines.append((line, colour))
        if len(self._term_lines) > 5000: self._term_lines = self._term_lines[-3000:]
        if not self._filter_text or self._filter_text.lower() in line.lower():
            self._append_terminal(line, colour)

    def _append_terminal(self, text, colour):
        ts = time.strftime("%H:%M:%S")
        cursor = self._terminal.textCursor(); cursor.movePosition(QTextCursor.End)
        self._terminal.setTextCursor(cursor)
        self._terminal.setTextColor(QColor("#475569")); self._terminal.insertPlainText(f"[{ts}] ")
        self._terminal.setTextColor(QColor(colour)); self._terminal.insertPlainText(f"{text}\n")
        self._terminal.ensureCursorVisible()

    def _on_filter_changed(self, text):
        self._filter_text = text.strip()
        self._terminal.clear()
        for line, colour in self._term_lines:
            if not self._filter_text or self._filter_text.lower() in line.lower():
                self._append_terminal(line, colour)

    def _term_print(self, text, colour="#c0c0c0"):
        self._term_lines.append((text, colour))
        if not self._filter_text or self._filter_text.lower() in text.lower():
            self._append_terminal(text, colour)

    def _classify(self, line):
        l = line.lower()
        if re.search(r"\b(err|error|exception|critical)\b", l): return "#FF5555"
        if re.search(r"\b(wrn|warn|warning)\b", l):             return "#FFD700"
        if re.search(r"(from chat|chat:)", l):                   return "#00FFFF"
        if re.search(r"\b(player|joined|left|spawned)\b", l):   return "#88FF88"
        return "#c0c0c0"

    def _set_status(self, msg, colour="#888888"):
        self._status_bar.showMessage(msg); self._status_bar.setStyleSheet(f"color:{colour};background:#080b11;")

    # ─────────────────────────────────────────────────────────
    #  HELP + COMMAND TABS
    # ─────────────────────────────────────────────────────────
    def _fetch_help(self):
        self._help_lines=[]; self._collecting_help=True
        self._worker.send("help"); self._help_timer.start(self.HELP_TIMEOUT_MS)

    def _finish_help(self):
        self._collecting_help=False; self._command_map=parse_help("\n".join(self._help_lines))
        if self._command_map:
            self._term_print(f"[INFO] {len(self._command_map)} commands loaded.", "#64748b")
            self._build_command_tabs(self._command_map)
        else:
            self._term_print("[WARN] Could not parse help output.", "#FFD700")

    def _build_command_tabs(self, cmds):
        horde_tab = self._tabs.widget(self._tabs.count()-1); self._tabs.clear()
        tabs = categorise_commands(cmds)
        for label, tab_cmds in [("All",sorted(cmds.keys()))]+list(tabs.items()):
            self._tabs.addTab(self._make_command_tab(tab_cmds, cmds), f"  {label}  ")
        self._tabs.addTab(horde_tab, "  🧟 Horde  ")

    def _make_command_tab(self, tab_cmds, cmds):
        container = QWidget(); container.setObjectName("tab_container")
        layout = QVBoxLayout(container); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        desc_panel = QFrame(); desc_panel.setObjectName("desc_panel"); desc_panel.setMinimumHeight(160)
        dl = QVBoxLayout(desc_panel); dl.setContentsMargins(16,14,16,10); dl.setSpacing(8)
        cmd_title = QLabel("Select a command below"); cmd_title.setObjectName("desc_title"); dl.addWidget(cmd_title)
        cmd_desc_lbl = QLabel("Click any command button to see what it does before running it.")
        cmd_desc_lbl.setObjectName("desc_body"); cmd_desc_lbl.setWordWrap(True); dl.addWidget(cmd_desc_lbl)
        syntax_lbl = QLabel(""); syntax_lbl.setObjectName("syntax_lbl"); syntax_lbl.setVisible(False); dl.addWidget(syntax_lbl)
        cmd_input = QLineEdit(); cmd_input.setObjectName("cmd_param_input"); cmd_input.setVisible(False)
        cmd_input.setMinimumHeight(30); dl.addWidget(cmd_input); dl.addStretch()
        ar = QHBoxLayout(); ar.setSpacing(8)
        btn_initiate = QPushButton("⚡  Initiate"); btn_initiate.setObjectName("btn_initiate")
        btn_initiate.setMinimumHeight(34); btn_initiate.setMinimumWidth(110); btn_initiate.setVisible(False)
        btn_back = QPushButton("← Back"); btn_back.setObjectName("btn_back")
        btn_back.setMinimumHeight(34); btn_back.setMinimumWidth(80); btn_back.setVisible(False)
        ar.addWidget(btn_initiate); ar.addWidget(btn_back); ar.addStretch(); dl.addLayout(ar)
        layout.addWidget(desc_panel)
        div = QFrame(); div.setFrameShape(QFrame.HLine); div.setObjectName("divider"); layout.addWidget(div)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setObjectName("cmd_scroll")
        inner = QWidget(); grid = QGridLayout(inner); grid.setContentsMargins(10,10,10,10); grid.setSpacing(6)
        for col in range(3): grid.setColumnStretch(col,1)
        selected_btn = [None]

        def on_cmd_clicked(cmd, btn):
            if selected_btn[0] and selected_btn[0] is not btn:
                selected_btn[0].setObjectName("btn_cmd"); selected_btn[0].setStyleSheet("")
            selected_btn[0]=btn; btn.setObjectName("btn_cmd_selected")
            btn.setStyleSheet("background-color:#1d4ed8;color:#fff;border-color:#1d4ed8;")
            v = cmds.get(cmd,{})
            desc  = v.get("desc","") if isinstance(v,dict) else (v or "No description.")
            syn   = v.get("syntax","") if isinstance(v,dict) else ""
            needs = v.get("needs_params",False) if isinstance(v,dict) else cmd in PARAM_COMMANDS
            # Pre-fill selected player ID if applicable
            if needs and self._selected_player_id and any(k in cmd for k in ['player','kick','ban','give','buff','tp']):
                cmd_input.setText(self._selected_player_id)
            else:
                cmd_input.clear()
            cmd_title.setText(f"  {cmd}"); cmd_desc_lbl.setText(desc)
            if needs:
                cmd_input.setPlaceholderText(syn or "enter parameters…")
                cmd_input.setVisible(True)
                syntax_lbl.setText(f"syntax:  {cmd} {syn}" if syn else f"syntax:  {cmd} <params>")
                syntax_lbl.setVisible(True)
            else:
                cmd_input.setVisible(False); syntax_lbl.setVisible(False)
            btn_initiate.setVisible(True); btn_back.setVisible(True)
            try: btn_initiate.clicked.disconnect()
            except RuntimeError: pass
            btn_initiate.clicked.connect(lambda: self._confirm_command(cmd, cmd_input.text().strip() if needs else ""))

        def on_back():
            cmd_title.setText("Select a command below")
            cmd_desc_lbl.setText("Click any command button to see what it does before running it.")
            cmd_input.setVisible(False); syntax_lbl.setVisible(False)
            btn_initiate.setVisible(False); btn_back.setVisible(False)
            if selected_btn[0]: selected_btn[0].setObjectName("btn_cmd"); selected_btn[0].setStyleSheet(""); selected_btn[0]=None

        btn_back.clicked.connect(on_back)

        for i, cmd in enumerate(sorted(tab_cmds)):
            btn = QPushButton(cmd); btn.setObjectName("btn_cmd"); btn.setMinimumHeight(32)
            btn.clicked.connect(lambda checked, c=cmd, b=btn: on_cmd_clicked(c,b))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, c=cmd, b=btn: self._cmd_btn_context_menu(c, b, pos))
            grid.addWidget(btn, i//3, i%3)

        scroll.setWidget(inner); layout.addWidget(scroll)
        return container

    def _cmd_btn_context_menu(self, cmd, btn, pos):
        menu = QMenu(self)
        is_fav = cmd in self._favourites
        action_text = f"★ Remove '{cmd}' from Favourites" if is_fav else f"☆ Add '{cmd}' to Favourites"
        menu.addAction(action_text, lambda: self._toggle_favourite(cmd))
        menu.exec(btn.mapToGlobal(pos))

    def _toggle_favourite(self, cmd):
        if cmd in self._favourites: self._favourites.discard(cmd)
        else: self._favourites.add(cmd)
        save_favourites(self._favourites)
        self._rebuild_quick_bar()

    # ─────────────────────────────────────────────────────────
    #  COMMANDS
    # ─────────────────────────────────────────────────────────
    def _confirm_command(self, cmd, params=""):
        if not self._worker or not self._worker._running:
            QMessageBox.warning(self,"Not connected","Connect to a server first."); return
        full = f"{cmd} {params}".strip()
        if QMessageBox.question(self,"Are you sure?",f"Run command:\n\n  {full}\n\nThis cannot be undone.",
                                QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        self._term_print(f"> {full}", "#1d8348"); self._worker.send(full)

    def _send_raw(self):
        cmd = self._cmd_input.text().strip()
        if not cmd: return
        if not self._worker or not self._worker._running:
            QMessageBox.warning(self,"Not connected","Connect to a server first."); return
        self._term_print(f"> {cmd}", "#1d8348"); self._worker.send(cmd)
        self._cmd_input.push(cmd); self._cmd_input.clear()

    def _do_keepalive(self):
        if self._worker and self._worker._running: self._worker.send("gettime")

    # ─────────────────────────────────────────────────────────
    #  PROFILES
    # ─────────────────────────────────────────────────────────
    def _save_profile(self):
        name, ok = QInputDialog.getText(self,"Save Profile","Profile name:")
        if not ok or not name: return
        self._profiles[name] = {"host":self._host_input.text(),"port":self._port_input.text(),"password":self._pass_input.text()}
        save_profiles(self._profiles)
        self._profile_combo.blockSignals(True); self._profile_combo.clear()
        self._profile_combo.addItems([""] + list(self._profiles.keys()))
        self._profile_combo.setCurrentText(name); self._profile_combo.blockSignals(False)

    def _delete_profile(self):
        name = self._profile_combo.currentText()
        if name and name in self._profiles:
            del self._profiles[name]; save_profiles(self._profiles)
            self._profile_combo.blockSignals(True); self._profile_combo.clear()
            self._profile_combo.addItems([""] + list(self._profiles.keys())); self._profile_combo.blockSignals(False)

    def _on_profile_selected(self, name):
        p = self._profiles.get(name,{})
        self._host_input.setText(p.get("host","")); self._port_input.setText(p.get("port",""))
        self._pass_input.setText(p.get("password",""))

    # ─────────────────────────────────────────────────────────
    #  STYLES
    # ─────────────────────────────────────────────────────────
    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color:#0f1117; color:#e2e8f0;
                font-family:'Segoe UI','Consolas',monospace; font-size:14px; }
            #title { font-size:18px; font-weight:700; color:#f8fafc; letter-spacing:0.5px; }
            #topbar, #quickbar, #inputbar { background-color:#141820; border-bottom:1px solid #1e293b; }
            #inputbar { border-top:1px solid #1e293b; border-bottom:none; }
            #field_label { color:#64748b; font-size:13px; }
            #field_input, QLineEdit { background-color:#1e293b; color:#e2e8f0; border:1px solid #334155;
                border-radius:5px; padding:4px 8px; selection-background-color:#1d4ed8; }
            #field_input:focus, QLineEdit:focus { border-color:#1d4ed8; }
            #filter_input { background-color:#0d1117; color:#e2e8f0; border:1px solid #1e293b;
                border-radius:5px; padding:4px 8px; }
            #filter_input:focus { border-color:#7c3aed; }
            QComboBox { background-color:#1e293b; color:#e2e8f0; border:1px solid #334155;
                border-radius:5px; padding:4px 8px; }
            QComboBox::drop-down { border:none; }
            QComboBox QAbstractItemView { background-color:#1e293b; color:#e2e8f0; selection-background-color:#1d4ed8; }
            QSpinBox#spinbox { background-color:#1e293b; color:#e2e8f0; border:1px solid #334155;
                border-radius:5px; padding:3px 4px; }
            QSpinBox#spinbox::up-button, QSpinBox#spinbox::down-button { width:18px; background:#2d3f55; border:none; }
            QSpinBox#spinbox::up-button:hover, QSpinBox#spinbox::down-button:hover { background:#1d4ed8; }
            #btn_connect { background-color:#166534; color:#f0fdf4; border:none; border-radius:6px; font-weight:700; }
            #btn_connect:hover { background-color:#15803d; }
            #btn_connect:disabled { background-color:#1e293b; color:#475569; }
            #btn_disconnect { background-color:#7f1d1d; color:#fef2f2; border:none; border-radius:6px; font-weight:700; }
            #btn_disconnect:hover { background-color:#991b1b; }
            #btn_disconnect:disabled { background-color:#1e293b; color:#475569; }
            #btn_quick { background-color:#1e3a5f; color:#bfdbfe; border:1px solid #1d4ed8;
                border-radius:5px; font-size:13px; font-weight:600; padding:4px 10px; }
            #btn_quick:hover { background-color:#1d4ed8; color:#fff; }
            #btn_fav { background-color:#3b1f6e; color:#d8b4fe; border:1px solid #7c3aed;
                border-radius:5px; font-size:13px; font-weight:600; padding:4px 10px; }
            #btn_fav:hover { background-color:#7c3aed; color:#fff; }
            #btn_icon { background-color:#1e293b; color:#94a3b8; border:1px solid #334155; border-radius:5px; }
            #btn_icon:hover { background-color:#334155; }
            #btn_cmd { background-color:#1e293b; color:#cbd5e1; border:1px solid #2d3f55;
                border-radius:5px; font-size:13px; font-family:'Consolas',monospace; padding:6px; }
            #btn_cmd:hover { background-color:#1d4ed8; color:#fff; border-color:#1d4ed8; }
            #btn_send { background-color:#1d4ed8; color:#fff; border:none; border-radius:5px; font-weight:600; padding:4px 16px; }
            #btn_send:hover { background-color:#2563eb; }
            #btn_initiate { background-color:#166534; color:#f0fdf4; border:none; border-radius:6px; font-weight:700; }
            #btn_initiate:hover { background-color:#15803d; }
            #btn_back { background-color:#1e293b; color:#94a3b8; border:1px solid #334155; border-radius:6px; }
            #btn_back:hover { background-color:#334155; color:#e2e8f0; }
            #btn_lvl { background-color:#1e293b; color:#94a3b8; border:1px solid #334155;
                border-radius:6px; font-size:13px; font-weight:600; padding:6px 12px; }
            #btn_lvl:hover { background-color:#4c1d95; color:#e9d5ff; border-color:#7c3aed; }
            #btn_lvl_selected { background-color:#7c3aed; color:#fff; border:1px solid #7c3aed;
                border-radius:6px; font-size:13px; font-weight:700; padding:6px 12px; }
            #btn_add { background-color:#1e293b; color:#64748b; border:1px solid #334155;
                border-radius:5px; font-size:12px; padding:3px 10px; }
            #btn_add:hover { background-color:#166534; color:#f0fdf4; border-color:#166534; }
            #btn_del { background-color:transparent; color:#7f1d1d; border:none; border-radius:4px; }
            #btn_del:hover { background-color:#7f1d1d; color:#fef2f2; }
            #panel { background-color:#0f1117; border:1px solid #1e293b; border-radius:8px; }
            #panel_header { background-color:#141820; color:#475569; font-size:14px; font-weight:600;
                letter-spacing:1px; padding:6px 12px; border-bottom:1px solid #1e293b; border-radius:8px 8px 0 0; }
            #terminal { background-color:#080b11; color:#94a3b8; border:none; border-radius:0 0 8px 8px;
                font-family:'Consolas','Courier New',monospace; font-size:13px; padding:8px; }
            #player_table { background-color:#0d1117; color:#e2e8f0; border:none; font-size:13px;
                gridline-color:#1e293b; selection-background-color:#1d4ed8; }
            QHeaderView::section { background-color:#141820; color:#475569; border:none;
                border-bottom:1px solid #1e293b; padding:4px 8px; font-size:12px; font-weight:600; }
            #placeholder_label { color:#334155; font-size:13px; }
            #prompt { color:#00ff88; font-size:16px; font-family:'Consolas',monospace; font-weight:700; }
            #cmd_input { background-color:#080b11; color:#00ff88; border:1px solid #1e293b;
                border-radius:5px; padding:5px 10px; font-family:'Consolas',monospace; font-size:14px; }
            #cmd_input:focus { border-color:#00ff88; }
            QTabWidget#cmd_tabs::pane { border:none; background-color:#0f1117; }
            QTabWidget#cmd_tabs QTabBar::tab { background:#141820; color:#64748b; padding:7px 14px;
                margin-right:2px; border-radius:5px 5px 0 0; font-size:13px; border:1px solid #1e293b; border-bottom:none; }
            QTabWidget#cmd_tabs QTabBar::tab:selected { background:#1d4ed8; color:#f8fafc; font-weight:700; }
            QTabWidget#cmd_tabs QTabBar::tab:hover:!selected { background:#1e293b; color:#cbd5e1; }
            #cmd_scroll { background-color:#0f1117; border:none; }
            QScrollBar:vertical { background:#0f1117; width:8px; border-radius:4px; }
            QScrollBar::handle:vertical { background:#334155; border-radius:4px; min-height:20px; }
            QScrollBar::handle:vertical:hover { background:#475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#0f1117; height:8px; border-radius:4px; }
            QScrollBar::handle:horizontal { background:#334155; border-radius:4px; min-width:20px; }
            QScrollBar::handle:horizontal:hover { background:#475569; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QStatusBar { background-color:#080b11; color:#475569; font-size:14px; border-top:1px solid #1e293b; }
            QMessageBox, QInputDialog { background-color:#0f1117; color:#e2e8f0; }
            QMenu { background-color:#141820; color:#e2e8f0; border:1px solid #334155; }
            QMenu::item:selected { background-color:#1d4ed8; color:#fff; }
            QToolTip { background-color:#1e293b; color:#cbd5e1; border:1px solid #334155; font-size:13px; padding:4px 8px; }
            #desc_panel { background-color:#0d1117; border-bottom:1px solid #1e293b; }
            #desc_title { font-size:17px; font-weight:700; color:#f1f5f9; }
            #desc_body  { font-size:14px; color:#94a3b8; line-height:1.5; }
            #divider    { color:#1e293b; background-color:#1e293b; max-height:1px; }
            #vdivider   { color:#334155; background-color:#334155; max-width:1px; }
            #tab_container { background-color:#0f1117; }
            #syntax_lbl { font-family:'Consolas',monospace; font-size:13px; color:#475569; padding:2px 0; }
            #horde_progress { font-family:'Consolas',monospace; font-size:14px; color:#FFD700; font-weight:700; padding:2px 0; }
            #cmd_param_input { background-color:#0d1117; color:#e2e8f0; border:1px solid #1d4ed8;
                border-radius:5px; padding:5px 10px; font-family:'Consolas',monospace; font-size:14px; }
            #wave_frame { background-color:#141820; border:1px solid #1e293b; border-radius:6px; }
            #section_label { color:#475569; font-size:12px; font-weight:700; letter-spacing:1px; padding:4px 0; }
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
