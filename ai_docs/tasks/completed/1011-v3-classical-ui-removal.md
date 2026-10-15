---
title: TASK-1011 — Usunięcie zatwierdzonych pozostałości V1.1 z V3
status: done
last_updated: 2026-10-15
---

# TASK-1011 — Usunięcie zatwierdzonych pozostałości V1.1 z V3

## Status

`done`

## Goal

Ekrany V3 pokazują właściwy model i dostępne działania.

## Context

Task jest częścią zaakceptowanej rewizji 6. Ograniczone zmiany UI i regresja starej gry. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1004.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. ograniczona zmiana UI z regresją starej gry.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, D-541/D-544.

- [D-541](../../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-544](../../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Usunąć klasyczny panel z F15, klasyczną gotowość z F16 i stare opcje tworzenia z F17.
- Dokładne stare wartości to `framed_full_page_v2` i `requires_clarification`.
- Zwykły formularz traci również wybór dwóch profili V3 na rzecz default.

## Out of scope

- Nie usuwać historycznych enumów z odczytu API ani backendu klasycznego.
- Inne pozostałości wpisać do listy decyzji operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] V3 nie pokazuje klasycznych działań; pokazuje stan przypisanej wersji.
- [x] Stara 777 nadal poprawnie odczytuje historyczne wartości i raporty.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Kontrakt wykonawczy zaakceptowany przez leada przed kodowaniem, 2026-10-15, po TASK-1004 v1.7.377: wspólny komponent wyłącznie odczytuje istniejący `getGameGridModelAssignment(gameId)` dla renderowanej karty lub sekcji jakości. Nie pobiera default ani katalogu wersji, nie wykonuje mutacji, nie dodaje cache ani automatycznych ponowień. Osobne stany loading/error/unassigned/assigned pokazują wynik dla bieżącej gry; brak odpowiedzi nie oznacza braku przypisania. Dostępność artefaktów i aktualność dowodu są niezależne: komponent pokazuje oba problemy, jeśli wystąpią razem. `GRID_MODEL_EVALUATION_STALE` i `GRID_MODEL_PUBLICATION_STALE` nie zdejmują assignment. Historyczne unpublished/eligible=false nie blokuje importu; preflight pozostaje właściwą bramką.

Rodzina, wersja i identyfikator pochodzą z wygenerowanego kontraktu assignment. Zmiana gameId resetuje odczyt; cleanup ignoruje spóźnione odpowiedzi, a reload pobiera nowy stan. `usesNeuralGridConfiguration(configuration, code)` ma pierwszeństwo kodu7 przed konfiguracją. Kontekst gry przechodzi z `CatalogWorkspace` do `ModelQualityWorkspace`; symboliczny workspace i jego trening pozostają bez zmian. V3 zastępuje klasyczną geometrię informacją o przypiętej wersji; legacy zachowuje panel, raporty i edycję. Picker create/V3 edit usunięty w1004 jest objęty regresją, bez powtórnej implementacji. Statyczne opisy i historyczne etykiety zostają; dalsze pozostałości trafiają wyłącznie do Outcome/inventory.

Usunąć wyłącznie trzy zatwierdzone miejsca V3: montowanie klasycznego panelu w `ModelQualityWorkspace`, tekst klasycznej gotowości w `game-catalog.tsx` oraz stare opcje tworzenia w `game-catalog-state.ts`. Zwykły formularz nie przesyła `shapeGeometryConfiguration` ani wyboru dwóch profili V3; używa kontraktu TASK-1004 z neutralnym `neural_grid_v3`, ustawianym przez serwer. Przypięta wersja modelu ma odrębny assignment; zaawansowany wybór nie modyfikuje formatu.

Draft bez assignment pokazuje blokadę importu zamiast klasycznej gotowości. Istniejąca stara 777 nadal odczytuje i aktualizuje `framed_full_page_v2`, `requires_clarification` oraz pozostałe historyczne wartości; backend/enumy legacy nie są usuwane. Nowe klasyczne tworzenie jest zablokowane. Regresje kontraktu formularza i stanu UI obejmują oba typy gry, brak default, assignment oraz zmiany gry/reload. Przed startem zweryfikować symbole i konkretne komunikaty istniejących kontraktów; inne pozostałości zgłosić jako pytanie operatora, bez samodzielnego rozszerzania usuwania. Bootstrap nie zmienia komponentów.

