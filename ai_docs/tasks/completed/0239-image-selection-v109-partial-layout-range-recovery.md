---
title: TASK-0239 image selection v10.9 partial layout range recovery
status: done
release: "0.5"
last_updated: 2026-08-12
---

# TASK-0239 — Image selection v10.9 partial layout range recovery

## Goal

Usunąć przyczynę fałszywego `range_required` na czytelnych zdjęciach: zachować
częściową siatkę `3×3`, odczytywać najpierw etykiety faktycznie widocznych ramek
i akceptować krótszy dowód wyłącznie przy jawnych progach bezpieczeństwa.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/quality/image-selection-v109-acceptance-contract.json`
- `ai_docs/delivery/VERSION_0_4_EXECUTION_PLAN.md`

## Scope

- [x] Zachować historyczny manifest i fingerprint v10.8.
- [x] Dodać osobny manifest `fast-image-selector-v10.9`.
- [x] Odtwarzać ograniczone hipotezy siatki z co najmniej trzech ramek
      obejmujących dwa wiersze i dwie kolumny.
- [x] Wykonać progresywny OCR: widoczne ramki przed pozycjami odtworzonymi.
- [x] Akceptować cztery etykiety od `0.72`, trzy od `0.82`, a dwie od `0.90`
      dopiero po zgodnym odczycie z drugiego JPEG-a o innym checksumie.
- [x] Zachować fail-closed dla konfliktu geometrii lub zakresów oraz fallback
      siedmiu etykiet na poziomach `9/18`.
- [x] Zachować center-first, nie zmieniać progów grupowania ani publicznego API.
- [x] Dodać telemetrię częściowych kotwic i poziomów dowodu.
- [x] Sprawdzić 39 środkowych zdjęć z wcześniej nierozpoznanych grup.
- [x] Zaliczyć bramkę pierwszych 1440 źródeł.
- [x] Po zaliczeniu bramki rozpocząć pełny run 42 403 do nowego pustego katalogu.

## Acceptance

- 39 zdjęć regresyjnych: zero zaakceptowanych błędnych zakresów.
- Pierwsze 1440: 60 unikalnych zakresów, 40 duplikatów, zero review i zero
  błędnych zakresów; najwyżej 150 pełnych weryfikacji i 300 sekund.
- Pełny run jest dozwolony dopiero po zaliczeniu próby 1440.
- Istniejących 50 plików v10.8 nie wolno usuwać ani nadpisywać.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests -q --basetemp .runtime/pytest-v109-worker
.venv\Scripts\python.exe -m pytest services/api/tests -q --basetemp .runtime/pytest-v109-api
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images services/worker/tests
$env:MYPYPATH='services/api/src;services/worker/src'
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images services/worker/src/game_predictor_worker/cli.py scripts/profile_image_selection_slice.py
```

## Outcome

Implementacja v10.9 ma fingerprint
`6c14854d3f38744a3451da11e516bc4f10c348d3f8a4c32e9a999c69e9979720` i ten
sam fingerprint taniego skanu co v10.8, dzięki czemu nie wymaga ponownego
dekodowania 42 403 źródeł. Kontrola środkowego JPEG-a każdej z 39 wcześniej
nierozpoznanych grup dała 35 poprawnych zakresów i cztery bez decyzji; nie
zaakceptowano żadnego błędnego zakresu. Cztery przypadki fail-closed mogą zostać
rozstrzygnięte przez inne centralne zdjęcie grupy lub próbkę brzegową.

Finalna bramka pierwszych 1440 źródeł przeszła w 110,883022 s: pierwszych 100
domkniętych grup dało dokładnie 60 automatycznych unikalnych zakresów i 40
`skipped_existing_range`, bez review, nieznanego zakresu ani outputu dla
duplikatów. Wykonano 148 pełnych weryfikacji, a cache skanu miał 1624 trafienia i
zero chybień. Raport:
`artifacts/image-selection-v109-first-1440-gate-final.json`.

Pełne testy: 665 workera oraz 327 API (23 świadomie pominięte). Ruff i mypy dla
zmienionych modułów przechodzą. Pełne repozytoryjne Ruff/mypy nadal pokazują
wyłącznie wcześniejszy dług zapisany w TASK-0238: sześć E501 w migracji `0035`
i dziesięć błędów mypy w trzech niezmienionych modułach.

Po bramce rozpoczęto pełny run `2fa7f363-a9d4-406e-8b51-ed22da21f259` i job
`9974c3e1-505c-43dd-be22-becc86a688b1` na wszystkich 42 403 źródłach. Używa
nowego pustego katalogu `C:\Users\user\Documents\19810 - 45152 v10.9`; 50
plików v10.8 pozostało bez zmian. Raport i PID monitora:
`artifacts/image-selection-v109-live-19810-45152.json` oraz
`.runtime/live-image-selection-v109-19810-45152.pid.json`. Przy checkpointcie
1568 selektor miał 63 zapisane unikalne zakresy, 39 duplikatów, zero błędów i
jeden tymczasowy `range_required` grupy 35. Jest to ten sam dokładnie
zidentyfikowany fragment `19918–19926`, który etap końcowego domknięcia zmienia
na duplikat po zakończeniu selekcji.

Pełne runy ujawniły błąd trwałości końcowej korekty fragmentacji. Gdy dokładna
luka dziewięciu layoutów obejmowała więcej niż jedną podgrupę `range_required`,
engine wybierał poprawny najlepszy JPEG, ale przepinał kandydatów pozostałych
podgrup do pierwszej grupy. Trwała unikalność `(run_id, order_index)` poprawnie
blokowała taką zmianę jako `IMAGE_SELECTION_PERSISTENCE_CONFLICT`, przez co run
kończył się przy ostatnim checkpointcie. Przypadek runu
`823c5b99-9447-4f25-940f-b2aaba8db56f` dotyczył fragmentów 3263/3264 i
bezpiecznie domkniętej luki `88507–88515` pomiędzy `88498–88506` oraz
`88516–88524`.

Korekta zachowuje najlepszy JPEG w jego źródłowej grupie, tej grupie przypisuje
dokładną lukę, a pozostałe fragmenty zapisuje jako `skipped_existing_range` z
tym samym zakresem i `duplicate_of_group_order`. Różny checksum albo zwykłe
ponowne użycie `order_index` nadal kończy się fail-closed. Przeszło 105 testów
skupionych, Ruff, mypy oraz pełne 666 testów workera.

Kontrolowany retry tego samego runu od checkpointu 42 400 zakończył 42 422 / 42
422 w drugim podejściu. Grupa 3264 została właścicielem `88507–88515`, a grupa
3263 otrzymała `skipped_existing_range`; job przeszedł do
`waiting_for_review` bez błędu. Terminalny monitor otrzymał dodatkową korektę:
po zakończeniu runu opróżnia wszystkie strony grup zamiast wychodzić po
pierwszych 100 rekordach. Uzgodnienie dopisało 21 brakujących JPEG-ów i
potwierdziło 2 567 plików wynikowych. Skupiona regresja selektora, persistence i
monitora przechodzi 111/111.

Właściciel zaakceptował 2026-08-12 v10.9 jako wystarczająco dobrze działający
algorytm wyboru zdjęć i zamknął tor wersji 0.5. Trwające lokalne runy pozostają
pracą operatorską na dostarczonym selektorze; ich ręczne review ani dokończenie
nie blokują zamknięcia zadania implementacyjnego.
