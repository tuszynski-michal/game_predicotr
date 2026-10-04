---
title: TASK-0845 — Mumie, test rzeczywistego folderu
status: done
last_updated: 2026-10-05
---

# TASK-0845 — Mumie, test rzeczywistego folderu

## Status

`done`

## Goal

Przetworzyć 200 zdjęć pierwszego folderu Mumii i porównać dwa modele na 11
nowych zdjęciach z zatwierdzoną geometrią, dostarczając przegląd i uczciwy raport.

## Context

Po 20 zdjęciach iteracja 3 pogorszyła image-macro względem stanu początkowego,
a iteracja 4 nie wybrała lepszego modelu. Operator dodał 11 zatwierdzeń i zlecił
test folderu `C:\Users\tuszy\Documents\mumie wybrane\1 - 23175 cut` (2580 JPEG-ów).

## Dependencies / entry conditions

Fakty: 31 kompletnych zdjęć, rewizja anotacji 591, dwa eksporty iteracji 2 i 3.
11 nowych zdjęć nie uczestniczyło w treningu. Modele sprawdzane istniejącym ONNX
na CPU. Założenie: 200 równomiernie dobranych zdjęć do pierwszego przeglądu;
metadane zakresu nie stanowią referencji geometrii ani dowodu niezależności.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Według planu testu z 2026-10-05, bez delegowania.
Brak zgodnych SHA, nieaktualne geometrie lub błędy inferencji blokują krok.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/MUMIE_REAL_FOLDER_TEST_20261005.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/tasks/0802-neural-grid-whole-screen-network.md` — D-483
- `ai_docs/quality/MUMIE_TRAINING_RESUME_20261004.md`

## Scope

Manifest źródeł, dobór 200 zdjęć, inferencja dwóch zapisanych modeli, osobna
ocena nowych 11, nakładki, przegląd i trwały raport z ograniczonych kroków.

## Out of scope

Trening, aktywacja modeli, baza, migracje, V3-D, symbole, payouty i zatwierdzenia.

## Acceptance criteria

- [x] Źródła i modele przypięte do SHA, dobór deterministyczny i bez znanych źródeł.
- [x] 200 zdjęć ma wyniki obu modeli oraz nakładki; braki nie są maskowane.
- [x] 11 nowych zdjęć oceniono metryką D-483, bez uczenia na nich.
- [x] Odróżniono zgodną liczność plansz od poprawnej geometrii.
- [x] Wznowienie i integralność potwierdzone w nowym procesie.
- [x] Raport, testy, CURRENT_STATE, Outcome i osobny commit.

## Technical notes

Wykorzystać `neural_grid_inference.onnx_engine`, `structurally_valid`,
`neural_grid_metrics.evaluate_photo`/`summarize`, `assisted_annotation.photo_complete`
i katalog labu. Nowe narzędzie jest adapterem testu, nie równoległym silnikiem.
Nie przypisywać ostatecznych sequence_number wykrytym planszom.

## Expected files

Nowy CLI `scripts/test_mumie_folder.py`, testy, raport jakości oraz plan i task.
Szablon podglądu `scripts/mumie_folder_gallery.html`.
Zmiana CURRENT_STATE. Wyniki i obrazy w ignorowanym `artifacts/` głównego checkoutu.

## Test cases

Zakresy sortowane liczbowo; rozłożenie doboru po zakresie; wykluczenia SHA;
drift obrazu blokuje wznowienie; brakujące wynikowe pliki nie dają pozornego sukcesu.

## Verification

Testy adaptera, Ruff check/format, Mypy strict zakresu. Inferencja w krokach
do 120 s z postępem, nowy proces odzyskuje wyniki, podgląd obejrzany wizualnie.

## Risks / open questions

Pierwszy folder i nowe 11 nie są niezależnymi nagraniami. Zgodność 9 plansz
nie wykrywa wszystkich przesunięć granic. Bez etykiet 200 nie ma accuracy.

## Outcome

Wykonano 422 inferencje: po 200 zdjęć folderu i 11 nowych zatwierdzonych
zdjęć na iteracjach 2 i 3. Oba modele znalazły po 9 plansz na wszystkich
200 zdjęciach; zero nieprawidłowych struktur i pól poza obrazem. To diagnostyka,
nie accuracy. Obejrzano 20 równomiernie dobranych par nakładek i dwa arkusze
135 wycinków; bez oczywistego przesunięcia siatek, przy widocznych odblaskach
i zasłonięciach obrazu źródłowego. Nie oceniono ręcznie każdego pola z 200 zdjęć.

Oba modele spełniły D-483 dla 11/11 zdjęć i 99/99 plansz. Audyt wykazał,
że wszystkie 99 referencji pochodzi z niezmienionych propozycji iteracji 3
zatwierdzonych przez operatora. Zgodność pozostaje ważna, ale wynik nie dowodzi
niezależnej przewagi iteracji 3. Zatwierdzeń nie zmieniono. Raport i podgląd
ujawniają ten fakt. Brak nowego treningu, DB, migracji, aktywacji i V3-D.

7 testów adaptera PASS; Ruff check/format PASS; Mypy strict CLI PASS (jeden
moduł z pominięciem kontroli importowanych zależności). Nowe procesy odzyskały
211 wyników dla każdego modelu, pending=0; verify, finish i audit PASS.
W przeglądarce sprawdzono nawigację, filtry 200/11, pusty filtr i wycinki.
Raport: `ai_docs/quality/MUMIE_REAL_FOLDER_TEST_20261005.md`.

Numer zmieniono z 0844 na 0845 przed commitem: w głównym checkoutcie inny
trwający task zajął 0844. Jego zmian nie włączono do tego zadania.
Commit: `v1.7.189`; pełny hash zostanie dopisany po commicie.
