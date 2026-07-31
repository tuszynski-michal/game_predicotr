---
title: Current project state
status: active
last_updated: 2026-07-31
---

# Current State

## Phase

`TASK-0120 complete — clean PostgreSQL baseline ready for version 0.2`

## Aktywne tory wydań

### Wersja 0.1

- TASK-0118 jest ukończony,
- lokalna paczka `0.1.5 (6)` zawiera jedną grę i 500 000 layoutów,
- APK ma SHA-256
  `d94061734d1e141ee9e68bf0e532eeb0ac1d485b68796f853c0dc3589326c522`,
- snapshot ma SHA-256
  `ddbfa90e673811efe2acad8e8049acc2435389bbbcaf256715573a744ef66de8`,
- TASK-0119 — instalacja, testy offline i odbiór Pixela — pozostaje otwarty,
- błędy znalezione w odbiorze 0.1 będą naprawiane równolegle z pracą nad 0.2.

### Wersja 0.2

- rozwój może rozpocząć się przed zakończeniem TASK-0119,
- TASK-0120 zakończył kontrolowany reset lokalnego PostgreSQL,
- Admin i workflow powstają od czystej bazy,
- testy używają jednej gry i małego kontrolowanego datasetu,
- pełne 500 000 rzeczywistych layoutów i nowe gry nie należą do 0.2,
- zakres zadań 0.2 to TASK-0120–0134.

### Wersja 0.3

- startuje dopiero po odbiorze 0.1 i 0.2 oraz wymaganych poprawkach,
- obejmuje pełne dane, nowe gry, wielogrowe wydanie, pełną skalę i hardening,
- TASK-0076 oraz TASK-0080–0089 są przypisane do 0.3.

## Dane i artefakty

### Chronione

- `artifacts/v01-representative-release/` — kompletna paczka odbiorowa 0.1,
- `artifacts/v01-ready-for-pixel/Game-Predictor-0.1.5-v6-Pixel.apk` — prosta
  kopia APK gotowa do instalacji na Pixelu,
- `artifacts/v02-clean-baseline/pre-reset/` — pełny dump i inwentarz danych
  istniejących bezpośrednio przed resetem 0.2,
- `.tooling/android-signing/` — prywatny klucz i konfiguracja podpisu,
- zdjęcia źródłowe i ręczne materiały wejściowe poza PostgreSQL,
- dokumentacja decyzji, migracje, kod i raporty jakości.

### Robocze

- PostgreSQL ma 32 tabele na migracji `0021_reviewer_access` i 0 rekordów we
  wszystkich tabelach domenowych,
- nie istnieją aktywne joby, sesje Reviewera, gry, datasety ani wydania,
- dane poprzedniej iteracji są dostępne wyłącznie w kontrolowanym dumpie
  pre-reset; nie należy go automatycznie importować do workflow 0.2,
- `apps/mobile/assets/snapshot/m1-snapshot.db` jest małym fixture’em
  deweloperskim; pozostaje do świadomego zastąpienia fixture’em 0.2.

## Ukończony fundament

- aplikacja mobilna działa całkowicie offline i używa SQLite w APK,
- matching rozróżnia unique, duplicate i not found,
- payout-v2 ocenia prefiks od pierwszej kolumny i precomputed payout,
- Target przechodzi pełny cykl i pokazuje dodatnie lokalne maksima,
- lokalny Admin, FastAPI, PostgreSQL i wersjonowanie domenowe działają,
- import ręczny, snapshot/release pipeline i kontrolowane joby działają,
- pipeline zdjęć, geometria, OCR adapter, klasyfikacja i manual review mają
  działające piony oraz raporty jakości,
- osobny Reviewer działa lokalnie i przez ograniczony link z kodem,
- lokalny Admin API jest chroniony przez loopback/origin/intencję i audyt.

Szczegółowe wyniki historyczne znajdują się w `tasks/completed/`,
`process/DECISION_LOG.md` i raportach `quality/`; nie są powtarzane tutaj.

## Otwarte pytania

- Q-020 — dozwolony zakres analizy aplikacji referencyjnej,
- Q-022–Q-032 — UX usuwania, retencja, foldery i własność danych Admina 0.2,
- finalny model OCR i nazwa sekcji `Result`/`Target` nie blokują najbliższego
  pionu nawigacji Admina.

Q-022–Q-032 należy rozstrzygnąć przed zadaniami, których semantykę zmieniają.
Nie wszystkie są wymagane do rozpoczęcia samego szkieletu nawigacji TASK-0121.

## Blocked / deferred

- TASK-0076 pozostaje zablokowany przez `massImportAllowed = false` i należy do
  0.3,
- TASK-0080–0089 należą do pełnego hardeningu 0.3,
- masowy import, nowe gry i pełne benchmarki danych nie mogą wejść do bramki 0.2.

## Next recommended task

Po odpowiedziach właściciela na pytania 0.2 utworzyć i wykonać
`TASK-0121 — Admin workspace navigation and collapsible sections`. Zadanie ma
zbudować prostą nawigację i zachowanie kontekstu bez ponownego wprowadzania
danych usuniętych w TASK-0120.

## Do not start yet

- pełnego importu około 500 000 rzeczywistych layoutów,
- dodawania i testowania kolejnych gier,
- wielogrowego wydania mobilnego,
- pełnej macierzy urządzeń i hardeningu przypisanego do 0.3,
- Celery/Redis, mikroserwisów, chmury, Google Play lub publicznego Admin API.
