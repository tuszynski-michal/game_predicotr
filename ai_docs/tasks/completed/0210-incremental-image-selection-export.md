---
title: TASK-0210 incremental image-selection export
status: done
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0210 — Przyrostowy eksporter

## Goal

Zastąpić pełne pobieranie grup kursorem, zachowując atomowy zapis, checksumy,
kolizje i nazwy `seq_<start>-<end>.jpg`.

## Verification

Pełne uzgodnienie po resume, potem tylko nowe/zmienione grupy; identyczne bajty.

## Outcome

Skrypt live zapisuje schemat raportu v2 i trwały `exportCursor`. Panel Admin
pobiera po pierwszym uzgodnieniu wyłącznie grupy za `afterGroupOrder`; ręczna
rewizja wcześniejszej luki jest zapisywana bezpośrednio przez callback decyzji.
Testy kursora i idempotentnego zapisu przechodzą. Pomiar zapytań na realnym runie
pozostaje bramką wydajnościową TASK-0218 i nie blokuje ukończenia kontraktu
eksportera. Skupiona regresja workera/API przeszła 149/149, a Admin 179/179;
test panelu potwierdza pobieranie wyłącznie grup po `afterGroupOrder` oraz
natychmiastowy, idempotentny zapis ukończonej grupy.
