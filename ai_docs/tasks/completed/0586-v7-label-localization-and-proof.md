---
title: TASK-0586 — V7 label localization and proof
status: done
last_updated: 2026-09-21
---

# TASK-0586 — Lokalizacja etykiet i dowód v7

## Status

`done`

## Goal

Udostępnić source-local dowód zakresu v7: pięć wiarygodnych etykiet albo niezależne 3+3 z jednego wystąpienia, bez wnioskowania z sąsiadów.

## Context

T00 wykazał, że historyczny v3 uruchamia Paddle, ale nie odczytuje etykiet na próbie realnych zdjęć. T02 rozpoczyna nowy kontrakt dowodu i następnie musi sprawdzić lokalizację na korpusie T01.

## Dependencies / entry conditions

- T00 i T01 ukończone; istnieje model OCR oraz lokalny, zamrożony inwentarz korpusu.
- Progi `0,90` są wyłącznie propozycją startową wersjonowanej polityki i wymagają kalibracji T05.

## Recommended execution

`gpt-6-astra high`; niezależny review `gpt-6-astra medium` przed commitem. Nie akceptować dowodu opartego na nazwie pliku, oczekiwanym następnym zakresie, jakości kadru albo sąsiednim zdjęciu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0584-v7-selection-feasibility-and-isolation.md`
- `ai_docs/tasks/completed/0585-v7-corpus-and-configuration-contract.md`

## Scope

- Kontrakt pozycji 3×3, źródłowych etykiet, veto konfliktu i audytowalnego 5/3+3.
- Adapter lokalizatora i OCR z ograniczoną próbą realnego korpusu.

## Out of scope

- Grupowanie wystąpień, wybór jakości, checkpoint, zapis plików, API i UI.

## Acceptance criteria

- [x] Pięć zgodnych, własnych etykiet z bocznie uciętej pełnej strony zachowuje `seq_1-9`.
- [x] Wiarygodna szósta sprzeczna etykieta veto'uje hipotezę; nieczytelna etykieta nie jest konfliktem.
- [x] 3+3 wymaga różnych źródeł, klastrów wizualnych i jednego occurrence.
- [x] Lokalizator oraz OCR dają mierzalny wynik na ograniczonej próbie realnego korpusu; aktywacja pozostaje zablokowana do kalibracji T05.

## Test cases

- Lewa/prawa kolumna poza kadrem, 5+1 sprzeczność, 3+2, dwa niemal identyczne kadry i różne occurrence.
- Każdy wynik zachowuje identyfikatory źródeł potwierdzających do późniejszego audytu.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_range_proof.py -q
```

## Risks / open questions

- Początkowe cropy odczytują liczby na prawdziwym kadrze `777`, lecz bez
  niezależnie mierzonej geometrii ich proof jest poprawnie fail-closed. T05
  musi skalibrować lokalizację; przed jego odbiorem V7 nie może aktywować
  automatycznych zapisów.

## Outcome

- Dodano czysty kontrakt 3×3 oraz source-local proof: pięć wiarygodnych
  etykiet lub dwa własne dowody 3+3 z różnych klastrów tego samego occurrence.
  Wiarygodny konflikt blokuje hipotezę, a niewiarygodny odczyt jest brakiem
  dowodu.
- Dodano lokalizator dziewięciu etykiet i dwa read-only probe'y OCR. Rzeczywista
  próbka `777/302200 777_000645.jpg` potwierdza odczyt liczb, lecz nie tworzy
  automatycznego proofu przed pomiarem geometrii w T05.
- Probe korpusu waliduje manifest i zamrożony inwentarz T01, domyślnie obejmuje
  tylko development/calibration i odrzuca drift przed OCR. Wynik oraz warunek
  braku aktywacji: `ai_docs/quality/V7_T02_LABEL_LOCALIZATION_PROBE.md`.
- Weryfikacja: 10 testów proof/localizatora, Ruff i mypy zmienionych modułów;
  probe pojedynczego źródła oraz probe manifestowego korpusu.
- Self-audyt wykrył brak mierzonej pewności pozycji. Niezależny audit
  `gpt-6-astra medium` znalazł tę lukę oraz zbyt szeroki probe splitów;
  poprawki są objęte ponownymi testami i zostały zatwierdzone przez Astra.
