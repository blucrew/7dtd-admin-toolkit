"""
7DTD Horde Test
  python horde_test.py 1  — Level 1: 8 zombie waves, 30s gaps
  python horde_test.py 2  — Level 2: + dogs & birds breaks, 25s gaps
  python horde_test.py 3  — Level 3: + ferals, screamer & demo breaks, 20s gaps

Setup:
  Copy .env.example to .env and fill in your server details.
  pip install -r requirements.txt
"""
import socket, time, sys, os
from dotenv import load_dotenv

load_dotenv()

HOST  = os.getenv('TDTD_HOST', '127.0.0.1')
PORT  = int(os.getenv('TDTD_PORT', '8081'))
PASS  = os.getenv('TDTD_PASS', '')

LEVEL = int(sys.argv[1]) if len(sys.argv) > 1 else 1

# ── Spawn radius ──────────────────────────────────────────────
D, D14 = 35, 25          # cardinal / diagonal distance (blocks)

# ── Base coordinates — update to your base location ──────────
bx, by, bz = -189, 70, 879

# ── Cooldowns (scale down per level) ─────────────────────────
WAVE_GAP   = 30 - (LEVEL - 1) * 5   # L1=30  L2=25  L3=20
BREAK_LEAD = 10 - (LEVEL - 1) * 2   # L2=10  L3=8
BREAK_TAIL = 10 - (LEVEL - 1) * 2   # L2=10  L3=8

# ── Zombie types per level ────────────────────────────────────
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

import itertools
normal_cycle = itertools.cycle(NORMAL[LEVEL])
mean_cycle   = itertools.cycle(MEAN[LEVEL])

waves = [
    ('NORTH',     bx,     by, bz+D  ),
    ('NORTHWEST', bx-D14, by, bz+D14),
    ('WEST',      bx-D,   by, bz    ),
    ('SOUTHWEST', bx-D14, by, bz-D14),
    ('SOUTH',     bx,     by, bz-D  ),
    ('SOUTHEAST', bx+D14, by, bz-D14),
    ('EAST',      bx+D,   by, bz    ),
    ('NORTHEAST', bx+D14, by, bz+D14),
]

# ── Telnet helper ─────────────────────────────────────────────
def send_cmd(cmd):
    s = socket.socket()
    s.connect((HOST, PORT))
    s.settimeout(3)
    time.sleep(0.8)
    s.recv(4096)
    s.sendall((PASS + '\r\n').encode())
    time.sleep(0.8)
    s.recv(4096)
    s.sendall((cmd + '\r\n').encode())
    time.sleep(1)
    try: s.recv(4096)
    except: pass
    s.close()

def say(msg):
    send_cmd('say "[HORDE] ' + msg + '"')

def coord(x, y, z):
    return str(x) + ' ' + str(y) + ' ' + str(z)

# ── Break spawns ──────────────────────────────────────────────
def spawn_dog_bird_break():
    say('DOGS AND BIRDS! Watch the skies!')
    send_cmd('sea animalZombieDog '     + coord(bx,   by,    bz+D)  + ' 2')
    send_cmd('sea animalZombieDog '     + coord(bx-D, by,    bz)    + ' 2')
    send_cmd('sea animalZombieDog '     + coord(bx,   by,    bz-D)  + ' 2')
    send_cmd('sea animalZombieDog '     + coord(bx+D, by,    bz)    + ' 2')
    send_cmd('sea animalZombieVulture ' + coord(bx,   by+20, bz)    + ' 5')
    print('  >> DOGS + BIRDS break!')

def spawn_feral_break():
    say('SCREAMER! DEMOLISHER! RUN!!')
    send_cmd('sea zombieScreamer '   + coord(bx,     by, bz+D)   + ' 2')
    send_cmd('sea zombieScreamer '   + coord(bx,     by, bz-D)   + ' 2')
    send_cmd('sea zombieDemolition ' + coord(bx-D14, by, bz+D14) + ' 1')
    send_cmd('sea zombieDemolition ' + coord(bx+D14, by, bz-D14) + ' 1')
    send_cmd('sea zombieBoeFeral '   + coord(bx-D,   by, bz)     + ' 3')
    send_cmd('sea zombieBoeFeral '   + coord(bx+D,   by, bz)     + ' 3')
    print('  >> FERALS + SCREAMER + DEMO break!')

# ── Run ───────────────────────────────────────────────────────
print('=' * 40)
print('  HORDE TEST — LEVEL ' + str(LEVEL))
print('  Server: ' + HOST + ':' + str(PORT))
print('  Wave gap: ' + str(WAVE_GAP) + 's')
print('=' * 40)
say('HORDE INCOMING — LEVEL ' + str(LEVEL) + '! Good luck!')

for i, (direction, x, y, z) in enumerate(waves):
    normal = next(normal_cycle)
    mean   = next(mean_cycle)
    say('Wave ' + str(i+1) + '/8 from the ' + direction + '!')
    send_cmd('sea ' + normal + ' ' + coord(x, y, z) + ' 3')
    send_cmd('sea ' + mean   + ' ' + coord(x, y, z) + ' 1')
    print('Wave ' + str(i+1) + '/8: ' + direction + '  (' + normal + ' / ' + mean + ')')

    if i < len(waves) - 1:
        if LEVEL >= 2 and (i + 1) % 2 == 0:
            time.sleep(BREAK_LEAD)
            spawn_dog_bird_break()
            if LEVEL >= 3:
                time.sleep(4)
                spawn_feral_break()
            time.sleep(BREAK_TAIL)
        else:
            time.sleep(WAVE_GAP)

say('All waves done! You survived... for now.')
print('Done.')
