---
title: TASK-0621 — maska czerwieni odporna na ciemną ramkę
status: done
last_updated: 2026-09-23
---

# TASK-0621 — maska czerwieni odporna na ciemną ramkę

## Status

`done`

## Goal

`page_geometry_registration._red_mask` wykrywa ciemnoczerwoną ramkę górnego
rzędu plansz na nowych stagingach (V ≈ 40–45) tak, aby strony z silnym
dowodem homografii przechodziły bazową bramkę red-edge coverage bez
osłabiania progów `PageRegistrationThresholds`.

## Context

Preflight geometrii stron (`verified-page-registration-v1`) dla nowych
stagingów `777` (np. `a139379b`) kieruje dużą część zdjęć do
`review_required` z powodem `PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`.
Zmierzono (read-only, 2026-09-23), że nowe zdjęcia mają ciemnoczerwoną ramkę
górnego rzędu (hue-red 53–82%, S ≈ 150–190, V ≈ 40–45), którą obecny próg
`_red_mask` (V ≥ 50) odrzuca. `PAGE_REGISTRATION_THRESHOLDS_VERSION` i
`PageRegistrationThresholds` mają pozostać bez zmian — poprawka dotyczy
wyłącznie pomiaru pokrycia, nie bramek.

## Dependencies / entry conditions

- Brak zależności od innych tasków. Fakty pomiarowe pochodzą z read-only
  diagnostyki opisanej w zaakceptowanym planie (nie commitowanej do repo).
- Wejście: obecny stan `page_geometry_registration.py` na branchu
  `version-0.10`, commit bazowy `dc877905` (v0.10.387).

## Recommended execution

`claude-sonnet-5`, reasoning `high`. Uzasadnienie: mała zmiana kodu, ale
globalna dla rejestracji wszystkich gier V1.1; wymaga pomiaru na
rzeczywistych danych i starannej dokumentacji decyzji. Eskalacja: wynik
kroku 1.3 (pomiar read-only) < 25/30 odzyskanych stron albo jakakolwiek
regresja na starym stagingu (mniej niż 30/30 `registered`).
Dodatkowy review: `claude-opus-5-5` / `high`, review diffu i wyników kroku
1.3 przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-420)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja „Zweryfikowana geometria
  pełnej strony…”)

## Scope

- `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`:
  próg jasności `_red_mask` (V 50 → 30 dolna granica w obu `inRange`), nowa
  stała `PAGE_REGISTRATION_RED_MASK_VERSION`, dopisanie
  `"redMaskVersion"` do `RegisteredPageGeometry.to_payload()`.
- Nowe testy jednostkowe w
  `services/worker/tests/test_page_geometry_registration.py`.
- Dokumentacja: `DECISION_LOG.md` (D-430), `IMAGE_INGESTION.md` (jedno
  zdanie o zakresie dowodu czerwonej ramki + korekta opisu D-420),
  `CURRENT_STATE.md`.
- Read-only pomiar (krok 1.3) na istniejących manifestach/obrazach, wynik
  zapisany w `Outcome`, bez commitowania skryptu pomiarowego.

## Out of scope

- `PageRegistrationThresholds` i ich wartości, `_relaxed_red_edge_accepted`,
  stałe `lateral_partial_contract`, `_strong_auto_anchor`.
- `PAGE_REGISTRATION_THRESHOLDS_VERSION`, `PAGE_REGISTRATION_VERSION`,
  `PAGE_REGISTRATION_FEATURES_VERSION`, wersje preflightu, tożsamość jobów
  w `application/jobs.py`, logika reuse w `page_geometry_incremental.py`.
- `_snap_quad_to_red_edges` (algorytm, promień), `_red_edge_coverage`.
- Maski czerwieni w `geometry.py`, `structured_geometry/*`, V1.2
  `contrast_frame_grid_v12.py`.
- T2 / TASK-0622 (quad słabej planszy z projekcji homografii) — osobny task,
  warunkowy, wymaga osobnego potwierdzenia DA-2.
- API, OpenAPI, Admin, migracje, manifesty i pliki w `artifacts/`,
  `imports/`. Żadnego uruchamiania preflightu, restartu workerów ani korekt
  na danych produkcyjnych.

