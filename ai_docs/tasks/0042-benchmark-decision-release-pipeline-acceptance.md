---
title: Benchmark decision and release pipeline acceptance
status: blocked
last_updated: 2026-07-27
---

# TASK-0042 — Benchmark decision and release pipeline acceptance

## Status

`blocked`

## Goal

Zebrać dowody M3.4–M3.5 w jednym deterministycznym raporcie, podjąć
warunkową decyzję o pozostaniu przy tekstowej sygnaturze, Expo SQLite i
TypeScript albo wskazać potrzebę zmiany adaptera oraz zaliczyć G3 wyłącznie po
spełnieniu wszystkich kryteriów fizycznych i release.

## Context

TASK-0040 dostarczył zwalidowany dataset 500 000 layoutów. TASK-0041 zapisał
wyniki Windows/SQLite i workera oraz przygotował harness Android, ale pozostaje
zablokowany bez APK i pomiarów na Pixelu oraz Samsungu. TASK-0039 ma kompletną
automatyczną macierz awarii, lecz nie ma fizycznego APK i aktualizacji
urządzenia. Na polecenie właściciela TASK-0042 rozpoczyna się mimo tych braków,
aby brakujące dowody były raportowane maszynowo, a nie zastępowane
założeniami.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/quality/m35-benchmark-dataset-report.json`
- `ai_docs/quality/m35-repository-benchmark.json`
- `ai_docs/quality/m35-worker-benchmark.json`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- walidacja spójności checksum, wersji i liczników raportów M3.5,
- ocena exact, prefix, pełnego cyklu, Target E2E, widocznego postępu i pamięci
  na obu urządzeniach,
- jawny dowód płynnego przewijania wirtualizowanej tabeli na obu urządzeniach,
- porównanie wszystkich pomiarów z budżetami `TEST_STRATEGY.md`,
- ocena bounded batch workera i granicy rozmiaru kilku GB,
- ocena pełnego workflow panel → snapshot → zweryfikowany APK,
- dowód odtwarzalności, niezmienności i gotowego APK do ręcznego sideloadu,
- kontrola bezpośrednich zależności pod kątem niedozwolonego Redis/Celery oraz
  alternatywnego natywnego adaptera,
- raport JSON z osobnymi stanami `passed`, `failed` i `missing`,
- decyzja architektoniczna dopiero po kompletnych wynikach urządzeniowych.

## Out of scope

- tworzenie brakującego APK bez rozwiązania blokady ACL,
- wykonywanie pomiaru Android bez podłączonego urządzenia,
- wybór konkretnego nowego adaptera przed dowodem przekroczenia budżetu,
- Redis/Celery, mikroserwisy, chmura i publiczna dystrybucja,
- OCR/ML oraz M4.

## Acceptance criteria

- [x] Jeden skrypt tworzy deterministycznie ustrukturyzowany raport G3.
- [x] Brak dowodu daje `missing/blocked`, a nie fałszywy wynik pozytywny.
- [x] Niezgodny checksum, wersja, offline state albo przekroczony budżet daje
      dokładny wynik `failed`.
- [x] Raport obejmuje dataset, SQLite, worker, Pixel, Samsung, rozmiary oraz
      workflow release.
- [x] Decyzja `retain_text_signature_and_typescript_adapter` powstaje wyłącznie
      po przejściu obu urządzeń; przekroczenie budżetu wskazuje
      `adapter_change_required`.
- [x] Raport potwierdza brak Redis/Celery i alternatywnego natywnego adaptera
      w bezpośrednich zależnościach.
- [ ] Pełny workflow tworzy gotowy, odtwarzalny i zweryfikowany APK wskazywany
      przez panel.
- [ ] Wszystkie pomiary `TEST_STRATEGY.md`, w tym ręczne przewijanie, są
      zapisane dla obu urządzeń.
- [x] Testy, lint, format i typecheck zmienionych części przechodzą.
- [ ] G3 zostaje oznaczona jako zaliczona dopiero, gdy raport ma status
      `passed`.

## Assumptions

- brak pliku lub pola dowodowego jest stanem `missing`, nie `failed`,
- dowód niezgodny z kontraktem albo jawnie negatywny jest stanem `failed`,
- przy kilku raportach tego samego modelu oceniany jest najnowszy według
  `capturedAt`, a ścieżka wybranego raportu pozostaje w wyniku,
- robocze budżety obowiązują na obu urządzeniach; decyzja opiera się na
  słabszym wyniku,
- zaakceptowana granica „kilku GB” jest automatycznie sprawdzana jako najwyżej
  5 GiB dla estymowanego wydania 15 gier,
- wynik Windows jest baseline’em diagnostycznym i sam nie zatwierdza adaptera
  Android,
- plik dowodu release jest produktem odbioru TASK-0039; TASK-0042 nie tworzy
  go na podstawie opisu tekstowego.

## Release evidence contract

Domyślna ścieżka:
`ai_docs/quality/m35-release-workflow-acceptance.json`.

Raport musi zawierać `status = passed`, pomiary rozmiaru PostgreSQL/SQLite/APK,
potwierdzenia pełnego workflow z panelu, odtwarzalności tych samych wejść,
niezmienności poprzednich artefaktów, audytu offline, zgodności snapshotu,
gotowości APK do pobrania oraz aktualizacji in-place z aktywacją nowej wersji.
Brak pliku pozostaje jawną blokadą TASK-0039.

## Expected files

- `services/worker/src/game_predictor_worker/benchmarks/acceptance.py`
- `services/worker/tests/test_benchmark_acceptance.py`
- `scripts/evaluate_m35_acceptance.py`
- `ai_docs/quality/m35-acceptance-report.json`
- `package.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe scripts/evaluate_m35_acceptance.py
.venv\Scripts\python.exe scripts/evaluate_m35_acceptance.py --require-pass
.venv\Scripts\python.exe -m pytest services/worker/tests/test_benchmark_acceptance.py -q
.venv\Scripts\python.exe -m ruff check services/worker scripts
.venv\Scripts\python.exe -m mypy services/worker/src scripts
```

`--require-pass` ma zwracać kod różny od zera, dopóki fizyczne dowody są
niekompletne.

## Risks / open questions

- TASK-0041 nie może dostarczyć raportów urządzeń bez benchmarkowego APK.
- TASK-0039 nie może dostarczyć dowodu release bez minimalnego dostępu builda
  do dwóch plików snapshotu i fizycznej aktualizacji urządzenia.
- Jeśli urządzenie przekroczy 10 s dla Target E2E, potrzebny będzie osobny
  pomiar po udokumentowanej zmianie adaptera przed zaliczeniem G3.

## Outcome

### Changed

- dodano czystą, testowaną ocenę datasetu, baseline SQLite, workera, obu
  urządzeń, zależności i fizycznego workflow release,
- `evaluate_m35_acceptance.py` wykrywa raporty urządzeń, wybiera najnowszy dla
  każdego modelu, zapisuje atomowo jeden raport i opcjonalnie wymaga pełnego
  wyniku przez `--require-pass`,
- harness Android raportuje czas gotowości wskaźnika postępu, a kolektor ADB
  przyjmuje jawny wynik ręcznego odbioru wirtualizowanej tabeli; brak parametru
  pozostaje `null`, nie domyślnym sukcesem,
- kontrola manifestów potwierdza, że bezpośrednie zależności nadal używają
  `expo-sqlite` i nie zawierają Redis, Celery ani alternatywnego natywnego
  adaptera SQLite,
- dodano komendę `m35:acceptance:evaluate`.

### Current evaluation

`ai_docs/quality/m35-acceptance-report.json` ma status `blocked`:

- `passed`: dataset 500 000, baseline SQLite, bounded worker i kontrola
  zależności,
- `missing`: Pixel 10 Pro XL, Galaxy S21 Ultra, workflow panel → ready APK,
  odtwarzalność/niezmienność release oraz rozmiary i aktualizacja in-place,
- decyzja: `pending_device_evidence`,
- nie ma wyniku `failed`, więc obecne pomiary nie uzasadniają zmiany adaptera.

`--require-pass` zgodnie z kontraktem zwraca kod `1`.

### Verification

- `243 passed, 8 skipped` Python; skipy wymagają jawnej flagi fizycznego
  PostgreSQL,
- `66 passed` mobile,
- `8 passed` dla helperów benchmarku i nowej oceny,
- mypy: `94 source files`,
- Ruff, TypeScript, ESLint zmienionych plików, Prettier oraz składnia 11
  skryptów PowerShell przeszły.

Pierwszy pełny pytest bez `--basetemp` nie mógł odczytać systemowego katalogu
`pytest-of-user` w sandboxie. Powtórzenie z ignorowanym
`.tmp/task0042-pytest` wewnątrz workspace przeszło w całości.

### Not completed

- nie utworzono benchmarkowego APK i nie wykonano pomiarów obu telefonów,
- nie utworzono fizycznego raportu release z TASK-0039,
- nie podjęto ostatecznej decyzji TEXT/BLOB ani adaptera,
- G3 i M3 pozostają niezaliczone.

### Recommended next step

Rozwiązać minimalny dostęp builda do chronionych plików bez zmiany ACL bez
zgody właściciela, dokończyć TASK-0039 i TASK-0041, a następnie ponowić
`m35:acceptance:evaluate -- --require-pass`.
