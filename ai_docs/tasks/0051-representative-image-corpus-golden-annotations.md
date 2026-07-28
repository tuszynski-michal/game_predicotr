---
title: TASK-0051 Representative image corpus and golden annotations
status: in_progress
last_updated: 2026-07-28
---

# TASK-0051 — Representative image corpus and golden annotations

## Status

`in_progress`

## Goal

Zbudować zatwierdzony, odtwarzalny korpus 20–100 zdjęć oraz niezależne od
algorytmu golden annotations i mierzalne progi dla prototypu geometrii i OCR.

## Context

Właściciel dostarczył 12 zdjęć 960 × 1280 z jednej sesji i jednej gry.
Potwierdzają podstawowy wariant strony: 9 mini-layoutów w siatce 3 × 3,
plansze 3 × 5 i ciągłe numery sekwencji 1–108. Zgodnie z D-050 są
prototypowym korpusem roboczym, ale nie wystarczają do wykazania
reprezentatywności między grami, urządzeniami i rozdzielczościami.

Na podstawie D-049 właściciel dopuścił rozpoczęcie wyłącznie M5.1 przed
domknięciem fizyczznej bramki G3. Nie oznacza to zaliczenia TASK-0041,
TASK-0042 ani G3 i nie uruchamia jeszcze automatycznego pipeline'u zdjęć.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-006, D-010, D-014 i D-049 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- odpowiedzi właściciela na Q-015–Q-017,
- inwentaryzacja 20–100 reprezentatywnych zdjęć bez modyfikacji oryginałów,
- stabilny identyfikator i SHA-256 każdego pliku,
- metadane rozdzielczości, orientacji, źródła i kontrolowanych zakłóceń,
- jawne zasady dozwolonego użycia i lokalnego przechowywania materiału,
- podział korpusu według zdjęcia źródłowego bez przecieku między zbiorami,
- wersjonowany format golden annotations dla strony, dziewięciu plansz,
  numerów sekwencji i opcjonalnych komórek,
- walidator kompletności, geometrii, indeksów i referencji do manifestu,
- definicje metryk i progi akceptacji ustalone przed optymalizacją algorytmu.

## Out of scope

- implementacja detekcji strony, plansz lub komórek,
- uruchomienie PaddleOCR,
- klasyfikacja i trening symboli,
- zapis zdjęć jako BLOB w PostgreSQL,
- automatyczny import, staging i manual review,
- poprawianie albo nadpisywanie oryginalnych zdjęć,
- zaliczenie G3 bez fizycznych raportów urządzeń.

## Acceptance criteria

- [ ] Właściciel odpowiedział na Q-015–Q-017; Q-015 jest zamknięte, Q-016 i
      Q-017 pozostają otwarte.
- [ ] Zatwierdzony korpus zawiera 20–100 reprezentatywnych zdjęć.
- [x] Każde zdjęcie ma stabilny identyfikator, SHA-256, rozmiar, wymiary,
      orientację, źródło i tagi warunków.
- [x] Manifest nie zawiera ścieżek bezwzględnych ani binarnej zawartości zdjęć.
- [x] Oryginały pozostają niezmienione, a ich checksumy są ponownie
      weryfikowalne.
- [ ] Golden annotations opisują oczekiwany obszar strony, pozycje plansz,
      narożniki/bounding boxes, indeks 0–8 i numer sekwencji.
- [x] Walidator blokuje brakujące pliki, niezgodne checksumy, złe indeksy,
      geometrię poza obrazem i niepełne wymagane adnotacje.
- [x] Podział train/validation/test jest wykonywany według zdjęcia źródłowego,
      nie według wycinka.
- [ ] Definicje metryk i zaakceptowane progi geometrii oraz OCR są zapisane
      przed rozpoczęciem TASK-0054/TASK-0056.
- [x] Testy, formatowanie, lint i typecheck zmienionych części przechodzą.

## Technical notes

- Oryginały pozostają lokalnymi, ignorowanymi przez Git plikami pod
  kontrolowanym katalogiem `examples/imgs/`.
- Repozytorium przechowuje jedynie małe manifesty, schema, walidator, testowe
  metadane i — jeśli prawa na to pozwalają — jawnie zatwierdzone małe fixture.
- Współrzędne golden są zapisywane w pikselach obrazu po zastosowaniu wyłącznie
  deklarowanej orientacji EXIF; normalizacja obrazu należy do TASK-0053.
- Indeks pozycji planszy jest 0-based w porządku row-major siatki 3 × 3.
- Nie ustalamy progu confidence przed zdefiniowaniem ground truth i metryki.

## Existing seed inventory

Korpus roboczy zawiera 12 unikalnych plików JPEG 960 × 1280 o łącznym
rozmiarze `2 057 855` bajtów. Pokrywają numery sekwencji 1–108. Dokładne
rozmiary, SHA-256, tagi warunków i grupę źródłową zapisuje
`ai_docs/quality/m5-corpus-manifest.json`.

Wszystkie obrazy pochodzą z jednej gry, sesji i rozdzielczości. Jest to
zatwierdzony materiał do pracy kontraktowej i prototypowej, ale nie pełny
reprezentatywny benchmark G5.1.

## Expected files

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/quality/m5-corpus-manifest.json`
- `ai_docs/quality/m5-golden-annotations.json`
- `ai_docs/quality/m5-golden-annotations.schema.json`
- `ai_docs/quality/m5-quality-thresholds.json`
- `services/worker/src/game_predictor_worker/images/corpus.py`
- `scripts/validate_m5_corpus.py`
- `services/worker/tests/test_m5_corpus.py`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/validate_m5_corpus.py
.venv\Scripts\python.exe -m pytest services/worker/tests/test_m5_corpus.py -q
.venv\Scripts\python.exe -m ruff check scripts services/worker/tests
.venv\Scripts\python.exe -m mypy scripts
```

## Risks / open questions

- Q-016: stabilność siatki 3 × 3, ramek i obszaru numerów między grami.
- Q-017: możliwość późniejszego uzyskania około 100 oznaczonych wycinków na
  symbol z wielu zdjęć źródłowych.
- D-050 dopuszcza lokalne użycie dostarczonych zdjęć w tym prywatnym projekcie,
  ale nie ich redystrybucję ani dodanie binariów do Git.
- 12 obecnych zdjęć nie reprezentuje różnych gier, urządzeń, rozdzielczości
  ani wszystkich warunków optycznych.

## Outcome

Przygotowano wersjonowany manifest 12 lokalnych zdjęć, adnotacje ciągów
1–108, schema pełnych adnotacji geometrii, proponowane progi jakości oraz
walidator z testami negatywnymi. Walidator świadomie zwraca
`readyForGeometryBenchmark = false`, dopóki Q-016/Q-017, pełna geometria,
reprezentatywność i akceptacja progów nie zostaną domknięte.

Po D-056 zadanie było zablokowane. Właściciel dostarczył 31 dalszych zdjęć,
zamknął Q-016/Q-017 i polecił domknięcie G5. Rozszerzenie manifestu, pełne
goldeny geometrii oraz ponowna walidacja są realizowane w TASK-0091.