## Acceptance criteria

- [x] `_red_mask` akceptuje piksele HSV z V ≥ 30 w obu pasmach hue (S ≥ 80
      bez zmian), odrzuca V < 30.
- [x] Strona z ciemną ramką górnego rzędu (V≈40) przechodzi bazową bramkę
      (`slot_qualifications is None`, wszystkie pokrycia ≥ 0,45) bez zmiany
      progów.
- [x] `RegisteredPageGeometry.to_payload()["redMaskVersion"] ==
      PAGE_REGISTRATION_RED_MASK_VERSION`.
- [x] Istniejące testy `test_page_geometry_registration.py` oraz pliki
      wymienione w kroku 1.2 (`test_page_geometry_preflight.py`,
      `test_production_image_workflow.py`, `test_lateral_partial_workflow.py`,
      `test_lateral_page_registration.py`, `test_page_anchor_qualification.py`,
      `test_board_cell_geometry_audit.py`) pozostają zielone bez osłabienia
      istniejących asercji.
- [x] `ruff` czyste dla zmienionego pliku; `mypy` nie wprowadza nowych
      błędów (patrz Outcome — 14 istniejących błędów importu to
      środowiskowy problem preexisting).
- [x] Pomiar read-only (krok 1.3): 29/30 (≥ 25/30) nieudanych stron nowego
      stagingu zwraca `result`; stary staging nadal 30/30 `registered` —
      zero regresji. Odchylenie pokrycia od zapisanych w manifeście
      przekracza orientacyjne ±0,02 z planu ze względu na zastępczy zestaw
      kotwic (patrz Outcome).
- [x] `DECISION_LOG.md` ma nowy wpis D-430 na górze; `IMAGE_INGESTION.md` i
      `CURRENT_STATE.md` zaktualizowane.

## Technical notes

Aktualne zachowanie: `_red_mask` używa `cv2.inRange` z dolną granicą V=50 w
obu pasmach hue (0–18 i 165–179), S ≥ 80. Ciemnoczerwone piksele ramki
(V≈40–45) wypadają z maski, więc `_red_edge_coverage` dla górnego rzędu jest
zaniżone i strona ląduje w `review_required`.

Wymagane zachowanie: dolna granica V → 30 w obu `inRange`. Hue i S bez
zmian. `_snap_quad_to_red_edges` i `_red_edge_coverage` korzystają z tej
samej, poprawionej maski bez zmian algorytmu. Kontrola negatywna z planu
(quad przesunięty o 35%/45%) potwierdza, że dyskryminacja wobec losowego
tła nie spada poniżej historycznie akceptowanego poziomu przy V≥30.

`PAGE_REGISTRATION_RED_MASK_VERSION: Final = "hsv-red-s80-v30-v1"` — nowa
stała modułowa, dopisana do `__all__`. `RegisteredPageGeometry.to_payload()`
dodaje `"redMaskVersion": PAGE_REGISTRATION_RED_MASK_VERSION` zawsze (nie do
`PageRegistrationInitialization` ani `LateralPageRegistrationCandidate` —
ich koperty są walidowane ściśle w `lateral_partial_artifact.py`).

Przykład wejście → wynik: piksel HSV (hue=5, S=190, V=40) → maska 255 (nowe
zachowanie; przy starym progu V≥50 → 0). Piksel HSV (hue=5, S=190, V=29) →
0 (nadal odrzucony). Piksel (hue=110, *, *) → 0 (niebieski, bez zmian).

## Expected files

