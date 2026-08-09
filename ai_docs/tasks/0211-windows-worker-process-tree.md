---
title: TASK-0211 Windows worker process tree
status: in_progress
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0211 — Trwałe drzewo procesów Windows

## Goal

Supervisor zapisuje i kontroluje launcher oraz rzeczywisty interpreter lane,
nie pozostawiając osieroconych procesów i nie kończąc obcych Pythonów.

## Verification

Bounded start/status/stop/restart z nowego PowerShella i dokładnie jeden worker.

## Outcome

Supervisor używa wersji stanu 2, wykrywa potomków przez Toolhelp32 i rozróżnia
launcher od interpretera. Odczyt istniejących lane działa również dla stanu v1.
Po potwierdzeniu braku aktywnego joba wykonano dwa kontrolowane cykle. Drugi
cykl zmienił drzewo `17228 + 11288 + 11648` na `19540 + 14656`; żaden PID
poprzedniego drzewa nie pozostał aktywny. Worker image-selection działa z nowym
stanem v2. Powtórzenie testu po restarcie komputera pozostaje częścią odbioru
operatorskiego.

Nowy proces PowerShell odczytał stan 2026-08-09 i potwierdził pojedyncze drzewo
lane selekcji: launcher `19540`, interpreter `14656`. Test po fizycznym
restarcie komputera nadal wymaga obecności właściciela i pozostaje otwarty.
