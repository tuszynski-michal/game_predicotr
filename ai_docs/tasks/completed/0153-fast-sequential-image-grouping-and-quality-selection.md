---
title: TASK-0153 fast sequential image grouping and quality selection
status: done
release: "0.4"
last_updated: 2026-08-02
---

# TASK-0153 — Fast sequential image grouping and quality selection

## Status

`done`

## Goal

Zaimplementować wersjonowany `fast-image-selector-v1`, który strumieniowo
grupuje kolejne ujęcia i automatycznie wybiera bezpiecznego reprezentanta bez
uruchamiania cropów komórek i klasyfikacji symboli.

## Context

Pełny pipeline na każdym duplikacie nie skaluje się do 10–30 tys. zdjęć.
Selektor musi łączyć tanią jakość obrazu, geometrię, fingerprint i sparse OCR,
przy czym fałszywe scalenie jest niedopuszczalne.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_07_0_EXECUTION_PLAN.md`
- `ai_docs/tasks/0151-image-selection-domain-contract-and-storage.md`

## Scope

- dodać porty miniatury, jakości, lattice/fingerprint i range recognizer,
- reużyć Pillow, OpenCV, NumPy oraz wymienny OCR bez sprzęgania domeny,
- przetwarzać naturalną kolejność wejścia małymi partiami,
- wykrywać dowolny skok zakresu bez oczekiwania ciągłości,
- utrzymywać top-k kandydatów i uruchamiać dokładniejszą weryfikację tylko dla
  nich,
- uwzględnić konsensus liczby plansz, końcową stronę 1–9 i późniejsze duplikaty,
- zapisać metryki, reason codes, wersję, checkpoint i deterministyczny wynik,
- przygotować golden grupowania, jakości i przypadków zasłoniętych.

## Out of scope

- symbol inference i cropy 3×5,
- UI manualnej decyzji,
- kopiowanie finalnego outputu,
- trening progów z zachowania użytkownika.

## Acceptance criteria

- [x] Skok `19–27` do `400–408` tworzy dwie prawidłowe grupy bez raportu luki.
- [x] Powrót zakończonego zakresu jest pomijany, a nierozwiązany zakres może
      przyjąć późniejszego dobrego kandydata.
- [x] Kandydat zasłonięty, obcięty lub bez pełnej geometrii nie jest auto-selected.
- [x] Końcowa strona z mniej niż dziewięcioma planszami może zostać poprawnie
      wybrana.
- [x] Niepewny zakres daje `manual_required`, nie wymyślony numer.
- [x] Wynik dwóch przebiegów dla tych samych bajtów i manifestu jest identyczny.
- [x] Test udowadnia brak wywołania croppera komórek i symbol ONNX.
- [x] Liczba OCR/pełniejszych weryfikacji jest bounded przez grupy × top-k.

## Technical notes

Progi i wagi muszą należeć do manifestu/fingerprintu selektora. Nie optymalizować
na jednym wskazanym zdjęciu; golden musi obejmować różne kąty, refleksy,
zasłonięcia, blur i nieciągłe zakresy.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/`
- `ai_docs/quality/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests -q
.venv\Scripts\python.exe -m ruff check services/worker/src services/worker/tests
```

## Risks / open questions

- Obecny OCR numerów ma niską jakość auto-accept, dlatego sam OCR nie może być
  jedynym sygnałem grupy ani wyboru.

## Outcome

- Dodano jeden kanoniczny manifest i fingerprint `fast-image-selector-v1` z
  wersjami adapterów, progami, wagami, rozmiarem miniatury, batch size,
  boundary guard oraz `topK = 3`; API używa tej samej tożsamości runu.
- Dodano czyste kontrakty i osobne porty miniatury, jakości,
  lattice/fingerprint oraz range recognizera. Adaptery Pillow/OpenCV pracują na
  jednej miniaturze, a pełny obraz jest dekodowany tylko dla top-k.
- State machine zachowuje naturalny `order_index`, wykrywa dowolne skoki,
  rozdziela niepotwierdzone granice fail-closed, pomija późniejszy zakończony
  zakres i pozwala późniejszemu dobremu kandydatowi uzupełnić grupę manualną.
- Sparse OCR czyta batchowo wyłącznie pierwszą, środkową i ostatnią planszę;
  zakres wymaga dodatnich, zgodnych kotwic i liczby pozycji. Brak lub niski
  confidence kończy się `manual_required`.
- Samodzielny tryb CLI czyta checksumowany browser manifest, nie zapisuje do
  stagingu i publikuje `candidates.jsonl`, `groups.jsonl`, atomowy checkpoint
  oraz deterministyczny raport. Tryb bez OCR ma osobny fingerprint i nie może
  auto-wybrać zakresu.
- Dodano golden skoków, duplikatów, blur/crop/occlusion, niepewnego OCR i strony
  pięcioelementowej oraz pinned obserwacje pięciu prywatnych zdjęć z obu grup
  jakości. Obrazy prywatne pozostają poza Git.
- Weryfikacja: 469 testów workera przeszło w czterech ograniczonych czasowo
  partiach, 14 skupionych testów API przeszło, Ruff przeszedł dla całego
  workera, a mypy przeszedł dla dziewięciu zmienionych modułów.
- Nie wykonywano benchmarku 10k/30k ani integracji trwałego joba z retry;
  należą odpowiednio do TASK-0157 i TASK-0156. Immutable output oraz handoff są
  zakresem następnego TASK-0154.
