---
title: TASK-0171 fast selection real corpus regression and activation
status: in_progress
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0171 — Fast selection real-corpus regression and activation

## Status

`in_progress`

## Goal

Udowodnić na realnym korpusie, że nowa selekcja jest szybka, nie traci różnych
ekranów i może zostać aktywowana dla nowych runów przed końcowym odbiorem
TASK-0157.

## Context

Pełne przebiegi 40 000 zdjęć nie mogą służyć jako metoda strojenia każdej małej
zmiany. Najpierw obowiązują krótkie regresje, a jeden pełny rerun jest końcową
bramką techniczną.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`
- `ai_docs/tasks/completed/0165-image-selection-stage-timing-and-real-corpus-baseline.md`
- `ai_docs/tasks/completed/0166-reduced-jpeg-scan-and-bounded-cpu-budget.md`
- `ai_docs/tasks/completed/0167-appearance-only-sequential-image-grouping.md`
- `ai_docs/tasks/completed/0168-first-usable-range-free-representative-selection.md`
- `ai_docs/tasks/completed/0169-range-agnostic-selection-output-and-import-handoff.md`
- `ai_docs/tasks/0170-versioned-image-scan-cache-and-resume.md`

## Scope

- zbudować niezależny golden kolejnych ekranów i dopuszczalnych granic,
- uruchamiać iteracje najpierw na 500–1000, następnie 3000 zdjęć,
- przygotować dokładnie 40 000 naturalnie uporządkowanych zdjęć i uruchomić
  jeden kontrolowany profil po przejściu krótkich bramek,
- zmierzyć scan throughput, całkowity czas, peak RSS, liczbę grup, false split,
  false merge, output count, cache hits i błędy plików,
- potwierdzić zero wywołań OCR, geometrii plansz i croppera w selekcji,
- porównać liczbę JPEG-ów przekazanych do Importu z liczbą wejść,
- aktywować v9 tylko po wyniku `ready`; inaczej pozostawić status `optimize`.

## Out of scope

- testowanie dokładności OCR, cropów i symboli Importu layoutów,
- pełne 500 000 layoutów,
- profil 100 000 zdjęć w wersji 0.4,
- dalsze strojenie podczas pracującego pełnego joba.

## Acceptance criteria

- [ ] Krótki profil raportuje porównywalny throughput pierwszego przebiegu bez
      cache na komputerze właściciela.
- [ ] Pełny run 40 000 zdjęć zapisuje całkowity czas, throughput i peak RSS bez
      sztywnego progu czasu.
- [ ] Właściciel po otrzymaniu wyniku jawnie wybiera `accepted | optimize`.
- [ ] Golden ma zero fałszywych scaleń różnych kolejnych ekranów.
- [ ] Recall unikalnych kolejnych ekranów wynosi 100%; false split jest jawnie
      raportowany, ale nie może prowadzić do utraty zdjęcia.
- [ ] Każda grupa z dekodowalnym wejściem publikuje jeden reprezentant.
- [ ] OCR, `PageBoardDetector`, homografia, cropy komórek i symbol inference mają
      dokładnie zero wywołań w selektorze.
- [ ] Działający upload nie został zmieniony ani powtórzony przez benchmark.
- [ ] Raport zawiera decyzję `ready | optimize | reject` i porównanie z v8.

## Technical notes

Każdy benchmark ma jawny timeout i cleanup. Pełnego profilu nie wolno uruchomić,
jeśli profil 3000 nie spełnia throughputu albo golden wykazuje false merge.

## Expected files

- `scripts/run_image_selection_benchmark.py`
- `scripts/run_image_selection_benchmark.ps1`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Verification

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile smoke -TimeoutSeconds 300
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 3000 -TimeoutSeconds 900
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 30000 -TimeoutSeconds 3600
```

## Risks / open questions

- Końcowa ocena czasu należy do właściciela. Raport nie może sam oznaczyć
  `ready` wyłącznie dlatego, że proces jest szybszy od wersji historycznej.

## Outcome

Realizacja rozpoczęta 2026-08-05 na wyzerowanej lokalnej bazie. Aktywny
historyczny job `3b8d1d17-b4fd-4af8-8e83-54cc5afb262b` został kontrolowanie
anulowany przy checkpointcie `6464 / 32079`, procesy API/worker/Admin zatrzymano,
a lokalny PostgreSQL zresetowano i zmigrowano do head. Kontrola po resecie
potwierdziła `games = 0`, `jobs = 0`, `image_selection_runs = 0` i `layouts = 0`.
Źródłowy staging 32 079 JPEG-ów oraz artefakty APK pozostały nienaruszone.

Niezależny golden
`ai_docs/quality/image-selection-real-corpus-golden-v1.json` opisuje pierwsze
500 naturalnie uporządkowanych zdjęć i 20 kolejnych ekranów od layoutów `1–9`
do `172–180`. Pierwsza próba ujawniła, że binarny pHash był niestabilny dla
niemal identycznych klatek, a historyczne progi były nieadekwatne do realnej
skali odległości. Przedaktywacyjny v9 używa teraz ciągłego,
znormalizowanego deskryptora DCT obszaru plansz oraz wycentrowanej odległości
cosinusowej. Selector fingerprint wynosi
`eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`, a
scan-adapter fingerprint
`408bd8574526e07d055958734ce6136288beff5a54cf1dcd9f76f6291edea396`.
Domyślny produkcyjny manifest nadal pozostaje v8.

Wyniki krótkich profili z `scanWorkers = 4`:

| Wejście | Czas cold | Throughput | Peak RSS delta | Grupy / reprezentanci | Golden |
|---:|---:|---:|---:|---:|---|
| 500 | 16,725 s | 29,8947/s | 82 014 208 B | 20 / 20 | recall 100%, false merge 0, false split 0 |
| 3000 | 131,558 s | 22,8036/s | 99 037 184 B | 217 / 217 | przypięte pierwsze 500: recall 100%, false merge 0, false split 0 |

Warm-cache rerun był deterministycznie identyczny i trwał odpowiednio 2,281 s
oraz 18,822 s przy 500/500 i 3000/3000 trafień. Oba profile raportują dokładnie
zero wywołań OCR, `PageBoardDetector`, homografii, croppera i symbol inference.
Testy selektora i adapterów przechodzą `81 passed`; Ruff oraz MyPy zmienionych
modułów również przechodzą.

TASK-0171 pozostaje otwarty. Właściciel potwierdził 2026-08-05 dostępność
40 000 naturalnych zdjęć i polecił aktywować v9 przed właściwym runem, aby nowy
run utworzony z panelu był już badaną wersją. Produkcyjny
`DEFAULT_SELECTOR_MANIFEST` oraz fingerprint nowych runów wskazują teraz
`fast-image-selector-v9`; v2–v8 pozostają w rejestrze kompatybilności i mogą być
wznawiane bez zmiany zachowania.

Aktywacja nie oznacza jeszcze odbioru bramki. Po uruchomieniu pełnego korpusu
trzeba zapisać czas, throughput, peak RSS, grupy, reprezentantów, cache i
liczniki kosztownych adapterów, porównać wynik z v8 oraz uzyskać jawną decyzję
właściciela `accepted | optimize`.

Regresja aktywacji przeszła: `88 passed` dla selektora, adapterów i durable
handlera oraz `28 passed` dla API tworzenia/rerunu stagingu. Ruff, MyPy i jawna
kontrola importów potwierdziły, że API i worker widzą ten sam fingerprint v9.
Oba worker lanes pozostają zatrzymane, aby właściciel uruchomił nowe procesy już
z aktywnym manifestem.
