#!/usr/bin/env python3
"""
Deezer Desk Gadget - compagnon Windows
--------------------------------------
Pont entre Deezer (media session SMTC) et le Pico (USB CDC).

- Lit titre / artiste / etat / position via SMTC, et le volume via pycaw.
- Recupere la pochette via un WORKER SMTC persistant (session WinRT gardee
  ouverte) + un cache par titre : changement de piste quasi instantane.
- Tourne meme sans le Pico (mode apercu console), reconnexion serie auto.

IMPORTANT : lancer avec le Python OFFICIEL Windows (python.org / Store),
PAS celui de MSYS2 (winsdk et pycaw n'y fonctionnent pas).

Dependances :  py -m pip install -r requirements.txt
Lancement   :  py "...\companion\deezer_companion.py"   (ou COM force en argument)
"""

import asyncio
import io
import json
import queue
import sys
import threading
import time

import serial
import serial.tools.list_ports
from PIL import Image

from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winsdk.windows.storage.streams import DataReader

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

# Sortie non bufferisee (sinon les prints restent coinces sous Git Bash)
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

DEEZER_PROC = "deezer.exe"
ACCEPTED_VIDS = (0x2E8A, 0x303A)   # 0x2E8A = Raspberry Pi (Pico), 0x303A = Espressif
BAUD = 921600
ART_SIZE = 240
POLL_S = 0.2
VOL_EVERY = 4
RECONNECT_S = 3.0
ENABLE_VOLUME = True

cmd_q = queue.Queue()
ser = None
ser_lock = threading.Lock()


# ----------------------------------------------------------------- serie
def list_ports_str():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return "   (aucun port serie detecte)"
    out = []
    for p in ports:
        vid = f"{p.vid:#06x}" if p.vid is not None else "----"
        pid = f"{p.pid:#06x}" if p.pid is not None else "----"
        mark = "  <-- Pico" if (p.vid in ACCEPTED_VIDS) else ""
        out.append(f"   {p.device}  VID:PID={vid}:{pid}  {p.description}{mark}")
    return "\n".join(out)


def find_port():
    forced = sys.argv[1] if len(sys.argv) > 1 else None
    if forced:
        return forced
    for p in serial.tools.list_ports.comports():
        if p.vid in ACCEPTED_VIDS:
            return p.device
    return None


def serial_reader(s):
    while True:
        try:
            if not s.is_open:
                break
            line = s.readline()
        except Exception:
            break
        if not line:
            continue
        txt = line.decode(errors="ignore").strip()
        if txt:
            cmd_q.put(txt)


def try_open_serial():
    global ser
    port = find_port()
    if not port:
        return False
    try:
        s = serial.Serial(port, BAUD, timeout=0.2)
    except Exception as e:
        print(f"[serie] echec ouverture {port} : {e}")
        return False
    with ser_lock:
        ser = s
    threading.Thread(target=serial_reader, args=(s,), daemon=True).start()
    print(f"[serie] >>> connecte sur {port}")
    return True


def serial_write(data):
    global ser
    with ser_lock:
        s = ser
    if s is None:
        return False
    try:
        s.write(data)
        return True
    except Exception as e:
        print(f"[serie] <<< perdu ({e}), reconnexion...")
        with ser_lock:
            try:
                s.close()
            except Exception:
                pass
            ser = None
        return False


# ----------------------------------------------------------------- volume Deezer
def _deezer_session():
    for s in AudioUtilities.GetAllSessions():
        if s.Process and "deezer" in s.Process.name().lower():
            return s._ctl.QueryInterface(ISimpleAudioVolume)
    return None


def get_deezer_volume():
    v = _deezer_session()
    return int(round(v.GetMasterVolume() * 100)) if v else None


def set_deezer_volume(pct):
    pct = max(0, min(100, pct))
    v = _deezer_session()
    if v:
        v.SetMasterVolume(pct / 100.0, None)
        return True
    return False


def get_volume_sync():
    """Lecture du volume dans un thread dedie (evite le deadlock COM)."""
    try:
        return get_deezer_volume()
    except Exception:
        return None


# ----------------------------------------------------------------- SMTC
def pick_session(mgr):
    for s in mgr.get_sessions():
        try:
            if "deezer" in (s.source_app_user_model_id or "").lower():
                return s
        except Exception:
            pass
    return mgr.get_current_session()


