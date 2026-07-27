---
title: Representative 500k benchmark dataset
status: done
last_updated: 2026-07-27
---

# TASK-0040 — Representative 500k benchmark dataset

## Status

`done`

## Goal

Wygenerować deterministyczny, reprezentatywny dataset jednej gry zawierający
dokładnie 500 000 ciągłych layoutów wraz z kontrolowanymi duplikatami,
konfiguracją payout-v2 i niezależnie weryfikowalnym manifestem wejścia do
benchmarków M3.5.

## Context

Fixture M1 zawiera tylko 1000 layoutów. Przed pomiarem SQLite, workera, APK i
urządzeń potrzebny jest jeden odtwarzalny zestaw o docelowym rzędzie wielkości,
który zachowuje domenowe wymiary 3 × 5, tekstowy codec v1, ciągłość sekwencji i
rzadkie duplikaty.

`TASK-0039` pozostaje zablokowany wyłącznie w fizycznym buildzie/odbiorze APK.
Polecenie właściciela z 2026-07-27 jawnie rozpoczyna M3.5; TASK-0040 nie zmienia
ACL i nie uznaje bramki G3.4 za zaliczoną.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/PROJECT_BRIEF.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- stały seed i jawna wersja generatora benchmarkowego,
- jedna gra 3 × 5, koszt spinu 10, `signature_cell_width = 2`,
- realistyczny alfabet z jednym jokerem i kompletna konfiguracja payout-v2,
- dokładnie 500 000 rekordów o `sequence_number = 1..500000`,
- 5–10 jawnych grup duplikatów treści bez luk w numeracji,
- generowanie strumieniowe/batchowe bez materializacji 500 000 layoutów,
- deterministyczne payouty lub dane wystarczające do ich odtworzenia,
- manifest z seedem, wersjami, licznikami, grupami duplikatów i checksumą
  logiczną,
- walidator odtwarzający ciągłość, codec, zakres symboli, duplikaty i checksumę,
- zapis wielkości wygenerowanych danych jako wejścia do estymacji 12–15 gier.

## Out of scope

- pomiar exact/prefix/pełnego Target na telefonie (`TASK-0041`),
- ostateczna decyzja TEXT kontra BLOB (`TASK-0042`),
- rzeczywisty APK i aktualizacja urządzenia z `TASK-0039`,
- import zdjęć, OCR/ML, Redis/Celery i chmura.

## Acceptance criteria

- [x] Dwa przebiegi z tym samym seedem tworzą identyczną checksumę logiczną.
- [x] Dataset ma dokładnie 500 000 ciągłych numerów bez luk.
- [x] Każda plansza ma 15 poprawnych kodów oraz 30-znakową sygnaturę codec v1.
- [x] Istnieje 5–10 jawnych grup duplikatów, a poza nimi sygnatury są unikalne.
- [x] Generator i walidator działają bounded-memory oraz raportują postęp.
- [x] Manifest zawiera wszystkie parametry potrzebne do powtórzenia benchmarku.
- [x] Testy pokrywają deterministyczność, granice batchy, duplikaty i korupcję.
- [x] Pełna jakość przechodzi bez uruchamiania benchmarku urządzeniowego.

## Technical notes

- Layouty muszą być generowane bez `set` przechowującego 500 000 pełnych
  sygnatur. Deterministyczna bijekcja/licznik jest preferowana nad losowaniem z
  retry.
- Należy zachować tekstową sygnaturę v1 do czasu decyzji TASK-0042.
- Artefakt benchmarkowy nie jest domyślnie bundlowany do APK ani commitowany,
  jeżeli jego rozmiar jest niepraktyczny; repo zawiera generator, walidator,
  manifest dowodowy i małe testy.
- Pełne generowanie 500 000 rekordów ma być jawnie uruchamianą komendą Windows,
  nie częścią zwykłych unit testów.

## Expected files

- generator/kontrakty fixture benchmarkowego w `services/worker/src/`
- testy jednostkowe generatora i walidatora,
- skrypt PowerShell/Python uruchamiający pełne 500 000 rekordów,
- manifest/report w `ai_docs/quality/`,
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
pytest services/worker/tests -q
python scripts/generate_m35_benchmark_dataset.py --layout-count 500000
python scripts/validate_m35_benchmark_dataset.py
npm run quality
```

## Risks / open questions

- Pełne dane mogą zajmować setki MB; duży artefakt pozostaje lokalny i
  ignorowany przez Git.
- Payout engine dla 500 000 rekordów może dominować czas generowania; pomiar
  workera należy do TASK-0041, więc TASK-0040 nie może maskować go
  predefiniowanymi wynikami bez jawnego opisu.

## Outcome

Dodano generator `m35-benchmark-v1`, który przez deterministyczną bijekcję
afiniczną tworzy layout na żądanie i nie przechowuje zbioru 500 000 sygnatur.
Dokładnie sześć ostatnich rekordów powtarza jawne wcześniejsze sekwencje;
pozostałe 499 994 sygnatury są unikalne.

Generator zasila istniejący produkcyjny pipeline snapshotu SQLite i oblicza
każdy payout prawdziwym engine `payout-v2`. Dodatkowy kanoniczny manifest
zapisuje seed, pełną konfigurację gry/reguł, grupy duplikatów, checksumy i
rozmiar. Niezależny walidator najpierw uruchamia produkcyjną kontrolę artefaktu,
a następnie partiami po 1000 odtwarza każdą sygnaturę i każdy payout.

Pełny przebieg utworzył lokalny, ignorowany przez Git artefakt
`artifacts/m35-benchmark`:

- `layoutCount = 500000`, sekwencje `1..500000`,
- `uniqueSignatureCount = 499994`,
- sześć grup duplikatów po dwa rekordy,
- logiczny SHA-256
  `1b03171b268be8ee370151fc1033a7e64cb644d21610a2d4145be0d4e7492d89`,
- SHA-256 pliku SQLite
  `04b4136ca2c9452bc45de09182907e1a0276acb9f4f96b209f8da00a8b0e0f27`,
- rozmiar `41025536` bajtów (`39.125 MiB`).

Liniowa estymacja samego snapshotu wynosi `469.5 MiB` dla 12 gier i
`586.875 MiB` dla 15 gier. Dowód zapisano w
`ai_docs/quality/m35-benchmark-dataset-report.json`.

Weryfikacja:

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_benchmark_dataset.py -q
.venv\Scripts\python.exe scripts/generate_m35_benchmark_dataset.py --layout-count 500000
.venv\Scripts\python.exe scripts/validate_m35_benchmark_dataset.py
npm run quality
```

Pełne kontrole składowe zakończyły się poprawnie: formatowanie, OpenAPI, lint
TypeScript/Python/PowerShell, cztery kontrole typów TypeScript, strict mypy,
`64` testy mobile, `57` panelu, `23` shared, `9` klienta API oraz `235`
standardowych testów Python (`8` integracyjnych PostgreSQL pominiętych zgodnie
z ich jawną flagą). Snapshot M1 i fixture również przeszły walidację.

Zbiorcze `npm run quality` uruchomione poza sandboxem nie mogło odczytać
`apps/mobile/assets/snapshot/manifest.json` z powodu istniejącego ograniczenia
ACL opisanego w `TASK-0039`. Ten sam typecheck uruchomiony jako właściciel pliku
przeszedł; ACL nie zmieniono. Dodatkowo usunięto kolizję nazwy modułu pytest,
zmieniając nazwę integracyjnego testu release workflow bez zmiany jego treści.
