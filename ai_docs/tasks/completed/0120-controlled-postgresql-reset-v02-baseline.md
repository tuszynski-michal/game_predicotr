---
title: TASK-0120 Controlled PostgreSQL reset and v0.2 clean baseline
status: done
last_updated: 2026-07-31
---

# TASK-0120 — Controlled PostgreSQL reset and v0.2 clean baseline

## Status

`done`

## Goal

Zabezpieczyć nieodtwarzalne dane wydania `0.1`, a następnie wyczyścić wyłącznie
lokalny PostgreSQL i przygotować pusty, zmigrowany baseline dla wersji `0.2`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- zweryfikowanie i skopiowanie APK `0.1.5 (6)` do prostej lokalizacji gotowej
  do instalacji na Pixelu,
- zachowanie pełnej paczki `artifacts/v01-representative-release/`,
- wykonanie pełnego dumpu PostgreSQL sprzed resetu,
- zapis inwentarza tabel i liczników przed resetem,
- reset dokładnej lokalnej bazy `game_predictor` przez Alembic downgrade/upgrade,
- potwierdzenie pustych tabel domenowych i `alembic head`,
- zapis raportu resetu i aktualizacja aktywnej dokumentacji.

## Protected data

- `artifacts/v01-representative-release/`,
- nowa kopia `artifacts/v01-ready-for-pixel/`,
- `.tooling/android-signing/`,
- `apps/mobile/assets/snapshot/m1-snapshot.db`,
- zdjęcia, cropy i materiały źródłowe poza PostgreSQL,
- kod, migracje, dokumentacja, completed tasks i raporty jakości.

## Destructive target

Wyłącznie baza PostgreSQL `game_predictor` dostępna przez loopback
`127.0.0.1:5432`, obsługiwana przez usługę `postgres` w
`infra/docker/compose.yaml`. Nie usuwamy wolumenu Dockera, innych baz ani
plików repozytorium.

## Acceptance criteria

- [x] gotowy do instalacji APK ma checksumę zgodną z wydaniem `0.1`,
- [x] pełna paczka `0.1` i snapshot 500k pozostają niezmienione,
- [x] dump sprzed resetu istnieje i ma niezerowy rozmiar,
- [x] raport pre-reset zawiera listę tabel i liczników,
- [x] reset dotknął wyłącznie dokładnej lokalnej bazy `game_predictor`,
- [x] Alembic wskazuje aktualny `head`,
- [x] wszystkie tabele domenowe są puste,
- [x] brak aktywnych jobów, sesji Reviewera i wydań w PostgreSQL,
- [x] raport końcowy wymienia dane usunięte oraz chronione.

## Verification

```powershell
Get-FileHash -Algorithm SHA256 artifacts\v01-ready-for-pixel\Game-Predictor-0.1.5-v6-Pixel.apk
npm run db:current
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_postgres_baseline.ps1
```

## Outcome

- APK `0.1.5 (6)` skopiowano do
  `artifacts/v01-ready-for-pixel/Game-Predictor-0.1.5-v6-Pixel.apk`. Kopia i
  oryginał mają identyczny SHA-256
  `D94061734D1E141EE9E68BF0E532EEB0AC1D485B68796F853C0DC3589326C522`.
- Snapshot wydania 0.1 pozostał niezmieniony: 40 972 288 bajtów, SHA-256
  `DDBFA90E673811EFE2ACAD8E8049ACC2435389BBBCAF256715573A744EF66DE8`.
- Przed resetem zapisano inwentarz 32 tabel, 23 niepustych tabel i 10 126
  rekordów oraz pełny dump w formacie custom PostgreSQL. Dump ma 1 120 055
  bajtów, 234 wpisy TOC i SHA-256
  `FAE0A23C2FC1995282341C60B44E58EB4248653EFD559D4BEC286A5BA0610C1D`.
- Skrypt `scripts/reset_local_admin_database.ps1 -ConfirmReset` wykonał pełny
  cykl Alembic `downgrade base` → `upgrade head` wyłącznie dla bazy
  `game_predictor` na loopback. Wolumen Dockera i pliki repozytorium nie były
  usuwane.
- Po resecie istnieją 32 tabele, `alembic_version` wskazuje
  `0021_reviewer_access`, a 31 tabel domenowych zawiera łącznie 0 rekordów.
- Bezpośrednia kontrola potwierdziła 0 aktywnych jobów, sesji Reviewera i
  wydań mobilnych. Szczegóły zapisano w
  `artifacts/v02-clean-baseline/reset-report.json`.
- Kontrola sum plików i `npm run db:current` przeszły. Zestaw integracyjny
  PostgreSQL zakończył się wynikiem 9 passed, 3 failed, 2 errors. Niepowodzenia
  nie dotyczą resetu: dwa testy oczekują starszego schematu/revizji, jeden
  ujawnia istniejącą rozbieżność DTO diagnostyki, a dwa setupy blokują
  uprawnienia globalnego katalogu tymczasowego Pytest na Windows. Rozbieżności
  należy obsłużyć w osobnym zadaniu utrzymaniowym; właściwa baza po testach
  nadal ma 0 rekordów domenowych.