## Expected files

- Istniejące: [model-quality-workspace.tsx](../../../apps/admin/src/features/model-quality/model-quality-workspace.tsx) — `ModelQualityWorkspace`, montowanie klasycznego panelu.
- Istniejące: [game-catalog.tsx](../../../apps/admin/src/features/games/game-catalog.tsx) — komunikat klasycznej gotowości i formularz.
- Istniejące: [game-catalog-state.ts](../../../apps/admin/src/features/games/game-catalog-state.ts) — `SHAPE_GEOMETRY_CONFIGURATION_LABELS`.
- Pozostały zakres wskazany w zaakceptowanym planie: testy `model-quality-workspace-contract`, `game-catalog-state`, `game-catalog-contract`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Istniejący `apps/admin/src/features/catalog/catalog-workspace.tsx` — przekazanie kodu i konfiguracji gry; istniejące testy interakcji jakości i formularza.
- Nowy proponowany `apps/admin/src/features/games/grid-model-assignment-summary.tsx` — wspólny komponent odczytu i prezentacji assignment.
- Nowy proponowany `apps/admin/test-interactions/v3-classical-ui-removal.test.mjs` — stany, obie gry, przełączenie i reload; umieszczony w katalogu zbieranym przez `test:geometry`.

## Test cases

- V3 nie pokazuje klasycznych działań; pokazuje stan przypisanej wersji.
- Stara 777 nadal poprawnie odczytuje historyczne wartości i raporty.

## Verification

Zakres: ADMIN, DOC; odbiór obu rodzajów gry.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie usuwać historycznych enumów z odczytu API ani backendu klasycznego.
- Inne pozostałości wpisać do listy decyzji operatora.

## Outcome

### Execution phase

- Faza: done; Claude medium R1 PASS, brak P0/P1; gotowe do osobnego commita i oczekiwania na integrację całego planu.
- Baza taska: v1.7.377 / `70058ee5b71ec6e7383d7038648bd5c0dc6a2ead`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream bazowy: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: przygotowany v1.7.378; pełny hash po utworzeniu. Bez scalenia/push.
- Audit: [Claude medium R1 PASS](../../quality/TASK-1011_AUDIT_claude-fable-5-1.md), limit1200s. P2-2/3 zamknięte dokumentacją i pełnym lintem, P2-1/4 jawnie przyjęte poniżej. Bez R2 i bez zmiany kodu po PASS.
- Następny krok: lead zapisuje osobny commit, następnie pełny hash i rozpoczyna0999. Integracja po całym planie i akceptacji operatora.

### Changed

- Wspólny komponent GET assignment zastępuje klasyczny panel/header jakości i klasyczną gotowość/statyczny checkpoint kart V3. Dostępność artefaktów oraz stale evidence są niezależne, także przy obu problemach naraz. Brak assignment blokuje import informacyjnie, a historyczne unpublished/eligible=false nie jest blokadą; preflight pozostaje źródłem gotowości.
- Kod7 ma pierwszeństwo przed konfiguracją. Odczyty dotyczą wyłącznie renderowanych kart/sekcji, bez default lookup, listy wersji, mutacji, cache i retry. Zmiana gry, opóźniona odpowiedź, reload, błędne lub obce dane mają regresje.
- SymbolQualityWorkspace i trening symboli pozostają bez zmian. Legacy zachowuje klasyczny panel, raporty i formaty. Picker create/V3 edit usunął TASK-1004; potwierdzono istniejącymi interakcjami zamiast powielać zmianę. game-catalog-state.ts nie wymagał zmiany.
- Pozostałości poza zakresem: GridEngineProfileHint i GRID_ENGINE_PROFILE_FALLBACK_DESCRIPTIONS pozostają dla historycznych odczytów/edycji; dalsza przebudowa wymaga decyzji operatora.

