---
title: Gra 777 — automatyczna reweryfikacja siatek „Do walidacji” i „Do poprawy”
status: active
last_updated: 2026-09-24
---

# Gra 777 — automatyczna reweryfikacja siatek

## Wymaganie użytkownika

Przepuścić wszystkie siatki z kolejek Reviewera „Do walidacji” i „Do poprawy”
gry 777 przez silnik. Gdy silnik jest pewny — poprawić/zatwierdzić siatkę, co
automatycznie wpuszcza planszę do weryfikacji symboli. Gdy nie jest pewny —
zostawić bez zmian. Jednorazowe narzędzie wyłącznie dla gry 777; bez zmian
w panelu Admin/Reviewer, API ani OpenAPI. Silnik 777 nie będzie ponownie
używany w innych grach.

## Stan obecny (fakty zmierzone read-only, 2026-09-24)

Gra `bfc4f949-5c14-4850-b02a-db99610bcfa5`, magazyn `game_data_v2`,
wszystkie plansze `asset_mode = virtual_source`.

| Populacja | Liczność | Pochodzenie |
|---|---|---|
| Do walidacji (plansze) | ~473 950 | `structured_opencv_v1` / `…-pinned-preflight-v1`, `disposition = automatic`, `approved_geometry_revision IS NULL`, rewizja 0 |
| Do poprawy (sloty odroczone) | 19 608 na 14 772 zdjęciach | `image_board_geometry_pending`, `reason_code = residual_too_high`, brak `automaticPartialProposal`/`automaticFrameProposal` |
| Do poprawy (plansze z `grid_issue`) | 1 | komórka z `quality_issue = grid_issue` |
| Zatwierdzone | 198 | ręcznie; w tym 135 ręcznych rewizji plansz (`corrected_by = local-admin`) |
| Ręczne geometrie źródeł | 15 (`manual-source-geometry-v1`) + 8 rozwiązanych slotów odroczonych | Reviewer |

Stan kolejki wynika z `storage/image_grid_review_repository.py::_state_expression`
(plansze) i `_pending_row_to_item` (sloty odroczone).

## Kluczowe decyzje

1. **Ponowne uruchomienie tego samego silnika nic nie daje** (deterministyczny).
   „Pewność” = zgodność z **niezależnym weryfikatorem** oraz bramki jakości.
2. **Weryfikator:** lokalny estymator siatki symboli
   `services/worker/src/game_predictor_worker/images/board_cell_geometry_estimator.py::estimate_board_cell_geometry(rgb, analysis_quad)`
   uruchamiany na `boardFrameQuad`/`analysisQuad` z automatycznej rewizji
   źródła. Wynik `status == "estimated"`, `lattice_bounds_quad`,
   `inlier_p95_residual_px`, `inlier_count`. Opcjonalnie, jeśli gra 777 ma
   dostępny profil V1.2 (`ContrastFrameGridV12Profile.available`), T1 mierzy
   także `ContrastFrameGridV12Registrar` jako drugi weryfikator; decyzja
   o jego użyciu zapada w T1 na podstawie danych.
3. **Progi nie są ustalane z góry.** T1 kalibruje je na złotym zbiorze z bazy
   (stan z chwili uruchomienia — obejmuje też nowe ręczne przykłady cięcia):
   - **G+**: plansze zatwierdzone bez korekty (`approved = geometry_revision = 0`)
     — silnik miał rację;
   - **G−**: plansze z ręczną rewizją `local-admin` — oryginalna siatka silnika
     vs siatka człowieka; „błąd silnika” = maks. odchylenie narożnika > ε_h
     (ε_h wyznacza T1 z rozkładu, raportowane jawnie);
   - **GP**: rozwiązane ręcznie sloty odroczone / ręczne geometrie źródeł —
     siatka człowieka dla slotów, których silnik nie wyznaczył.
   Kryterium doboru progów: **zero fałszywych akceptacji** na G− i GP; przy
   tym maksymalne pokrycie. Wynik zapisany jako D-445 w `DECISION_LOG.md`.
