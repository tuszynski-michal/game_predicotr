---
title: TASK-1004 — Tworzenie gry z domyślną geometrią V3
status: todo
last_updated: 2026-10-14
---

# TASK-1004 — Tworzenie gry z domyślną geometrią V3

## Status

`todo`

## Goal

Nowa gra korzysta z opublikowanej geometrii bez treningu od zera.

## Context

Task jest częścią zaakceptowanej rewizji 6. Nowe gry i izolacja symboli. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0998.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. spójny pion tworzenia i izolacja symboli.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, D-527, wymagania cold-start symboli.

- [D-527](../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Backend przypina domyślną wersję.
- Zaawansowany wybór/fork kontroluje zgodność i dziedziczy wyłączenia.
- Utworzenie gry i przypisania jest atomowe.
- Format danych strony nie pełni funkcji identyfikatora checkpointu.

## Out of scope

- Bez tworzenia rzeczywistych gier i przełączania istniejących przypisań.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] GameCreate bez `shapeGeometryConfiguration` zapisuje neutralne V3; modelassignment jest niezależny.
- [ ] Brak default dopuszcza draft/unassigned, blokuje import do assignment; jawna zgodna opublikowana wersja tworzy assigned.
- [ ] Nowe klasyczne tworzenie jest zablokowane, historyczny read/update zachowuje stare wartości.
- [ ] Brak default blokuje import; fork nie kopiuje etykiet ani wag.
- [ ] Nowa gra ma własny katalog i cold-start symboli, bez modelu obcej gry.
- [ ] Retry nie tworzy drugiej gry.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Zwykły GameCreate pomija `shapeGeometryConfiguration`; serwer nadaje proponowane `GameShapeGeometryConfiguration.NEURAL_GRID_V3 = "neural_grid_v3"`. Format/silnik jest niezależny od rodziny i wersji assignment. Backend waliduje opublikowaną zgodną wersję, jej artefakty i możliwości, następnie tworzy grę oraz assignment/fork atomowo w jednej transakcji. Idempotentne ponowienie odtwarza tę samą grę; zmienione polecenie lub konflikt przypisania nie pozostawia częściowego zapisu. Zaawansowany wybór wersji/forka nie zmienia formatu strony, nie kopiuje etykiet ani wag i dziedziczy wyłączenia.

GameCreate zachowuje dotychczasowy domyślny status DRAFT; jawnie żądany status nie jest po cichu zmieniany i nie powstaje nowa polityka statusu. Brak zatwierdzonego default pozwala zwykłemu formularzowi utworzyć grę bez assignment; import V3 jest zablokowany do zgodnego assignment. Jawnie wskazana zgodna opublikowana wersja w ustawieniach zaawansowanych może utworzyć przypisaną grę. Nowe klasyczne tworzenie jest zablokowane; historyczny odczyt/update starej 777 zachowuje stare wartości. Brak własnych korekt nie blokuje przypisania istniejącej zgodnej bazy. Własny katalog/cold-start symboli korzysta z `resolve_unclassified_cold_start`, bez obcego klasyfikatora.

Pion zmian: `application/catalog.py`, `schemas/catalog.py`, formularz/stan/akcje game-catalog, registry assignment, OpenAPI, wygenerowany klient/wrapper i test HTTP. Enum/CHECK jest zależnością TASK-0994. Przed kodowaniem sprawdzić kolejność blokad i aktualne kody błędów katalogu, rozwinąć je w tym tasku; żadnego nowego równoległego endpointu. Bootstrap ustala projektowany kontrakt, nie zmienia GameCreate ani bazy.

## Expected files

- Istniejące: [game-catalog.tsx](../../apps/admin/src/features/games/game-catalog.tsx) — komunikat klasycznej gotowości i formularz.
- Istniejące: [game-catalog-state.ts](../../apps/admin/src/features/games/game-catalog-state.ts) — `SHAPE_GEOMETRY_CONFIGURATION_LABELS`.
- Istniejące: [catalog.py](../../services/api/src/game_predictor_api/application/catalog.py) i [schematy katalogu](../../services/api/src/game_predictor_api/schemas/catalog.py) — tworzenie i aktualizacja gry.
- Istniejące: [symbol_model_snapshot_resolver.py](../../services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py) — `resolve_unclassified_cold_start`.
- Pozostały zakres wskazany w zaakceptowanym planie: –, `game-catalog-actions.ts`; klient i testy żądań.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_new_game_default_v3_geometry.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Brak default blokuje import; fork nie kopiuje etykiet ani wag.
- Nowa gra ma własny katalog i cold-start symboli, bez modelu obcej gry.
- Retry nie tworzy drugiej gry.

## Verification

Zakres: API, ADMIN, OpenAPI, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_api.py services/api/tests/test_symbol_model_catalog_binding.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez tworzenia rzeczywistych gier i przełączania istniejących przypisań.

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

- Nie rozpoczęto. Docelowy zapis wyniku: ścieżka nowej gry i test izolacji symboli.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- TASK-1015, rozliczenie P2-3 audytu: doprecyzowano projektowany neutralny format V3, oddzielny assignment oraz ochronę dawnych wartości; kontrakt nie jest jeszcze zaimplementowany.
- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1011
