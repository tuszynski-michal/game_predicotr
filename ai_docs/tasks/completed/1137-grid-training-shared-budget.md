---
title: Shared cumulative grid-training budget limits
status: done
last_updated: 2026-11-03
---

# TASK-1137 — Wspólne limity budżetu uczenia siatek

## Status

`done`

## Goal

Podnieść wspólne limity do 8000 kroków i 7200 s dla treningu siatek wszystkich gier, zachowując plan optymalizacji, checkpointy i skumulowane zużycie.

## Context

Operator odrzucił ręczne dopisanie +200 kroków jednemu zadaniu i polecił podnieść limity ogólnie. Bieżący run zachował checkpoint 3400/3600, ale wykorzystał 4000 rezerwacji (600 po awarii + 3400 po wznowieniu). TASK-1136 zamknięty, Opus PASS, v1.7.529–530; pierwotna awaria nadal nieodtworzona. Jednorazowy skrypt task1136-budget-extension NIE został wykonany.

## Recommended execution

gpt-6.1-sol / high, bez delegowania. Opus claude-opus-5-5 / high przed commitem. Zmiana architektury poza wersjonowaną polityką limitów wymaga ponownej analizy.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`: jakość modelu i trwałe uczenie z korekt.
- `ai_docs/architecture/VISION_LAB.md`: admission, budżet i trwały trening.
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`.
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-557--presety-treningu-geometrii-v3-dzierżawa-gpu-i-dopuszczenie-runu`.
- D-579 (nowa decyzja tej pracy): wspólna polityka budżetu, bez zmiany parametrów uczenia.

## Scope / technical notes

- Wersjonowana polityka limitów `grid-training-limits-v2` dla purpose=train, minimum 8000 kroków i 7200 s; smoke 50 kroków / 600 s bez zmian.
- Plan treningu i fingerprint historycznych presetów pozostają bez zmian. Podwyższenie limitu nie wydłuża automatycznie celu uczenia ani nie zmienia learning rate/early stopping.
- Nowe budżety otrzymują nową politykę. Istniejąca koperta bez znacznika polityki znaczy legacy `preset-v1`.
- Przy jawnie uruchomionym wznowieniu rozpoznanego legacy budżetu o dokładnych historycznych limitach następuje jednorazowe przyjęcie nowego wspólnego pułapu. Zużyte sekundy, zarezerwowane kroki, próby, fingerprint i checkpoint zachowane. Nieznane historyczne limity nie są automatycznie zmieniane.
- Przed rozliczeniem osieroconej próby nadzorca przyjmuje nowe pułapy, aby zachować również zużycie przekraczające stary limit. Nadzorca zapisuje receipt podwyższenia z poprzednią kopertą i nowymi pułapami w istniejącej historii checkpointu przed startem procesu. Kolejne wznowienia nie zwiększają pułapu. Zapis wyniku jest nadal przed release.
- Podgląd używa tej samej polityki limitów i kosztów; bez zmiany kształtu API, OpenAPI/SDK ani tabel.
- Odczyt panelu nie aktualizuje budżetów. Brak aktywacji/default/publikacji i nowych treningów na danych operatora.
- Zakres jest zgodą na kod ogólnego rozwiązania, nie na ręczną mutację jednego joba. Wdrożenie/merge i konieczny restart workera GPU wymagają akceptacji konkretnego wyniku.

## Assumptions / choices

8000 kroków i 7200 s to dwukrotność historycznego pułapu, wspólny ograniczony zapas na awarię. Operator został o liczbach poinformowany w czacie. Zapas nie gwarantuje odporności na dowolną liczbę awarii i nie maskuje błędów.

## Expected files

- `training_core/grid_training_admission.py`: RunBudget, estimate_cohort_cost, preset_view.
- `images/grid_training_handler.py`: trwały receipt jednorazowej zmiany limitów.
- Test podglądu API w `services/api/tests/test_grid_training_run_preview.py` (tylko nowy przypadek wspólnych limitów).
- Testy resource_admission i handler; nowy test round-trip/restart i wyczerpania nowego limitu.
- ADMIN_APP, VISION_LAB, D-579/indeksy, mapa, task/Outcome/audyt.

## Acceptance criteria

- [x] Nowe i jawnie wznowione rozpoznane legacy runy mają wspólne pułapy 8000/7200, plan i fingerprint bez zmian.
- [x] Pełne zużycie i historia zachowane; reset/restart/utrata odpowiedzi nie dodają kolejnego pułapu.
- [x] Przekroczenie nowego pułapu nadal blokuje; smoke i obce/nieznane koperty bez niejawnego upgrade.
- [x] Receipt utrwalony przed startem dziecka; replay po utracie odpowiedzi nie dubluje receiptu.
- [x] Podgląd i rzeczywiste dopuszczenie używają tych samych limitów; bez nowych endpointów.
- [x] Testy pionu/lint/typecheck/docs/map, Opus, task-close, osobny commit.

## Test cases / verification

- Legacy koperta bez policy, 4000/4000 kroków, 1149 s i attempt 2 → upgrade 8000/7200, zużycie zachowane, zgodny checkpoint, jeden receipt.
- Round-trip JSON i nowy obiekt nadzorcy → te same pułapy, zachowane liczniki, brak dodatkowego receiptu.
- Wyczerpane 8000 kroków lub 7200 s → blokada bez odnowienia.
- Smoke, obcy fingerprint/purpose, nierozpoznane legacy limity → bez upgrade.
- Nowy podproces odczytuje zapis budżetu i stosuje tę samą politykę.
- Pytest resource_admission/handler, lint/format/mypy modułów, docs/map. Każda komenda timeout ≤120 s; audyt ≤600 s.

## Out of scope

Zmiana parametrów nauki/presetów, UI, schema, migracje, automatyczna aktywacja. Globalny limit dotyczy wyłącznie geometrii, nie klasyfikatora symboli. Nie restartować usług przed osobną zgodą.

## Outcome

Commit: v1.7.531 (hash dopisuje kolejny commit).

### Changed

- Wspólna wersjonowana polityka limitów wykonania 8000 kroków/7200 s dla znanych presetów wszystkich gier. Parametry i fingerprint presetu, planowane 3600 kroków oraz smoke bez zmian.
- Legacy budget bez znacznika zachowuje interpretację `preset-v1`. Jednorazowe przejście do v2 podczas jawnego admission zachowuje zużycie i checkpoint. Receipt ze starym budżetem utrwalany przed launch.
- Podgląd pokazuje rzeczywiste nowe pułapy przez istniejące pola; bez zmiany API shape, OpenAPI/SDK i schematu bazy.

### Verification results

- Finalne 95 testów resource_admission/handler/durable/shared PASS w 15,47 s (`artifacts/task1137-final-tests.log`); wcześniej 94 PASS w 15,07 s (`artifacts/task1137-core-tests.log`). Obejmują legacy wszystkich trzech presetów, podwyższenie raz, wyczerpanie nowego limitu, smoke, nieznane limity/policy, nowy interpreter, receipt przed launch i utratę odpowiedzi.
- Nowy test podglądu limitów PASS w 2,36 s. 40 istniejących testów API/runów PASS; 2 zastane testy preview nadal FAIL, również po wykonaniu dokładnego modułu admission z main w odrębnym interpreterze (`artifacts/task1137-api-baseline.log`). Pierwszy oczekuje listy bez presetu korekt, drugi nieistniejącej blokady konsumenta wdrożonego w T2. Nie osłabiono ani nie zmieniono tych dwóch testów; izolowany baseline nie jest pełnym checkoutem main.
- Ruff format/lint PASS (5 plików). Scoped mypy PASS (2 moduły, cały config projektu z izolacją zewnętrznego torch jak TASK-1135; nie jest to pełny gate projektu).
- docs:check i code-map:check PASS; startup 44454/45000 B przed zamknięciem. Mapa zregenerowana.
- Czysty nowy interpreter odczytał rzeczywisty zapis zatrzymanego runu: propozycja wspólnej polityki daje 8000/7200 i zachowuje reserved=4000, used_seconds=1149,282, attempts=2 oraz checkpoint 3400. To tylko odczyt/pliki, nie modyfikacja bazy ani wznowienie (`artifacts/task1137-operator-budget-preview.json`).

### Not completed

- Rzeczywisty trening nadal zatrzymany na checkpoint 3400; model/kandydat i porównanie nie powstały. Jednostkowy skrypt +200 nie został wykonany.
- Wdrożenie i wymagany restart nadzorcy GPU wymagają osobnej zgody po wyniku. Nie restartowano usług, nie migrowano bazy, nie zmieniono defaultu/geometrii i nie uruchomiono nowego treningu.
- Audyt [Opus 5.5/high R1](../../quality/TASK-1137_AUDIT_claude-opus-5-5.md) PASS, bez P0/P1. Jedna runda poprawek P2: P2-1 usunięte — limit przyjmowany przed odzyskiem, nowa regresja 3550+100=3650 s potwierdza brak obcięcia do 3600 i receipt sprzed odzysku. P2-2 zaakceptowane i opisane w D-579: rollback samego kodu do starego readera nieobsługiwany po pierwszym zapisie limit_policy. P2-3 trwały wskaźnik dwóch zastanych FAIL dodany do CURRENT_STATE. Zamknięcie skillem task-close i osobny commit po końcowych kontrolach.

### Definition of Done

- Wszystkie właściwe kryteria spełnione dla kodu polityki; pełny odbiór treningu/HTML wymaga wdrożenia i jest jawnie poza ukończonym kodem. Historia, skumulowane zużycie i stare fingerprinty zachowane. Trwałość sprawdzona w nowym interpreterze, utrata odpowiedzi w trwałym punkcie admission.
- Brak zmian tabel, OpenAPI shape, UI, zależności i algorytmu uczenia; SDK/build/migracja niewymagane. Zastane błędy API i ograniczenie rollbacku jawnie opisane; nie osłabiono testów.
- Audyt PASS, dokumentacja, lint/format/scoped typy i mapa wykonane; task-close i commit zgodnie z procedurą.

### Documentation updates

- ADMIN_APP, VISION_LAB i D-579: wspólne limity, interpretacja legacy, zachowanie planu i zużycia oraz granica wdrożenia.

### Recommended next task

- Po akceptacji: scalić 1136+1137, push, restart nadzorcy GPU, wznowienie tego samego uczenia przez istniejący panel/API. Potem rzeczywista ocena i HTML na 230 pozostałych planszach.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1137 — wspólne limity uczenia | gpt-6.1-sol | high | Ograniczona polityka budżetu i zgodność wznowień | Claude Code claude-opus-5-5 / high, przed commitem |
