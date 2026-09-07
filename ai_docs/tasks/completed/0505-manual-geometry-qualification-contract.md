---
title: Shared manual geometry completeness and qualification
status: done
last_updated: 2026-09-07
---

# TASK-0505 — Wspólny kontrakt kompletności i kwalifikacji geometrii

## Status

`done`

## Goal

Zapis i odczyt rewizji zachowują kompletność, maskę niedostępnych komórek
i wykluczenie z uczenia każdego slotu, bez zmiany historycznych checksum.

## Context

Realizacja TASK-0505 zaakceptowanego w rozmowie planu „Niepełne plansze
i wykluczanie niepewnej geometrii z uczenia”. Istniejące `pending_partial`
i `unavailableCellIndices` pozostają jedynym mechanizmem częściowych plansz.

## Dependencies / entry conditions

- Migracja 0099 została osobno utrwalona w `v0.10.220` za zgodą operatora.
- Pozostałości przerwanego TASK-0504 i `apps/admin/next-env.d.ts` są poza zakresem.
- Nie stosujemy migracji na danych operatora ani nie restartujemy usług.

## Recommended execution

`gpt-6-astra high`, zgodnie z końcową tabelą zaakceptowanego planu.
Powód: wspólna semantyka, wersjonowanie i migracja wielu ścieżek zapisu.
Wymagany niezależny review `gpt-6-astra high`: kontrakty i kompatybilność.
Rekomendacja sama nie upoważnia do delegowania pracy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — decyzje guard i aktywne sloty
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Wersjonowane metadane slotu: kompletność, maska, wykluczenie i powód.
- Maska 1–15 dla niepełnej planszy; kompletna ma pustą maskę.
- Niepełna zawsze wykluczona; kompletna może być ręcznie wykluczona.
- Rewizja geometrii jest właścicielem, `recognized_boards` projekcją.
- Nowa migracja po 0099, istniejące API, OpenAPI, klient i test żądania.
- Historyczne payloady i ich checksumy nie są przepisywane.

## Out of scope

Narożniki poza zdjęciem i renderer (0506), kontrolki i szkice (0507),
kwalifikacja kohort/kotwic i reconciliacja częściowych rewizji (0508),
pełny odbiór UI (0509). Bez zmian detektora, OCR, importów i danych operatora.

## Acceptance criteria

- [x] Walidowane metadane wszystkich aktywnych slotów, także maska 15/15.
- [x] Zapis i odczyt page override/guard zachowują kompletność i wykluczenie każdego slotu; aktywacja kanonicznego zapisu Grid Review jest zależnością TASK-0508.
- [x] Checksum obejmuje nowe decyzje, historyczne payloady pozostają zgodne.
- [x] Migracja addytywna i bezpieczna ścieżka rollbacku.
- [x] Spójny kontrakt API/klienta, testy i niezależny review foundation.

## Technical notes

Nowy opcjonalny payload `geometryQualification` ma wersję
`manual-geometry-qualification-v1`. Brak oznacza historyczny kontrakt,
a nie jawną zgodę na uczenie częściowej planszy. Maska pozostaje nazwana
`unavailableCellIndices`. Nowe pola nie mogą być po cichu ignorowane przez
starych konsumentów. Wdrożenie foundation nie jest aktywacją całego workflow.

Stan implementacji: page override i guard zapisują/odczytują nowe decyzje;
Grid Review ma wspólny kontrakt i projekcję repozytorium, ale publiczne zapisy
z nowym polem są jawnie zatrzymane do reconciliacji TASK-0508. Manifest guard
v3 nie może uruchomić starego importera, a override z kwalifikacją starego
preflightu. To kontrolowana granica foundation wymagająca potwierdzenia
w audycie zgodności zakresu TASK-0505; nie deklarujemy działania UI ani całego
przepływu częściowej planszy na tym etapie.

## Expected files

- Nowe: `domain/geometry_qualification.py`, odpowiadający schema i testy;
  migracja `0100_manual_geometry_qualification`.
