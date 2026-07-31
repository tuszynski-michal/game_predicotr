---
title: TASK-0133 Safe cleanup controls for v0.2 working data
status: done
last_updated: 2026-08-01
---

# TASK-0133 — Safe cleanup controls for v0.2 working data

## Status

`done`

## Goal

Dodać kontrolowane, nieodwracalne operacje usunięcia pojedynczego wydania
Android oraz przywrócenia wskazanej gry do stanu sprzed importu layoutów, bez
usunięcia rekordu gry i bez naruszenia danych innej gry.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md` — D-103, D-112
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- udostępnić read-only preview zależności i zarządzanych artefaktów przed
  usunięciem wydania albo resetem danych gry,
- związać wykonanie z aktualnym preview tokenem i dokładnym identyfikatorem celu,
- objąć oba wykonania ochroną operacji wysokiego wpływu oraz append-only audytem,
- usunąć rekord wydania, jego powiązanie z grą oraz dedykowane artefakty,
- reset gry ma zachować `games`, lecz usunąć dane importów, symboli, reguł,
  review, datasetów, payoutów, wydań i powiązane artefakty,
- nie usuwać źródłowego folderu użytkownika ani blobu współdzielonego przez inną
  grę,
- pokazać preview i mocne potwierdzenie w odpowiednim miejscu Admina,
- zachować idempotentne zachowanie i stabilne błędy dla nieaktualnego preview,
  aktywnego workflow, złego potwierdzenia oraz błędu pliku.

## Expected files

- nowy pion cleanup w domenie, application, storage, schemas i API,
- ochrona high-impact i wygenerowany klient TypeScript,
- kontrolki Admina w workspace gry oraz historii wydań,
- testy domeny/API/UI i dokumentacja kontraktu.

## Acceptance criteria

- [x] preview nie mutuje danych i podaje dokładny cel, liczniki oraz artefakty,
- [x] wykonanie wymaga zgodnego tokenu, identyfikatora i dodatkowego potwierdzenia,
- [x] usunięcie wydania nie pozostawia rekordu ani dedykowanych artefaktów,
- [x] reset zachowuje grę, usuwa cały game-scoped workflow i nie narusza innej gry,
- [x] aktywne joby/sesje albo zmieniony stan blokują operację stabilnym konfliktem,
- [x] częściowy błąd pliku nie powoduje częściowego usunięcia bazy i pozwala retry,
- [x] UI obsługuje loading, preview, błąd, potwierdzenie i wynik bez podwójnego submitu,
- [x] OpenAPI, klient, testy, lint, typecheck i build zostały zweryfikowane w zakresie zmiany.

## Outcome

Dodano migrację `0024_cleanup_operations`, deterministyczny preview token,
idempotentne potwierdzenie wykonania oraz dwa chronione piony API. Reset usuwa
wyłącznie dane i zarządzane artefakty wskazanej gry, zachowuje rekord gry, joby,
współdzielony cache i współdzielone pliki. Usunięcie release obejmuje rekord,
powiązania i jego dedykowane katalogi snapshotu/APK.

Admin pokazuje zakres operacji w kontekście aktywnej gry i szczegółu wydania.
Wykonanie wymaga braku blokad, dokładnego identyfikatora i checkboxa; komponent
blokuje podwójny submit. OpenAPI i klient zostały wygenerowane ponownie.

Weryfikacja: 30 testów backendu cleanup/security/migration, 243 testy całego API
oraz dwa testy na izolowanym, zmigrowanym PostgreSQL, 126 testów Admina i 23
testy klienta przeszły. Przeszły też Ruff, ESLint, TypeScript, kontrola
generowanego OpenAPI oraz produkcyjny build Admina.
Pełny mypy wykazał 11 wcześniejszych błędów poza nowym pionem (legacy OpenAPI i
brak nowego argumentu w skrypcie `workbench_acceptance.py`); nowe moduły cleanupu
nie pojawiły się na liście błędów.
