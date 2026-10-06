---
title: TASK-0847 — poprawne wejście RGB i propozycje sieci w audycie siatek
status: done
last_updated: 2026-10-05
---

# TASK-0847 — poprawne wejście RGB i propozycje sieci w audycie siatek

## Status

`done`

## Goal

Usunąć odtworzone propozycje Śliwka → Arbuz/Pomarańcz i poprawić rozróżnianie
Cytryny/Pomarańcza przez wykorzystanie pełnego wycinka i wejścia zgodnego
z treningiem istniejącej sieci, z dodatkowym potwierdzeniem biblioteki.

## Context

Operator zgłosił liczne pomyłki czytelnych symboli w kolejce audytu po TASK-0846.
Odczyt czterech aktualnych plansz odtworzył p00519 pola 5, 10, 15: widoczna
śliwka, a kandydat odpowiednio Pomarańcz/Arbuz/Arbuz. Są to słabe wyniki.
W histogramie koloru tych wycinków dominuje brązowe tło. Kod głosowania jest
identyczny z worktree Claude Code, ale nie dowodzi to zgodności jakości na
innym cięciu i przy wyświetlaniu także wyników wcześniej pozostawianych pustymi.

## Dependencies / entry conditions

TASK-0846, zamrożona biblioteka 5653 wzorców i checkpoint. Diagnostyka dopasowała
5653/5653 wiersze biblioteki do rzeczywistych RGB w cache i zapisała sąsiadów.
TASK-0832/0833 pozostają zatrzymane; nie uruchamiać ich ani nie edytować worktree
Claude. Poprzednie zatwierdzenia operatora są chronione.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Samodzielny review oraz regresje rzeczywistych
wycinków, brak delegowania. Zmiana dotyczy doradczych wyników kolejki audytu,
bez zmiany ścisłej reguły i writera dawnych przebiegów biblioteki.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — D-491/D-493
- `ai_docs/architecture/API_CONTRACT.md` — sidecary audytu
- `ai_docs/process/DECISION_LOG.md` — D-464/D-465/D-493
- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md` — opisy i granice
- Aktywne TASK-0832/TASK-0833 — wyłącznie stan zatrzymania i ochrona zakresu.

## Scope

Ograniczony pomiar odczytowy na istniejących wycinkach. Operator doprecyzował,
że metoda ma wykorzystać kształt i detale, a kolor jest tylko jednym z sygnałów.
Propozycja pochodzi z głowicy istniejącej CNN na oryginalnym RGB, zgodnym
z treningiem. Biblioteka potwierdza propozycję tylko przy dotychczasowej
jednomyślności i zgodności z CNN. Brak zgodności daje `?`, nie puste pole.
Te same wagi i wzorce; zachowanie wyborów operatora, indeksów, sum i wznowienia.
Przeliczyć wyłącznie nadal otwarte plansze, pokazać wynik w obecnym Reviewerze.
API addytywnie rozpoznaje nową wersję algorytmu; bez nowego endpointu lub UI.

## Out of scope

Automatyczne zatwierdzenia, zmiana zatwierdzonych plansz, trening/aktywacja modeli,
operacje TASK-0832/0833, zmiana UI lub numeracji sekwencji, migracje, push/merge.

## Acceptance criteria

- [x] Regresja trzech odtworzonych śliwek daje Śliwkę przy identycznych pikselach.
- [x] Barwa symbolu nie jest usuwana przez balans bieli ani zastępowana barwą tła.
- [x] Testy rzeczywistych Cytryn/Pomarańczy i kontroli innych symboli bez pogorszenia
      na ustalonej małej próbce; ocena wzrokowa nie jest etykietą operatora.
- [x] Brak dowodu nie jest raportowany jako wysoka pewność; zmienione decyzje mają `?`.
- [x] Dawne reguły biblioteki i zatrzymane przebiegi pozostają bez zmian.
- [x] Checkpoint, katalog klas i wejście RGB są walidowane. Nowa polityka
      unieważnia stare wyniki kursora; nie powstaje dodatkowy cache deskryptorów.
- [x] Wszystkie nadal otwarte plansze mają wynik nowej polityki; nowy proces odzyskuje
      wynik bez powtórnego przeliczenia; stare zatwierdzenia nie są zapisywane.
- [x] Testy/lint/typy oraz odbiór widocznego Reviewera; osobny wersjonowany commit.

## Technical notes / plan wykonania

1. Na czterech istniejących planszach odczytać oryginalny PNG i sąsiadów biblioteki;
   potwierdzić klasę/kolor w cache i porównać strumień wejścia z Claude Code.
2. Zakończono próby barwy, przestrzennych opisów, równych grup klas i małej korekty
   dopasowania. Nie usunęły wszystkich pomyłek; nie są wdrażane. Odtworzono istotną
   różnicę wejścia: trening RGB, biblioteka używa dodatkowego `gray_world`.
   Głowica checkpointu na RGB daje 60/60 na pierwszej próbce (biblioteka 56/60),
   a na osobnej próbce z 20/40/60/80% kolejki 60/60 (biblioteka 59/60).
   Oceny wzrokowe agenta, nie truth operatora. Próbki i raporty w `.runtime/task0847/`.
3. Mały moduł audytu ładuje raz zamrożone wagi z kontrolą SHA, architektury,
   64px i dokładnej kolejności klas. Przekazuje pełne RGB z normalizacją /127.5−1.
   Argmax głowicy wybiera propozycję; `decide` 7/7 nadal tylko potwierdza ją.
   Rozbieżność lub abstencja biblioteki daje `?`. Nie zmieniać starego `decide`
   ani preprocessingu zatrzymanych przebiegów. Nowa wersja sidecara i polityki.
4. Addytywna wersja w odpowiedzi API: store, schema, OpenAPI, wygenerowany klient,
   wrapper bez ręcznych typów, test żądania starej i nowej wersji. Test kontraktu
   RGB, realnych przypadków, checksum/klas, wznowienia i utraty potwierdzenia zapisu.
5. Bounded CLI, nowy proces, read-only coverage i lokalny odbiór UI bez Save.

## Expected files

Istniejące: `scripts/recognize_grid_audit_symbols.py`, jego testy API/CLI,
`services/worker/src/game_predictor_worker/symbols/reference_library.py` (odczyt),
`ADMIN_APP.md`, `API_CONTRACT.md`, CURRENT_STATE i Decision Log.
Proponowane: moduł audytu RGB, testy i małe rzeczywiste fixture'y; store/schema
API, OpenAPI i klient wygenerowany oraz test wrappera.

## Test cases

Blue foreground on brown background; yellow vs orange with a common background;
no colour evidence; deterministic ties; invalid inputs; real reproduced plums;
unchanged catalogue mapping; frozen-cache checksum drift; old cursor invalidation;
publication acknowledgment loss and new-process recovery.

## Verification

Focused Python tests, Ruff and scoped strict Mypy. Bounded real-data
diagnostics and recognition rounds (45 s budget, 55 s hard process timeout).
No synthetic benchmark or large evaluation. Read-only browser acceptance without Save.

## Risks / open questions

Illumination and poor crops remain sources of error. Colour alone cannot separate
all classes, especially cherry/watermelon and plum/grape. Small visually inspected
samples do not establish overall accuracy. No blocking product question; evidence
must support the concrete improvement before publishing new advisory results.

## Outcome

- Implemented D-494: the existing frozen CNN head sees original RGB matching
  training. The unchanged library only confirms the candidate; disagreement
  remains tentative. No colour-only rule, new weights, training or activation.
- Reproduced p00519 cells 5/10/15 now propose `SLIWKA`; cell 11 `CYTRYNA`.
  Real fixtures contain eight lossless previews (637 kB total) and pixel SHA.
  CNN RGB 120/120 vs old policy 115/120 against agent visual expectations.
  The second 60-cell sample was inspected before reading model outputs. It is
  a separate diagnostic sample, not a verified held-out training split or
  operator ground truth. No population-accuracy claim.
- API/store support both algorithm versions. OpenAPI and generated client
  updated; the existing wrapper inherits generated types and has request tests
  for both versions. No new endpoint, UI or write contract.
- Python focused suite: 79 PASS; final worker suite 15 PASS, including one added
  incompatible-state regression. Client tests/build: 81 PASS. Ruff check/format,
  Prettier of changed client artifacts/fixtures/task, six-file scoped strict
  Mypy, API-client and Reviewer TypeScript, OpenAPI and generated-client checks PASS.
- Broad dependency Mypy hit unrelated share-query errors and timed out at 55 s;
  scoped configuration retains strict checks and NumPy/Pydantic types, skips
  unrelated repository imports and Torch internals. An intermediate skipped
  import run reported an unrelated training-dataset type error; none was changed.
  Sandbox Node user-info failure passed on the authorized retry. No orphaned
  terminated checker remained. Logs/config: `.runtime/task0847/`.
- Production advisory rounds: 110 + 116 + 119 + 107 + 44 = 496 open boards.
  Read-only verification: 7440 candidates, 5662 reference-confirmed, 1778 tentative,
  no missing candidate. All manifests/checkpoint/catalogue bindings valid;
  frozen library array SHA unchanged. Queue: 496 open, 479 corrected, total 975.
  Corrected boards and human approvals were not written.
- Fresh process completed with `processed=0`, `coveredOpenBoards=496`; lost-ack
  recovery, old-policy cursor invalidation and checkpoint drift covered by tests.
  CLI: `python -m scripts.recognize_grid_audit_symbols --game-id
  bfc4f949-5c14-4850-b02a-db99610bcfa5 --game-code 7 --output-dir
  artifacts/grid-audit-symbols-20261005 --library-cache
  artifacts/grid-audit-symbols-20261005/reference-crops.npz --max-seconds 45`.
- Reviewer read-only acceptance: new tab shows p00519 with the three plums,
  lemon and explicit `?`, 15/15 candidates. Initial load retry succeeded.
  Screenshot: `.runtime/task0847/reviewer-rgb.png`; no Save. Existing tab preserved.
- DoD/plan reviewed: all eight acceptance criteria met; initial colour proposal
  was replaced by the evidenced RGB contract fix following operator clarification.
  No migrations, service restarts, push/merge, paused-job resume or model activation.
  Physical Android, OS reboot and overall operator-labelled accuracy not measured.
- Next step: operator reviews candidates and corrects remaining mistakes before Save.
- Commit: `v1.7.192`, `8a42380bc9b6d13d125c5eab2873c8c58076134f`. Branch history
  advanced during work to `317a07c9` / v1.7.191; pre-existing work excluded.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0847 | gpt-6.1-sol | high | Reprodukcja na rzeczywistych pikselach, kontrakt RGB i trwałe propozycje bez zatwierdzeń. | Samodzielny review oraz regresje; bez delegowania. |