- Istniejące:
  `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`
  (`_red_mask`, nowa stała, `RegisteredPageGeometry.to_payload`, `__all__`).
  `services/worker/tests/test_page_geometry_registration.py` (nowe testy).
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md` (dokumentacja).

## Test cases

- `test_red_mask_accepts_dark_red_frame_pixels`: HSV (5, 190, 40) → 255;
  (172, 150, 30) → 255; (5, 190, 29) → 0; szary S<80 → 0; niebieski hue=110
  → 0.
- `test_registration_accepts_dark_top_row_frames_with_baseline_gate`:
  anchor = `_page()`; target z górnym rzędem przemalowanym na V≈40 (HSV
  (3, 200, 40)). Oczekiwane: `result is not None`, `slot_qualifications is
  None`, wszystkie pokrycia ≥ 0,45.
- `test_registration_payload_pins_red_mask_version`:
  `result.to_payload()["redMaskVersion"] == PAGE_REGISTRATION_RED_MASK_VERSION`.
- Regresja: `rejects_a_page_when_one_board_has_no_border_evidence`,
  `accepts_a_page_with_one_weak_board_using_relaxed_thresholds`,
  `reports_red_edge_rejection…` — bez zmian w asercjach.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_page_geometry_registration.py -q
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_page_geometry_preflight.py services/worker/tests/test_lateral_page_registration.py services/worker/tests/test_lateral_partial_workflow.py services/worker/tests/test_page_anchor_qualification.py services/worker/tests/test_production_image_workflow.py services/worker/tests/test_board_cell_geometry_audit.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/page_geometry_registration.py services/worker/tests/test_page_geometry_registration.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/page_geometry_registration.py
```

Timeout 120 s na każdą komendę. `npm run python:test -- -Suite Worker` jako
szerszy przebieg opcjonalny; jeśli > 120 s, zgłosić użytkownikowi.

## Risks / open questions

- R-2 (z planu): V≥30 dotyczy rejestracji wszystkich gier V1.1. Stare, jasne
  zdjęcia się nie zmieniają (do zweryfikowania w kroku 1.3).
- R-3: ekstrapolacja 28/30 z próbki 40 stron; faktyczny wynik potwierdza
  dopiero krok 1.3 i odbiór operatorski.

## Outcome

### Changed

- `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`:
  nowa stała `PAGE_REGISTRATION_RED_MASK_VERSION = "hsv-red-s80-v30-v1"` i
  `_RED_MASK_MINIMUM_VALUE: Final = 30`; `_red_mask` używa stałej zamiast
  literału 50 w obu `inRange`; `RegisteredPageGeometry.to_payload()` zapisuje
  zawsze `"redMaskVersion"`; nowa stała dopisana do `__all__`.
- `services/worker/tests/test_page_geometry_registration.py`: trzy nowe
  testy (`test_red_mask_accepts_dark_red_frame_pixels`,
  `test_registration_accepts_dark_top_row_frames_with_baseline_gate`,
  `test_registration_payload_pins_red_mask_version`) + import
  `PAGE_REGISTRATION_RED_MASK_VERSION`. Test regresyjny dla ciemnej ramki
  używa dedykowanego, achromatycznego tła (R=G=B) zamiast współdzielonej
  `_page()`, bo losowy szum `_page()` (0–59 na kanał) sporadycznie trafia w
  zakres barwy czerwonej i fałszywie zawyżał pokrycie niezależnie od progu —
  z takim tłem test dawał fałszywy `pass` nawet pod starym progiem V≥50.
- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-430 (na górze pliku) ze
  sprostowaniem opisu D-420.
- `ai_docs/requirements/IMAGE_INGESTION.md`: dodano definicję dowodu
  czerwonej ramki (hue 0–18/165–179, S≥80, V≥30) i zneutralizowano opis
  relaksacji („np. lampka nad numerem” → „powtarzalnie słaba ramka”).
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0621 na górze.
- `ai_docs/tasks/0621-red-mask-low-light-frames.md`: utworzony i uzupełniony
  (ten plik).

### Verification results

- `pytest services/worker/tests/test_page_geometry_registration.py -q`:
  20 passed (17 istniejących bez zmian w asercjach + 3 nowe).
- Regresja lokalna (tymczasowe przywrócenie `_RED_MASK_MINIMUM_VALUE = 50`,
  niecommitowane): oba nowe testy rejestracyjne/maski poprawnie failują pod
  starym progiem, potwierdzając, że demonstrują prawdziwą regresję, nie są
  wadliwe/nieskuteczne.
- `pytest services/worker/tests/test_page_geometry_preflight.py
  services/worker/tests/test_lateral_page_registration.py
  services/worker/tests/test_lateral_partial_workflow.py
  services/worker/tests/test_page_anchor_qualification.py
  services/worker/tests/test_production_image_workflow.py
  services/worker/tests/test_board_cell_geometry_audit.py -q`:
  147 passed, bez zmian w tych plikach.