4. **Reguła decyzji (kształt; liczby z T1):**

   | Populacja | Pewny, gdy | Akcja |
   |---|---|---|
   | Plansza „Do walidacji” (rev 0, niezatwierdzona, bez `grid_issue`) | weryfikator `estimated` ∧ p95 ≤ r ∧ inliers ≥ n ∧ maxCornerDist(weryfikator, `symbolGridQuad`) ≤ τ | zatwierdzenie bieżącej rewizji (bez nowej geometrii) |
   | Slot odroczony | weryfikator `estimated` ∧ p95 ≤ r ∧ inliers ≥ n ∧ siatka wewnątrz obrazu i ramki | nowa geometria = `lattice_bounds_quad` weryfikatora |
   | Plansza z `grid_issue`, plansza z rewizją > 0 niezatwierdzona, plansza zatwierdzona | nigdy | pomiń |

5. **Ścieżki zapisu — wyłącznie istniejące serwisy** (te same co Reviewer):
   - zatwierdzenie: `application/image_grid_reviews.py::ImageGridReviewService.approve_source`
     z podzbiorem pewnych plansz zdjęcia (jedna transakcja na zdjęcie);
   - sloty odroczone: `application/virtual_grid_geometry.py::VirtualGridGeometryService.save_source`.
     **Fakt z kodu:** `save_source` wymaga komend dla wszystkich aktywnych
     slotów zdjęcia i tworzy nową zatwierdzoną rewizję dla każdego z nich
     (`storage/virtual_grid_geometry_repository.py`). Dlatego zdjęcie ze
     slotem odroczonym jest zapisywane tylko, gdy **wszystkie** jego sloty
     odroczone są pewne **i** każda plansza-rodzeństwo jest już zatwierdzona
     albo pewna wg reguły dla „Do walidacji”. Rodzeństwo dostaje swój
     bieżący `symbolGridQuad` (zaokrąglony do int, jak w Reviewerze).
     W przeciwnym razie całe zdjęcie zostaje bez zmian.
   - Zapis `save_source` oznacza rewizję `engine_kind = manual_v1`
     (zachowanie istniejącej ścieżki); pochodzenie automatyczne odróżnia
     aktor `system:grid-reverify-777-v1`. Akceptowane, bez migracji.
   - Oba serwisy już wołają `SymbolCellReviewWriteThroughCoordinator`, więc
     zatwierdzona plansza trafia do weryfikacji symboli (cold start → `?`,
     D-444). Nie dodajemy osobnego kroku.
6. **Narzędzie:** jeden skrypt `scripts/reverify_777_grids.py` (proponowany)
   z podkomendami `calibrate`, `plan` (dry-run) i `execute`. Wymagane
   argumenty `--game-id`, `--import-job-id`; odmowa, gdy gra nie jest
   na `game_data_v2`. Wszystko w `game_storage_scope(game_id)`. Bez joba
   workera, migracji, API i UI.

## Skala, pamięć, transakcje

- ~53 tys. zdjęć, ~474 tys. plansz. Iteracja po zdjęciach kursorem
  `(sequence_range_start, source_image_id)`, partie po 200 zdjęć; obraz
  ładowany raz na zdjęcie, zwalniany po przetworzeniu.
- Czas weryfikatora na planszę mierzy T1; przy > 20 ms pełny przebieg trwa
  godziny → uruchomienie jako kontrolowany proces w tle z checkpointem
  (plik JSONL w `artifacts/grid-reverify-777/`, wznowienie od ostatniego
  zatwierdzonego zdjęcia). `plan` i `execute` są wznawialne.
- `calibrate`/`plan` otwierają transakcję `READ ONLY`. `execute`: jedna
  transakcja na zdjęcie (przez serwis), idempotencja
  `uuid5(NAMESPACE_URL, "grid-reverify-777-v1:{source_image_id}:{source_geometry_revision_id}")`.

## Błędy

| Warunek | Zasięg | Reakcja |
|---|---|---|
| `ImageGridReviewError` stale/conflict/drift (np. ktoś edytuje w Reviewerze) | zdjęcie | rollback zdjęcia, wpis `skipped_conflict`, kontynuacja |
| Brak pliku źródła / niedekodowalny obraz | zdjęcie | wpis `source_unavailable`, kontynuacja, liczność w raporcie |
| Wyjątek weryfikatora (`ValueError` z estymatora) | plansza | traktowana jako niepewna (`verifier_failed`) |
| Błąd bazy/infrastruktury, `AssertionError`, nieoczekiwany wyjątek | cały przebieg | zatrzymanie z kodem ≠ 0; checkpoint pozwala wznowić |
| Brak zgody (`--execute` bez `--confirm-game-id` równego `--game-id`) | cały przebieg | odmowa przed jakimkolwiek odczytem obrazów |

