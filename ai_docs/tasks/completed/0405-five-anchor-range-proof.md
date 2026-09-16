---
title: TASK-0405 — Proof zakresu z pięciu anchorów
status: done
created: 2026-09-02
---

# TASK-0405 — Proof zakresu z pięciu anchorów

## Goal

Zdefiniować czysty, wersjonowany proof `v6` dla wyniku recognition-only OCR z
pięciu pozycji etykiet: `top_left`, `top_right`, `center`, `bottom_left`,
`bottom_right`. Proof ma zwracać wyłącznie exact, jednoznacznie oczekiwany zakres
albo reason-coded `unknown`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0404-five-anchor-range-label-locator.md`

## Scope

- Dodać czysty moduł proofu
  `semi-automatic-range-only-ocr-v6-five-anchor-v1`.
- Zdefiniować stałą mapę anchor → slot pełnej strony 3×3:
  `0`, `2`, `4`, `6`, `8`.
- Zbudować immutowalną tabelę oczekiwanych zakresów i wartości dla pełnych
  stron; częściowa strona nie może otrzymać automatycznego exact na podstawie
  niepełnych pięciu punktów.
- Zweryfikować wszystkie pięć rozpoznań oraz ich source-direct kompletność i
  czytelność.
- Exact wymaga co najmniej trzech zgodnych, wysokiej pewności odczytów:
  środkowego oraz co najmniej jednego anchoru z góry i z dołu strony. Każdy
  obecny, wysokiej pewności odczyt sprzeczny z mapą oczekiwanego zakresu blokuje
  exact. Puste albo zbyt niepewne pozostałe anchor'y nie są sztucznie
  uzupełniane i nie stają się dowodem.
- Dodać deterministyczny fingerprint polityki, tabeli zakresów i wariantu.
- Dodać testy pełnej macierzy proofu oraz izolacji od obrazu, OCR runtime'u,
  nazw plików, sąsiadów i ciężkiego pipeline'u.

## Out of scope

- Paddle OCR, preprocessing, dekodowanie JPEG, lokalizator v6, runtime joba,
  checkpoint, grouping, wybór reprezentanta, API, UI i feature flag.
- Modyfikacja kontraktów, fingerprintów albo zachowania v1–v5.
- Wykorzystanie nazwy `seq_*`, expected filename, source indexu lub sąsiednich
  obrazów jako wartości dowodu.

## Invariants

- Pięć anchorów jest zawsze sprawdzanych, lecz wynik `exact` nie wynika z
  samego położenia ani nazwy pliku.
- Każda zaakceptowana liczba odpowiada dokładnie przypiętemu slotowi tego samego
  oczekiwanego zakresu; nie ma fuzzy correction ani inference ciągłości.
- Czytelny odczyt niepasujący do jedynego kandydata jest konfliktem, nie jest
  pomijany dla podniesienia recall.
- Brak trzech rozpiętych pionowo, zgodnych wartości jest `unknown`.
- Komponent jest wolny od importów image/OCR/SQL/HTTP i bez I/O plików.

## Acceptance criteria

- [x] Pełna strona tworzy jednoznaczny exact tylko z poprawnym evidence
  przypisanym do anchorów.
- [x] Puste i low-confidence wartości nie tworzą ani nie uzupełniają dowodu;
  non-numeric, clipped, blurred i niespójne wartości kończą się stable reason
  code bez fuzzy repair.
- [x] Przejście z dwoma zakresami oraz konflikt pojedynczego widocznego anchoru
  nie mogą utworzyć exact.
- [x] Tabela i fingerprint są deterministyczne dla rosnących i malejących
  granic runu.
- [x] Testy potwierdzają izolację domeny od runtime'ów i I/O.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_five_anchor_range_proof.py services/worker/tests/test_five_anchor_range_label_locator.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_five_anchor_range_proof.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection/five_anchor_range_proof.py
```

## Outcome

Ukończono 2026-09-02. Dodano czysty resolver v6, tabelę oczekiwanych wartości
pięciu anchorów, wersjonowaną politykę oraz stable reason codes. Exact wymaga
trzech zgodnych, wysokiej pewności wartości obejmujących centrum oraz pionowy
span; każda sprzeczna, czytelna wartość blokuje wynik.

Nie zmieniono runtime'u, lokalizatora, OCR, joba, API ani fingerprintów v1–v5.
Testy obejmują pełny i minimalny proof, konflikt, nienumeryczny OCR, częściową
stronę, clipping, blur, niską pewność, zakres malejący, collision i izolację
modułu.