### Verification results

- PASS: skoncentrowane interakcje 19/19 (nowy pion5, jakość8, formularz6); unit kontraktów/stanu22/22; pełny Admin unit738/738. Skoncentrowany lint siedmiu plików, tsc --noEmit, Prettier zmienionego kodu/testów, docs:check, code-map:check i diff --check PASS. Każda kontrola z subprocess timeout do120s.
- Szerszy test:geometry:215/225 PASS,10 FAIL w niezmienionym super-game-series-workspace.test.mjs: counts.undefined przy brakującym counts. Oddzielne uruchomienie odtwarza10 błędów; trzy pliki supergames identyczne z bazą377 po normalizacji końców linii. Dowód SHA w artifacts/audits/TASK-1011/unrelated-baseline.json; nie rozszerzano zakresu.
- Pierwsze interakcje17/18: niepełny mock LabCandidateRegistryPanel poprawiono; końcowe19/19 PASS. Pierwszy runner po PASS unit zapisał pełny UTF-8 log, lecz wydruk podsumowania trafił na cp1250; dalsze odczyty logów i runner używają jawnego UTF-8.
- Logi i wyniki: artifacts/audits/TASK-1011/{checks.json,focused-interactions.log,admin-unit.log,admin-interactions.log,baseline-super-games.log,lint.log,typecheck.log,map-generate.log,map-check.log,docs-check.log,diff-check.log}. Manifest dokładnych ścieżek/SHA: artifacts/audits/TASK-1011/manifest.json.

### Lead closure and audit disposition

- R1 Claude medium PASS; raport zachowany bez zmian, brak P0/P1. P2-1 przyjęte: produkcyjna fabryka klienta obsługuje ten sam wyłącznie odczytowy endpoint; mock modułu jest jawną izolacją testów. Nie rozszerzano istniejącego węższego ModelQualityClient bez potrzeby.
- P2-2 poprawione doprecyzowaniem własności zmian CURRENT_STATE. P2-3 zamknięte: lead wykonał pełne `npm run lint --workspace @game-predictor/admin`, exit0,0errors/5warnings w plikach niezmienianych przez1011; log `artifacts/audits/TASK-1011/full-admin-lint.log`.
- P2-4 przyjęte do TASK-1000: pełna sekcja przed odbiorem całego planu otrzyma zrozumiałe etykiety reasonCode i fallback. Surowe kody nie stanowią nowej oceny jakości ani samodzielnej blokady historycznego assignment. Jawny odsyłacz dopisano do taska1000.
- Nowy dowód niezwiązanych10FAIL: `artifacts/audits/TASK-1011/dependency-proof.json`. Domknięcie literalnych importów i re-exportów izolowanego supergames testu obejmuje46 lokalnych plików, identycznych z bazą377; żaden zmieniony moduł1011 nie jest osiągalny. Nie wykonano historycznego checkoutu/node_modules i nie raportuje się PASS pełnych interakcji.
- Kontrole zamknięcia DOC/map/diff oraz staged/stat/list i post-commit show/status prowadzi lead; ich receipt i hash zostaną zapisane po wykonaniu.

### Not completed

- Audyt zakończony PASS. Osobny commit prowadzi lead, integracja pozostaje niewykonana. Brak PASS pełnych interakcji przez niezwiązany zestaw supergames; fizyczny Android i odbiór na żywym API nie były wykonywane.
- Nie uruchamiano usług, bazy operatora, migracji, GPU, jobów, treningu, aktywacji ani backupu. Nie wykonywano stage, commita, merge ani push.

### Documentation updates

- ADMIN_APP opisuje odczyt assignment i stany V3; APP_V3_FUNCTIONAL_INVENTORY rozróżnia wdrożony odczyt od przyszłego treningu oraz wymienia zachowane pozostałości. Mapy zregenerowano po dodaniu modułu i symbolu. Wykonawca zmienił wyłącznie sekcję TASK-1011 w CURRENT_STATE; pozostałe wiersze diffu to księgowość leada po commicie1004/v1.7.377 oraz zamknięcie i posthash.
- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0999
