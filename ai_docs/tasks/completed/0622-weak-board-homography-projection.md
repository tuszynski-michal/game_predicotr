---
title: TASK-0622 — quad słabej planszy z projekcji homografii
status: done
last_updated: 2026-09-23
---

# TASK-0622 — quad słabej planszy z projekcji homografii

## Status

`done`

## Goal

Na stronie zaakceptowanej wyłącznie ścieżką relaksacji D-420 (jedna słaba
plansza), quad tej jednej słabej planszy pochodzi z projekcji homografii
(`projected_quads[slot]`), a nie ze snapu do czerwonej krawędzi; pozostałe
osiem plansz nadal używa snapniętego quadu jak dotąd. Strony bazowe
(baseline-accepted) i pozostałe osiem plansz na stronach relaksowanych są
bez zmian.

## Context

Warunkowy task T2 z zaakceptowanego planu (Plan: automatyczna geometria stron
dla ciemniejszych zdjęć z lampką, staging `a139379b`), zależny od T1
(TASK-0621, `v0.10.388`, ukończony). Pomiar z planu (`shift30.py` +
wizualizacja) pokazał, że `_snap_quad_to_red_edges` przesuwa quad średnio o
~7 px w górę na **wszystkich** dziewięciu planszach, niezależnie od progu V —
snap ciągnie siatkę symboli do górnej listwy ramki. Użytkownik zdecydował
(DA-2), po zapoznaniu się z tym pomiarem, że mimo systemowego biasu snapu na
wszystkich planszach, słaba plansza (ta z najsłabszym dowodem czerwonej
krawędzi, akceptowana tylko dzięki relaksacji D-420) ma używać
nieprzesuniętej projekcji homografii zamiast potencjalnie błędnego snapu —
DA-2 potwierdzone ponownie 2026-09-23 po zapoznaniu z pomiarem.

## Dependencies / entry conditions

- T1 / TASK-0621 ukończony i zacommitowany (`v0.10.388`,
  `ai_docs/tasks/completed/0621-red-mask-low-light-frames.md`).
- DA-2 potwierdzone ponownie przez użytkownika 2026-09-23 (wiadomość:
  „Ponownie potwierdzam DA-2 — zacznij T2/TASK-0622”).

## Recommended execution

