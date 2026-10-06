---
title: Mumie — train current approvals and finish automatic preparation
status: done
last_updated: 2026-10-05
---

# TASK-0850 — Mumie: aktualne zatwierdzenia i praca do interakcji operatora

## Status

`done` — praca do granicy wymaganej interakcji. Edytor etykiet wymaga nowego
kontraktu wersji; jego implementacja pozostaje osobnym TASK-0851.

## Goal

Wykonać jedną ocenianą iterację na obecnych 31 zdjęciach Mumii, sprawdzić
testy folderów i przygotować aktualne dane do pierwszej potrzebnej interakcji.

## Context / authorization

2026-10-05 operator zlecił wykonanie wszystkiego do chwili wymagającej jego
interakcji. Jest to rozszerzenie ukończonego TASK-0842 o iterację 5 na nowych
zatwierdzeniach. Nie uruchamiać powtarzanych treningów na tych samych danych.
Operator chce pozostawić główną grę Mumie bez plansz.

## Dependencies / entry conditions

- Odczyt kolejki 8105: rewizja 591, 236 źródeł, 31 complete, 11 started.
- Ledger ma zakończone iteracje 1–4; poprzednia użyła 20 zdjęć (16/4),
  preset F zachował model iteracji 3. Nowe 11 nie było trenowane.
- TASK-0845/0846 przetestowały po 200 zdjęć dwóch folderów modelami 2 i 3.
  Znaleziono fałszywą szóstą planszę i częściowo ucięty kadr.
- Potwierdzić checkpoint, pozostały budżet 14 400 s i brak aktywnego runu.
- Zachować wszystkie dotychczasowe zatwierdzenia, podział i artefakty.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`: kontrola checkpointu, podziału, pochodzenia
referencji i warunkowego porównania. Własny audyt; bez delegacji. Drift lub
brak GPU blokuje zależny krok; nie obchodzić guardów ani tworzyć nowego runu.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md`
- `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md`
- `ai_docs/delivery/MUMIE_REAL_FOLDER_TEST_20261005.md`
- `ai_docs/quality/MUMIE_SECOND_FOLDER_TEST_20261005.md`

## Scope / execution plan

1. Zapisać fingerprint anotacji oraz aktualny ledger i budżet. Zweryfikować
   historyczny podział; wznowić run 3 iteracją 5, preset F, bez allow-same-data.
   CLI `neural_grid_finetune iterate --no-wait` uruchamia odłączony worker.
2. Odczytywać stan w ograniczonych krokach. Po checkpointcie dokończyć tę
   samą iterację: ocena Mumii i strażnik 777, ewentualny ONNX/parity oraz nowe
   propozycje wyłącznie do niekompletnych zdjęć. Bez aktywacji produkcyjnej.
3. Jeśli powstał nowy model, porównać go z iteracją 3 na tych samych 400
   zdjęciach folderów, z create-only wynikami i bez udawania accuracy.
   Dostosowanie istniejącego adaptera do jawnego wyboru iteracji wymaga testu
   regresyjnego zachowania domyślnego. Jeśli nie powstał model, zweryfikować
   wcześniejsze wyniki obu folderów i odzyskać je bez ponownej inferencji.
4. Przygotować aktualne cropy z zatwierdzonych geometrii oraz stan słownika
   i etykiet symboli. Nie zgadywać symboli ani cechy Super. Dostarczyć
   konkretną kolejkę do interakcji, korzystając z istniejących narzędzi labu.
5. Sprawdzić wynik i trwałość w nowym procesie, zapisać raport, Outcome,
   CURRENT_STATE i osobny commit; zatrzymać się przy brakujących etykietach
   lub koniecznej ocenie/korekcie operatora.

## Out of scope

Import/materializacja plansz i zapisy do produkcyjnej bazy, migracje, Super
mechanika/wypłaty, aktywacja modelu produkcyjnego, shadow, kolejne iteracje
bez nowych decyzji, masowe oznaczanie za operatora, push i merge.

## Acceptance criteria

- [x] Iteracja 5 zakończona, 31 źródeł z aktualnym podziałem, bez przecieku
  przypisanego holdoutu do treningu; raport strażnika i decyzji F.
- [x] Zatwierdzenia i wcześniejsze pliki źródłowe/snapshoty niezmienione.
- [x] Nowy model przetestowany na dotychczasowej próbce albo wyraźnie
  wykazane, że model zachowany i wcześniejsze wyniki nadal aktualne.
- [x] Aktualny pakiet cropów i konkretna potrzebna interakcja przygotowane.
- [x] Trwałość potwierdzona z nowego procesu; główna gra nadal bez importu.
- [x] Własny audyt DoD, raport, osobny commit oraz hash w Outcome/CURRENT_STATE
  dopisywany po commicie.

## Technical notes / verification

Użyć istniejących `neural_grid_finetune.command_iterate`,
`scripts/test_mumie_folder.py` i `vision_lab.mumie_batches.prepare/verify`.
31 jest licznością odczytaną przed startem; snapshot iteracji zamraża wejście.
Ledger utrzymuje przydziały, nowe zdjęcia numeruje dalej i co piąte odkłada.
Referencje 11 nowych zdjęć to niezmienione propozycje iteracji 3 zatwierdzone
przez człowieka; pozostają ważne, ale nie są niezależnym dowodem jakości.

