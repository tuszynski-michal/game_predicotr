---
title: TASK-0993 — Edytor czterech rogów i 24 punktów
status: done
last_updated: 2026-10-15
---

# TASK-0993 — Edytor czterech rogów i 24 punktów

## Status

`done`

## Goal

Przyspieszyć korekty przesuniętej siatki bez utraty dokładnych węzłów.

## Context

Task jest częścią zaakceptowanej rewizji 6. Geometria edytora i zachowanie węzłów. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1015 done. Poprzedzający etap TASK-1008 done, v1.7.370 / `f4ff1f4d3b0d49600ffb8fbbdd948d60ff942a65`; brak operacyjnego backfillu i brak końcowego werdyktu audytu w480 s jawnie odnotowane zgodnie z wyjątkiem AGENTS.md.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. D-550/D-552 accepted; D-548/D-549/D-551 dotyczą odrębnych późniejszych pionów. Reguły edytora zatwierdzono bezpośrednio w zleconej rewizji6.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. istniejący kontrakt i ograniczona geometria.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- [API_CONTRACT](../../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, API_CONTRACT, reguły edytora w tym planie.

## Scope

- Oddzielić tryb uchwytów od danych.
- Dodać transformację wszystkich węzłów, przesunięcie całości, jawny reset, undo i konflikt szkicu.

## Out of scope

- Bez zmiany topologii, danych operatora i klasyfikacji symboli.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Roundtrip 24→4→24 zachowuje liczby.
- [x] Homografia, translacja, reset/undo, błędny quad, dotyk i reload są sprawdzone.
- [x] Podgląd i zapis mają zgodne wycinki.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Tryb uchwytów jest lokalnym stanem UI: domyślnie cztery rogi, opcjonalnie „Dokładna korekta” (24 węzły). Zmiana trybu nie zmienia geometrii ani klucza polecenia. Dla istniejącego lattice ruch rogu stosuje homografię starego i nowego obrysu do wszystkich węzłów, na bazie początku gestu, bez kumulowania błędu. Translacja zachowuje istniejącą funkcję i jej ograniczenie całej siatki do źródła.

Jawna akcja „Wyznacz regularną siatkę z czterech rogów” zmienia wyłącznie szkic i uruchamia obecny podgląd; „Cofnij zmianę siatki” odtwarza poprzednie współrzędne. Wewnętrzna opcjonalna capability `supportsLatticeEditing` zachowuje istniejące pełne lattice niezależnie od pinu, a dla pustego szkicu jest wyprowadzona w adapterach deferred/reported/operational z istniejącego `expectedProposalChecksumSha256`, czyli potwierdzonego neural provenance. Dla pustego szkicu z tym pinem cztery rogi tworzą regularne 24, po czym dostępna jest dokładna korekta; preview/save zachowują pin. Cele legacy bez pinu i adapter audytu zachowują quad-only oraz dotychczasowy transport. Żadna akcja trybu nie usuwa lattice. Nie dodajemy API: istniejące payloady reported/deferred/operational przenoszą dokładne 24 węzły, preview i save korzystają z tego samego walidatora commandKey.

Walidacja wymaga dodatniej orientacji wypukłych komórek i braku przecięć niesąsiadujących krawędzi. Nieprawidłowy ruch rogu nie zmienia danych; nieprawidłowa dokładna korekta blokuje podgląd i zapis. Undo obejmuje gesty i jawne odtworzenie regularnej siatki; reset sugestii przywraca stan bazowy. Trwały szkic przechowuje źródło i rewizję jako osobny scope pod stabilnym kluczem celu. Zmiana źródła/rewizji blokuje odtworzenie i zapis do jawnego przywrócenia sugestii; CAS i idempotencja istniejącego backendu pozostają bez zmian. Archiwalna777 oraz etykiety per gra pozostają poza zmianą.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [board-lattice-state.ts](../../../apps/reviewer/src/features/operational-reviews/board-lattice-state.ts) — `boardLatticePayload`, `translatedBoardLattice`; [edytor](../../../apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx) — `BoardGeometryCorrectionEditor`, `DeferredBoardCellGeometryEditor`.
- Istniejące: [board-lattice-draft-storage.ts](../../../apps/reviewer/src/features/operational-reviews/board-lattice-draft-storage.ts) — odczyt i zapis szkiców.
- Pozostały zakres wskazany w zaakceptowanym planie: testy interakcji Reviewera; opcjonalne rozszerzenie transportu tylko jeśli obecny kontrakt nie przenosi wymaganych danych.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Rzeczywiste testy pionu: `apps/reviewer/test/board-lattice.test.mjs` oraz `apps/reviewer/test-interactions/board-lattice-editor.test.mjs`; zastępują pierwotną propozycję `four_corner_grid_editor.test.ts`. Regresje adapterów, legacy quad-only, symboli i utraconej odpowiedzi korzystają z istniejących testów Reviewera.

## Test cases

- Roundtrip 24→4→24 zachowuje liczby.
- Homografia, translacja, reset/undo, błędny quad, dotyk i reload są sprawdzone.
- Podgląd i zapis mają zgodne wycinki.

## Verification

Zakres: REVIEWER, API przy zmianie transportu, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Rozszerzone rzeczywiste testy z Expected files muszą także zostać wykonane po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez zmiany topologii, danych operatora i klasyfikacji symboli.

## Outcome

### Execution phase

- Faza: oczekiwanie na końcową akceptację i integrację całego planu; current HEAD v1.7.370 / `f4ff1f4d3b0d49600ffb8fbbdd948d60ff942a65`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: v1.7.371 / `7d4b8cd60457650c8695be102399616cb9cf1692`; osobny commit18 plików, bez scalenia. Numer sprawdzono na wszystkich lokalnych referencjach i HEAD-ach worktree, bez kolizji. Ten zapis hasha powstał po commicie i wejdzie z następnym taskiem, bez amend.
- Audit: jedna próba `claude-fable-5-1` / `medium`, bez końcowego werdyktu po wznowieniu sesji. [Ograniczenie audytu](../../quality/TASK-0993_AUDIT_INTERRUPTED_CODEX.md); wyjątek AGENTS.md pozwala kontynuować, bez PASS i bez domniemanej listy znalezisk.
- Następny krok: TASK-1014. Integracja czeka na końcową akceptację całego planu.

### Changed

- Domyślny tryb4 i opcjonalne24 uchwyty nie modyfikują geometrii ani komendy. Ruch rogu mapuje wszystkie węzły homografią początku gestu; translacja przenosi całą siatkę. Jawna regularna siatka ma podgląd i jednostopniowe undo. Pusty neural szkic z istniejącym pinem można zbudować z4 rogów i dokalibrować; istniejące nodes bez pinu pozostają zachowane.
- `parseBoardLattice` sprawdza także przecinanie niesąsiadujących krawędzi. Błędny obrys nie zmienia danych; nieprawidłowe komórki blokują wspólny preview/save. Lokalny szkic używa istniejącego magazynu z opcjonalnym `revisionKey` i stabilnym `draftKey`; konflikt blokuje zapis do resetu. Starszy scope jest bezpiecznie odrzucany, bez automatycznej utraty lub nałożenia jego danych na nowszy serwer.
- API, topologia, sekwencje, archiwalna777, symbole per gra i legacy/audit quad-only pozostają chronione. Nie ma nowego endpointu ani migracji.
- Pliki taska: `board-lattice-state.ts`, `board-lattice-draft-storage.ts`, `board-geometry-correction-target.ts`, `deferred-board-cell-geometry-editor.tsx`, `test/board-lattice.test.mjs`, `test-interactions/board-lattice-editor.test.mjs`; owner docs ADMIN_APP/API_CONTRACT, mapy, ten task i własna sekcja CURRENT_STATE. Pełny ograniczony zakres w `artifacts/audits/TASK-0993_SCOPE.json`.

### Verification results

- Próba audytu i kontrola braku własnych procesów zapisane osobno. Nie ponawiano audytu po wznowieniu.

- Wszystkie procesy uruchomiono z worktree z twardym `subprocess.run(timeout=120)`; NativeNode `C:/Program Files/nodejs/node.exe`, npm przez `C:/Program Files/nodejs/node_modules/npm/bin/npm-cli.js`. `.venv` jest istniejącym junction, bez uruchamiania usług.
- `node --experimental-strip-types --test apps/reviewer/test/board-lattice.test.mjs`:10/10 PASS. Obejmuje niezależny przekształcenie projekcyjne, odrzucony quad, przecięcia zdalnych komórek, scope źródła/rewizji/stary format oraz3 adaptery z pinem/bez i brakującymi nodes.
- `npm run test:geometry --workspace @game-predictor/reviewer`:88/88 PASS, w tym5 testów lattice; touch, homografia, rigid translation, regular/reset/undo,24/4 roundtrip, reload, utracona odpowiedź, konflikt nowej rewizji, pusty neural i legacy/audit/symbole.
- `node --experimental-strip-types --test` dla `operational-review-state`, `operational-review-actions`, `board-geometry-correction-state`, `operational-board-geometry-target`, `deferred-board-cell-geometry`:54/54 PASS.
- Reviewer `lint`:PASS,0 błędów; zastany warning `_operationId` w `board-search-share-data-source.ts:320` poza taskiem. Reviewer `typecheck` z `next typegen`:PASS. Prettier write/check6 zmienionych plików kodu/testów:PASS.
- `python scripts/generate_code_map.py` oraz `npm run code-map:check`:PASS; `npm run docs:check`:PASS; `git diff --check`:PASS. Logi kontroli w ignored `artifacts/audits/TASK-0993_*.txt`.
- Pierwszy lint wykrył render-ref i brak dependency dodane przez task; poprawiono przez osobny `draftError` i dependency `target.draftKey`. Test konfliktu wykrył czyszczenie komunikatu podczas preview; ten sam osobny stan zachowuje komunikat. Końcowe kontrole powyżej są po tych poprawkach.

### Not completed

- Nie uzyskano niezależnego końcowego werdyktu audytu; próba i wyjątek AGENTS.md zostały jawnie rozliczone. Commit wykonano; integracja wymaga końcowej akceptacji. Nie raportujemy PASS audytu.
- Nie uruchamiano API/Admin/workera, nie zapisano geometrii operatora, nie wykonano migracji, backfillu, treningu, aktywacji, push ani nowego backupu.
- Nie wykonano odbioru na fizycznym Androidzie ani wizualnego odbioru z żywym API. Touch jest sprawdzony przez PointerEvent w jsdom. Nie uruchamiano pytest/OpenAPI: kontrakt HTTP i backend nie zostały zmienione.

### Documentation updates

- Task rozwinięty przed kodowaniem; zaktualizowano wymagania ADMIN_APP, komentarz implementacyjny API_CONTRACT, mapy i własny stan wznowienia. Nie dodano decyzji produktowej poza zaakceptowaną sekcją2.4 planu.

### Recommended next task

- TASK-1014