- Istniejące: domena, serwis i repozytorium page overrides; kontrakty guard,
  Grid Review, modele SQLAlchemy, klient Admin API i specyfikacja OpenAPI.

## Test cases

Roundtrip kompletnych/wykluczonych/niepełnych slotów, 15/15; niepoprawna maska,
nieznana wersja, niezgodność slotów; identyczny retry oraz zmiana decyzji;
odczyt historyczny; migracja SQL bez przebudowy/importu zdjęć.

## Verification

Testy modułów pytest, Ruff i mypy zmienionych modułów (timeout 120 s/krok),
OpenAPI generate/check, testy/typecheck klienta, format check.
Wyniki zostaną wpisane w Outcome; żaden test nie jest na tym etapie zaliczony.

## Risks / open questions

Nowe metadane wymagają wspólnej integracji konsumentów w 0506–0508 przed
produkcyjnym użyciem UI. Nie wolno uznać zapisu oznaczenia za odtrenowanie
aktywnego profilu. Historyczne wersje zachowują semantykę i replay.

## Outcome

### Changed

- Wspólna walidowana kwalifikacja, trwałe JSONB page overrides i guard,
  checksumy/manifest v3, opcjonalne kontrakty API i regeneracja klienta.
- Projekcja kwalifikacji z rewizji źródła do recognized board oraz CHECK
  zgodności. Migracja 0100 nie skanuje danych przy dodawaniu nowych CHECK;
  rollback odmawia utraty nowych decyzji. Historyczne payloady pozostają bez zmian.
- Bezpieczne odrzucenie nowego kontraktu przez nieprzystosowanych konsumentów.

### Verification results

- 177 testów API/workera: domena, HTTP, zapis/odczyt, guard, Grid Review,
  migracje offline SQL i historyczny preflight — passed, 53,37 s.
- 53 testy wygenerowanego klienta i wrappera — passed; build/typecheck klienta
  oraz `npm run openapi:check` — passed.
- 12 prób CHECK na PostgreSQL w read-only SELECT ze stałych — passed.
  Nie odczytywano tabel użytkownika ani nie modyfikowano bazy.
- Ruff zmienionych plików — passed. Mypy z poprawnym MYPYPATH wskazuje dwa
  istniejące wcześniej błędy: opcjonalny board w API preview i redundant cast
  w `_resolution_payload`; są poza nową logiką.
- Izolowany mypy pozostałych 14 zmienionych modułów — passed. Końcowy Ruff
  format check 22 plików — passed; Prettier zmienionego klienta, OpenAPI
  i testu wrappera oraz lint klienta — passed.
- `npm run format:check` — failed: 35 wcześniejszych plików poza zmianą,
  w tym chroniony `apps/admin/next-env.d.ts`. Nie formatowano ich.

### Independent audit

Niezależny `gpt-6-astra high` odebrał granicę foundation po usunięciu trzech
luk: historyczny zapis page override i guard nie może zdjąć kwalifikacji,
a downgrade blokuje wszystkich czterech właścicieli przed sprawdzeniem danych.
Audytor uruchomił 41 testów (2,41 s); dodatkowa kontrola po poprawkach:
80 testów page/guard/migracji (12,05 s) oraz Ruff — passed.
Pełny zapis kanonicznej rewizji i mapping DTO/response wymagają TASK-0508.

### Not completed

- Aktywacja zapisu Grid Review i pełny roundtrip kanonicznej source revision
  pozostają jawnie w TASK-0508. Foundation nie deklaruje odbioru całego planu.
- Nie wykonano migracji na bazie operatora, restartów ani przeliczania importów.
- Brak pełnego renderu/edycji częściowych plansz i ochrony konsumentów treningu:
  zgodnie z planem są to TASK-0506–0508, a odbiór interakcji to TASK-0509.

### Documentation updates

IMAGE_INGESTION, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP, D-371, CURRENT_STATE.

### Recommended next task

TASK-0506; użytkownik zlecił już całą serię wraz z audytami.
