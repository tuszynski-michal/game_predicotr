---
title: TASK-0119 Pixel 10 Pro XL release acceptance
status: in_progress
last_updated: 2026-07-31
---

# TASK-0119 — Pixel 10 Pro XL release acceptance

## Status

`in_progress`

## Goal

Zainstalować zachowane wydanie `0.1.5 (6)` na Google Pixel 10 Pro XL i zamknąć
bramkę wersji `0.1` po ręcznym potwierdzeniu podstawowych scenariuszy offline.

## Relevant docs

- `ai_docs/delivery/VERSION_0_1_RELEASE_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/quality/M1_DEVICE_ACCEPTANCE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- instalacja aktualizacyjna zachowanego, statycznie zweryfikowanego APK,
- potwierdzenie wersji pakietu i zachowania `firstInstallTime`,
- uruchomienie aplikacji bez Metro,
- ręczny test offline: duplicate, unique/Target, not found, Undo/Reset,
- kontrola płynności tabeli i ponownego uruchomienia aplikacji.

## Acceptance criteria

- [x] podłączono dokładnie jeden Google Pixel 10 Pro XL ze statusem `device`,
- [x] suma APK odpowiada zamrożonemu wydaniu 0.1,
- [x] aktualizacja `0.1.4 (5)` → `0.1.5 (6)` zakończyła się powodzeniem,
- [x] aktualizacja zachowała pierwotny `firstInstallTime`,
- [x] aplikacja została uruchomiona po instalacji,
- [ ] właściciel potwierdził start i restart całkowicie offline,
- [ ] właściciel potwierdził scenariusz wspólnej podpowiedzi duplikatu,
- [ ] właściciel potwierdził unique `#99` i pełny Target 499 999 spinów,
- [ ] właściciel potwierdził not found oraz Undo/Reset,
- [ ] właściciel potwierdził płynne przewijanie tabeli do końca,
- [ ] brak błędu blokującego podstawowy przepływ.

## Outcome

2026-07-31 zainstalowano przez `adb install -r` APK
`Game-Predictor-0.1.5-v6-Pixel.apk` na urządzeniu `Pixel 10 Pro XL`
(`59041FDCQ005E1`). Android raportuje `versionName=0.1.5` i `versionCode=6`.
Pierwotny `firstInstallTime=2026-07-31 08:44:07` został zachowany, a aktywność
`com.gamepredictor.mobile/.MainActivity` uruchomiła się poprawnie. Raport
instalacji znajduje się w
`artifacts/v01-ready-for-pixel/pixel-install-20260731.json`. Ręczny odbiór
funkcjonalny pozostaje do wykonania przez właściciela.

Właściciel wykonał następnie test wstępny i potwierdził, że aplikacja uruchamia
się, działa oraz wykonuje obliczenia. Szczegółowa kontrola poprawności wyników i
pozostałe scenariusze akceptacyjne są świadomie odłożone; potencjalne zmiany
mobile zostaną przypisane do wersji `0.2` albo `0.3` po zgłoszeniu wyników.
