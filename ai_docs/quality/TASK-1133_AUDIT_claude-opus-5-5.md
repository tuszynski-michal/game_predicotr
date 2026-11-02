# Audyt TASK-1133 — Spójne przyciski i odstępy jakości rozpoznawania

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...a06fe75ed045cfbf2a10590ec11dc38974633cb3 oraz zmiany niezacommitowane, data 2026-11-02
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem niezacommitowaną zmianę w 12 plikach TSX z `apps/admin/src/features/model-quality/`, w `globals.css`, w `grid-correction-learning.css` oraz w `ADMIN_APP.md`, `CURRENT_STATE.md` i pliku taska. Porównałem ją z kryteriami akceptacji i arkuszem `packages/ui/src/buttons.css`. Diff liczony bez białych znaków potwierdza, że zmiana dotyczy wyłącznie klas, opakowań `buttonRow` i formatowania. Logika akcji, warunki `disabled`, guardy i etykiety się nie zmieniły. Wszystkie 79 przycisków w 12 zmienionych plikach ma `primaryButton` albo `secondaryButton`. Podział na primary i secondary jest spójny z kryterium. Zostały dwa drobne ryzyka prezentacyjne: odstęp akcji w rzadkim stanie odzyskiwania polecenia w panelu ponownego rozpoznania oraz obniżenie wysokości przycisków panelu uczenia z 44 px do 42 px.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `apps/admin/src/features/model-quality/grid-reinference-preview.tsx:435`: zagnieżdżona `<section aria-label="Zapisane polecenie">` nie pasuje do żadnej nowej reguły układu. Reguła `.modelQualityWorkflowGroup > details > section` w `apps/admin/src/app/globals.css:24` obejmuje tylko sekcję główną panelu. Dlatego przycisk „Ponów dokładne polecenie” (linia 445), etykieta z checkboxem (453) i przycisk „Archiwizuj i porzuć polecenie” (462) układają się w jednej linii. Między końcem etykiety a drugim przyciskiem nie ma odstępu, bo JSX w osobnych liniach nie tworzy spacji. Stan jest widoczny tylko przy zapisanym niepotwierdzonym poleceniu, więc oględziny w normalnym stanie go nie wykryły. Kryterium „akcje geometrii mają odstęp” jest tu spełnione tylko częściowo. Analogiczne miejsca w `recording-groups-panel.tsx` mają już układ grid przez `.recordingGroupsPanel aside`. Proponowana poprawka: nadać tej sekcji układ grid z `gap` przez lokalną klasę albo rozszerzyć selektor w `globals.css` na `.modelQualityWorkflowGroup section`. Druga opcja wymaga sprawdzenia wpływu na pozostałe sekcje. Można też zaakceptować ryzyko, bo to rzadki stan odzyskiwania.
- [P2-2] `apps/admin/src/features/model-quality/grid-correction-learning.css:16`: z reguły `min-height: 44px; padding: 0.5rem` usunięto selektor `.gridCorrectionLearning button`. Przyciski panelu uczenia mają teraz wysokość ze wspólnego arkusza, `min-height: var(--button-height, 42px)` (`packages/ui/src/buttons.css:3`). W Outcome TASK-1122 zapisano „kontrole co najmniej 44 px” (`ai_docs/tasks/completed/1122-grid-correction-learning-panel.md:117`). Wymagania tego panelu w `ADMIN_APP.md` nie określają minimum. Na ekranie dotykowym przyciski są więc o 2 px niższe niż wcześniej deklarowane i niższe niż pola `select`/`input` tego panelu (44 px). Proponowana poprawka: zostawić wspólny wygląd, ale na urządzeniach dotykowych dodać lokalnie `--button-height: 44px` w `.gridCorrectionLearning`, na przykład w `@media (pointer: coarse)`. Bez kopiowania kolorów. Można też świadomie zaakceptować 42 px jako zgodne z globalnym wzorcem i zapisać to w Outcome.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Przyciski akcji geometrii używają istniejącego primaryButton lub secondaryButton | spełnione | Statyczne liczenie: liczba `<button` równa liczbie klas primary/secondary w każdym pliku `model-quality/*.tsx`. W zmienionych plikach 13+5+9+4+6+2+5+11+1+6+14+3 = 79, zgodnie z Outcome. Klasy pochodzą z `packages/ui/src/buttons.css`, importowanego w `apps/admin/src/app/globals.css:2`. |
| Główne start/zastosowanie są primary, odczyty/nawigacja/anulowanie secondary | spełnione | `grid-cohort-preview.tsx:832`–`905` (odczyt secondary; przygotowanie, kopiowanie i zamrożenie primary; anulowanie secondary). `grid-correction-learning-panel.tsx:572` (podgląd zakresu secondary), `:593` (start primary). `grid-model-versions-panel.tsx:397`, `:427` (publikacja i aktywacja primary), `:460` (przywrócenie secondary). `grid-reinference-preview.tsx:528`–`616`. `grid-training-run-panel.tsx:443`–`490`. |
| Akcje symboli i geometrii mają odstęp i zawijają się na wąskim ekranie | spełnione z wyjątkiem P2-1; zachowanie na wąskim ekranie niezweryfikowane statycznie | `globals.css:16`–`22` (`flex-wrap`, `gap: 0.75rem`), `model-quality-workspace.tsx:775` (para Ulepsz rozpoznawanie / Przelicz oczekujące w `buttonRow` wewnątrz `.modelQualityWorkspace`), `globals.css:24`–`42`. Wykonawca deklaruje oględziny przy 390 px. |
| Istniejące interakcje, scoped lint/typecheck i docs:check PASS | niezweryfikowane | Nie uruchamiano poleceń. Wynik zadeklarowany w Outcome: 87/87 interakcji, ESLint, tsc, docs:check i code-map:check PASS. Diff bez białych znaków nie pokazuje zmian logiki. |
| Oględziny działającego panelu bez uruchomienia treningu; audyt bez P0/P1 | oględziny niezweryfikowane; audyt bez P0/P1 spełniony | Deklaracja w Outcome taska. Ten raport nie ma otwartych P0 ani P1. |
| Outcome, task-close, osobny commit i record-hash | niezweryfikowane (kroki po audycie) | Outcome uzupełniony w `ai_docs/tasks/1133-model-quality-button-styles.md`. Status nadal `in_progress`, commitu ani hasha jeszcze nie ma, co jest zgodne z kolejnością procesu. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- Ręczne oględziny panelu „Ponowne rozpoznanie” z wstrzykniętym zapisanym poleceniem w `localStorage` (stan `hasRawPending`), na szerokości desktopowej i przy 390 px. Potwierdzają P2-1 albo jego poprawkę. Bez wykonywania polecenia.
- Ponowne uruchomienie istniejących interakcji paneli po ewentualnej poprawce: `npm run test:geometry --workspace @game-predictor/admin`. W szczególności `test-interactions/grid-reinference-preview.test.mjs`, `grid-correction-learning-panel.test.mjs` i `grid-model-workspace.test.mjs`.
- Zgodnie z zakresem taska nie proponuję testów odwzorowujących same klasy CSS.

## Zakres przeglądu i ograniczenia

Przeczytałem brief z pełnym diffem, plik taska, `AGENTS.md` (reguły procesu, wyrywkowo), diff `CURRENT_STATE.md`, `packages/ui/src/buttons.css`, początek `apps/admin/src/app/globals.css` i cały `grid-correction-learning.css`. Przejrzałem też fragmenty po zmianie w `grid-model-workspace.tsx`, `model-quality-workspace.tsx`, `grid-reinference-preview.tsx`, `recording-groups-panel.tsx`, `grid-correction-apply-panel.tsx`, `grid-correction-learning-panel.tsx`, `grid-model-versions-panel.tsx`, `grid-cohort-preview.tsx` i `lab-candidate-registry-panel.tsx`, oraz Outcome TASK-1122. Używałem tylko poleceń odczytu (`grep`, `sed`, `git diff`). Nie uruchamiałem testów, lintu, typechecku, docs:check ani przeglądarki. Wyniki weryfikacji i oględziny opieram na deklaracji wykonawcy. Nie dało się statycznie potwierdzić rzeczywistego renderowania (kaskady, `fieldset` jako grid, zawijania przy 390 px) ani zachowania HMR działającego Admina.