Start/status mają timeout 120/30 s. Worker ma trwały deadline istniejącego
runu, heartbeat, checkpoint i zapis tożsamości procesu. Nie czekać na niego
blokującym poleceniem foreground. Finalizacja/export jako kontrolowany krok
do 120 s albo osobny kontrolowany proces z jawnym statusem. CPU folderów:
max 40 zdjęć na krok, 4 wątki, timeout 120 s. Verify w nowym procesie.

## Expected files

- Nowy: ten task, po wykonaniu w `ai_docs/tasks/completed/`.
- Nowy: `ai_docs/quality/MUMIE_CURRENT_APPROVALS_20261005.md`.
- Istniejący: CURRENT_STATE, tylko sekcja TASK-0850.
- Warunkowo: `scripts/test_mumie_folder.py`, jego istniejące testy i galeria,
  wyłącznie jeżeli wybrano nowy model wymagający porównania.
- Lokalne artefakty: `artifacts/mumie-current-approvals-20261005/`.

## Risks / open questions

Nowa iteracja nie gwarantuje poprawy. Podział per zdjęcie nie dowodzi
niezależności filmów. Brak prawdziwych etykiet aktualnych cropów blokuje
trening symboli; katalog Admina nie jest zbiorem etykiet.

## Outcome

2026-10-05 wykonano jedną iterację 5 w runie 3, bez zmiany budżetu/presetu,
25 train / 6 holdout. 11 nowych zdjęć, wszystkie 99 siatek przyjęte bez korekt.
1831 kroków, 900,75 s treningu GPU. Kandydaci 1–3 przeszli strażnik 777,
ale każdy pogorszył Mumie image-macro względem 0,0022076230. F zachował
stan początkowy: brak nowego ONNX, propozycji i aktywacji. Ledger iteracji
jest `done`; run zatrzymany zgodnie z `NEURAL_GRID_ITERATION_COMPLETE`,
worker nie żyje. Zużycie 4718,62/14400 s; nie wykonano iteracji 6.

Oba wcześniejsze foldery zweryfikowane w nowych procesach: 211 wyników
każdego modelu na folder, w tym 200 zdjęć folderu i 11 osobnych kontroli.
Model pozostaje ten sam, więc nie powtarzano 400 inferencji. Nie raportuje
się accuracy na zdjęciach bez niezależnej referencji.

Nowy pakiet ma 4185 nieoznaczonych komórek z 31 kompletnych zdjęć; 236
nakładek i partie 50/50/50/50/36. Wszystkie 225 źródeł znanego folderu
pasują SHA. W nowym procesie wszystkie checksumy, 20 dawnych ról,
fingerprint anotacji oraz magazyn symboli zgodne. Słownik Mumii jest
zatwierdzony i zawiera 10 klas, ale obecne 31 zdjęć ma zero etykiet symboli.

Build istniejącego UI labu i TypeScript PASS. Gotowość 8102/3102 potwierdzona;
faktyczny podgląd cropów zwraca `HOLDOUT_POLICY_UNRESOLVED` z powodu
udokumentowanego `split_stale` dawnego pilota. Nie wyłączono guardów,
nie nadpisano splitu i nie użyto nieobsługiwanego rebase. Nowe własne procesy
panelu zatrzymano, 8105 przywrócono i potwierdzono rewizję 591 / 31/236.
To granica wymagająca jawnego kontraktu nowej wersji, nie gotowy edytor etykiet.

Przygotowano draft `MUMIE_SYMBOL_DATASET_VERSION_20261005.md` i TASK-0851;
wysłano operatorowi pytania o akceptację kontraktu i pochodzenie dwóch
folderów. Wszystkie 31 źródeł zachowuje provenance unresolved. Nie nadano
verified, etykiet ani pozornej niezależności testu.

Kontrole: 31 testów fine-tune/Mumie batches/folder CLI PASS (32,59 s),
istniejący build UI PASS (40,27 s), końcowa integralność PASS, oba foldery
verify PASS. Pytest nie istnieje w interpreterze treningowym; testy wykonano
istniejącym interpreterem projektu, bez instalowania zależności.

GET preview głównej gry: 10 symbols, 0 layouts, source_images, recognized_boards
i dataset_versions. Bez zapisu DB, migracji, materializacji, shadow, push/merge.
DoD porównano z punktami taska: wykonano trening/ocenę i przygotowanie do
decyzji operatora; niewykonana funkcja nowej wersji zbioru została jawnie
wyłączona do osobnego, oczekującego na akceptację kontraktu.

Raport: `ai_docs/quality/MUMIE_CURRENT_APPROVALS_20261005.md`.
Dowody: `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-current-approvals-20261005`.
Osobny commit na `feat/grid-engine-v3`: `v1.7.196`, hash do dopisania po commicie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0850 | gpt-6.1-sol | high | Trwały trening, pochodzenie nowych referencji, warunkowa ocena i ochrona danych operatora. | Własny audyt dowodów i regresji; bez delegacji. Stop przy drift lub braku etykiet. |