- `ruff check` na obu zmienionych plikach: czysty.
- `mypy --strict` na zmienionym pliku źródłowym: 14 błędów
  `import-not-found` dla `game_predictor_api.domain.*` w 9 plikach — te same
  błędy występują też na czystym `dc877905` (`git stash` + rerun), więc to
  preexisting problem środowiska mypy w tej sesji, niezwiązany z taskiem.
  Brak nowych błędów wprowadzonych przez zmianę.
- Krok 1.3 (pomiar read-only, PostgreSQL uruchomiony lokalnie, gra `777`,
  ~9,3 s łącznie dla 60 rejestracji): **29/30** próbkowanych stron
  `review_required` ze stagingu `a139379b` (manifest
  `8b2b0e30…`, najnowszy dostępny, 2707 registered / 245 review_required w
  chwili pomiaru) zwróciło wynik rejestracji po zmianie progu. **30/30**
  próbkowanych zarejestrowanych stron starszego stagingu `5eafd373`
  (manifest `90565e99…`) pozostało `registered` — zero regresji. Jedyna
  strona, która nadal nie przechodzi: inlier_ratio 0,254 < wymagane 0,30 dla
  ścieżki relaksowanej mimo mean coverage 0,72 — ograniczenie dowodu ORB, nie
  maski czerwieni; zgodne z oczekiwaniem planu (~28/30, nie 30/30).
  **Odstępstwo metodologiczne:** lokalna tabela `image_page_geometry_overrides`
  jest pusta (0 wierszy) — brak historycznych 9 override'ów wspomnianych w
  planie w tym środowisku deweloperskim. Zastąpiono je: (a) dla stagingu
  `a139379b` — 5 w pełni zarejestrowanymi stronami tego samego, aktualnego
  manifestu (pokrycie 1,0 na każdej planszy, bez wykluczeń) jako kotwice;
  (b) dla kontroli na `5eafd373` — analogicznie 5 najlepszymi zarejestrowanymi
  stronami z tego samego, starego stagingu (żeby uniknąć testowania
  generalizacji kotwic między stagingami zamiast wpływu zmiany progu —
  kotwice z `a139379b` słabo dopasowywały się ORB-em do zdjęć `5eafd373`,
  1/5 w próbie wstępnej). Odchylenie pokrycia per plansza względem wartości
  zapisanych w manifeście `90565e99…` wynosiło do 0,44 (typowo 0,01–0,06) —
  wyraźnie więcej niż orientacyjne ±0,02 z planu, co jest spodziewane przy
  innym zestawie kotwic niż oryginalny profil produkcyjny, a nie oznaką
  regresji (status `registered` zachowany we wszystkich 30/30 przypadkach).
  Zgodnie z hierarchią źródeł prawdy (AGENTS.md) zgłaszam tę rozbieżność
  między stanem lokalnej bazy a założeniem planu zamiast ją ukrywać.
  Skrypt pomiarowy zapisany w scratchpadzie sesji, nie commitowany.

### Not completed

- T2 / TASK-0622 nie został rozpoczęty (warunkowy, wymaga osobnego
  potwierdzenia DA-2 i osobnego polecenia użytkownika — poza zakresem tego
  taska).
- Nie uruchomiono `npm run python:test -- -Suite Worker` (szerszy przebieg
  opcjonalny w planie) — zakres zmienionego pionu i pliki regresyjne z planu
  pokryte bezpośrednimi wywołaniami pytest powyżej.
- `format:check` uruchomiony tylko jako kontrola całego repo (`ai_docs` nie
  jest objęty Prettier); 367 istniejących ostrzeżeń w plikach niezwiązanych z
  tym taskiem (JS/TS/JSON) — preexisting, nie ruszane.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` (D-430), `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Odbiór operatorski: restart workera i jedna ręczna korekta na stagingu
  `a139379b` (lub `3e3f510a`), porównanie liczników `review_required` przed/po.
- T2 / TASK-0622 pozostaje warunkowy na ponowne potwierdzenie DA-2 przez
  użytkownika, ze świadomością, że snap przesuwa wszystkie plansze (nie
  tylko słabe) — patrz rekomendacja w planie, by rozważyć osobną diagnozę
  biasu snapu (R-1) zamiast T2.
