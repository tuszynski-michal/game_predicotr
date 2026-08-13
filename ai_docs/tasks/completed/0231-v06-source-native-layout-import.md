---
title: TASK-0231 — Source-native layout import quality and completeness
status: done
last_updated: 2026-08-13
---

# TASK-0231 — Source-native layout import quality and completeness

## Status

`done`

## Goal

Przywrócić kompletność importu dziewięciu plansz ze zdjęcia i zachować możliwie
najlepszą jakość źródła: bez pośredniego obrazu planszy `500 × 300` w ścieżce
modelu oraz bez obrotu lub prostowania obrazu pokazywanego człowiekowi.

## Context

Rzeczywisty import siedmiu zdjęć zakończył automatyczne dwie fazy `14/14`, ale
utworzył tylko 9 z oczekiwanych 63 plansz. Sześć zdjęć zatrzymało się w detekcji,
chociaż bezpieczne odzyskiwanie częściowej siatki znajduje na każdym z nich jedną
hipotezę dziewięciu pozycji. Dotychczasowy cropper dodatkowo powiększa małe
plansze źródłowe do `500 × 300`, wycina `90 × 90`, a następnie ponownie skaluje
komórkę do wejścia modelu. Wielokrotna interpolacja rozmywa symbole.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

- zaakceptować odzyskaną częściową siatkę wyłącznie przy jednej jednoznacznej
  hipotezie dziewięciu plansz; przypadki wieloznaczne nadal kierować do review,
- zapisywać natywny, osiowy wycinek kontekstu z obrazu po korekcie EXIF, bez
  obrotu, prostowania i zmiany rozmiaru,
- tworzyć każdą komórkę bezpośrednio z jej czworokąta w obrazie źródłowym do
  ostatecznego rozmiaru wejścia przypiętego modelu, w jednym resamplingu,
- zapisać w geometrii pochodzenie podglądu i granice natywnego kontekstu,
- zachować odczyt starszych importów oraz fallback skalowania ich historycznych
  cropów,
- pokazać w Reviewerze nowy natywny kontekst jako główny podgląd,
- odróżnić postęp faz od liczby utworzonych plansz i ostrzegać o niekompletnym
  wyniku,
- umożliwić ponowne przetworzenie istniejącego importu z managed originals,
- uprościć etykietę procesu selekcji do daty, wersji silnika i zakresu `seq`.

## Out of scope

- generatywna poprawa jakości obrazu,
- zmiana architektury modelu symboli,
- nieodwracalne usuwanie istniejących danych,
- automatyczna akceptacja więcej niż jednej hipotezy geometrii.

## Acceptance criteria

- [x] Jednoznacznie odzyskana siatka tworzy dokładnie 9 plansz.
- [x] Niejednoznaczna siatka kończy etap stabilnym błędem wymagającym review.
- [x] Zapisany podgląd planszy ma natywną skalę źródła i nie ma wymiaru
      wymuszonego na `500 × 300`.
- [x] Nowe komórki mają od razu rozmiar wejścia modelu i nie są skalowane drugi
      raz w inferencji.
- [x] Reviewer pokazuje natywny kontekst bez transformacji obrazu.
- [x] Import pokazuje osobno kompletność plansz i czytelne ostrzeżenie o brakach.
- [x] Istniejący import można bezpiecznie ponowić z zachowanych oryginałów.
- [x] Rzeczywisty zestaw 7 zdjęć daje 63 plansze, 945 komórek i ciąg `1–63`.
- [x] Testy, Ruff, mypy, lint, typecheck i OpenAPI zmienionego pionu przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/source_direct_crops.py`
- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- `services/worker/src/game_predictor_worker/images/pipeline_contract.py`
- `services/worker/src/game_predictor_worker/images/pipeline_store.py`
- `services/worker/tests/test_production_image_workflow.py`
- `services/worker/tests/test_image_pipeline_execution.py`
- `services/api/src/game_predictor_api/application/image_imports.py`
- `services/api/src/game_predictor_api/api/image_imports.py`
- `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- `apps/reviewer/src/features/operational-reviews/operational-review-workspace.tsx`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Decisions and assumptions

- `500 × 300` pozostaje wyłącznie historycznym formatem lub opcjonalnym
  artefaktem diagnostycznym. Nie jest wejściem produkcyjnej ścieżki v0.6.
- „Oryginał” w pipeline oznacza obraz po bezstratnej korekcie orientacji EXIF;
  piksele nie są później globalnie obracane ani skalowane.
- Ujednolicenie skali dla modelu jest konieczne, ale odbywa się dokładnie raz,
  podczas bezpośredniej projekcji pojedynczej komórki.

## Outcome

Wdrożono source-native pipeline v0.6. Natywny kontekst pozostaje kopią pikseli
źródłowych, a komórka przechodzi jeden bezpośredni warp do rozmiaru modelu.
Detektor przyjmuje tylko jedną hipotezę częściowej siatki, ciągłość OCR wymaga
jednoznacznego konsensusu strony, a nowe wersje adapterów są częścią fingerprintu
pipeline'u. Admin pokazuje rzeczywistą kompletność i udostępnia bezpieczny rerun
z immutable managed originals; Reviewer rozpoznaje nowy typ podglądu. Historia
selekcji ma skróconą etykietę z zakresem `seq`.

Rzeczywista weryfikacja siedmiu zdjęć z joba
`04909a56-edc6-42b5-860e-70c662189d1d` dała 63 plansze, 945 komórek i ciąg
`1–63`; raport znajduje się w
`ai_docs/quality/v06-source-native-layout-import-7-photo-report.json`.

Zaliczone bramki: 58 skupionych testów Python, 9 testów operational review API,
198 testów Admina, 23 Reviewera i 37 klienta API; Ruff, skupiony mypy, oba
frontendowe linty/typechecki/buildy oraz drift OpenAPI. Pełny zestaw 670 testów
workera przekroczył 120 s i zatrzymał się na istniejącym driftcie checksumy
`m5-image-benchmark-report.json`; do chwili zatrzymania przeszedł 204 testy i
pominął jeden, a błąd nie dotyczy zmienionego pionu.
