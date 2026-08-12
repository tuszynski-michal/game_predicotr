---
title: TASK-0213 full verification cache
status: done
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0213 — Cache pełnej weryfikacji

## Goal

Rekonstruowalny cache geometrii/OCR po checksumie, fingerprintcie, liczbie
plansz i trybie dowodu przyspiesza retry bez zmiany wyniku.

## Verification

Cold/warm parity, uszkodzony wpis daje miss, zmiana fingerprintu izoluje cache.

## Outcome

Dodano atomowy cache rozdzielający ocenę reprezentanta i dowód zakresu według
checksumy, fingerprintu, wersji adaptera i oczekiwanej liczby plansz. Testy
cold/warm, uszkodzonego wpisu i izolacji fingerprintu przechodzą w skupionej
regresji 149/149. Realny pomiar zysku warm rerun pozostaje bramką
wydajnościową TASK-0218; nie wpływa na poprawność ani aktywację cache.
