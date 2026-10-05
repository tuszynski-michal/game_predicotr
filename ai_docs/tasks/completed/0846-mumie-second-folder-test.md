---
title: TASK-0846 — Mumie, test drugiego folderu
status: done
last_updated: 2026-10-05
---

# TASK-0846 — Mumie, test drugiego folderu

## Status

`done`

## Goal

Porównać istniejące modele geometrii iteracji 2 i 3 na 200 równomiernie
dobranych zdjęciach drugiego folderu oraz dostarczyć podgląd i raport.

## Context

Operator ocenił wyniki pierwszego folderu jako niemal identyczne i wskazał
`C:\Users\tuszy\Documents\mumie wybrane\481537- 500000 cut` do kolejnego testu.
Folder zawiera 2052 pliki. Zgoda obejmuje test offline, bez treningu i DB.

## Dependencies / entry conditions

TASK-0845 dostarczył `scripts/test_mumie_folder.py` oraz podgląd porównawczy.
Oba eksporty ONNX pozostają dostępne w ledgerze finetune-D. Założenie:
200 unikalnych zdjęć rozłożonych po całym folderze, wykluczenie znanych SHA.
Inny zakres numeracji nie dowodzi niezależnego nagrania. Istniejące 11
zatwierdzeń jest kontrolą poprzedniego pomiaru, nie nową próbą drugiego folderu.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Wykorzystanie gotowego narzędzia i audyt
rzeczywistych wyników; bez delegowania. Drift SHA lub błędy narzędzia blokują
zależny krok. Nie zmieniać modelu na podstawie nieoznaczonego materiału.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_REAL_FOLDER_TEST_20261005.md`
- `ai_docs/tasks/completed/0845-mumie-real-folder-test.md`
- `ai_docs/quality/MUMIE_REAL_FOLDER_TEST_20261005.md`

## Scope

Inwentarz i SHA, dobór 200, inferencja obu ONNX, podgląd pełnych nakładek
i cropów, ograniczony przegląd wizualny, diagnostyka i trwały raport.

## Out of scope

Trening, aktywacja, DB, migracje, import produkcyjny, V3-D, etykietowanie,
symbole i ramka Super, push, merge oraz zmiany równoległego taska 0844.

## Acceptance criteria

- [x] Manifest wskazuje drugi folder, dokładne źródła i oba modele z SHA.
- [x] 200 zdjęć ma komplet wyników i podgląd obu modeli albo jawny blocker.
- [x] Obejrzano 20 rozłożonych po zakresie par nakładek i reprezentatywne cropy.
- [x] Liczność i zgodność modeli nie są przedstawione jako accuracy.
- [x] Kontrolne 11 zdjęć i pochodzenie ich referencji są ujawnione osobno.
- [x] Nowy proces odzyskuje wyniki i potwierdza ich integralność.
- [x] Raport, Outcome, CURRENT_STATE i osobny commit.

## Technical notes / plan wykonania

1. Istniejący `test_mumie_folder.prepare` czyta katalog, ledger i anotacje,
   deduplikuje dokładne bajty, wyklucza znane źródła, wybiera 200 po zakresach.
   Nowy create-only katalog wyniku:
   `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-folder-test-20261005\second-481537-500000`.
   Pierwszy test pozostaje niezmieniony; lokalny serwer może udostępnić podkatalog.
2. Kroki `run` dla iteracji 2 i 3, maksymalnie 40 zdjęć na proces, limit 120 s,
   postęp po zdjęciu. Użyć istniejącego engine, renderera i progów D-483.
3. `finish`, `audit` i `verify`; nie nadpisywać niezgodnych wyników. Nowy proces
   `run` ma odzyskać gotowe wiersze bez inferencji. Zmiana źródła/modelu/anotacji
   blokuje zależny krok; brak pliku nie jest sukcesem ani pustą planszą.
4. Obejrzeć 20 par nakładek równomiernie po zakresie i arkusze pól. Ujawnić
   każde zauważone przesunięcie, zasłonięcie lub złą geometrię. Bez decyzji za
   operatora. Podgląd obu modeli ma dostęp do tych samych zdjęć i cropów.
5. Raportować liczności, błędy struktury i ograniczenia, bez procentu poprawności
   nieoznaczonych źródeł. Metryki istniejących 11 służą wyłącznie kontroli;
   wszystkie 99 referencji poprzednio pochodziło z iteracji 3 bez zmian.
6. Uzupełnić dokumenty i commit zgodnie z historią worktree. Nie przenosić
   zastanych zmian użytkownika do zakresu; nie scalać równoległego checkoutu.

## Expected files

Istniejące: CURRENT_STATE. Proponowane: ten task i
`ai_docs/quality/MUMIE_SECOND_FOLDER_TEST_20261005.md`. Kod aplikacji nie wymaga
zmiany. Ignorowane artefakty obejmą manifest, wyniki, obrazy i galerię.

## Test cases / Verification

7 istniejących testów adaptera; faktyczny odczyt źródeł i inferencja CPU.
Każda komenda wykonana z runnerem `run_step.py`, timeout 30/60/120 s.
Wznowienie, verify, powtórny finish/audit oraz sprawdzenie podglądu w przeglądarce.
Bez szerszych benchmarków i bez budowania aplikacji, których kod się nie zmienia.

## Risks / open questions

Brak referencji geometrii drugiego folderu. Nieznane powiązanie nagrania
z wcześniejszym materiałem. Sama zgodność obu modeli nie dowodzi poprawności.
Widoczny błąd należy potwierdzić na obrazie, a nie automatycznie zatwierdzać.

## Outcome

### Changed

Wykonano porównanie istniejącym adapterem, bez zmiany kodu aplikacji. 200/2052
zdjęć równomiernie po zakresie, zero kopii i zero znanych SHA. 422 wyniki
(200 nowych + 11 kontrolnych, oba modele). Każdy model ma 199 zdjęć z 9
planszami i jedno z 6. Ostatnie źródło ma wizualnie pięć: oba tworzą fałszywą
szóstą planszę. Drugie źródło ma górę pierwszej planszy poza kadrem;
2/3 cropy nie dają się wyrenderować. Brak przewagi obecnego modelu.

Dopasowanie IoU predykcji: 43128 węzłów, mediana różnicy 0,327794 px,
P95 0,794990 px, maksimum 28,947359 px. Zgodność nie jest accuracy.
20 par nakładek, pięć największych różnic i oba przypadki obejrzane;
pełne źródła i reprezentatywne cropy sprawdzone. Podgląd `case-review.html`
oddziela kontrolne 11 i startuje dwoma przypadkami do sprawdzenia.

### Verification results

7 testów adaptera PASS. Nowe procesy odzyskały 211/211 wyników dla każdego
modelu, pending=0; ponowne finish/audit/verify PASS. Kontrola 11 odtworzyła
metryki poprzedniego testu i 99 referencji `proposal_unchanged` iteracji 3.
Galeria: nawigacja, filtry 200/11/2, wycinki i render obu modeli PASS.
Wszystkie kroki w limitach 30/60/120 s. Bez zmiany modułów aplikacji;
szerszy build, lint i typecheck aplikacji nie były potrzebne.

### Not completed

Bez accuracy nieoznaczonego folderu, ręcznego audytu każdego pola, nowego
treningu, zatwierdzeń, DB, migracji, aktywacji, symboli, Super i V3-D.
Bez push i merge; zastane zmiany pozostały poza zakresem.

### Documentation updates

Raport `ai_docs/quality/MUMIE_SECOND_FOLDER_TEST_20261005.md`, ten task
i CURRENT_STATE. Commit `v1.7.190`; pełny hash dopisywany po commicie.

### Recommended next task

Przygotować rzeczywiste referencje niepełnych ekranów i pustych miejsc,
nie traktować fałszywej szóstej siatki jako targetu. Uzyskać zatwierdzenia
i sprawdzić obsługę nieobecności przed następnym treningiem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0846 — porównanie siatek drugiego folderu | gpt-6.1-sol | high | Audyt integralności i geometrii na rzeczywistych zdjęciach przy gotowym adapterze | Testy adaptera, nowe procesy i przegląd wizualny; bez delegowania |
