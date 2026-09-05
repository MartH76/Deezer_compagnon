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
from PIL import Image, ImageDraw
import os

try:
    import pystray
    from pystray import MenuItem as Item, Menu
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False

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
COVER_MAX_BYTES = 12000   # budget JPEG : temps d'envoi ~constant
POLL_S = 0.2
VOL_EVERY = 4
RECONNECT_S = 3.0
HEARTBEAT_S = 1.0   # reveil periodique (progression + filet de securite)
ENABLE_VOLUME = True

cmd_q = queue.Queue()
ser = None
last_port = None
paused = False        # mis en pause depuis l'icone tray
force_full = False    # forcer un renvoi complet (reprise / reconnexion)
_icon = None
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
    global ser
    while True:
        try:
            if not s.is_open:
                break
            line = s.readline()          # timeout -> b"" (pas d'exception)
        except Exception:
            break                        # port perdu (debranchement)
        if not line:
            continue
        txt = line.decode(errors="ignore").strip()
        if txt:
            cmd_q.put(txt)
    # sortie de boucle => port perdu : declenche la reconnexion cote boucle principale
    with ser_lock:
        if ser is s:
            ser = None


def try_open_serial():
    global ser, last_port
    port = find_port()
    if not port:
        return False
    try:
        s = serial.Serial(port, BAUD, timeout=0.2)
    except Exception as e:
        print(f"[serie] echec ouverture {port} : {e}")
        return False
    time.sleep(1.0)                 # laisser le CDC du Pico finir son enumeration
    try:
        s.reset_input_buffer()
        s.reset_output_buffer()
    except Exception:
        pass
    with ser_lock:
        ser = s
    threading.Thread(target=serial_reader, args=(s,), daemon=True).start()
    last_port = port
    print(f"[serie] >>> connecte sur {port}")
    return True


def serial_write(data):
    global ser
    if paused:
        return False
    with ser_lock:
        s = ser
    if s is None:
        return False
    for attempt in range(3):
        try:
            s.write(data)
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(0.2)
                continue
            print(f"[serie] <<< perdu ({e}), reconnexion...")
            with ser_lock:
                try:
                    s.close()
                except Exception:
                    pass
                if ser is s:
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
    # Encodage vers un budget d'octets : on baisse la qualite jusqu'a passer sous
    # COVER_MAX_BYTES (ecran 240 px -> la perte est invisible), pour un temps
    # d'envoi/decodage quasi constant quelle que soit la pochette.
    data = None
    for q in (72, 60, 48, 38, 30, 24):
        out = io.BytesIO()
        img.save(out, "JPEG", quality=q)
        data = out.getvalue()
        if len(data) <= COVER_MAX_BYTES:
            break
    return data


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


current_track = None


async def fetch_and_send_cover():
    """Recupere la pochette de la piste courante et l'envoie.
    Retries : la vignette SMTC arrive souvent un peu apres le titre.
    Garde-fou : on n'envoie pas si l'utilisateur a change de piste entre-temps."""
    if _cover_loop is None:
        return
    for _ in range(6):
        target = current_track
        if not target:
            return
        art = None
        try:
            fut = asyncio.run_coroutine_threadsafe(_worker_read_cover(), _cover_loop)
            art = await asyncio.wait_for(asyncio.wrap_future(fut), timeout=6.0)
        except Exception as e:
            print(f"[pochette] echec/timeout: {e}")
        if art and current_track == target:
            cover_cache[target] = art
            _cache_order.append(target)
            if len(_cache_order) > 40:
                cover_cache.pop(_cache_order.pop(0), None)
            if serial_write(f"ART:{len(art)}\n".encode()) and serial_write(art):
                print(f"[pochette] envoyee {len(art)} octets")
            return
        await asyncio.sleep(0.3)
    print("[pochette] pas de vignette (abandon apres retries)")


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


# ----------------------------------------------------------------- evenements SMTC
main_loop = None
wake_event = None
_sub_session = None
_sub_tokens = []
_mgr_handlers = []


def _wake(*_):
    """Appele depuis un thread WinRT : reveille la boucle asyncio immediatement."""
    if main_loop is not None and wake_event is not None:
        main_loop.call_soon_threadsafe(wake_event.set)


def subscribe_events(mgr):
    """(Re)abonne la session courante : changement de piste + play/pause."""
    global _sub_session, _sub_tokens
    try:
        if _sub_session is not None:
            for kind, tok in _sub_tokens:
                if kind == "mp":
                    _sub_session.remove_media_properties_changed(tok)
                elif kind == "pi":
                    _sub_session.remove_playback_info_changed(tok)
    except Exception:
        pass
    _sub_tokens = []
    sess = pick_session(mgr)
    _sub_session = sess
    if sess is not None:
        try:
            _sub_tokens.append(("mp", sess.add_media_properties_changed(_wake)))
            _sub_tokens.append(("pi", sess.add_playback_info_changed(_wake)))
        except Exception as e:
            print(f"[event] abonnement session impossible : {e}")


