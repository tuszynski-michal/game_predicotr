---
title: TASK-0994 — Rejestr rodzin, wersji i przypisań
status: todo
last_updated: 2026-10-14
---

# TASK-0994 — Rejestr rodzin, wersji i przypisań

## Status

`todo`

## Goal

Zastąpić statyczny wybór wersji trwałym katalogiem.

## Context

Task jest częścią zaakceptowanej rewizji 6. Rejestr i migracja przypisań. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1014; aktualne Alembic heads.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. migracja i zgodność istniejących gier.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [DATA_MODEL](../architecture/DATA_MODEL.md).
- [API_CONTRACT](../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: DATA_MODEL, API_CONTRACT, D-527/D-544.

- [D-527](../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-544](../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Addytywne encje rodzin, wersji, przypisań i zdarzeń.
- Zarejestrować bazy historyczne bez fikcyjnych kohort i PASS.
- Przypisania istniejących V3 odzwierciedlają dotychczasowe wersje.

## Out of scope

- Bez aktywacji nowych modeli i migracji bazy operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Addytywny enum/CHECK dopuszcza `neural_grid_v3` i wszystkie stare wartości; istniejące gry nie są przepisywane.
- [ ] Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment.
- [ ] Brak artefaktu blokuje udostępnienie.
- [ ] Powtórna rejestracja jest idempotentna.
- [ ] Gra nie odczytuje cudzych danych przez błędny zakres.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Rejestr modelu i format strony mają oddzielnych właścicieli: assignment wskazuje niezmienną wersję, `shape_geometry_configuration` identyfikuje silnik. Proponowane rozszerzenie enum `GameShapeGeometryConfiguration.NEURAL_GRID_V3 = "neural_grid_v3"` i addytywna migracja CHECK `games` zachowują każdą starą wartość. Migracja nie aktualizuje formatu istniejących gier, nie dodaje neural assignment starej 777 i nie zmienia cropów. Bazy historyczne rejestrują faktyczne artefakty/raporty; brak kohorty lub nowej oceny nie staje się PASS.

Przed rejestracją sprawdzić zgodność możliwości/topologii, tożsamość bazy, manifest, istnienie/rozmiar/hash artefaktów. Zapis wersji i zdarzenia jest atomowy i idempotentny; ponowienie tej samej treści odtwarza wynik, odmienna treść pod tym samym kluczem daje konflikt bez częściowego zapisu. Odczyty i assignment kontrolują zakres gry. Dokładny porządek blokad, nazwy błędów i nowe symbole wykonawca rozwinie przed kodowaniem na podstawie istniejącego kontraktu, bez osłabienia jego ochrony. Pliki: `domain/grid_engine_profiles.py`, `storage/models.py`, proponowane moduły registry oraz migracja Alembic; API/schema/OpenAPI/klient/test HTTP tworzą jeden pion. Bootstrap nie implementuje tego kontraktu.

## Expected files

- Istniejące: [models.py](../../services/api/src/game_predictor_api/storage/models.py) — encje i relacje magazynu.
- Pozostały zakres wskazany w zaakceptowanym planie: `services/api/src/game_predictor_api/domain/grid_engine_profiles.py`; nowe proponowane `services/api/src/game_predictor_api/domain/grid_model_registry.py`, `services/api/src/game_predictor_api/application/grid_model_registry.py`, `services/api/src/game_predictor_api/storage/grid_model_registry.py`, schema/router i migracja.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_model_registry.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment.
- Brak artefaktu blokuje udostępnienie.
- Powtórna rejestracja jest idempotentna.
- Gra nie odczytuje cudzych danych przez błędny zakres.

## Verification

Zakres: API, MIG, OpenAPI, MAP, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_domain.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez aktywacji nowych modeli i migracji bazy operatora.

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

- Nie rozpoczęto. Docelowy zapis wyniku: schemat, mapowanie istniejących profili i wyniki migracji testowej.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- TASK-1015, rozliczenie P2-3 audytu: doprecyzowano projektowany neutralny format V3, oddzielny assignment oraz ochronę dawnych wartości; kontrakt nie jest jeszcze zaimplementowany.
- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1012