`claude-sonnet-5`, reasoning `medium`. Uzasadnienie: lokalna zmiana w jednej
funkcji (`_evaluate_final_registration`) z jasnym fail-closed i testami;
uruchamiana tylko po ponownym potwierdzeniu DA-2. Eskalacja: niejasny wpływ
na gałąź frame-support-review lub na `active_board_slots` przy niepełnej
siatce wymaga przerwania i eskalacji do `claude-opus-5-5` / `medium`.
Dodatkowy review: nie wymagany; opcjonalnie `claude-opus-5-5` / `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-420, D-430)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja „Zweryfikowana geometria
  pełnej strony…”)
- `ai_docs/tasks/completed/0621-red-mask-low-light-frames.md`

## Scope

- `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`:
  `_evaluate_final_registration` — projekcja quadu słabej planszy tylko na
  ścieżce relaksacji; `RegisteredPageGeometry` — nowe opcjonalne pole
  `weak_board_quad_source`.
- Nowe testy w `services/worker/tests/test_page_geometry_registration.py`.
- Dokumentacja: `DECISION_LOG.md` (uzupełnienie D-430 albo nowy D-431),
  `IMAGE_INGESTION.md`, `CURRENT_STATE.md`.

## Out of scope

- `PageRegistrationThresholds`, `_relaxed_red_edge_accepted` (algorytm i
  wartości), stałe `lateral_partial_contract`, `_strong_auto_anchor`.
- `PAGE_REGISTRATION_THRESHOLDS_VERSION`, `PAGE_REGISTRATION_VERSION`,
  `PAGE_REGISTRATION_FEATURES_VERSION`, `PAGE_REGISTRATION_RED_MASK_VERSION`,
  wersje preflightu, tożsamość jobów w `application/jobs.py`, logika reuse w
  `page_geometry_incremental.py`.
- `_snap_quad_to_red_edges` (algorytm, promień) i `_red_edge_coverage` —
  używane bez zmian; diagnoza biasu snapu (R-1) to osobne zadanie.
- Gałąź frame-support-review i `_lateral_search_candidate` — kolejność
  sprawdzeń wobec nich pozostaje identyczna (warunek `not relaxed_accepted`
  bez zmian).
- API, OpenAPI, Admin, migracje, manifesty i pliki w `artifacts/`,
  `imports/`. Żadnego uruchamiania preflightu, restartu workerów ani korekt
  na danych produkcyjnych.

## Acceptance criteria

- [x] Na stronie akceptowanej wyłącznie relaksacją (`relaxed_accepted and
      not baseline_accepted`), slot ze `coverage[slot] <
      thresholds.minimum_board_red_edge_coverage` ma quad równy
      `projected_quads[slot]` (nieprzesunięty snapem); pozostałe sloty mają
      quad jak ze snapu (bez zmian względem dotychczasowego zachowania).
- [x] Jeżeli `final_quads` nie tworzy poprawnej, uporządkowanej siatki
      (`is_complete_ordered_grid` zwraca `False`), funkcja zwraca `None` i
      diagnostykę `PAGE_GEOMETRY_QUADS_INVALID` (fail-closed, strona do
      review) zamiast częściowo poprawnej projekcji.
- [x] `RegisteredPageGeometry.to_payload()` ma klucz `"weakBoardQuadSource":
      "homography_projection"` tylko dla stron relaksowanych; strony
      bazowe (`baseline_accepted`) nie mają tego klucza w payloadzie.
- [x] `board_red_edge_coverages`, `mean_red_edge_coverage` i decyzja
      akceptacji (dowód akceptacji) pozostają zmierzone tak jak dotąd —
      projekcja quadu nie zmienia progów ani sposobu liczenia pokrycia.
- [x] Istniejący test
      `test_registration_accepts_a_page_with_one_weak_board_using_relaxed_thresholds`
      pozostaje zielony bez zmiany asercji.
- [x] Wszystkie istniejące testy `test_page_geometry_registration.py`
      (włącznie z T1) oraz pliki regresyjne z T1 pozostają zielone.
- [x] `ruff` i `mypy` czyste (bez nowych błędów) dla zmienionego pliku.

## Technical notes

Aktualne zachowanie: `_evaluate_final_registration` liczy `quads` jako
`_snap_quad_to_red_edges(red_neighbourhood, quad)` dla każdego z dziewięciu
`projected_quads` (projekcja anchora przez homografię), niezależnie od tego,
czy strona zostanie przyjęta bazowo czy przez relaksację D-420. Snap
przesuwa quad w promieniu ≤12 px, żeby zmaksymalizować pokrycie czerwonej
krawędzi.

Wymagane zachowanie: po obliczeniu `relaxed_accepted` (linia ok. 900) i po
przejściu bramek odrzucenia (frame-support-review, `PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`)
bez zmian w ich kolejności ani warunkach — tuż przed konstrukcją
`RegisteredPageGeometry` — gdy `relaxed_accepted and not baseline_accepted`:
zbudować `final_quads[slot] = projected_quads[slot] if coverage[slot] <
thresholds.minimum_board_red_edge_coverage else quads[slot]`. Sprawdzić
`is_complete_ordered_grid(final_quads, target_rgb.shape[1],
target_rgb.shape[0])`; jeśli `False`, zwrócić `(None,
PageRegistrationAttemptDiagnostic(reason_code="PAGE_GEOMETRY_QUADS_INVALID",
...))` z tymi samymi polami diagnostycznymi co inne odrzucenia w tej
funkcji (feature_count, anchor checksum, inlier_count/ratio, p95, mean/min
coverage). W przeciwnym razie użyć `final_quads` jako `quads` przekazywane
do `RegisteredPageGeometry` i ustawić `weak_board_quad_source =
"homography_projection"`. `board_red_edge_coverages` i
`mean_red_edge_coverage` pozostają wartościami zmierzonymi na snapniętych
`quads` sprzed projekcji (dowód akceptacji się nie zmienia — akceptacja już
zapadła na starych `coverage`).

Relaksacja D-420 gwarantuje dokładnie jeden słaby slot: `min_coverage < 0.45`
(wymagane przez `_relaxed_red_edge_accepted`) i najwyżej jedna plansza
poniżej `relaxed_minimum_other_boards_red_edge_coverage` (=0.45) — więc
`weak_board_quad_source` ustawiony na stronie relaksowanej zawsze odpowiada
dokładnie jednemu przeprojektowanemu slotowi.

Przykład wejście → wynik: target = anchor (dokładna kopia, identyczna
homografia ≈ macierz jednostkowa), plansza nr 9 (slot 8) ma wymazane wnętrze
→ relaksacja akceptuje stronę → `result.quads[8]` równa się
`projected_quads[8]` (czyli, dla targetu = anchor, kwadowi anchora dla slotu
8) → `result.to_payload()["weakBoardQuadSource"] ==
"homography_projection"`; `result.quads[0:8]` pozostają jak w dotychczasowym
teście (snap, może się różnić od quadu anchora).

## Expected files

- Istniejące:
  `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`
  (`_evaluate_final_registration`, `RegisteredPageGeometry`).
  `services/worker/tests/test_page_geometry_registration.py` (nowe testy).
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md` (dokumentacja).

