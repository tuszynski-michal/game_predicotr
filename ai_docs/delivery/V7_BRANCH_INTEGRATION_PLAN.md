---
title: V7 calibration branch integration into the main vision lab branch
status: accepted
last_updated: 2026-10-07
---

# Stan, cel i zakres

Operator polecił przenieść brakujące poprawki na `v1.1-vision-lab-hybrid-geometry`.
Main HEAD v1.7.249 /34e35a2f72d72e87357a6c7625c8a3f41d914df1 ma tylko entry
TASK-0919. Źródło `claude/kalibracja-etykiet-v7-85fdaa` /b087ad08b62992c54f5e26191e6408d287b64273
zawiera kalibrację, reviewed delivery, postęp bez przepisywania historii,
zatwierdzanie, output picker, reopen i propozycję dla każdego zakresu.
Git merge-base: fbef9096a1c937ad4884e745b48dc57bffa815af. Product diff: 129 plików.

## TASK-0920 — spójne przeniesienie V7

1. Przygotować prywatny snapshot aktualnego main bez danych i runtime; na nim
   scalić pliki produktu i testy three-way względem merge-base. Nie kopiować
   starszej wersji całego backendu, klienta lub dokumentacji. Zachować późniejsze
   main zmiany symboli, Mumie, storage, kontroli usług oraz entry TASK-0919.
   Konflikty rozwiązać na poziomie symboli, z kontrolą obu stron.
2. Zachować niezmienne migracje obu branchy. Main i V7 mają różne pełne IDs
   0144–0146; proponowana nowa merge revision `0147_merge_v7_main` łączy
   `0146_symbol_review_import_filter_index` i `0146_v7_operator_sources`.
   Nie zmieniać historycznych IDs lub istniejących baz. Schema readiness ma
   wskazywać jedyny połączony head. Test grafu i offline DDL; bez upgrade danych.
3. Backend wyznacza scalony OpenAPI; zregenerować klienta, zachować wrapper obu
   branchy i request tests. UI działa z tym samym API; output picker/reopen/pełne
   drafty przenoszą się razem z workerem, progress/recovery i writerem. Same-origin
   proxy pozostaje opcją izolowanego pilota, nigdy globalnym przekierowaniem main.
4. Dokumentacja main pozostaje nadrzędna. Nowa decyzja D-532 opisuje integrację
   oraz wymagane operacje użytkownika. Policies draft/explicit approval/imported
   V7 zapisane pod tym taskiem bez kolizji numerów z historycznymi main taskami.
   Kopie/corpus/profiles/acceptance/run data nie są migrowane przez scalenie kodu.
5. Focused testy przeniesionych algorytmów, recovery, API, wrapper/UI i dotychczasowy
   entry; Ruff/format/types i Admin checks; wygenerowany klient/OpenAPI drift.
   W pierwszej kolejności snapshot, potem sprawdzone zmiany na main checkout,
   finalna kontrola i osobny commit v1.7.250, tylko hunki tego zadania.

## Odbiór i granice

Planned: pełne 20/2 midpoint coverage, konflikty/końce/brak kotwic/descending,
EOF/restart/response-loss/no-overwrite, output folder/reopen/explicit approval,
API/client zgodność, pojedynczy Alembic head i zachowane poprzednie main funkcje.
Nie wykonywać SQL upgrade, decyzji operatora, OCR, treningu, aktywacji, startu lub
restartu API/Admin/workera, merge danych, monitora, push lub deploymentu.

Scalony backend wymaga migracji do nowego head przed uruchomieniem. To jawna
operacja użytkownika po odbiorze kodu; samo przeniesienie na branch nie jest
aktywowaniem V7 w API8000 ani przeniesieniem istniejących runów z pilot DB.
Fail-closed schema/gate pozostają. Istniejący WT/pilot nie są zmieniane.

## Wynik odbioru

TASK-0920 ukończony: 131 plików produktu i testów przeniesione three-way;
obie historie migracji zachowane i połączone w 0147. 814 testów snapshotu
oraz ponowny odbiór API 62, writer/recovery 75 i UI 62 w nowych procesach main
przeszły. Typy, lint, format oraz zgodność OpenAPI/klienta przeszły.
Kod zawiera pełne propozycje, katalog zapisu, szybkie review i reopen;
oszacowania pozostają jawne. Usługi, dane i gate nie są przenoszone.
Migracja i przygotowanie aktywnego main runtime pozostają osobną operacją
użytkownika opisaną w Outcome taska. Commit v1.7.250, hash w tasku i CURRENT_STATE.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0920 | gpt-6.1-sol | high | Scalenie pełnego pionu wymaga zachowania późniejszych zmian main, kontraktów i niezmiennych migracji. Konfiguracja dostępna. | Własny review konfliktów i testów; bez delegowania. |
