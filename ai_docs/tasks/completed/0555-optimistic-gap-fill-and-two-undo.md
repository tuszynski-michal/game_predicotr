---
title: Natychmiastowe przejście po uzupełnieniu luki i cofanie dwóch fillów
status: done
last_updated: 2026-09-15
---

# TASK-0555 — Natychmiastowe przejście po uzupełnieniu luki i cofanie dwóch fillów

## Status

`done`

## Goal

Po zatwierdzeniu uzupełnienia luki operator natychmiast widzi następne już
buforowane zdjęcie, a trwały zapis pliku i manifestów wykonuje jedna kontrolowana
kolejka; może cofnąć najwyżej dwa ostatnie trwale zapisane uzupełnienia.

## Context

Tryb delete już przełącza podgląd przed zapisem katalogu. Tryb fill nadal czeka
na skopiowanie JPEG-a, checksumę oraz synchronizację manifestów, mimo że viewer
ma cache Object URL i następne zdjęcie może być pokazane od razu. Operator
potrzebuje też ograniczonego cofania fillów, bez powrotu do rosnącej historii
repair manifestu ani przechowywania obrazów w pamięci.

## Dependencies / entry conditions

- TASK-0554 wprowadził `manual-image-selection-repair-v2.json`, kontrolowaną
  kolejkę i fail-closed dla opóźnionego delete.
- `ManualSelectionRepairWorkspace` używa już scoped cache viewer'a dla trybu
  fill i delete.
- Założenie: dwa ostatnie fill'e oznaczają dwie ostatnie **trwale zakończone**
  operacje w bieżącej sesji workspace'u; po ponownym wejściu do fill workspace
  sloty mogą zostać odtworzone z dwóch najnowszych aktywnych wpisów fill.

## Recommended execution

`gpt-6-astra` z reasoning `high`: zmiana obejmuje optymistyczny stan UI,
asynchroniczną kolejkę File System Access API i ograniczone cofanie bez utraty
fail-closed. Ponowna analiza mocniejszym modelem jest wymagana, jeżeli podczas
implementacji okaże się, że potrzebna jest zmiana schematu repair manifestu lub
kontraktu importu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md` (D-388)

## Scope

- Optymistyczne przejście w trybie fill przed wykonaniem trwałego zapisu.
- Zachowanie i wykorzystanie scoped cache bieżącego oraz następnego zdjęcia.
- Jedna kolejka zapisu JPEG-a, intencji recovery, repair manifestu, handoffu i
  output manifestu.
- Cofanie najwyżej dwóch ostatnich pomyślnie zapisanych fillów.
- Fail-closed po błędzie opóźnionego zapisu oraz testy regresji i dokumentacja.

## Out of scope

- Zmiana schematu `manual-image-selection-repair-v2.json` albo formatu handoffu.
- Cofanie usunięć, przechowywanie Blobów/File w pamięci i historyczny repair trace.
- Zmiany algorytmów cięcia, importu plansz lub danych katalogów użytkownika.

## Acceptance criteria

- [x] Zatwierdzenie fill'a przełącza UI na następny obraz przed zakończeniem
      zapisu pliku lub manifestów.
- [x] Następny obraz korzysta z istniejącego cache viewer'a; nawigacja działa,
      gdy trwa pojedyncza mutacja fill.
- [x] Drugi fill, delete, paczkowe usuwanie i zmiana trybu nie rozpoczynają
      mutacji, dopóki trwa opóźniony fill.
- [x] Sukces finalizuje standardowy checksum-bound zapis i uaktualnia snapshot.
- [x] Błąd nie jest ukrywany: blokuje kolejne mutacje do jawnej inspekcji
      katalogu, bez automatycznego nadpisania stanu lokalnego.
- [x] UI pozwala cofnąć wyłącznie jeden z dwóch ostatnich trwale zapisanych
      fillów; cofnięcie wraca do właściwego źródła i nie odtwarza delete.
- [x] Testy chronią kolejność optymistycznego przejścia, blokadę, limit dwóch
      cofnięć oraz zachowanie dotychczasowej transakcji storage.

## Technical notes

`manual-selection-repair-storage.ts:writeRepairFile` pozostaje jedynym
writerem katalogu i zachowuje kolejność intent → JPEG → SHA-256 → finalny
repair/handoff/output manifest. Workspace przed wpisaniem kolejki tworzy tylko
lokalny manifest widoku: dodaje zakres do `activeFiles` bez checksummy,
usuwa go z `deletedRanges`, ustawia następny `sourceCursor` i ustawia snapshot.
Nie dodaje `filledGapEntries` ani uchwytu pliku, zanim adapter nie zwróci
potwierdzonego wyniku.

W queue zabraniamy następnej mutacji fill/delete, ale nie nawigacji viewer'a.
Sukces zastępuje optymistyczny snapshot finalnym wynikiem adaptera i dopisuje
identyfikator fill'a do maksymalnie dwóch slotów undo. Błąd pozostawia widok
do odczytu, lecz blokuje dalsze mutacje do ponownego wskazania katalogu.
W razie reloadu dwie najnowsze aktywne proweniencje fill odtwarzają sloty undo;
nie są zapisywane jako nowa historia.

`undo_fill` nadal przechodzi przez tę samą serializowaną kolejkę i używa
checksummy ze wskazanego, już trwałego wpisu `filledGapEntries`. Po cofnięciu
usuwa tylko odpowiedni slot, wraca do jego `sourceIndex` oraz zostawia starszy
slot do ewentualnego użycia. Nie wolno nadpisywać pliku źródłowego ani
przywracać usuniętych sekwencji.

## Expected files

- Istniejące: `apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx` — optymistyczny fill, bramki kolejki i dwa sloty undo.
- Istniejące: `apps/admin/test/manual-selection-repair.test.mjs` — kontrakty
  regresji widoku i kolejki.
- Istniejące: `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md` — wymagania
  interakcji fill i cofania.
- Istniejące: `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md` — transakcja,
  cache, kolejka i recoverability.
- Istniejące: `ai_docs/process/CURRENT_STATE.md` — stan po wykonaniu.
- Istniejące: `ai_docs/process/DECISION_LOG.md` — decyzja o ograniczonym undo.

## Test cases

- Fill aktualnej luki → widok przechodzi do następnego źródła przed callbackiem
  zapisu, a adapter zapisuje końcowy plik i manifest po kolei.
- Fill w toku → nawigacja jest dostępna, lecz drugi fill, delete i powrót do
  wyboru trybu są zablokowane.
- Udany fill → dokładnie dwa najnowsze identyfikatory są dostępne do cofnięcia;
  trzeci usuwa dostęp do najstarszego slotu.
- Cofnięcie najnowszego fill'a → usuwa tylko checksummowany wynik, wraca do
  jego obrazu źródłowego i zachowuje drugi slot.
- Błąd opóźnionego zapisu → widoczny komunikat wymaga ponownej inspekcji i nie
  pozwala na następną mutację.
- Reload → dwa najnowsze aktywne fill'e mogą ponownie utworzyć sloty undo,
  bez dopisywania historii do manifestu.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout pojedynczego kroku <= 120 s
node --experimental-strip-types --test apps/admin/test/manual-selection-repair.test.mjs
pnpm --filter @game-predictor/admin typecheck
pnpm --filter @game-predictor/admin lint
pnpm exec prettier --check apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx apps/admin/test/manual-selection-repair.test.mjs
pnpm --filter @game-predictor/admin build
```