## Test cases

- Rozszerzenie scenariusza z
  `test_registration_accepts_a_page_with_one_weak_board_using_relaxed_thresholds`
  **nowym** testem: `result.quads[8] == projected_quads[8]` (dla targetu =
  anchor, czyli quadowi anchora dla slotu 8); payload ma
  `weakBoardQuadSource == "homography_projection"`; `result.quads[0:8]`
  niezmienione względem obecnego (snapowanego) zachowania.
- Test fail-closed: `monkeypatch` na `is_complete_ordered_grid`, żeby drugie
  wywołanie (dla `final_quads`) zwróciło `False` → `registrar.register(...)`
  zwraca `None` (poprzez `evaluate(...)`, sprawdzić `reason_code ==
  "PAGE_GEOMETRY_QUADS_INVALID"` w diagnostyce best-attempt).
- Test strony bazowej (`test_registration_transforms_all_nine_quads_to_target_specific_geometry`
  lub podobny scenariusz baseline): payload **nie** ma klucza
  `weakBoardQuadSource`.
- Regresja: istniejący test relaksacji bez zmiany dotychczasowych asercji
  (`slot_qualifications`, `mean_red_edge_coverage`).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_page_geometry_registration.py -q
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_page_geometry_preflight.py services/worker/tests/test_lateral_page_registration.py services/worker/tests/test_lateral_partial_workflow.py services/worker/tests/test_page_anchor_qualification.py services/worker/tests/test_production_image_workflow.py services/worker/tests/test_board_cell_geometry_audit.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/page_geometry_registration.py services/worker/tests/test_page_geometry_registration.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/page_geometry_registration.py
```

Timeout 120 s na każdą komendę.

## Risks / open questions

- R-1 (z planu, poza zakresem): bias snapu (~7 px w górę, wszystkie
  plansze) pozostaje nierozwiązany; ta zmiana adresuje tylko slot słabej
  planszy na stronach relaksowanych.
- Niespójność geometryczna: mocne plansze pozostają ze snapu, słaba
  plansza z czystej projekcji — akceptowane świadomie przez DA-2 jako
  kompromis mniejszego ryzyka niż błędny snap na niepewnym dowodzie.

## Outcome

### Changed

- `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`:
  `RegisteredPageGeometry` — nowe opcjonalne pole `weak_board_quad_source:
  Literal["homography_projection"] | None`, serializowane jako
  `weakBoardQuadSource` tylko gdy nie `None`. `_evaluate_final_registration`
  — po obliczeniu `relaxed_accepted`/`slot_qualifications`, gdy
  `relaxed_accepted and not baseline_accepted`: buduje `final_quads` (słaby
  slot → `projected_quads[slot]`, pozostałe → dotychczasowy snapnięty
  `quads[slot]`), sprawdza `is_complete_ordered_grid` na `final_quads` i przy
  `False` zwraca fail-closed `PAGE_GEOMETRY_QUADS_INVALID` z tymi samymi
  polami diagnostycznymi co pozostałe odrzucenia w tej funkcji; w przeciwnym
  razie podstawia `final_quads` jako `quads` i ustawia
  `weak_board_quad_source`. Kolejność sprawdzeń (frame-support-review,
  bramka `RED_EDGE_COVERAGE_INSUFFICIENT`) niezmieniona — nowa logika działa
  dopiero po nich, tuż przed konstrukcją `RegisteredPageGeometry`.
- `services/worker/tests/test_page_geometry_registration.py`: trzy nowe
  testy (`test_registration_uses_homography_projection_for_the_relaxed_weak_board`,
  `test_registration_fails_closed_when_weak_board_projection_breaks_the_grid`,
  `test_registration_omits_weak_board_quad_source_for_baseline_pages`).
  Test fail-closed monkeypatchuje `page_geometry_registration.is_complete_ordered_grid`
  tak, by co drugie wywołanie (call_count % 2 == 0) zwracało `False` — bo
  `evaluate()` ponawia próbę z rosnącym budżetem cech ORB (1000/1500/3000)
  po każdym odrzuceniu, więc stałe „drugie wywołanie” (call_count==2) nie
  wystarczało: po wymuszonym odrzuceniu próby 1000-cechowej kolejna próba
  (1500 cech) przechodziła normalnie, bo licznik był już nieparzysty przy jej
  drugim (krytycznym) wywołaniu. Zweryfikowano logicznie (bez uruchamiania
  starego kodu), że bez nowej gałęzi projekcji funkcja wywołuje
  `is_complete_ordered_grid` tylko raz na próbę, więc `call_count` nigdy nie
  osiąga parzystej wartości w trakcie próby i test wykryłby regresję,
  gdyby ktoś usunął nową gałąź (rejestracja zakończyłaby się sukcesem,
  `evaluation.result is None` by nie trzymało).
- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-431 (na górze pliku).
- `ai_docs/requirements/IMAGE_INGESTION.md`: dodano akapit o źródle quadu
  słabej planszy na stronach relaksowanych.
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0622 na górze.
- `ai_docs/tasks/0622-weak-board-homography-projection.md`: utworzony i
  uzupełniony (ten plik).

### Verification results

- `pytest services/worker/tests/test_page_geometry_registration.py -q`:
  23 passed (20 z T1 bez zmian w asercjach + 3 nowe).
- `pytest services/worker/tests/test_page_geometry_preflight.py
  services/worker/tests/test_lateral_page_registration.py
  services/worker/tests/test_lateral_partial_workflow.py
  services/worker/tests/test_page_anchor_qualification.py
  services/worker/tests/test_production_image_workflow.py
  services/worker/tests/test_board_cell_geometry_audit.py -q`:
  147 passed, bez zmian w tych plikach.
- `ruff check` na obu zmienionych plikach: czysty.
- `mypy --strict` na zmienionym pliku źródłowym: te same 14 błędów
  `import-not-found` co w TASK-0621 (potwierdzone tam jako preexisting,
  niezwiązane z żadnym z tych dwóch tasków); brak nowych błędów.

### Not completed

- Diagnoza biasu snapu (R-1 z planu, ~7 px w górę na wszystkich planszach)
  pozostaje osobnym, nierozpoczętym zadaniem — świadomie poza zakresem T2.
- Odbiór operatorski (restart workera, ręczna korekta na danych
  produkcyjnych, wizualna kontrola quadów w edytorze geometrii) — poza
  zakresem read-only/code-only tego taska, wymaga osobnego polecenia.
- Krok pomiaru read-only na rzeczywistych danych (analogiczny do kroku 1.3 w
  T1) nie był częścią planu dla T2 — plan przewidywał go tylko dla T1.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` (D-431), `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Odbiór operatorski całego przepływu T1+T2: restart workera, jedna ręczna
  korekta na stagingu `a139379b` (lub `3e3f510a`), porównanie liczników
  `review_required`, oraz wizualna kontrola kilku nowo zarejestrowanych stron
  (w tym stron z `weakBoardQuadSource`) w edytorze geometrii przed importem.
- Rozważyć osobne zadanie diagnostyczne biasu snapu (R-1), zgodnie z
  rekomendacją z planu.
