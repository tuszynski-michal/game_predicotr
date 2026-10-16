---
title: TASK-1000 — Pełna sekcja „Geometria V3”
status: done
last_updated: 2026-10-16
---

# TASK-1000 — Pełna sekcja „Geometria V3”

## Status

`done`

## Goal

Udostępnić cały proces z poziomu gry.

## Context

Task jest częścią zaakceptowanej rewizji 6. Integracja gotowych funkcji panelu. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0995, TASK-0997, TASK-0998, TASK-1003, TASK-1011; bez zależności od pozytywnego wyniku TASK-1006.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`medium`; wybór wykonawcy po sugestii operatora 2026-10-16, uzasadnienie w sekcji 8 planu). integracja gotowych kontraktów.
- Dodatkowy review: `gpt-6-astra` (przy braku dostępności `gpt-6.1-sol`), reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- [Audyt TASK-1011](../../quality/TASK-1011_AUDIT_claude-fable-5-1.md), P2-4: przed odbiorem całego planu zastąpić techniczne reasonCode/eligibilityReasonCode zrozumiałymi etykietami i fallbackiem w pełnym panelu/shared summary. Zachować odrębność dostępności i aktualności dowodu; kod nie jest samodzielną oceną jakości.

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- Zakres odczytu uzupełniający z planu: ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, D-527/D-541.