Zaliczenie wymaga zielonych testów skoncentrowanych, kontroli typów, lint,
formatowania i builda produkcyjnego oraz ręcznej kontroli, że `next-env.d.ts`
nie trafił do commita.

## Risks / open questions

- Optymistyczny snapshot po błędzie celowo może chwilowo różnić się od katalogu;
  automatyczne wycofanie bez sprawdzenia byłoby niebezpieczne. Wyjściem jest
  fail-closed i jawna inspekcja.
- Limit dwóch slotów nie daje nieograniczonego historycznego undo; jest to
  świadomy zakres wymagany przez operatora i nie zmienia formatu trwałego stanu.

## Implementation plan

1. Dodać stan trwającego i zablokowanego fill'a oraz pomocniczy optymistyczny
   snapshot, nie zmieniając adaptera zapisu.
2. Przenieść zapis fill'a do istniejącej serializowanej kolejki po przejściu
   view/source cursor i ujednolicić bramki wszystkich mutacji.
3. Dodać dwa trwałe sloty cofania oparte o finalne `filledGapEntries` oraz
   ograniczoną rekonstrukcję slotów po wejściu do fill mode.
4. Dodać regresje i zaktualizować dokumentację zgodnie z wynikiem weryfikacji.

### Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0555 — Natychmiastowe przejście po uzupełnieniu luki i cofanie dwóch fillów | gpt-6-astra | high | Potrzebna jest ostrożna koordynacja trwałego zapisu katalogu, stanu React i cofania bez regresji recovery. | Nie; ponowna analiza gpt-6-astra/high tylko przy potrzebie zmiany trwałego schematu lub kontraktu importu. |

## Outcome

Wypełnia agent po pracy.

### Changed

- Fill buduje lokalny, niesynchronizowany snapshot z kolejną luką już przed
  wpisaniem istniejącego `writeRepairFile` do jednej kolejki. Następne źródło
  korzysta ze scoped cache viewer'a, natomiast kolejne mutacje i zmiana trybu
  czekają na finalizację.
- Sukces kolejki zastępuje lokalny snapshot checksummowanym wynikiem adaptera.
  Błąd blokuje następne mutacje do jawnego ponownego wyboru katalogu.
- Cofnięcie używa najwyżej dwóch identyfikatorów pomyślnie zakończonych fillów.
  Sloty po otwarciu trybu są wyprowadzane z dwóch najnowszych aktywnych wpisów
  `filledGapEntries`; repair manifest nie otrzymał nowego pola ani historii.
- Dodano regresję kontraktu workspace'u dla natychmiastowego fill'a, blokad i
  limitu dwóch cofnięć.

### Verification results

- `node --experimental-strip-types --test apps/admin/test/manual-selection-repair.test.mjs` — 17/17 green. Windowsowy sandbox zwraca dla runnera `spawn EPERM`; ten sam
  test przeszedł poza sandboxem.
- `node_modules\.bin\tsc --project apps/admin/tsconfig.json --noEmit` — green.
- `eslint` dla zmienionego workspace'u i testu — green.
- `prettier --check` dla zmienionych plików i zadania — green.
- Produkcyjny `next build` Admina — green.

### Not completed

- Nie wykonywano mutacji żadnego rzeczywistego katalogu użytkownika; działanie
  katalogowe zostało pokryte adapterem pamięciowym i kontraktami workspace'u.

### Documentation updates

- Zaktualizowano wymagania i architekturę lokalnej korekty, `CURRENT_STATE` oraz
  D-389 w Decision Log.

### Recommended next task

- Po pracy na rzeczywistym katalogu potwierdzić, czy limit dwóch cofnięć jest
  wystarczający dla operatora.
