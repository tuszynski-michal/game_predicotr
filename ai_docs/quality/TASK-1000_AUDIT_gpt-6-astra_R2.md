# Audyt TASK-1000 — Pełna sekcja „Geometria V3”

Werdykt: REVISE
Audytor: Codex, gpt-6-astra / medium (etykieta briefu)
Wykonawca: claude-opus-5-5 / high
Zakres: HEAD...1b38ae6ce742272a5f63557670b7e8ed5bbc7c3a oraz niezacommitowane zmiany TASK-1000, data 2026-10-16
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono poprawki po R1, integrację paneli, rozszerzenie selektora kohort oraz testy odzyskiwania poleceń. Wybór wielu importów, stronicowanie i testy ponowienia po odmontowaniu usuwają większość wcześniejszych zastrzeżeń. Pozostaje luka wyboru wspólnej rodziny treningowej przy przypisaniu z forkiem oraz niepełne odświeżanie kolejnych kroków.

## Znaleziska

### P0

- [P0-2] `apps/admin/src/features/model-quality/grid-cohort-preview.tsx:345` — Poprawka wyboru wspólnej bazy nie obejmuje przypisań z własną rodziną treningową. Dla przypisanej wersji formularz wymusza `assignment.trainingFamilyId`, natomiast dla tej samej wersji wybranej w innej grze używa `manifest.familyId`. Jednocześnie przypisana wersja jest usuwana z katalogu alternatywnych wyborów w linii 355. Przykład: gra A ma bazę X i rodzinę treningową F-A, gra B ma bazę Y i wybiera X z katalogu. Powstaną kohorty z tą samą bazą X, lecz różnymi rodzinami; backend odrzuci wspólny trening jako `GRID_SHARED_COHORT_MISMATCH` (`services/api/src/game_predictor_api/domain/shared_grid_model_candidate.py:78`). Przy dwóch forkach przypisanych do X problem występuje również między nimi. Należy umożliwić jawny, nazwany wybór wspólnej rodziny i bazy niezależnie od przypisania gry, zachowując walidację rodowodu. Samo usunięcie filtra przypisanej wersji nie wystarczy — gałąź w linii 346 nadal wymusza rodzinę przypisania.

### P1

Brak.

### P2

- [P2-1] `apps/admin/src/features/model-quality/grid-training-run-panel.tsx:133` — Odświeżanie między krokami naprawiono częściowo. Zakończenie treningu przez worker nie wywołuje `onChanged`; panel nie ma pollingu ani przycisku odczytu aktualnego stanu. Po zakończeniu runu lista może nadal pokazywać kolejkę, a porównanie nie zobaczy kandydata do reloadu lub innej mutacji. Ponadto `refresh()` panelu wersji odczytuje katalog i przypisania, ale nie listę ocen wybranego kandydata (`grid-model-versions-panel.tsx:100`), więc nowa ocena wymaga ponownego wyboru kandydata. Zalecane jawne odświeżenie zależnych odczytów i test zakończenia runu bez kolejnej mutacji; alternatywnie należy opisać ograniczenie.

- [P2-3] `ai_docs/tasks/1000-v3-grid-model-workspace.md:163` — `Not completed` nadal deklaruje ograniczenie do pierwszych 100 kohort i 200 nagrań, mimo wdrożonego stronicowania i przeciwnego opisu w sekcji poprawek. Należy usunąć nieaktualny wpis i opisać rzeczywisty limit 50 stron z `grid-model-state.ts:277`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Proces działa bez skryptów operatora | niespełnione | P0-2: brak pełnego wyboru wspólnej rodziny przy forku |
| Zwykły przebieg używa nazw zamiast ręcznych UUID | niespełnione | Importy i wersje mają selektory, lecz wymagany wariant wspólnej rodziny pozostaje niedostępny; `grid-cohort-preview.tsx:345` |
| Wejście na ekran nie uruchamia joba | spełnione | Statyczna analiza efektów montowania; `grid-training-run-panel.tsx:105`, `grid-model-versions-panel.tsx:116` |
| Zmiana gry/reload zachowuje właściwy stan | spełnione | Klucze zakresu i testy remount/retry; `apps/admin/test-interactions/grid-model-workspace.test.mjs:524`, `:574` |
| Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem | niespełnione | Podstawowe warianty pokryto; wariant rodziny treningowej nadal blokuje P0-2 |
| Kontrole, audyt i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Wyniki zapisano w tasku od linii 153, ale ich nie odtwarzano; pozostaje P2-3 |

## Listy zamknięte i otwarte

Zamknięte:

- P0-1 — selektor wielu importów i dokładna walidacja zakresu: `grid-cohort-preview.tsx:360`, `grid_training_cohort_commands.py:60`; test formularza od `grid-cohort-preview.test.mjs:452`.
- P0-3 — stronicowanie nagrań i kohort: `grid-cohort-preview.tsx:195`, `grid-training-run-panel.tsx:92`, `grid-model-comparison.tsx:166`.
- P1-1 — dodano remount, brak automatycznego POST, identyczne retry i odmowę 409: `grid-model-workspace.test.mjs:524`, `:574`.
- P2-2 — unieważnianie odczytu także przy pustym wyborze: `grid-model-versions-panel.tsx:151`, `:164`, `grid-training-run-panel.tsx:146`; test od `grid-model-workspace.test.mjs:629`.

Otwarte: P0-2, P2-1, P2-3.

## Proponowane testy

- W `apps/admin/test-interactions/grid-cohort-preview.test.mjs`: dwie gry z różnymi przypisanymi bazami, jedna z forkiem; wybór wspólnej bazy musi dać zgodne `familyId`, `baseVersionId` i tryb bez zmiany przypisań. Dodatkowo dwa forki tej samej bazy.
- W `apps/admin/test-interactions/grid-model-workspace.test.mjs`: zakończenie runu przez backend oraz utworzenie oceny dla już wybranego kandydata; odświeżenie udostępnia następny krok bez dodatkowej mutacji.

Komenda: `npm run test:geometry --workspace @game-predictor/admin`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task i raport R1, właściwe fragmenty planu, wymagania, decyzje D-527/D-541, zmienione komponenty i testy oraz powiązane kontrakty selektora, rodowodu i wspólnego treningu. Sprawdzono rozszerzenie OpenAPI, wygenerowanego typu i przekazywanie treści przez wrapper klienta.

Nie uruchamiano testów, usług, migracji, treningów ani operacji na danych. Wyniki kontroli wykonawcy nie zostały niezależnie potwierdzone. Przegląd nie potwierdza działania na rzeczywistych danych operatora ani jakości modeli.