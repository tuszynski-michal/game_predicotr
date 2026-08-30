---
title: TASK-0340 Finalize manual selection repair
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0340 — Integracja sekcji i dane treningowe

## Goal

Udostępnić cały lokalny workflow w Adminie, zachować jedno aktywne źródło
wyborów i połączyć wiarygodny repair trace z kohortą rankera zdjęć.

## Scope

- karta `Popraw selekcję` bezpośrednio pod lokalnym selektorem;
- kierowanie naprawionego katalogu z normalnego resume do nowej sekcji;
- aktywny output manifest jako jedyne źródło pozytywów;
- opcjonalne scalenie widocznych fill events z pierwotnym trace;
- wymagania, architektura, Current State, Decision Log i instrukcja operatora.

## Out of scope

- API, PostgreSQL, worker job i zdalna korekta przez link;
- przechowywanie binariów undo poza bieżącą kartą.

## Outcome

- Karta `Popraw selekcję` jest montowana bezpośrednio pod lokalnym selektorem,
  a istniejący repair manifest przekierowuje start i resume do jednego writera.
- Tryby fill i delete mogą bezpiecznie wrócić do wyboru trybu bez zmiany
  wybranych katalogów; aktywny zapis nadal blokuje przełączenie.
- Ranker opcjonalnie scala wiarygodne zdarzenia repair `viewed`/`fill` z
  pierwotnym trace. Aktywny output manifest pozostaje jedynym źródłem
  pozytywów, więc delete/restore/undo nie dodają usuniętej próbki do kohorty.
- Dokumentacja wymagań, architektury, Current State i D-276 opisuje ten sam
  operator-local, checksummowany model bez API i migracji PostgreSQL.