async def read_thumbnail(props):
    ref = props.thumbnail
    if ref is None:
        return None
    stream = await ref.open_read_async()
    size = stream.size
    if not size:
        return None
    reader = DataReader(stream)
    await reader.load_async(size)
    buf = bytearray(size)
    reader.read_bytes(buf)             # winsdk : read_bytes remplit le buffer
    raw = bytes(buf)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = img.resize((ART_SIZE, ART_SIZE), getattr(Image, "Resampling", Image).LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


# ----------------------------------------------------------------- worker pochettes
_cover_loop = None
_cover_mgr = None
cover_cache = {}
_cache_order = []


def _cover_thread_main():
    global _cover_loop, _cover_mgr
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _cover_mgr = loop.run_until_complete(MediaManager.request_async())
    _cover_loop = loop
    loop.run_forever()


def start_cover_worker():
    """Demarre le thread dedie aux pochettes (session WinRT persistante)."""
    threading.Thread(target=_cover_thread_main, daemon=True).start()
    for _ in range(60):
        if _cover_loop is not None and _cover_mgr is not None:
            print("[pochette] worker SMTC pret")
            return True
        time.sleep(0.05)
    print("[pochette] worker SMTC non pret (on continue quand meme)")
    return False


async def _worker_read_cover():
    s = pick_session(_cover_mgr)
    if s is None:
        return None
    props = await s.try_get_media_properties_async()
    return await read_thumbnail(props)


async def fetch_and_send_cover(track_id):
    """Recupere la pochette via le worker persistant, met en cache et envoie."""
    if _cover_loop is None:
        return
    try:
        fut = asyncio.run_coroutine_threadsafe(_worker_read_cover(), _cover_loop)
        art = await asyncio.wait_for(asyncio.wrap_future(fut), timeout=8.0)
    except Exception as e:
        print(f"[pochette] echec/timeout: {e}")
        return
    if not art:
        return
    cover_cache[track_id] = art
    _cache_order.append(track_id)
    if len(_cache_order) > 40:
        cover_cache.pop(_cache_order.pop(0), None)
    if serial_write(f"ART:{len(art)}\n".encode()) and serial_write(art):
        print(f"[pochette] envoyee {len(art)} octets")


# ----------------------------------------------------------------- commandes
async def exec_cmd(mgr, txt):
    s = pick_session(mgr)
    if s is None and not txt.startswith("CMD:VOL="):
        return
    print(f"[cmd] {txt}")
    if txt == "CMD:TOGGLE":
        await s.try_toggle_play_pause_async()
    elif txt == "CMD:NEXT":
        await s.try_skip_next_async()
    elif txt == "CMD:PREV":
        await s.try_skip_previous_async()
    elif txt == "CMD:PLAY":
        await s.try_play_async()
    elif txt == "CMD:PAUSE":
        await s.try_pause_async()
    elif txt.startswith("CMD:VOL="):
        try:
            set_deezer_volume(int(txt.split("=", 1)[1]))
        except ValueError:
            pass


# ----------------------------------------------------------------- boucle principale
async def main():
    print("======== Deezer companion ========")
    print("Ports serie detectes :")
    print(list_ports_str())
    if not try_open_serial():
        print("[serie] Pico non trouve -> mode APERCU CONSOLE (Deezer lu quand meme).")
        print("        Branche le Pico flashe : connexion automatique.")

    mgr = await MediaManager.request_async()
    print("[deezer] init OK, lecture de l'etat en cours...")
    loop = asyncio.get_running_loop()
    start_cover_worker()

    last_send = None
    last_print = None
    last_track = None
    vol_cache = 0
    tick = 0
    last_reco = 0.0
    last_warn = 0.0

    while True:
        tick += 1
        now = time.time()

        # reconnexion serie
        with ser_lock:
            connected = ser is not None
        if not connected and (now - last_reco) >= RECONNECT_S:
            last_reco = now
            try_open_serial()

        # commandes venant du Pico
        while not cmd_q.empty():
            txt = cmd_q.get()
            if txt == "HELLO":
                last_send = None
                last_track = None
                print("[serie] HELLO recu -> renvoi complet de l'etat")
            else:
                await exec_cmd(mgr, txt)

        # volume (allege, dans un thread dedie)
        if ENABLE_VOLUME and tick % VOL_EVERY == 1:
            try:
                v = await asyncio.wait_for(loop.run_in_executor(None, get_volume_sync), timeout=2.0)
                if v is not None:
                    vol_cache = v
            except Exception:
                pass

        # lecture de l'etat Deezer
        state = {"t": "", "a": "", "st": "pause", "vol": vol_cache, "pos": 0, "dur": 0}
        s = pick_session(mgr)
        if s:
            try:
                props = await s.try_get_media_properties_async()
                state["t"] = props.title or ""
                state["a"] = props.artist or ""
                info = s.get_playback_info()
                state["st"] = "play" if info.playback_status == PlaybackStatus.PLAYING else "pause"
                tl = s.get_timeline_properties()
                state["pos"] = int(tl.position.total_seconds())
                state["dur"] = int(tl.end_time.total_seconds())
                track_id = state["t"] + "|" + state["a"]
                if track_id != last_track and state["t"]:
                    last_track = track_id
                    cached = cover_cache.get(track_id)
                    if cached:
                        if serial_write(f"ART:{len(cached)}\n".encode()) and serial_write(cached):
                            print(f"[pochette] (cache) {len(cached)} octets")
                    else:
                        asyncio.create_task(fetch_and_send_cover(track_id))
            except Exception as e:
                if now - last_warn > 10:
                    last_warn = now
                    print(f"[deezer] lecture etat impossible : {e}")
        else:
            if now - last_warn > 10:
                last_warn = now
                print("[deezer] aucune session -> ouvre l'appli Deezer et joue un titre")

        # envoi de l'etat des qu'il change (pos inclus -> barre de progression)
        if state != last_send:
            serial_write(("ST " + json.dumps(state, ensure_ascii=False) + "\n").encode("utf-8"))
            last_send = state

        # affichage console sur changement "utile" (pas chaque seconde)
        pkey = (state["t"], state["a"], state["st"], state["vol"])
        if pkey != last_print and state["t"]:
            last_print = pkey
            tag = "PLAY " if state["st"] == "play" else "PAUSE"
            print(f"[etat] {tag}| {state['t']} - {state['a']} | vol={state['vol']}%")

        await asyncio.sleep(POLL_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[compagnon] arret.")