def subscribe_manager(mgr):
    """S'abonne aux changements de session et re-hooke la nouvelle session courante."""
    def on_sessions_changed(*_):
        _wake()
        if main_loop is not None:
            main_loop.call_soon_threadsafe(lambda: subscribe_events(mgr))
    _mgr_handlers.append(on_sessions_changed)   # garder une reference (anti-GC)
    try:
        mgr.add_current_session_changed(on_sessions_changed)
        mgr.add_sessions_changed(on_sessions_changed)
    except Exception as e:
        print(f"[event] abonnement manager impossible : {e}")


# ----------------------------------------------------------------- boucle principale
async def main():
    global main_loop, wake_event, current_track, force_full
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
    main_loop = loop
    wake_event = asyncio.Event()
    subscribe_manager(mgr)
    subscribe_events(mgr)
    print("[event] abonnements SMTC actifs")

    last_send = None
    last_print = None
    last_track = None
    vol_cache = 0
    tick = 0
    last_reco = 0.0
    last_warn = 0.0
    last_vol = 0.0
    cover_task = None

    while True:
        tick += 1
        now = time.time()

        if force_full:            # reprise apres pause / reconnexion
            force_full = False
            last_send = None
            last_track = None

        # reconnexion serie
        with ser_lock:
            connected = ser is not None
        if not connected and (now - last_reco) >= RECONNECT_S:
            last_reco = now
            if try_open_serial():
                # Pico (re)branche : forcer le renvoi complet de l'etat + pochette
                last_send = None
                last_track = None

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
        if ENABLE_VOLUME and (now - last_vol) >= 1.0:
            last_vol = now
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
                current_track = track_id
                if track_id != last_track and state["t"]:
                    last_track = track_id
                    cached = cover_cache.get(track_id)
                    if cached:
                        if serial_write(f"ART:{len(cached)}\n".encode()) and serial_write(cached):
                            print(f"[pochette] (cache) {len(cached)} octets")
                    elif cover_task is None or cover_task.done():
                        cover_task = asyncio.create_task(fetch_and_send_cover())
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

        try:
            await asyncio.wait_for(wake_event.wait(), timeout=HEARTBEAT_S)
        except asyncio.TimeoutError:
            pass
        wake_event.clear()


# ----------------------------------------------------------------- icone tray
def _make_icon(active):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (139, 92, 246, 255) if active else (110, 110, 110, 255)
    d.ellipse((3, 3, 61, 61), fill=bg)
    w = (255, 255, 255, 255)
    d.ellipse((20, 38, 34, 50), fill=w)                       # tete de note
    d.rectangle((31, 17, 35, 46), fill=w)                     # hampe
    d.polygon([(35, 17), (47, 21), (47, 30), (35, 26)], fill=w)  # drapeau
    return img


def _status_text(_item=None):
    with ser_lock:
        connected = ser is not None
    if paused:
        return "Etat : en pause"
    if connected:
        return f"Pico : connecte ({last_port})"
    return "Pico : non connecte"


def _track_text(_item=None):
    return "Deezer : " + (current_track.split("|")[0] if current_track else "-")


def _toggle_pause(icon, item):
    global paused, force_full
    paused = not paused
    if not paused:
        force_full = True     # forcer le renvoi complet a la reprise
    icon.update_menu()


def _quit(icon, item):
    icon.stop()
    os._exit(0)


def _tray_updater():
    prev = None
    while True:
        with ser_lock:
            connected = ser is not None
        active = connected and not paused
        if active != prev:
            prev = active
            try:
                _icon.icon = _make_icon(active)
                _icon.title = "Deezer companion - " + ("actif" if active else ("en pause" if paused else "en attente"))
            except Exception:
                pass
        try:
            _icon.update_menu()
        except Exception:
            pass
        time.sleep(1.5)


def _run_asyncio():
    try:
        asyncio.run(main())
    except Exception:
        pass


if __name__ == "__main__":
    if HAS_TRAY:
        menu = Menu(
            Item("Deezer companion", None, enabled=False),
            Item(_status_text, None, enabled=False),
            Item(_track_text, None, enabled=False),
            Menu.SEPARATOR,
            Item("En pause", _toggle_pause, checked=lambda i: paused),
            Item("Quitter", _quit),
        )
        _icon = pystray.Icon("deezer_companion", _make_icon(False), "Deezer companion", menu)
        threading.Thread(target=_run_asyncio, daemon=True).start()
        threading.Thread(target=_tray_updater, daemon=True).start()
        _icon.run()          # bloquant sur le thread principal
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n[compagnon] arret.")
