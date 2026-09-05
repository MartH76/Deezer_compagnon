#!/usr/bin/env python3
"""Diagnostic SMTC : liste toutes les sessions media vues par Windows.
Lance-le AVEC Deezer en train de jouer :
    python3.10 "...\companion\smtc_debug.py"
"""
import asyncio
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PS,
)

STATUS = {0: "CLOSED", 1: "OPENED", 2: "CHANGING", 3: "STOPPED", 4: "PLAYING", 5: "PAUSED"}

async def main():
    mgr = await MediaManager.request_async()
    sessions = list(mgr.get_sessions())
    print(f"Nombre de sessions media : {len(sessions)}")
    if not sessions:
        print(">>> AUCUNE session : ni l'appli Deezer ni le navigateur n'exposent SMTC.")
    for i, s in enumerate(sessions):
        aumid = s.source_app_user_model_id
        try:
            props = await s.try_get_media_properties_async()
            title, artist = props.title, props.artist
        except Exception as e:
            title, artist = f"<err {e}>", ""
        st = s.get_playback_info().playback_status
        print(f"[{i}] AUMID = {aumid!r}")
        print(f"     status = {STATUS.get(int(st), st)}  titre = {title!r}  artiste = {artist!r}")
    cur = mgr.get_current_session()
    print("Session courante :", cur.source_app_user_model_id if cur else None)

asyncio.run(main())
