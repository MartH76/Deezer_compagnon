#!/usr/bin/env python3
"""
Deezer Desk Gadget - compagnon Windows (verbeux)
------------------------------------------------
Pont entre Deezer (media session SMTC) et le Pico (USB CDC).

- Tourne MEME sans le Pico : mode apercu console (utile pour valider Deezer).
- Reconnexion serie automatique quand le Pico apparait/disparait.

IMPORTANT : lancer avec le Python OFFICIEL Windows (python.org / Store),
PAS celui de MSYS2 (winsdk et pycaw ne marchent pas sous mingw).

Dependances :  py -m pip install -r requirements.txt
Lancement   :  py "...\companion\deezer_companion.py"   (ou COM force en argument)
"""

import asyncio
import hashlib
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
import functools
print = functools.partial(print, flush=True)  # flush systematique (Git Bash)

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
DEBUG = False   # True = traces detaillees
ENABLE_VOLUME = True    # volume Deezer lu dans un thread dedie (evite le deadlock COM)

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
    DEBUG and print(f"[pochette-dbg] thumbnail ref = {'oui' if ref else 'NON'}")
    if ref is None:
        return None
    stream = await ref.open_read_async()
    size = stream.size
    DEBUG and print(f"[pochette-dbg] taille flux = {size}")
    if not size:
        return None
    reader = DataReader(stream)
    await reader.load_async(size)
    buf = bytearray(size)
    reader.read_bytes(buf)
    raw = bytes(buf)
    DEBUG and print(f"[pochette-dbg] octets bruts = {len(raw)} (magic {raw[:3].hex() if raw else '--'})")
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = img.resize((ART_SIZE, ART_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    data = out.getvalue()
    DEBUG and print(f"[pochette-dbg] jpeg final = {len(data)} octets")
    return data


def fetch_cover_sync():
    """Lit la pochette dans un THREAD dedie (event loop et apartment COM neufs)
    pour eviter le deadlock winsdk observe sur le thread principal."""
    async def _inner():
        mgr = await MediaManager.request_async()
        s = pick_session(mgr)
        if s is None:
            return None
        props = await s.try_get_media_properties_async()
        return await read_thumbnail(props)
    try:
        return asyncio.run(_inner())
    except Exception as e:
        DEBUG and print(f"[pochette-dbg] exception: {e!r}")
        return None


def get_volume_sync():
    """Idem pour pycaw (COM) : dans un thread dedie."""
    try:
        return get_deezer_volume()
    except Exception:
        return None


async def fetch_and_send_cover(loop):
    """Recupere la pochette (thread dedie) et l'envoie, SANS bloquer le flux d'etat."""
    try:
        art = await asyncio.wait_for(loop.run_in_executor(None, fetch_cover_sync), timeout=8.0)
    except Exception as e:
        print(f"[pochette] echec/timeout: {e}")
        return
    if art:
        if serial_write(f"ART:{len(art)}\n".encode()) and serial_write(art):
            print(f"[pochette] envoyee {len(art)} octets")


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
        print("[serie] Pico non trouve -> mode APERCU CONSOLE (je lis Deezer quand meme).")
        print("        Branche le Pico flashe et je m'y connecterai tout seul.")

    mgr = await MediaManager.request_async()
    print("[deezer] init OK, lecture de l'etat en cours...")
    loop = asyncio.get_running_loop()

    last_send = None
    last_print = None
    last_track = None
    cover_task = None
    last_art_hash = None
    vol_cache = 0
    tick = 0
    last_reco = 0.0
    last_warn = 0.0

    while True:
        tick += 1
        now = time.time()
        if DEBUG:
            print(f"[trace] LOOP start tick={tick}")

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
                last_send = last_track = last_art_hash = None
                print("[serie] HELLO recu -> renvoi complet de l'etat")
            else:
                await exec_cmd(mgr, txt)

        # volume (allege)
        if ENABLE_VOLUME and tick % VOL_EVERY == 1:
            try:
                v = await asyncio.wait_for(loop.run_in_executor(None, get_volume_sync), timeout=2.0)
                if v is not None:
                    vol_cache = v
            except Exception:
                pass

        # lecture de l'etat Deezer
        state = {"t": "", "a": "", "st": "pause", "vol": vol_cache, "pos": 0, "dur": 0}
        track_id = None
        art = None
        if DEBUG: print(f"[trace] tick={tick} avant pick_session")
        s = pick_session(mgr)
        if DEBUG: print(f"[trace] tick={tick} pick_session -> {(s.source_app_user_model_id if s else None)!r}")
        if s:
            try:
                if DEBUG: print(f"[trace] tick={tick} avant get_media_properties")
                props = await s.try_get_media_properties_async()
                if DEBUG: print(f"[trace] tick={tick} apres get_media_properties")
                state["t"] = props.title or ""
                state["a"] = props.artist or ""
                if DEBUG: print(f"[trace] tick={tick} avant playback/timeline")
                info = s.get_playback_info()
                state["st"] = "play" if info.playback_status == PlaybackStatus.PLAYING else "pause"
                tl = s.get_timeline_properties()
                state["pos"] = int(tl.position.total_seconds())
                state["dur"] = int(tl.end_time.total_seconds())
                track_id = state["t"] + "|" + state["a"]
                if track_id != last_track and state["t"]:
                    last_track = track_id
                    if cover_task is None or cover_task.done():
                        cover_task = asyncio.create_task(fetch_and_send_cover(loop))
            except Exception as e:
                if now - last_warn > 10:
                    last_warn = now
                    print(f"[deezer] lecture etat impossible : {e}")
        else:
            if now - last_warn > 10:
                last_warn = now
                print("[deezer] aucune session -> ouvre l'appli Deezer et joue un titre")

        if DEBUG:
            _a = (s.source_app_user_model_id if s else None)
            print(f"[dbg] tick={tick} session={_a!r} titre={state['t']!r} status={state['st']} vol={state['vol']}")

        # envoi vers le Pico des que l'etat change (pos inclus -> barre de progression)
        if state != last_send:
            serial_write(("ST " + json.dumps(state, ensure_ascii=False) + "\n").encode("utf-8"))
            last_send = state

        # affichage console seulement sur changement "utile" (pas chaque seconde)
        pkey = (state["t"], state["a"], state["st"], state["vol"])
        if pkey != last_print and state["t"]:
            last_print = pkey
            tag = "PLAY " if state["st"] == "play" else "PAUSE"
            print(f"[etat] {tag} | {state['t']} - {state['a']} | vol={state['vol']}%")

        await asyncio.sleep(POLL_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[compagnon] arret.")
