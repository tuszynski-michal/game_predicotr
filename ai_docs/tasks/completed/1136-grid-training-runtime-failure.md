---
title: Diagnose and repair the real training child failure
status: done
last_updated: 2026-11-03
---

# TASK-1136 — Awaria procesu treningowego

## Status

`done`

## Goal

Naprawić potwierdzoną utratę diagnostyki i wyniku niespodziewanego błędu trenera oraz wykonać ograniczoną diagnozę i kontrolowane wznowienie rzeczywistego zadania, zachowując identyfikator i budżet.

## Context

Po zatwierdzonym wdrożeniu TASK-1135 kohorta operatora została prawidłowo zamrożona (rewizja 164). Wznowiony parent utworzył trening `5eeaac0b-5e3e-4dfe-8f49-4fe618cb0837`. Trener wykonał co najmniej 388 kroków, następnie zakończył się bez result/checkpointu; nadzorca zapisał GRID_TRAINING_CHILD_EXITED. Sam evaluator VALIDATION na 13 oryginalnych zdjęciach przechodzi CPU i CUDA na bazowych wagach. To osobna awaria po naprawionym etapie freeze. W chwili diagnozy nie powstał kandydat.

Doprecyzowanie po diagnostyce: pierwotna przyczyna wyjścia procesu nie została odtworzona. Potwierdzono osobny defekt obsługi: niespodziewany wyjątek Python omijał zapis wyniku i zwolnienie lease, a stderr był odrzucany. Task naprawia ten potwierdzony defekt; nie deklaruje usunięcia nieustalonej przyczyny pierwszej awarii.

## Recommended execution

