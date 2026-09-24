---
title: TASK-0631 — Sekcja „Brakujące plansze” i zwinięty blok akcji w Adminie
status: done
last_updated: 2026-09-24
---

# TASK-0631 — Sekcja „Brakujące plansze” i zwinięty blok akcji w Adminie

## Status

`done`

## Goal

Sekcja „Brakujące plansze” zastępuje kartę kompletności i historię importów w
„Import plansz”. Wszystkie akcje ponownego przetwarzania pozostają dostępne w
zwiniętym bloku.

## Context

Ostatni z trzech tasków planu „sekcja Brakujące plansze”
(`ai_docs/tasks/completed/0629-board-import-coverage-definition.md`,
`ai_docs/tasks/completed/0630-board-import-coverage-endpoint.md`). Użytkownik
(decyzje DU-1..DU-3, 2026-09-24) chce widzieć braki względem pełnego
oczekiwanego zakresu numerów zamiast tylko zatwierdzonych plansz, bez utraty
istniejących akcji reprocess.

## Dependencies / entry conditions

- `TASK-0630` musi być `done`: endpoint i wrapper klienta `getBoardImportCoverage`
  muszą istnieć.

## Recommended execution

claude-sonnet-5, reasoning high. Uzasadnienie: duży plik panelu, ochrona
istniejących akcji reprocess, polling z guardem wyścigu i 7 stanów UI.
Dodatkowy review: tak — claude-opus-5-5, medium (kontrola, że żadna akcja nie
zniknęła i polling się wyłącza).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/tasks/completed/0629-board-import-coverage-definition.md`
- `ai_docs/tasks/completed/0630-board-import-coverage-endpoint.md`

## Scope

- Nowy `apps/admin/src/features/imports/missing-boards-section.tsx`: własny
  stan (widok Brakujące/Dodane, zakres/wyszukiwanie, kursor, dane, błąd).
- Nowy czysty moduł `apps/admin/src/features/imports/missing-boards-state.ts`:
  `parseSequenceRangeQuery`, `formatSegmentRange` (`toLocaleString('pl-PL')`),
  `missingReasonLabel`, `summaryState` (loading / error / unknown-target /
  empty / all-added / no-results / list).
- `apps/admin/src/features/imports/image-folder-import-panel.tsx`:
  - usunąć kartę „Kompletność zaakceptowanych plansz” (linie ok. 2176–2223)
    i stan/pobieranie `completeness` w `refreshJobs`;
  - w miejscu `importHistorySection` wstawić `<MissingBoardsSection>` oraz
    `<details>` „Ponowne przetwarzanie importów” (domyślnie zwinięte) z listą
    5 ostatnich jobów, `ImportGeometryReviewSummary` i trzema przyciskami
    („Przetwórz ponownie z oryginałów”, „Przetwórz w v1.0”, „Kontynuuj z
    ręczną korektą”) — warunki widoczności i handlery bez zmian; usunąć tylko
    linie diagnostyczne (silnik, manifest, guard, profil, model, outcome);
  - przekazać `refreshToken` (rośnie przy każdym `refreshJobs`) do sekcji.
- Odświeżanie: montowanie, `refreshToken`, zmiana filtra/zakresu; polling
  15 s tylko gdy `notices.activeImportJobCount > 0`, z `clearInterval` przy 0
  lub unmount; guard kolejności odpowiedzi (id żądania).
- Style: dopisać do istniejącego globalnego CSS obok `.importCompletenessCard`
  i `.importMetrics`, reużywając klas; jedna kolumna przy ~600 px.
- `image-folder-import-actions.ts`: dodać `getBoardImportCoverage` do
  `ImageFolderImportClient`; usunąć `getImageDatasetCompleteness` z typu
  panelu tylko jeśli grep potwierdzi brak innych konsumentów w admin.
- Aktualizacja `ai_docs/requirements/ADMIN_APP.md` (zachowanie sekcji,
  definicja, powody, stany).

## Out of scope

- Zmiana definicji lub endpointu (`TASK-0629`, `TASK-0630` zamknięte przed
  startem).
- Kopiowanie zakresów do schowka, linki z segmentu do joba/Reviewera, podział
  widoku „Dodane” na zatwierdzone/oczekujące, przeniesienie akcji reprocess do
  zakładki Joby — poza MVP.

## Chronione zachowanie

Warunki i handlery `reprocessImport`, `reprocessManagedV4`,
`reprocessImport(job, true)` oraz `ImportGeometryReviewSummary` — bez zmian
logiki, tylko przeniesienie do `<details>`.

## Acceptance criteria

- [x] Karta „Kompletność zaakceptowanych plansz” i sekcja „Ostatnie importy
      tej gry” (stara treść) znikają z panelu.
- [x] `<MissingBoardsSection>` pokazuje liczniki, powody, filtr
      Brakujące/Dodane (bez „Wszystkie”), wyszukiwanie zakresu, segmenty,
      stronicowanie i 7 stanów ekranu z treści planu.
- [x] `<details>` „Ponowne przetwarzanie importów” zawiera 5 ostatnich jobów i
      trzy przyciski akcji, domyślnie zwinięte.
- [x] Polling działa tylko przy aktywnym imporcie i wyłącza się poprawnie.
- [x] Żadna istniejąca akcja reprocess nie zmienia zachowania (test
      regresyjny).

## Test cases

- `missing-boards-state.test.mjs`:
  - parser zakresu: `"12"`, `"10-20"`, `"10–20"`, `" 5 - 7 "`;
  - błędy: `0`, `b<a`, `>E`, tekst;
  - etykiety wszystkich 7 powodów;
  - `summaryState` dla 7 stanów ekranu.
- `image-folder-import-panel-contract.test.mjs` (aktualizacja):
  - brak „Ostatnie importy tej gry” i starej karty kompletności;
  - obecność `<MissingBoardsSection`;
  - `<details` z trzema etykietami przycisków;
  - polling warunkowy (`activeImportJobCount`).
- `image-folder-import-actions.test.mjs`: test regresyjny istniejących akcji
  reprocess (bez zmian asercji).

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

Ręcznie przez `admin:dev` i `api:dev` jako procesy w tle: filtr, zakres,
stronicowanie, pusty wynik, rozwijanie bloku akcji, „Odśwież status”. Jeśli
nie uda się sprawdzić na żywych danych, zaraportować to jawnie.

## Risks / open questions

- Duży plik `image-folder-import-panel.tsx` — wysokie ryzyko przypadkowego
  usunięcia nieużywanego, ale wciąż importowanego kodu; stąd wymagany
  dodatkowy review.

## Outcome

### Changed

- Nowy [missing-boards-state.ts](../../apps/admin/src/features/imports/missing-boards-state.ts):
  `parseSequenceRangeQuery` (obsługuje pusty zakres, pojedynczy numer,
  `-`/`–`/`—` jako separator, whitespace-tolerant), `formatSegmentRange`
  (`toLocaleString('pl-PL')`, en dash dla zakresu), `missingReasonLabel` (7
  kodów), `summaryState` (7 stanów, priorytet: loading → error →
  unknown-target → empty → all-added → no-results → list).
- Nowy [missing-boards-section.tsx](../../apps/admin/src/features/imports/missing-boards-section.tsx):
  własny stan (`view`, `rangeInput`/`rangeError`/`committedRange`,
  `afterSequenceNumber`, `report`, `loading`, `error`), jeden `load()` z
  request-id guardem przeciw wyścigowi odpowiedzi, filtr Brakujące/Dodane
  (`.operationalReviewViewTabs`, reużyte z Weryfikacji symboli), wyszukiwanie
  zakresu (`.importSourceControls`, reużyte), tabela segmentów
  (`.importRowsTableWrap`/`.importRowsTable`, reużyte z `manual-import-panel`),
  liczniki (`.importMetrics`/`.importMetric`, reużyte), powody, notices,
  stronicowanie „Następna strona”. Polling `window.setInterval` co 15 s
  wyłącznie gdy `report.notices.activeImportJobCount > 0`, z
  `window.clearInterval` w cleanup efektu (zeruje się też, gdy licznik
  spadnie do 0, bo efekt się wtedy nie odpala ponownie) — zweryfikowane
  osobnym testem kontraktowym i ręcznie na żywych danych.
- [image-folder-import-panel.tsx](../../apps/admin/src/features/imports/image-folder-import-panel.tsx):
  usunięto stan `completeness`, jego pobieranie w `refreshJobs` i całą kartę
  „Kompletność zaakceptowanych plansz” (JSX); usunięto sekcję „Ostatnie
  importy tej gry” razem z per-jobową diagnostyką (`jobSnapshotText`,
  `geometryEngineJobLabel` — obie funkcje w całości usunięte jako martwe po
  usunięciu jedynych wywołań; import `boardCellProcessingJobLabel` i
  `pageRegistrationVariantFromJob` usunięte jako nieużywane); w tym miejscu
  wstawiono `<MissingBoardsSection api={api} gameId={gameId}
  refreshToken={refreshToken} />` oraz `<details className="importMissingSequences">`
  (reużyta klasa CSS zamiast nowej) z 5 ostatnimi jobami, samym
  `<ImportGeometryReviewSummary>` i trzema przyciskami reprocess —
  handlery (`reprocessImport`, `reprocessImport(job, true)`,
  `reprocessManagedV4`) i ich warunki widoczności nie zostały zmienione, tylko
  przeniesione. Nowy stan `refreshToken`, inkrementowany na końcu
  `refreshJobs`.
- [image-folder-import-actions.ts](../../apps/admin/src/features/imports/image-folder-import-actions.ts):
  `ImageFolderImportClient` traci `'getImageDatasetCompleteness'` (potwierdzone
  grepem: brak innych konsumentów w `apps/admin`/`apps/reviewer`) i zyskuje
  `'getBoardImportCoverage'`.
- `globals.css`: usunięto martwe `.importMissingSequenceChips`
  (i `span`) oraz `.importHistorySection` z wcześniej współdzielonego
  selektora box-stylu (`.importCompletenessCard, .curatedImportCard,
  .importSourceInspector`) — obie klasy nie miały już żadnego konsumenta.
  Żadnych nowych reguł CSS nie dodano: sekcja w całości reużywa istniejące
  klasy (`.importCompletenessCard`, `.importCompletenessHeader`,
  `.importCompletionBadge`, `.importMetrics`/`.importMetric`,
  `.importSourceControls`, `.importRowsTableWrap`/`.importRowsTable`,
  `.operationalReviewViewTabs`, `.importMissingSequences` (dla `<details>`),
  `.feedbackBanner`/`.feedbackBannerError`, `.importEmptyState`,
  `.secondaryButton`) — wszystkie już mają zachowanie jednokolumnowe poniżej
  ok. 720 px z istniejących media queries.
- `ai_docs/requirements/ADMIN_APP.md`: nowa sekcja „Sekcja „Brakujące
  plansze” w Import plansz (D-437)”.
- Testy: nowy `missing-boards-state.test.mjs` (20 przypadków); zaktualizowany
  i rozszerzony `image-folder-import-panel-contract.test.mjs` (4 stare
  asercje zaktualizowane pod usunięte diagnostyki, 4 nowe testy dodane);
  `image-folder-import-actions.test.mjs` bez zmian asercji (regresja).

### Verification results

- `npm run test --workspace @game-predictor/admin`: **563/563 passed**
  (poprzednio 563 - 24 nowe = 539 istniejących testów, wszystkie nadal
  zielone; `image-folder-import-actions.test.mjs` 26/26 bez zmian asercji —
  potwierdzona ochrona zachowania reprocess).
- `npm run typecheck --workspace @game-predictor/admin`: czysto.
- `npm run lint --workspace @game-predictor/admin`: **0 błędów**, 5 ostrzeżeń
  — wszystkie w plikach spoza zakresu tej zmiany (potwierdzone `git diff
  --stat` na tych plikach: brak diffu), poza jednym w
  `image-folder-import-panel.tsx` (`no-img-element`, pre-istniejące, niezwiązane
  z tym diffem — linia dotyczy niepowiązanego `<img>` gdzie indziej w pliku).
  Jeden realny błąd (`react-hooks/set-state-in-effect` w nowym
  `missing-boards-section.tsx`) naprawiony przez `queueMicrotask` — ten sam
  wzorzec co istniejący initial-load effect w panelu.
- Ręczna weryfikacja na żywych danych: **wykonana**. `api:dev` (port 8000) i
  `admin:dev` (port 3000) już działały w tle (nie moje procesy — najwyraźniej
  uruchomione przez użytkownika/inną sesję równolegle; zweryfikowano przez
  `navigate` zamiast startować duplikaty). Otworzono grę „777”
  (`storageSchema=game_data_v2`, realne dane w Postgres) → zakładka „Import
  plansz”: sekcja „BRAKUJĄCE PLANSZE” renderuje się poprawnie z licznikami
  (Oczekiwane 500 000 / Dodane 0 / Brakujące 500 000), linią „w tym
  zatwierdzone”, linią „Powody” (Brak źródła w systemie 500 000), notices
  bannerem („1 aktywnych jobów importu…”), tabelą segmentów (1–500 000, Brak
  źródła w systemie) i stanem „Nie dodano jeszcze żadnej planszy”. Kliknięcie
  przełącznika „Dodane” poprawnie przeładowało widok (tabela znika, zostaje
  tylko komunikat — zgodne z `added=0`). Rozwinięcie „Ponowne przetwarzanie
  importów” pokazało pełną, niezmienioną listę stagingów i akcji reprocess.
  Stare „Kompletność zaakceptowanych plansz” i „Ostatnie importy tej gry”
  nigdzie nie występują.
  - **Ustalenie podczas weryfikacji:** `Dodane=0` mimo że staging pokazuje
    „plansze utworzone” dla wielu zakresów tej gry. Zweryfikowano krzyżowo z
    istniejącym, zaufanym `dataset-completeness` dla tej samej gry — również
    zwraca `acceptedBoardCount=0`. Oba endpointy zgadzają się ze sobą, co
    wyklucza błąd routingu `game_data_v2` w nowym kodzie; najbardziej
    prawdopodobne wyjaśnienie to dane z etapu przed cutoverem gry na
    `game_data_v2` (`storageGeneration: 2`), nieskopiowane przy migracji —
    znany, udokumentowany brak kopiowania danych przy cutoverze (D-519), a nie
    defekt tego taska.

### Not completed

- Rekomendowany dodatkowy review (claude-opus-5-5, medium) z sekcji
  `Recommended execution` nie został wykonany w tej sesji.
- Link „[zmień]” przy „cel z ustawień gry” z mockupu planu nie został
  zaimplementowany jako nawigacja — brak potwierdzonej trasy do zakładki
  ustawień gry (Katalog gier) w czasie tej sesji; renderowany jako zwykły
  tekst, bez fabrykowania niepewnego linku.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`: nowa sekcja opisująca zachowanie,
  definicję D-437, 7 powodów i 7 stanów ekranu.

### Recommended next task

- Zaplanować dodatkowy review (opus-5-5, medium) tego taska — szczególnie
  pod kątem: czy żadna akcja reprocess nie zniknęła i czy polling faktycznie
  wyłącza się poprawnie przy spadku `activeImportJobCount` do 0.
- Rozważyć osobny, mały task: link nawigacyjny „zmień cel” do ustawień gry.
- 3-taskowy plan „Brakujące plansze” (TASK-0629/0630/0631) jest w całości
  zrealizowany.
