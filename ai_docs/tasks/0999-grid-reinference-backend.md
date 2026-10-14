---
title: TASK-0999 — Backend ponownego rozpoznania wybranego zakresu
status: todo
last_updated: 2026-10-14
---

# TASK-0999 — Backend ponownego rozpoznania wybranego zakresu

## Status

`todo`

## Goal

Przeliczyć wskazane cele z trwałym postępem i ochroną danych.

## Context

Task jest częścią zaakceptowanej rewizji 6. Ponowne zapisy i ochrona sekwencji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1017, TASK-1012, TASK-0998; bez zależności od treningu.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. zapis geometrii, wycinków i kontrola właściciela.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../requirements/IMAGE_INGESTION.md).
- [VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP](../architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, D-462/D-523/D-543, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.

- [D-462](../process/decisions/DECISION_LOG_2026.md#d-462--weryfikacja-per-komórka-bez-zatwierdzania-planszy-i-siatki) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-523](../process/decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-543](../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Preview, zamrożony manifest, jeden inference na zdjęcie, zapis tylko wybranych celów.
- Dla zgłoszeń wynik pozostaje propozycją przekazywaną do TASK-1013.
- Admission uwzględnia kolidujące zadania geometrii i symboli.

## Out of scope

- Bez automatycznego przejęcia kanonu i uruchamiania pełnej gry.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Aktualna baza działa bez treningu.
- [ ] Chronione decyzje pozostają identyczne.
- [ ] Brak środkowego slotu nie przesuwa sekwencji.
- [ ] Restart nie dubluje zapisu; identyczny wynik nie jest „naprawą”.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Preview, zamrożony manifest, jeden inference na zdjęcie, zapis tylko wybranych celów. Dla zgłoszeń wynik pozostaje propozycją przekazywaną do TASK-1013. Admission uwzględnia kolidujące zadania geometrii i symboli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [image_review_repository.py](../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt.
- Istniejące: [jobs.py](../../services/api/src/game_predictor_api/application/jobs.py) — preflight, snapshoty, admission i start zadań.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejące blokady własności i runtime geometrii; nowe proponowane `services/api/src/game_predictor_api/application/grid_reinference.py`, `services/api/src/game_predictor_api/storage/grid_reinference.py`, `services/worker/src/game_predictor_worker/images/grid_reinference_handler.py` oraz migracja receipts.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_reinference_backend.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Aktualna baza działa bez treningu.
- Chronione decyzje pozostają identyczne.
- Brak środkowego slotu nie przesuwa sekwencji.
- Restart nie dubluje zapisu; identyczny wynik nie jest „naprawą”.

## Verification

Zakres: API, WORKER, MIG, renderer parity, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_operational_image_reviews.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_neural_folder_correction_pipeline.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez automatycznego przejęcia kanonu i uruchamiania pełnej gry.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `claude-fable-5-1`, reasoning `high`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: zakres, konflikty, receipts i rozdzielenie zapisów automatycznych od propozycji.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1013
