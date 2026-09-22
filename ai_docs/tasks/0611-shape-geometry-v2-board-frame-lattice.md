---
title: TASK-0611 — Real-data board-frame lattice core for shared geometry V2.1
status: in_progress
---

# TASK-0611 — Rdzeń V2.1 dla siatki osobnych ramek plansz

## Status

`in_progress`

## Goal

Wykrywać na prawdziwych zdjęciach 777 i Mumii pełną siatkę 3 × 3 osobnych ramek plansz, bez zależności od koloru, jako deterministyczną propozycję testową bez importu ani zapisu danych gry.

## Context

Rzeczywiste `seq_1-9.jpg` Mumii oraz próbki 777 nie mają jednej ramki wokół całej strony. Obecny `shape-frame-geometry-v2-core-v1` szuka właśnie takiej ramki, więc zwraca `frame_evidence_insufficient` dla wszystkich sprawdzonych zdjęć. Zmiana progu pola byłaby błędna: pojedyncza plansza zostałaby omyłkowo potraktowana jak cała strona.

## Dependencies / entry conditions

- Potwierdzone read-only sprawdzenie czterech zdjęć `C:\Users\tuszy\Documents\mumie` i czterech zdjęć z katalogu testowego 777: obecny rdzeń nie zwrócił propozycji dla żadnego.
- TASK-0604/G02, G03 i globalna biblioteka pozostają historycznie zgodne; nie ma aktywnego profilu V2 ani zgody na import V2.
- Operator udostępnił oba katalogi wyłącznie do lokalnego pomiaru. Zdjęcia nie trafiają do repozytorium, bazy ani artefaktów taska.

## Recommended execution

`gpt-5.6-sol`, reasoning `high`: zmiana łączy geometrię obrazu, deterministyczny ranking i zachowanie fail-closed. Po implementacji wymagany jest niezależny review `gpt-6-astra`, reasoning `medium`; eskalacja jest wymagana, jeśli realne zdjęcia wymagają kopiowania JPEG-ów do repozytorium albo osłabienia warunku kompletnej siatki.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-421 i D-428)
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`

## Scope

- Dodać do wspólnego rdzenia jawny, testowy wariant `board-frame-lattice-v2.1`, uruchamiany wyłącznie gdy wcześniejszy detektor ramki całej strony nie daje propozycji.
- Znajdować kandydatów pojedynczych ramek przez kontrast i geometrię, normalizować ich kształt względem mediany oraz deterministycznie przypisywać tylko kompletną, jednoznaczną siatkę 3 × 3.
- Wyprowadzać dziewięć quadów plansz i po piętnaście quadów komórek wewnątrz każdej planszy. Kolor może być metryką, lecz nie bramką ani kluczem dopasowania.
- Zachować `needs_manual_review` dla brakującego slotu, wieloznacznej siatki, pionowego ucięcia albo słabego dowodu komórek.
- Dodać regresje syntetyczne dla dziewięciu osobnych ramek o różnych kolorach oraz read-only kontrolę rzeczywistych Mumii i 777, bez kopiowania ich do repozytorium.

## Out of scope

- Podłączenie V2.1 do importu, tworzenie profilu globalnego, zmiany stanu `candidate`/`active`, migracje i endpointy.
- Import, cropy, symbole, OCR, payouty, V1.0, V1.1 oraz istniejący full-page wariant V2.
- Automatyczne uznawanie wyniku za import-ready.

## Acceptance criteria

- [ ] Syntetyczna pełna siatka dziewięciu odrębnych ramek daje `proposal` i dokładnie 9 × 15 quadów niezależnie od koloru ramek.
- [ ] Brak jednej ramki, istotna niejednoznaczność albo ucięcie daje `needs_manual_review` bez plansz.
- [ ] Wcześniejszy test pojedynczej ramki całej strony pozostaje zielony i nie zmienia payloadu tego wariantu.
- [ ] Read-only kontrola czterech Mumii i reprezentatywnych pełnych 777 zapisuje wyłącznie wynik konsoli; nie tworzy plików, jobów ani rekordów.
- [ ] Nie powstaje aktywny profil globalny ani ścieżka importu V2.1.

## Technical notes

`detect_shape_geometry_v2` zachowuje najpierw istniejącą ścieżkę full-page. Dopiero jej brak przechodzi do nowego resolvera ramek plansz. Resolver nie wybiera najlepszego pojedynczego konturu jako strony: wymaga dziewięciu różnych kandydatów z rosnącymi centroidami trzech wierszy i kolumn oraz zgodnymi rozmiarami. Każdy slot otrzymuje najwyżej jednego kandydata; duplikat, brak albo konflikt kończy się review.

Quad strony jest wyłącznie geometryczną obwiednią kompletnej siatki używaną do diagnostyki i kontroli proporcji. Quady plansz oraz komórek wyprowadza się lokalnie z wykrytych ramek plansz, nie przez dzielenie obwiedni na dziewięć równych prostokątów. To chroni perspektywę i odstępy pomiędzy planszami.

Wynik V2.1 pozostaje `proposal_requires_manual_confirmation` w przyszłym preflighcie. Nie wolno przekazywać do globalnego profilu obrazu, ścieżki, symboli, payoutów, sekwencji, lokalnej kotwicy ani danych V1.1. Dopiero kolejny task będzie mógł zbudować descriptor-only kandydat z zatwierdzonych wyników V2.1 i udostępnić test Mumii w panelu.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/core.py` — wariant detekcji siatki ramek.
- Istniejące: `services/worker/tests/test_shape_geometry_v2_core.py` — regresje pełnej i niepełnej siatki.
- Istniejące: `ai_docs/process/DECISION_LOG.md` — decyzja o V2.1.
- Istniejące: `ai_docs/process/CURRENT_STATE.md` — wynik taska po ukończeniu.

## Test cases

- Dziewięć perspektywicznych ramek o mieszanych kolorach → `proposal`, sloty 0..8, 15 komórek per slot.
- Osiem ramek albo dwa konkurencyjne kontury jednego slotu → `needs_manual_review`, brak quadów importowych.
- Jedna pełnostronicowa ramka z istniejącej regresji → niezmieniony payload starej ścieżki.
- Cztery Mumie i ograniczona próbka pełnych 777 → wynik read-only zapisany w raporcie Outcome; niepowodzenie pozostaje blockerem taska, nie jest maskowane zmianą progów.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; timeout maksymalnie 120 s na krok
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_shape_geometry_v2_core.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/shape_geometry_v2/core.py services/worker/tests/test_shape_geometry_v2_core.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/shape_geometry_v2/core.py
```

## Risks / open questions

- Rzeczywiste kadry mogą mieć za słaby kontrast ramek dla geometrii bez lokalnej kalibracji. Wtedy task kończy się fail-closed i dokumentuje dowód; nie dodaje koloru per gra ani fallbacku do V1.1.
- V2.1 jest nowym testowym wariantem obok historycznego `framed_full_page_v2`; nie zmienia istniejącej aktywacji globalnej biblioteki.

## Outcome

Wypełnia agent po pracy.