## Aktualizacja 2026-09-24 po TASK-0644

Kalibracja wykazała, że lokalny estymator nie jest niezależny od silnika
(przy tej samej podpowiedzi zwraca identyczną siatkę), a złoty zbiór nie
zawiera błędów silnika, choć na podglądzie siatki silnika 777 są widocznie
przesunięte. Decyzja użytkownika: nie używać ręcznych siatek jako wzorca;
zbudować nowy silnik v3 (model ekranu 3 × 3) z analizy zdjęć —
[TASK-0648](../tasks/0648-screen-layout-grid-engine-v3-prototype.md).
TASK-0645–0647 są wstrzymane do czasu oceny v3 i zostaną przepisane tak,
by v3 był źródłem propozycji siatki, a nie weryfikatorem.

## Taski

1. [TASK-0644](../tasks/0644-777-grid-reverify-calibration.md) — kalibracja weryfikatora na złotym zbiorze (read-only), D-445.
2. [TASK-0645](../tasks/0645-777-grid-reverify-dry-run.md) — reguła decyzji + pełny dry-run (read-only).
3. [TASK-0646](../tasks/0646-777-grid-reverify-execute.md) — ścieżka `execute` z testami (bez uruchomienia na żywych danych).
4. [TASK-0647](../tasks/0647-777-grid-reverify-live-run.md) — przebieg na żywych danych **za osobną zgodą**, odbiór, dokumentacja.

## Mapa wymaganie → task → kryterium

| Wymaganie | Task | Kryterium |
|---|---|---|
| Pewność potwierdzona danymi | T1 | 0 fałszywych akceptacji na G−/GP, raport progów, D-445 |
| Niepewne zostają bez zmian | T2, T3 | test: niepewna plansza/slot → brak zapisu; liczniki dry-run |
| Pewne poprawione/zatwierdzone | T3, T4 | test serwisowy; spadek liczników „Do walidacji”/„Do poprawy” |
| Automatyczne przejście do symboli | T3, T4 | komórki symboli dla nowych rewizji istnieją (sync coordinator) |
| Bez panelu | wszystkie | brak zmian w `apps/*`, API, OpenAPI |

## Odbiór całego przepływu

Dry-run (T2) i przebieg (T4) raportują liczności: pewne/niepewne/pominięte
per populacja i per powód. Po T4: liczniki Reviewera zgodne z raportem ±
konflikty; użytkownik ogląda losową próbkę 30 automatycznie zatwierdzonych
plansz i 30 rozwiązanych slotów.

## Ryzyka i zakres wyłączony

- Weryfikator i silnik mogą dzielić błędy systematyczne (ta sama rodzina
  metod lattice) — dlatego G− jest kluczowe; jeśli T1 pokaże fałszywe
  akceptacje przy każdym sensownym progu, T2–T4 są wstrzymane i plan wraca
  do korekty (np. V1.2 jako drugi weryfikator).
- Mały złoty zbiór (setki, nie tysiące) — progi zachowawcze; pokrycie może
  być niższe niż oczekiwane. To akceptowalne: niepewne zostają do ręcznej pracy.
- Poza zakresem: zmiany UI, nowe typy jobów, trening modeli symboli,
  zmiana silnika importu, inne gry, cofanie zatwierdzeń (brak automatycznego
  rollbacku — cofnięcie wymaga ręcznej korekty w Reviewerze; aktor
  `system:grid-reverify-777-v1` pozwala zidentyfikować zapisy).

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0644 | claude-opus-5-5 | high | Dobór złotego zbioru i progów przesądza o bezpieczeństwie danych; wymaga oceny rozkładów, nie tylko kodu. | Nie; wynik akceptuje użytkownik (D-445). |
| TASK-0645 | claude-sonnet-5 | high | Czysta funkcja decyzji + read-only iteracja wg rozstrzygniętej reguły; umiarkowane ryzyko. | Nie. |
| TASK-0646 | claude-opus-5-5 | high | Zapis do domeny przez serwisy, reguła rodzeństwa w `save_source`, idempotencja i obsługa konfliktów. | Tak: claude-opus-5-5, reasoning high — review diffu przed T4. |
| TASK-0647 | claude-sonnet-5 | medium | Uruchomienie gotowego narzędzia w tle, monitoring i dokumentacja; logika już przetestowana. | Nie. |