- [D-527](../../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Diagnostyka, próbka, korekty, dane, run, porównanie, wersje i ponowne rozpoznanie.
- Backend określa dostępność działań.
- Brak danych pokazuje konkretne wymagania.

## Out of scope

- Bez połączenia treningu symboli z geometrią i bez przebudowy archiwalnej 777.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Proces działa bez skryptów operatora.
- [ ] Zwykły przebieg używa nazw gier, importów, nagrań i wersji; operator nie musi wpisywać technicznych UUID ani składni poleceń.
- [ ] Wejście na ekran nie uruchamia joba.
- [ ] Zmiana gry/reload zachowuje właściwy stan.
- [ ] Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Diagnostyka, próbka, korekty, dane, run, porównanie, wersje i ponowne rozpoznanie. Backend określa dostępność działań. Brak danych pokazuje konkretne wymagania.

Integracja zastępuje techniczne pola wejściowe pomocniczych paneli powstałych we wcześniejszych taskach, w tym pól family/base/source/recording UUID z pierwszego preview0995. Operator wybiera import/nagrania i zgodną wersję po czytelnych nazwach w istniejącym katalogu gry. Przypięty identyfikator pozostaje wewnętrzną wartością wyboru; opcjonalne szczegóły diagnostyczne mogą go pokazać. Nie ukrywamy rozstrzygnięć ról lub zakresu pod automatycznym wyborem. Stosujemy istniejące kontrakty katalogu/nagrań/importów oraz ich stronicowanie, zamiast wymagać kopiowania identyfikatorów ze skryptów. Dotychczasowe pomocnicze formularze nie stanowią odbioru finalnego procesu operatora. Kwalifikacja metadanych oraz bieżąca dostępność bajtów pozostają rozróżnione zgodnie z D-556.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

### Kontrakt przed kodem (2026-10-16, Claude Code)

Stan zastany (v1.7.390): sekcja „Geometria V3” montuje podsumowanie przypisania, nagrania, kontrolę jakości, kohorty i porównanie. Kohorty wymagają wpisania UUID rodziny, bazy, źródeł/importu i nagrań; porównanie wymaga wierszy „gra kohorta” w UUID; brak UI runów treningu, publikacji, aktywacji, default i rollback; ponowne rozpoznanie jest montowane tylko dla gier klasycznych; kody `reasonCode`/`eligibilityReasonCode` i powody kohort są pokazywane surowo (P2-4 TASK-1011).

- **Jeden przebieg w `grid-model-workspace.tsx`** (montowany przez `ModelQualityWorkspace` dla gier V3, klucz gry): 1. przypisanie i wersja, 2. nagrania, 3. kontrola jakości (próbka), 4. dane (kohorty), 5. trening, 6. porównanie z bazą, 7. wersje (publikacja, aktywacja, default, rollback, historia), 8. ponowne rozpoznanie. Korekty pozostają w istniejącym Reviewerze. Wejście, zmiana gry i reload wykonują wyłącznie GET; każda mutacja to jawny przycisk.
- **Nazwy zamiast UUID:** rodzina i baza kohorty pochodzą z przypisania gry (etykieta rodziny i wersji), import wybierany po nazwie i dacie (istniejący picker), nagrania z listy nagrań gry z etykietą i rolą; kohorty, runy, wersje i oceny mają etykiety daty, trybu, statusu i nazwy wersji; inne gry porównania i runu wspólnego wybiera się po nazwie gry, a ich kohortę po etykiecie. Dokładne UUID zdjęć i uzupełnienie tożsamości źródeł zostają w zwiniętych sekcjach „Zaawansowane”; identyfikator jest wewnętrzną wartością wyboru.
- **Dostępność z backendu:** run startuje tylko bez `apiBlockers` podglądu (zajętość GPU nie blokuje kolejki), anulowanie/wznowienie według statusu runu, publikacja tylko dla oceny `PASS` z aktualnymi dowodami wszystkich kohort, aktywacja i default tylko dla wersji `eligible`, rollback tylko do wersji z historii gry; każdy brak pokazuje etykietę powodu, a backend i tak sprawdza polecenie.
- **Etykiety kodów:** `grid-model-state.ts` mapuje kody `GRID_MODEL_*`, `GRID_RUN_*`, `GRID_EVALUATION_*`, `GRID_SHARED_*`, `GRID_COHORT_*`, `SOURCE_*`, `RECORDING_*` i powody kohort na tekst; nieznany kod ma fallback „Inny powód (KOD)”. Dostępność artefaktów, publikacja, kwalifikacja i aktualność dowodu pozostają osobnymi informacjami.
- **Polecenia:** run, publikacja, aktywacja, default i rollback zapisują klucz i treść w `localStorage` (zakres API, gry i rodzaju) przed POST; utrata odpowiedzi zachowuje polecenie, ponowienie jest jawne; zmiana gry odrzuca spóźnione odpowiedzi.
- **Bez zmian API i migracji**; używane są istniejące wrappery klienta.

## Expected files

- Istniejące: [model-quality-workspace.tsx](../../apps/admin/src/features/model-quality/model-quality-workspace.tsx) — `ModelQualityWorkspace`, montowanie klasycznego panelu.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejąca nawigacja; nowe proponowane `grid-model-workspace.tsx`, `grid-model-state.ts`, `grid-model-client.ts`; wcześniejsze panele.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `apps/admin/src/features/model-quality/v3_grid_model_workspace.test.ts`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Proces działa bez skryptów operatora.
- Wybór importu, nagrań i wersji po nazwach tworzy poprawne przypięte polecenie bez ręcznie wpisanych UUID; zmiana gry usuwa obce wybory, a reload nie uruchamia mutacji.
- Wejście na ekran nie uruchamia joba.
- Zmiana gry/reload zachowuje właściwy stan.
- Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem.

## Verification

Zakres: ADMIN, testy transportu i interakcji, DOC.

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

- Bez połączenia treningu symboli z geometrią i bez przebudowy archiwalnej 777.

## Outcome

### Execution phase

- Wykonano 2026-10-16: Claude Code `claude-opus-5-5`/`high`, baza v1.7.390 `9bf3a4b9315fecdd7a55e71a857d376e769bf70c`; przed audytem gałąź scaliła `main` v1.7.385 (v1.7.391 `1b38ae6c`, skille `task-close`/`merge-to-main`). Branch `codex/v3-grid-fine-tuning`, worktree `D:\game_predicotr\worktrees\v3-grid-fine-tuning`.
- Kontrakt przed kodem w Technical notes. Bez migracji; runda poprawek rozszerzyła kontrakt API selektora kohorty (pion: backend, OpenAPI, klient, test żądania).
- Commit: v1.7.392 (hash dopisuje kolejny commit).
- Audyt R1: Codex `gpt-6-astra`/`medium`, limit 1200 s — [raport R1](../../quality/TASK-1000_AUDIT_gpt-6-astra_R1.md), werdykt REVISE: P0-1, P0-2, P0-3, P1-1, P2-1, P2-2. Jedna runda poprawek poniżej.
- Audyt R2: [raport R2](../../quality/TASK-1000_AUDIT_gpt-6-astra_R2.md), werdykt REVISE: zamknięte P0-1, P0-3, P1-1, P2-2; otwarte P0-2 (forki rodzin), P2-1 (zakończenie runu, nowe oceny), P2-3 (nieaktualny wpis). Operator 2026-10-16 wybrał drugą rundę poprawek; audyt R3 po niej.
- Audyt R3: [raport R3](../../quality/TASK-1000_AUDIT_gpt-6-astra_R3.md), werdykt **PASS**, brak P0/P1; zamknięte P0-2, P2-1, P2-3. Jedyne P2-4 (szczegóły wybranej oceny po sprawdzeniu aktualności w innym kroku) poprawione przed commitem: odświeżenie panelu wersji czyta ponownie wybraną ocenę z ochroną przed spóźnioną odpowiedzią; test interakcji dopisany.

### Changed

- `grid-model-workspace.tsx`: cały przebieg V3 w kolejności pracy (przypisanie, nagrania, kontrola jakości, kohorty, trening, porównanie, wersje, ponowne rozpoznanie — wcześniej niedostępne dla gier V3), montowany przez `ModelQualityWorkspace` z kluczem gry.
- `grid-model-state.ts`: etykiety kodów `GRID_MODEL_*`, `GRID_RUN_*`, `GRID_TRAINING_*`, `GRID_SHARED_*`, `GRID_EVALUATION_*`, `GRID_COHORT_*`, `SOURCE_*`, `RECORDING_*` i powodów oceny D-559 z fallbackiem „Inny powód (KOD)” (P2-4 TASK-1011), etykiety wersji, kohort, treningów i gier, bramka publikacji z oceny i aktualności, trwałe polecenia w `localStorage`.
- Nowe panele: `grid-training-run-panel.tsx` (kohorta po etykiecie, podgląd z blokadami, opcjonalny kandydat wspólny z innymi grami V3 po nazwie, lista treningów z anulowaniem i wznowieniem) i `grid-model-versions-panel.tsx` (publikacja kandydata z oceną PASS i aktualnymi dowodami, aktywacja, wersja domyślna, przywrócenie z historii, historia gry).
- Kohorty: rodzina i baza z przypisania gry, import przez istniejący picker, nagrania z listy z rolami, UUID zdjęć i uzupełnienie tożsamości w „Zaawansowane”, etykiety kohort, kwalifikacji i powodów. Porównanie: inne gry i ich kohorty po nazwach, kohorty wspólnego treningu dodawane zawsze, nazwy gier i etykiety powodów zamiast UUID i kodów. Kontrola jakości: trudne przykłady w „Zaawansowane”. Podsumowanie przypisania: etykiety kodów.
- Odczyty montowania przez `Promise.resolve().then`, aby brak lub błąd jednego odczytu nie przerywał pozostałych.
- Testy: nowe `test/grid-model-state.test.mjs` i `test-interactions/grid-model-workspace.test.mjs`; aktualizacje `grid-cohort-preview`, `v3-classical-ui-removal`, `model-quality-workspace-contract`, `grid-model-evaluation-state` (etykiety zamiast surowych kodów, kilka odczytów tego samego przypięcia, usunięte parsowanie wierszy UUID).

### Runda poprawek po audycie R1

- P0-1: selektor kohorty przyjmuje kilka importów (`importJobIds`, 2–50, unikalne, wyłącznie jedna forma wyboru); backend wymaga, aby każdy import miał własne zdjęcia gry (`GRID_COHORT_SELECTION_UNAVAILABLE`), a router zachowuje dotychczasowy kształt treści bez tego pola, więc replay starych poleceń się nie zmienia. Formularz zbiera importy wybranych nagrań i opcjonalny import z pickera po nazwie; jeden import wysyła dotychczasowe `importJobId`. Walidator zapisanych poleceń akceptuje dokładnie jedną formę wyboru.
- P0-2: baza treningowa jest wyborem po nazwie z katalogu dostępnych wersji (domyślnie przypisanie gry); rodzina pochodzi z wybranej wersji, a dla wersji przypisanej z rodziny treningowej przypisania. Przypisanie gry nie jest zmieniane; rodowód sprawdza backend.
- P0-3: kohorty (panel treningu, inne gry w treningu i porównaniu) i nagrania są czytane ze wszystkich stron (`readAllPages`, limit 50 stron z jawnym błędem).
- P1-1: utrata odpowiedzi runu i polecenia wersji przetrwa odmontowanie i nowy mount z tym samym storage, bez automatycznego POST; jawne ponowienie wysyła identyczny klucz i treść; odmowa 4xx (409) usuwa polecenie i odczytuje stan, a 5xx lub brak odpowiedzi je zachowuje.
- P2-1: potwierdzona zmiana nagrania, kohorty, runu, oceny, aktualności lub wersji odświeża listy pozostałych kroków i podsumowanie przypisania (`refreshKey`/`onChanged` w `GridModelWorkspace`).
- P2-2: każda zmiana wyboru kohorty, kandydata i oceny, także na pusty, unieważnia spóźnioną odpowiedź; ocena jest przyjmowana tylko dla bieżącego identyfikatora.
- Odczyty jednego panelu startują w osobnych obietnicach, aby błąd jednego odczytu nie zostawiał innej obietnicy bez obsługi.

### Druga runda poprawek po audycie R2 (decyzja operatora)

- P0-2: rodzina treningowa jest osobnym wyborem po nazwie spośród rodziny wybranej bazy i rodzin treningowych (forków) wszystkich gier V3 przypisanych do tej bazy, odczytanych z ich przypisań (tylko odczyty, bez zmian API). Domyślnie przypisana baza używa rodziny treningowej gry, inna baza — rodziny bazy; zmiana bazy przywraca domyślną rodzinę. Przypisania gier się nie zmieniają; rodowód sprawdza backend.
- P2-1: panel treningu czyta listę co 15 s wyłącznie, gdy run czeka lub trwa, i ma przycisk „Odśwież stan treningów”; run zakończony przez worker powiadamia raz pozostałe kroki. Odświeżenie panelu wersji czyta też oceny wybranego kandydata.
- P2-3: usunięto nieaktualny wpis o limicie pierwszej strony.

### Verification results

- Nowe testy: stan 4 PASS, interakcje 5 PASS (wejście do całej sekcji wykonuje wyłącznie odczyty także przy błędach backendu; run wspólny wybrany po nazwach gier i etykietach kohort zapisuje dokładne body przed POST i zachowuje je po utracie odpowiedzi; zmiana gry odrzuca wybór i czyta tylko nową grę; dwie bazy i odrzucony wspólny kandydat bez publikacji; PASS z aktualnymi dowodami publikuje z raportem jako dowodem).
- Admin przed audytem: unit 771/771, interakcje 269/279.
- Po rundzie poprawek: nowe testy interakcji panelu 11/11 (druga strona kohort, utrata odpowiedzi runu i wersji z remountem, jawnym ponowieniem i odmową 409, wyczyszczenie oceny przed spóźnioną odpowiedzią, odświeżenie po zmianie innego kroku w panelu i w całej sekcji), formularz kohorty 9/9 (trzy importy po nazwach z drugiej strony nagrań i bazą z katalogu; jedno nagranie z dotychczasowym `importJobId`), walidator poleceń i stan 8/8. Admin unit 772/772, interakcje 277/287 — 10 porażek wyłącznie w `super-game-series-workspace.test.mjs`, te same co w baseline [HEAD380](../../quality/TASK-1003_BASELINE_HEAD380.md) (`undefinedSeriesCountLabel`, plik bez zmian w tym diffie). `tsc --noEmit` PASS, ESLint 0 błędów (5 starych ostrzeżeń w nietkniętych plikach), Prettier PASS dla zmienionych plików.
- Po P2-4 (stan końcowy): interakcje Admina 281/291 — te same 10 porażek supergier co w baseline; tsc, ESLint (0 błędów, 5 starych ostrzeżeń), Prettier PASS.
- Po drugiej rundzie: formularz kohorty i panel 23/23 (wybór rodziny treningowej innej gry dla wspólnej bazy, domyślna rodzina własnego forka; run zakończony przez worker wykryty samym odczytem i jednokrotne powiadomienie, bez dalszego odpytywania; nowa ocena wybranego kandydata po zmianie w innym kroku). Admin unit 772/772, interakcje 280/290 — te same 10 porażek supergier co w baseline. tsc, ESLint (0 błędów), Prettier PASS.
- API: `test_grid_training_cohort_requests.py` i PostgreSQL `test_exact_owned_application_prepare_page_restart_and_minimum_rejection` (dwa importy, replay, import obcy) — 14 PASS; ruff, ruff format i mypy --strict zmienionych modułów PASS. Klient `admin-api-client` 129/129 (z nowym przypadkiem `importJobIds`), `openapi:check` PASS. W tym samym pliku PostgreSQL `test_exact_owned_v3_migration_privileges_use_and_read_only_validation` FAIL z przyczyny spoza tego taska: po scaleniu `main` (migracja łącząca 0164, v1.7.387) cofnięcie do 0162 zostawia drugą głowicę `0155_board_search_panels`, a test oczekuje jednej wersji Alembic; poprawka oczekiwania należy do regresji odbioru TASK-1001.

### Not completed

- Przeglądarkowy odbiór na działającej aplikacji i rzeczywistych danych operatora — po integracji (TASK-1001). Rzeczywiste runy, publikacja i aktywacja pozostają decyzjami operatora.
- Listy kohort i nagrań są czytane w całości do 50 stron (5000 kohort, 10 000 nagrań); większy katalog kończy się jawnym błędem odczytu. Lista importów w pickerze pozostaje ograniczona do 200 najnowszych importów gry (istniejący komponent, z ostrzeżeniem).

### Documentation updates

- Sekcja TASK-1000 w `requirements/ADMIN_APP.md`, kontrakt w tym pliku, CURRENT_STATE, CODE_MAP.

### Recommended next task

- TASK-1001
