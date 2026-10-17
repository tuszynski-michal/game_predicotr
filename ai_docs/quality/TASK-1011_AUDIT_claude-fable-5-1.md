# Audyt TASK-1011 — Usunięcie zatwierdzonych pozostałości V1.1 z V3

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning medium
Wykonawca: gpt-6.1-sol, reasoning medium
Zakres: HEAD...70058ee5b71ec6e7383d7038648bd5c0dc6a2ead oraz zmiany niezacommitowane (13 plików wskazanych przez leada), data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano nowy komponent `grid-model-assignment-summary.tsx`, zmiany w `game-catalog.tsx`, `model-quality-workspace.tsx` i `catalog-workspace.tsx`, nowy test interakcji, zaktualizowane testy kontraktowe oraz dokumentację (ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, CURRENT_STATE, mapy kodu, plik taska). Zmiana trzyma się zatwierdzonego kontraktu: jedyny odczyt to istniejący `getGameGridModelAssignment(gameId)` dla renderowanej karty lub sekcji jakości, bez default lookup, mutacji, cache i retry; kod `7` ma pierwszeństwo przed konfiguracją, a legacy zachowuje klasyczny panel, gotowość i edycję historycznych wartości. Stany loading/error/unassigned/assigned są rozdzielone, obca lub niepełna odpowiedź daje błąd, a dostępność artefaktów i nieaktualny dowód są niezależne. Główne ryzyko to brak możliwości wstrzyknięcia klienta assignment do sekcji jakości (testy muszą mockować moduł fabryki klienta) oraz nieprecyzyjny zapis w Outcome o zakresie zmian w CURRENT_STATE; żadne z nich nie blokuje commita.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `apps/admin/src/features/model-quality/model-quality-workspace.tsx:900` — `GridModelAssignmentSummary` w sekcji jakości nie dostaje `client`, bo `ModelQualityClient` (`model-quality-actions.ts:65`) nie zawiera `getGameGridModelAssignment`. Skutek: komponent zawsze tworzy własnego klienta przez `createConfiguredAdminApiClient`, więc testy interakcji jakości muszą podmieniać moduł `api/admin-api-client.ts` hookiem ładowania (`apps/admin/test-interactions/v3-classical-ui-removal.test.mjs:19`), a wstrzyknięty `client` w `ModelQualityWorkspace` nie obejmuje tego odczytu. Proponowana poprawka: rozszerzyć `ModelQualityClient` o `getGameGridModelAssignment` i przekazać `client={props.client}` albo jawnie odnotować w Outcome, że mock modułu jest przyjętym sposobem izolacji.
- [P2-2] `ai_docs/tasks/1011-v3-classical-ui-removal.md:146` — zapis „W CURRENT_STATE zmieniono wyłącznie sekcję TASK-1011” nie zgadza się z diffem: zmienione są też wiersz „V3 rewizja 6” (`ai_docs/process/CURRENT_STATE.md:30`), wiersz TASK-1015 (`CURRENT_STATE.md:96`) i sekcja TASK-1004 z pełnym hashem v1.7.377 (`CURRENT_STATE.md:924`). Brief leada opisuje te zmiany jako księgowość leada po commicie 1004, co jest zgodne z regułą AGENTS.md o dopisaniu hasha. Proponowana poprawka: doprecyzować zdanie w Outcome (np. „wykonawca zmienił wyłącznie sekcję TASK-1011; pozostałe wiersze to zapis leada po commicie v1.7.377”).
- [P2-3] `ai_docs/tasks/1011-v3-classical-ui-removal.md:134` — sekcja Verification taska wymienia pełne `npm run lint --workspace @game-predictor/admin`, a wykonane zostało skoncentrowane ESLint siedmiu plików (`artifacts/audits/TASK-1011/checks.json:16`). ESLint działa per plik i wszystkie zmienione pliki zostały objęte, więc ryzyko regresji jest niskie. Proponowana poprawka: uruchomić pełny lint workspace przed commitem albo zapisać w Outcome, że kontrola była skoncentrowana z uzasadnieniem.
- [P2-4] `apps/admin/src/features/games/grid-model-assignment-summary.tsx:88` i `:93` — komunikaty pokazują surowe kody (`reasonCode`, `eligibilityReasonCode`) bez etykiet. Zgodne z kontraktem (komponent nie tłumaczy katalogu kodów), ale operator widzi identyfikatory techniczne. Akceptacja ryzyka: etykiety kodów należą do TASK-1000 (pełna sekcja „Geometria V3”); odnotować w Outcome.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| V3 nie pokazuje klasycznych działań; pokazuje stan przypisanej wersji | spełnione | Sekcja jakości: `model-quality-workspace.tsx:891-903` montuje `GridModelAssignmentSummary` zamiast `GridQualityPanel` dla `usesNeuralGridConfiguration`. Karta: `game-catalog.tsx:957-965` zastępuje gotowość klasyczną, `game-catalog.tsx:941-951` ukrywa tekst profilu silnika dla V3. Stany: `grid-model-assignment-summary.tsx:38-43` (obca/niepełna odpowiedź → błąd), `:64-71` (loading/error nie udają unassigned), `:73-78` (brak assignment → blokada importu), `:79-81` i `:88-97` (niezależne dostępność i stale). Reset przy zmianie gry: `:19` (`key={gameId}`), `:33-50` (`cancelled`). Testy: `v3-classical-ui-removal.test.mjs:94`, `:135`, `:157`, `:190`, `:237`. Formularz create bez pickera i z neutralnym `neural_grid_v3`: `game-catalog.tsx:455-477`, `game-catalog-state.ts:38`, `new-game-create-command.ts:92`. |
| Stara 777 nadal poprawnie odczytuje historyczne wartości i raporty | spełnione | `game-catalog-state.ts:130-140` (`gameCode !== '7'` ma pierwszeństwo). Legacy picker z `framed_full_page_v2`/`requires_clarification`: `game-catalog.tsx:688-721`, `game-catalog-state.ts:88-97`; zapis przez `updateGame` z `shapeGeometryConfiguration`: `game-catalog-actions.ts:116-122`. Klasyczny panel dla kodu 7: `model-quality-workspace.tsx:905-926`. Testy: `v3-classical-ui-removal.test.mjs:178-180` (kod 7 → raporty, zero wywołań assignment), `:257-260` (karta legacy z profilem wspólnym i komunikatem). Brak zmian w enumach generowanego klienta. |
| Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Outcome wypełniony kontrolami i ograniczeniami (`1011-v3-classical-ui-removal.md:112-146`); raport audytu i commit jeszcze nie istnieją, więc kryterium domyka się po tej rundzie. Dokumentacja zgodna z kodem: `ADMIN_APP.md:100-108`, `APP_V3_FUNCTIONAL_INVENTORY.md:58`, `:107`, `:117`. Zastrzeżenie P2-2 dotyczy precyzji zapisu w Outcome. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- Test kontraktowy przewodu z `CatalogWorkspace` do `ModelQualityWorkspace`: asercja w `apps/admin/test/catalog-workspace-contract.test.mjs` (lub istniejącym teście kontraktu katalogu), że źródło `catalog-workspace.tsx` zawiera `gameCode={activeGame.code}` i `shapeGeometryConfiguration={activeGame.shapeGeometryConfiguration}` (`catalog-workspace.tsx:577-580`). Dziś nowy test interakcji renderuje `ModelQualityWorkspace` bezpośrednio z propsami, więc brak przekazania z katalogu nie zostałby wykryty. Komenda: `npm run test --workspace @game-predictor/admin`.
- Po ewentualnym rozszerzeniu `ModelQualityClient` (P2-1): przypadek w `v3-classical-ui-removal.test.mjs`, w którym `client` wstrzyknięty do `ModelQualityWorkspace` obsługuje `getGameGridModelAssignment` bez hooka na `api/admin-api-client.ts`. Komenda: `npm run test:geometry --workspace @game-predictor/admin`.
- Regresja dla nieznanego kodu `reasonCode`/`eligibilityReasonCode` (np. nowy kod z backendu) potwierdzająca, że komponent nadal pokazuje przypisanie i nie traktuje go jako stale ani jako błędu (`grid-model-assignment-summary.tsx:79-81`).

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief, plik taska (sekcje Scope, Out of scope, Technical notes, Expected files, Verification, Outcome), fragment planu, diff zmian niezacommitowanych, pełną treść `grid-model-assignment-summary.tsx` i `v3-classical-ui-removal.test.mjs`, `game-catalog.tsx` (linie 1-140, 140-380, 380-1039), `game-catalog-state.ts` (linie 1-243 w częściach), `saveGameIdentity` w `game-catalog-actions.ts`, definicje `GamesClient` i `ModelQualityClient`, typy generowane `GameGridModelAssignmentResponse`, `GridModelVersionResponse`, `GridModelManifest` (pola `familyLabel`, `version`, `versionId`, `available`, `reasonCode`, `eligibilityReasonCode` istnieją), `new-game-create-command.ts` w zakresie `shapeGeometryConfiguration`, nagłówek `model-quality-loading.test.mjs`, importy `super-game-series-workspace.tsx`, `checks.json` i `unrelated-baseline.json` w `artifacts/audits/TASK-1011/`, sekcję audytową AGENTS.md (linie 340-389).

Zależność niezwiązanych błędów supergames: `super-game-series-workspace.tsx` importuje wyłącznie `@game-predictor/board-search-ui`, `@/api/admin-api-client`, własny CSS i własne moduły; nie importuje żadnego z 13 plików taska, a błąd `counts.undefined` pochodzi z `super-game-series-state.ts:101` przy `counts` innym niż `null`. Moduły zmienione w TASK-1011 nie mogą wpływać na ten zestaw. Nie wykonano uruchomienia na bazie 377 ani odczytu historii git (sesja bez narzędzia powłoki), więc pochodzenie błędów z upstreamu pozostaje potwierdzone tylko przez manifest SHA wykonawcy.

Nie uruchamiano testów, lintera, typecheck ani usług; wyniki 738/738 unit, 19/19 skoncentrowanych interakcji i 215/225 pełnych interakcji przyjęto z `checks.json` i Outcome bez niezależnej reprodukcji. Nie weryfikowano zachowania na żywym API ani liczników w wygenerowanych mapach kodu poza spójnością z dodanym plikiem i symbolem.
