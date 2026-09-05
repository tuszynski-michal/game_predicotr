---
title: Stabilize Python test cleanup
status: done
last_updated: 2026-09-02
---

# TASK-0381 — Stabilne sprzątanie testów Python na Windows

## Goal

Nie raportować zielonego zestawu pytest jako awarii z powodu przejściowego
wyścigu podczas usuwania katalogu `basetemp`.

## Scope

- maksymalnie pięć prób usunięcia zweryfikowanego katalogu w `.venv`;
- krótkie, ograniczone opóźnienie pomiędzy próbami;
- zachowanie fail-closed, jeżeli katalog nadal istnieje po ostatniej próbie.

## Outcome

Przejściowe `DirectoryNotFound` podczas rekurencyjnego sprzątania jest
ponawiane, ale trwały błąd nadal kończy wrapper niepowodzeniem. Kontrola
bezpieczeństwa nie pozwala usuwać katalogu spoza `.venv`.
