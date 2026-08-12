---
title: TASK-0168 first usable range-free representative selection
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0168 — First-usable range-free representative selection

## Status

`done`

## Goal

Wybrać dla każdej wizualnej grupy pierwsze wystarczająco czytelne zdjęcie bez
OCR, a przy jego braku najlepszy dekodowalny fallback zamiast odrzucenia grupy.

## Context

Celem selekcji jest szybkie zmniejszenie liczby zdjęć. Marginalne poszukiwanie
najlepszego kadru oraz wymaganie rozpoznanego zakresu powodują kosztowne
fallbacki, które należą do późniejszego importu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0167-appearance-only-sequential-image-grouping.md`

## Scope

- oceniać wyłącznie tanie metryki: dekodowalność, ostrość, ekspozycję,
  przepalenie i podstawową widoczność centralnego ekranu,
- utrzymywać pierwszego kandydata spełniającego wersjonowany próg oraz najwyżej
  jeden jakościowy fallback,
- po zamknięciu grupy wybierać pierwszego użytecznego bez pełnej weryfikacji,
- gdy żaden kandydat nie przechodzi miękkiego progu, wybrać najlepszy
  dekodowalny obraz z ostrzeżeniem `QUALITY_BEST_AVAILABLE`,
- pomijać wyłącznie niedekodowalne pliki albo twardy błąd integralności,
- nie usuwać niekolejnych wizualnych duplikatów na podstawie niepewnego
  podobieństwa; dokładny zakres i deduplikację pozostawić importowi.

## Out of scope

- OCR, geometria, identyfikacja numeru strony i symbol inference,
- manualne poprawianie jakości każdej grupy,
- poszukiwanie absolutnie najlepszego zdjęcia po całej serii,
- zmiana outputu i handoffu.

## Acceptance criteria

- [x] Typowa grupa nie uruchamia żadnej dodatkowej pełnej weryfikacji.
- [x] Każda grupa zawierająca co najmniej jeden dekodowalny JPEG dostaje
      reprezentanta.
- [x] Pierwszy użyteczny obraz wygrywa z późniejszym tylko nieznacznie lepszym.
- [x] Słaba grupa zachowuje best-available zamiast przejścia do obowiązkowego
      manual review.
- [x] Twarde błędy pojedynczego pliku nie kończą całego runu.
- [x] Ranking i remisy są deterministyczne po `order_index` oraz checksumie.

## Technical notes

Miękkie progi nie służą do odrzucania całej strony. Import i Reviewer mogą
później poprawić geometrię albo uzupełnić niewidoczne layouty.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/contracts.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/tests/test_fast_image_selector.py`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_fast_image_selector.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/selection services/worker/tests/test_fast_image_selector.py
```

## Risks / open questions

- Zbyt łagodny próg zwiększy liczbę słabych reprezentantów. Jest to akceptowane,
  o ile nie tracimy unikalnego ekranu i zachowujemy ostrzeżenie w audycie.

## Outcome

- Manifest v9 zawiera wersjonowaną politykę pięciu tanich progów i ogranicza
  `topK` do dwóch. Jego bieżący fingerprint wynosi `65c19a84a959…`; v8 nadal
  pozostaje domyślny do bramki TASK-0171.
- State machine zachowuje niezmienne pierwsze użyteczne źródło oraz jeden
  deterministyczny fallback. Przed znalezieniem użytecznego JPEG-a checkpoint
  zawiera tylko jeden najlepszy fallback.
- Finalizacja v9 nie wywołuje verifiera. Dekodowalna grupa zawsze dostaje
  `auto_selected`; fallback ma `QUALITY_BEST_AVAILABLE`, a grupa z samymi
  błędami dekodowania pozostaje `manual_required`.
- Weryfikacja: `85 passed` dla selektora, adapterów i joba; Ruff bez błędów;
  mypy bez błędów dla modułów engine i manifestu. Pierwsza próba pełnej regresji
  ujawniła wyłącznie brak dostępu do systemowego katalogu pytest; powtórzenie z
  repozytoryjnym `--basetemp` przeszło w całości.
