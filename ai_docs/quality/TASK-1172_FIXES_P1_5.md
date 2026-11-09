# TASK-1172 — dodatkowa poprawka P1-5

Data: 2026-11-09. Operator zatwierdził dodatkową poprawkę i skupiony audyt po
R2 słowami „Tak, popraw i dokończ cały plan”, po przedstawieniu kosztu20–40min
w dotychczasowym budżecie6–10h. Jest to jawny wyjątek od jednej rundy poprawek;
istniejących raportów i receipt R1/R2 nie zmieniano.

## Zakres

Wyłącznie `services/worker/tests/test_crop_blocked_repeatability_postgres.py`:
przed importem współdzielonych fixture dopisuje dokładny katalog
`services/api/tests/integration`, wyliczony względem własnego `__file__`.
To istniejący wzorzec jawnego testowego importu w repozytorium. Nie zmieniono
globalnego PYTHONPATH, konfiguracji pytest, warunku skip ani logiki testu.
Pozostały kod T3 pozostaje zamrożony.

## Weryfikacja w nowych procesach

Interpreter `D:/game_predicotr/.venv/Scripts/python.exe`; cwd worktree
`D:/game_predicotr/worktrees/grid-symbol-crop-preview`. Każdy proces testowy
uruchomiono osobno z całkowicie usuniętym `PYTHONPATH`, UTF-8 i timeout120s.
Żaden test nie był wykonywany: użyto wyłącznie `--collect-only -q`.

| Kontrola | Wynik | Dowód |
|---|---|---|
| Jeden plik PostgreSQL | exit0, 1 test; pytest15.96s, cały proces21.38s | `artifacts/t1172-p15-single.log` i `.json` |
| Cała suita Worker | exit0, 3623 testy; pytest33.87s, cały proces39.41s | `artifacts/t1172-p15-worker.log` i `.json` |
| Ruff check | PASS | `artifacts/t1172-p15-ruff.log` |
| Ruff format --check | PASS, 1 plik | `artifacts/t1172-p15-format.log` |

JSON zawiera dokładne argumenty, interpreter, cwd, `PYTHONPATH:null`,
`freshProcess:true`, timeout i kod wyjścia. Wynik dowodzi usunięcia blokady
kolekcji; nie jest deklaracją wykonania3623 testów ani ponownej próby bazy.
PostgreSQL nie powtarzano: wcześniejszy actual advance/JSONB PASS29.87s i cleanup0
pozostają odrębnym dowodem niezmienionej logiki testu.

## Pozostawione ograniczenia

- P2-7: wcześniejszy fixture PG warunkowo wykonuje asercje v2. Nie zastąpiono
  tego bezwarunkową asercją i nie deklarujemy takiej dodatkowej kontroli.
- P2-8: Admin wybiera v2, a serwer bezpiecznie blokuje utworzenie sesji, jeśli
  wybrany materiał nie ma wymaganego rodowodu, również dla TRAIN. Odbiór T4
  musi jawnie pokazać to ograniczenie i potrzebę zawężenia wyboru źródeł.
- P2-1/P2-4/P2-5 pozostają opisane w Outcome oraz `TASK-1172_FIXES_R1.md`.

Bez operatorowej bazy, GPU, usług, aktywacji/default, reimportu, stage i commita.
Root prowadzi dodatkowy focused review; ten dokument jest odpowiedzią wykonawcy,
nie niezależnym werdyktem audytu.