gpt-6.1-sol / high, bez delegowania. Claude Code claude-opus-5-5 / high przed commitem. Głębsza zmiana architektury/presetu wymaga ponownej oceny zakresu.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`.
- `ai_docs/architecture/VISION_LAB.md` — durable grid training.
- `ai_docs/requirements/ADMIN_APP.md` — trwały przebieg uczenia.
- `ai_docs/architecture/CODE_MAP.md`, `ai_docs/architecture/CODE_MAP_SYMBOLS.md`.

## Scope

- Zachować traceback i ewentualny native fault w osobnym logu każdej próby w istniejącym katalogu runu; probe pozostaje JSON-only.
- Ograniczona diagnoza pierwszej awarii: rzeczywiste wejścia walidacyjne CPU/CUDA i partie danych z zakresu 388–600. Wynik nieodtworzony pozostaje jawnym ograniczeniem.
- Odtworzyć i naprawić potwierdzoną utratę tracebacku/wyniku przy niespodziewanym wyjątku. Nie maskować błędu sukcesem ani nie obniżać presetów/buforów/liczby przykładów.
- Istniejąca zgoda operatora obejmuje wznowienie tej samej próby i jej pierwotny budżet; diagnostyka nie tworzy nowego treningu ani nie odnawia budżetu.

## Out of scope

Publikacja/aktywacja/default, zmiana ręcznej geometrii, migracje, ponowne przygotowanie kohorty i nowy budżet. Kolejny merge/push/restart dopiero po review i akceptacji wyniku. Nie restartować workera GPU bez jawnej zgody.

## Expected files

- `services/worker/src/game_predictor_worker/images/grid_training_child.py` — main/run, trwała diagnostyka.
- Odpowiedni moduł przyczyny po jej potwierdzeniu; zakres doprecyzować przed zmianą.
- Test regresji workera, VISION_LAB, mapa kodu, task i raport audytu.

## Acceptance criteria

- [x] Potwierdzony defekt obsługi błędu ma regresję; pierwsza awaria jest jawnie nieodtworzona, bez przypisywania jej hipotetycznej przyczyny.
- [x] Niespodziewany wyjątek Python pozostawia diagnostykę i failed result per attempt przed release; probe nie zmienia działania. Twarde zakończenie zewnętrzne pozostaje ograniczeniem.
- [x] Naprawa ma regresję odtwarzającą potwierdzony przypadek.
- [x] Identyfikator, zamrożona kohorta i oryginalny budżet zachowane, bez automatycznej aktywacji modelu.
- [x] Scoped testy/lint/typecheck, docs/map, Opus i task-close rozliczone (zamknięcie skryptem przed commitem).

## Verification

Skończone komendy ≤ 120 s. Ograniczona diagnostyka i wznowienie zatwierdzonego zadania tylko w pierwotnym budżecie. Bez ponawiania w ciemno; przed następnym runem musi istnieć zapis diagnostyczny.

## Risks / open questions

Brak wynikowego checkpointu w pierwszej próbie. Stan budżetu: 131,407 s zużyte, 600 kroków zarezerwowanych, próba 1; nie zerować tych wartości. Pierwotny traceback/natywny kod pozostaje nieznany. Poprawka gwarantuje wynik dla przechwyconego niespodziewanego wyjątku Python; nie gwarantuje diagnozy twardego kill ani nie rozwiązuje nieodtworzonej pierwszej awarii.

## Outcome

Commit: v1.7.529 / `910bb70ec599acf1180b5d4bb919cb50f2403d9d`.

### Changed

- Osobny, buforowany liniowo log Python stderr/traceback/faulthandler dla każdej próby, probe bez zmian. Natywny fd 2 pozostaje poza przechwytywaniem.
- Niespodziewany wyjątek trenera daje trwały failed result z osiągniętym krokiem przed zwolnieniem lease. Bez publikacji i bez automatycznej aktywacji.

### Verification results

- Ruff lint i format PASS; scoped mypy PASS (1 moduł, cały config projektu z izolacją zewnętrznego torch jak w TASK-1135; nie jest to pełny gate projektu).
- 46 testów child/diagnostics/handler/durable PASS w 57,53 s, w tym prawdziwy krótki trener CPU z checkpointem, eksportem i release; `artifacts/task1136-tests.log`.
- Pierwsza próba w ograniczonym środowisku wykonała 46 testów, ale zawiesiła zakończenie procesu: przerwana, nie zaliczona. Powtórzenie z dostępem do lokalnych gniazd Windows ma exit 0.
- Ograniczona diagnostyka na rzeczywistych danych: VALIDATION CPU 9,77 s, CUDA 5,28 s; partie 388–600 CPU 49,86 s, wszystkie PASS. Nie odtwarza to awarii ani nie dowodzi poprawy modelu.
- Wznowiono ten sam parent i child (attempt 2), ten sam snapshot i oryginalny budżet. Próba 2 zakończyła się poprawnym interrupted/RUN_BUDGET_EXHAUSTED na kroku 3400, zachowując checkpoint 7245dacd… i historię. Oryginalny budżet 4000 kroków ma rezerwację 4000 (600 z niepotwierdzonej próby 1 + 3400 próby 2), czas zużyty 1149,282 s z 3600 s. Plan wymaga 3600 kroków; kandydat i ocena nie powstały. Nie zerowano zużycia.

- Audyt [Opus 5.5/high, runda 1](../../quality/TASK-1136_AUDIT_claude-opus-5-5.md): PASS, brak P0/P1. P2-1 naprawione: `buffering=1`, dodatkowy test w nowym procesie potwierdza zachowanie pełnej linii stderr po `os._exit(4)`. Finalne 4 testy diagnostyki PASS w 3,07 s. P2-2 zaakceptowane i opisane: log przechwytuje Python stderr i faulthandler, nie dowolne zapisy CUDA/C++ na fd 2. Komunikat w teście zawężony do Python library warning. Bez kolejnej rundy, ponieważ nie było uwagi P0/P1.
- docs:check i code-map:check PASS, startup 44167 B / 45000 B przed zamknięciem. Mapa zregenerowana. Zmiana nie dotyczy UI/API, schematu, zależności ani migracji; build i SDK niewymagane.

### Not completed

- Przyczyna pierwszego wyjścia procesu po 388 krokach nie została ustalona; brak historycznego stderr/result. Nie przypisano jej OOM ani błędowi danych bez dowodu.
- Końcowa ocena i porównanie nowego kandydata zablokowane przez wyczerpanie kroków. Pytanie o jednorazowe +200 kroków dotyczy tylko istniejącego treningu, bez resetu czasu, zużycia, historii ani aktywacji. Zgoda nadal oczekiwana.
- Status HTML zaktualizowany: `artifacts/grid-learning-report-20261103/index.html`. Wyraźnie pokazuje brak kandydata i blokadę porównania; 147/147 odczytów bazowego modelu gotowych, bez deklarowania poprawy. Default bez zmian.

### Documentation updates

- VISION_LAB: trwała diagnostyka, failed result i granica gwarancji przy twardym zakończeniu procesu.

### Definition of Done

- Defekt obsługi odtworzony i naprawiony wraz z testem wyniku przed release i oddzielnych prób. Trwałość logu sprawdzona w nowym interpreterze, również przy nagłym zakończeniu.
- Kryteria danych/kontraktu/UI niemające zastosowania nie rozszerzają zakresu. Nie zmieniono budżetów ani modelu domyślnego; brak pełnej oceny modelu jest jawny.
- Dokumentacja, audyt i kontrola mapy wykonane; task-close i wersjonowany commit zamykają tylko naprawę diagnostyki, nie cały odbiór rzeczywistego uczenia.

### Recommended next task

- W przypadku ponownej awarii analizować konkretny log; nie zerować budżetu ani powielać treningów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1136 — awaria trenera | gpt-6.1-sol | high | Diagnostyka rzeczywistego procesu i trwałości błędów | Claude Code claude-opus-5-5 / high, przed commitem |
