---
title: TASK-0744 — T3 — zapis predykcji biblioteki wzorców dla oczekujących komórek
status: done
last_updated: 2026-09-30
---

# TASK-0744 — T3 — zapis predykcji biblioteki wzorców dla oczekujących komórek

## Status

`done`

## Goal

Narzędzie zapisuje nową wersję predykcji (`symbol-reference-library-v1`) dla
oczekujących komórek z pewną propozycją biblioteki, wyłącznie według
zatwierdzonego podglądu, planszami, z możliwością wznowienia i kontrolą
po zapisie.

## Context

D-466: operator zlecił zapis propozycji biblioteki do oczekujących komórek
(wariant b: także potwierdzenia dotychczasowego symbolu). Istniejący
mechanizm `image_symbol_prediction_revisions` + synchronizacja komórek
(`synchronize_after_prediction_refresh`) jest używany przez przeliczanie
predykcji (`pending_symbol_reinference.py`) i zachowuje decyzje człowieka.

## Dependencies / entry conditions

- TASK-0743 done; kod scalony do `v1.1-vision-lab-hybrid-geometry` (v1.7.74).
- Najnowsza wersja predykcji planszy jest wersją bieżącą
  (`_current_cells` wybiera najnowszą po `created_at`).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-fable-5-1`,
reasoning `medium` na polecenie operatora (poziomu nie da się ustawić z
sesji; rekomendacja warunkowa), osobny agent.

## Relevant docs

- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-464–D-466)

## Scope

- Moduł `symbols/reference_library_writer.py`: przepisanie predykcji planszy
  dla komórek docelowych, skrót predykcji, zapis jednej planszy z blokadami
  i kontrolą po zapisie.
- Podkomendy skryptu: `apply-preview` (manifest z sumą kontrolną, tylko
  odczyt), `apply` (tylko dla identycznego manifestu, wznawialne,
  pokwitowania, `--board` dla kanarka), `apply-revert` (cofnięcie przebiegu
  dla wskazanych plansz albo `--all`), `apply-verify` (odczyt stanu po zapisie).

## Out of scope

- Zatwierdzanie komórek, zmiana komórek z decyzją człowieka, migracje, UI.

## Acceptance criteria

- [x] Komórka docelowa: `pending`, `assignment_source = model`, bez flagi
  jakości, pełna widoczność, pewna propozycja (R7).
- [x] `apply` odrzuca manifest o innej sumie; plansza, której wersja
  predykcji, skrót predykcji lub stan komórki zmienił się od podglądu,
  jest pomijana jako `stale`, bez zapisu.
- [x] Zapis planszy w jednej transakcji: nowa wersja predykcji, projekcja
  wyszukiwania, synchronizacja komórek; kontrola: komórki docelowe mają nowy
  symbol i nadal `pending`, pozostałe komórki planszy bez zmian decyzji i
  przypisania; niezgodność wycofuje transakcję i zatrzymuje przebieg.
- [x] Ponowienie pomija plansze już zapisane (pokwitowania i stan bazy).
- [x] Testy części czystych, Ruff, mypy; audyt bez P0–P2; commit.

## Technical notes

- Predykcja komórki docelowej: `symbolCode` = propozycja, `confidence` =
  0,99 (zmierzona precyzja pewnych propozycji 99–100%), `alternatives` z tym
  jednym symbolem, dodatkowy klucz `referenceLibrary` (wersja, głosy).
- `model_checksum_sha256` wersji = `revisionChecksumSha256` manifestu: skrót
  tożsamości biblioteki (wersja, polityka, liczba wzorców na grupę,
  checkpoint modelu, klucze wzorców) razem z parametrami zakresu (symbol,
  pasmo pewności). Inny zakres zapisuje własną wersję.
- Sesja w `game_storage_scope(game_id)`, jak w workerze.

## Test cases

- Przepisanie predykcji: tylko wskazane komórki, zgodność starego symbolu
  wymagana, nieznany indeks komórki → błąd.
- Skrót predykcji niezależny od kolejności kluczy.

## Outcome

- `reference_library_writer.py`: `apply_board` i `revert_board` na wspólnej
  ścieżce `_write_revision` (blokady item → board → komórki, nowa wersja,
  projekcja wyszukiwania, synchronizacja, kontrola po zapisie). Kontrola
  obejmuje komórki planszy i komórki o tych samych `sequence_number`; zmiana
  zbioru komórek → `SYMBOL_REFERENCE_WRITE_SIDE_EFFECT`.
- `apply_board`: `already_applied` tylko dla wersji z sumą tego przebiegu;
  `stale:library_revision_exists`, gdy migawka tego przebiegu już istniała i
  została nadpisana (zamiast `IntegrityError`).
- `revert_board`: nowa wersja bieżąca z kopią poprzednich predykcji, wersją i
  iteracją modelu, suma `sha256("revert:" + suma przebiegu)`. Działa tylko,
  gdy bieżąca wersja planszy to wersja biblioteki tego przebiegu. Decyzje
  operatora podjęte w międzyczasie zostają. Zrevertowana plansza nie wraca do
  biblioteki w tym samym zakresie (unikalność migawki).
- Skrypt: `apply-preview` pomija komórki z predykcją biblioteki
  (`already_library_prediction`), manifest ma `revisionChecksumSha256`
  (wymagany przy odczycie). `apply` i `apply-revert`: pokwitowania
  `failed:<kod>` są ponawiane, `DBAPIError` (np. zakleszczenie) zapisuje
  pokwitowanie i kończy przebieg kodem 2; `--board` wybiera plansze kanarka;
  `apply-revert` wymaga `--board` albo `--all`. `apply-verify` rozróżnia
  `library_prediction`, `reverted`, `unchanged`, `decided_by_operator`,
  `other_library_run`.
- Manifest Arbuz <60%: `artifacts/symbol-reference-library/apply-arbuz-lt60/
  apply-manifest.json`, sha256 `1e4be8ce89590a0532a2b7d8483e030c12df6da289a8746a9bd622fdca1ecd61`,
  2703 plansze, 2918 komórek (2621 potwierdzeń ARBUZ, 297 zmian), 0 wykluczeń.
- Weryfikacja: 49 testów (`test_symbol_reference_library*.py`,
  `test_evaluate_symbol_reference_library_script.py`), Ruff, mypy `--strict`.
- Audyt `claude-fable-5-1` (3 rundy): runda 1 FAIL (P2: klucz idempotencji
  bez zakresu przebiegu) — poprawione; rundy 2 i 3 PASS bez P0–P2. Uwagi P3
  wdrożone: cofnięcie, `--board`, wczesne `stale` zamiast `IntegrityError`,
  wymagany klucz manifestu, ochrona pełnego revertu, klasyfikacja `reverted`.
  Pozostałe P3: brak testu integracyjnego zapisu na bazie (zastępuje go
  kanarek B1), brak wpisu w `image_symbol_review_cell_events` dla zmiany
  predykcji (jak przy przeliczaniu modelem; ślad: `revision`,
  `last_reviewed_by`, `updated_at`, wersja predykcji).
- Reguła operacyjna: `apply` bez równoległej weryfikacji w Adminie i bez
  joba przeliczania predykcji (ryzyko zakleszczenia; każde `apply` podbija
  `catalog_revision`, więc zamrożone operacje masowe w Adminie są odrzucane).
