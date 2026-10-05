---
title: Ponowne przetworzenie oczekujących komórek symboli metodą RGB v2
status: accepted
last_updated: 2026-10-05
---

# Ponowne przetworzenie oczekujących komórek symboli metodą RGB v2

## Stan obecny

- Oczekujące komórki gry `777` przeszły dotąd przez bibliotekę wzorców
  `symbol-reference-library-v1` (D-466): B1–B3 (< 99%, wszystkie symbole),
  TASK-0828 (Winogron ≥ 99%, gotowy), TASK-0832 (Śliwka ≥ 99%, zatrzymana w
  części 16 na `SYMBOL_REFERENCE_WRITE_SIDE_EFFECT`), TASK-0833 (Arbuz, niezaczęty).
  Stan 2026-10-05: 1 431 745 rewizji biblioteki na 456 797 planszach; ok.
  1,67 mln oczekujących komórek ma predykcję biblioteki (0,99), ok. 5,7 mln
  nadal predykcję modelu.
- `ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md` przekazuje metodę
  `symbol-audit-rgb-classifier-v2`: argmax istniejącej `SpatialSymbolCnn` na
  oryginalnym cropie RGB 64 × 64 (`/127.5 - 1`, bez `gray_world`), biblioteka
  tylko potwierdza (jednomyślne 7/7 obu opisów = ta sama klasa); rozbieżność =
  propozycja CNN ze znacznikiem `?` (do przeglądu). Zgodność z zatwierdzeniami
  operatora 98,27% (5688/5788), w przeglądzie z propozycjami 98,84%.
  Handoff zabrania: wznawiania starych przebiegów pod dawnymi manifestami,
  użycia `reference_features` jako wejścia głównego wyboru i automatycznego
  „99%” dla samego argmaxu bez jawnej zmiany kontraktu i pochodzenia.
- Istniejące elementy: `services/worker/src/game_predictor_worker/symbols/audit_rgb_classifier.py`
  (`AuditRgbClassifier.candidates`, `candidate_is_tentative`),
  `.../symbols/reference_library.py` (`decide`, `vote_batch`, `NEIGHBOUR_COUNT = 7`),
  `.../symbols/reference_library_writer.py` (`apply_board`, `revert_board`,
  `_write_revision`, `MODEL_VERSION`, `LIBRARY_CONFIDENCE`),
  `scripts/evaluate_symbol_reference_library.py` (`apply-preview`, `apply`,
  `apply-verify`, `apply-revert`, `--shard`), filtr Admina „Źródło predykcji”
  (`image_symbol_review_repository.py`, `SymbolCellReviewPredictionSource`).

## Cel i wymagania operatora (2026-10-05)

1. Wybór symbolu według RGB v2 z handoffu.
2. Zakres: **wszystkie oczekujące komórki ośmiu symboli**, także te już
   przepisane starą biblioteką.
3. Kolejność pasm według pierwotnej pewności modelu: < 60%, 60–80%, 80–90%,
   90–99%, na końcu 99–100%. W każdym paśmie wszystkie osiem symboli, potem
   następne pasmo.
4. Zapis **tylko gdy wynik się różni** od obecnej predykcji (symbol albo status
   pewna / do przeglądu).
5. Niepewne (`?`) zapisywane jako **do przeglądu** z niską pewnością.
6. Przed zapisem każdego pasma **podgląd próbki każdej klasy** i zgoda operatora.

## Kluczowe decyzje projektu

### Kontrakt zapisu (proponowane, wymaga D-496)

| Wynik RGB v2 | `symbolCode` | `confidence` | Rewizja `model_version` |
| --- | --- | --- | --- |
| pewny: CNN = jednomyślna biblioteka 7/7 | klasa CNN | 0,99 | `symbol-rgb-v2` |
| do przeglądu (`?`): rozbieżność lub brak jednomyślności | klasa CNN | 0,50 | `symbol-rgb-v2` |

Wpis predykcji dostaje `rgbV2 = {version, status: confirmed|tentative,
cnnSymbolCode, libraryClass|null, shapeVotes, combinedVotes, previousSymbolCode,
previousConfidence, previousSource: model|reference_library|rgb_v2,
checkpointSha256}`. 0,50 nie jest skalibrowaną pewnością; to umowny znacznik,
który umieszcza komórkę w paśmie Admina < 60%. Stara stała `LIBRARY_CONFIDENCE`
i wersja `symbol-reference-library-v1` zostają bez zmian dla starych rewizji.

### Reguła „zapis tylko przy różnicy”

Status obecny: **pewna**, gdy obecna pewność ≥ 0,99 (model albo stara biblioteka),
inaczej **do przeglądu**. Zapis, gdy `symbol RGB ≠ obecny symbol` albo status
RGB ≠ status obecny. Przykłady:

| Obecnie | RGB v2 | Zapis |
| --- | --- | --- |
| model Winogron 0,55 | pewny Winogron | tak → 0,99 (status się zmienia) |
| model Winogron 0,995 | pewny Winogron | nie |
| stara biblioteka Siedem 0,99 | pewny Siedem | nie (zostaje stare pochodzenie) |
| stara biblioteka Siedem 0,99 | pewny Winogron | tak → Winogron 0,99 |
| model Śliwka 0,999 | do przeglądu Śliwka | tak → 0,50 |
| model Arbuz 0,70 | do przeglądu Wiśnia | tak → Wiśnia 0,50 |

### Pasmo i symbol komórki

- Symbol grupy = **obecny** symbol predykcji (to, co widzi Admin).
- Pasmo = **pierwotna pewność modelu**: dla komórek z rewizją modelu ich obecna
  pewność; dla komórek ze starą biblioteką pewność wpisu tej komórki w
  najnowszej rewizji planszy, której `model_version` nie jest wersją biblioteki
  ani `symbol-rgb-v2`. Granice: `[0, 0.6)`, `[0.6, 0.8)`, `[0.8, 0.9)`,
  `[0.9, 0.99)`, `[0.99, 1.0001)`.
- Komórki z flagą jakości, niepełną widocznością, bez renderu, nie `pending`
  albo z przypisaniem człowieka są poza zakresem (jak dotąd). Geometria i pola
  rozwiązane przez człowieka pozostają nienaruszone.

### Błędy zapisu

- `SYMBOL_REFERENCE_WRITE_SIDE_EFFECT` na komórce **niebędącej celem**
  (np. `5bc8d6ad…` z nieaktualną widocznością): rollback planszy, pokwitowanie
  `stale:side_effect`, przebieg idzie dalej (dziś zatrzymuje cały przebieg).
  Liczba takich plansz trafia do raportu pasma.
- Pozostałe błędy jak dotąd: `failed:<code>` zatrzymuje przebieg; restart
  części zawsze od nowego podglądu.

### Skala i zasoby

- Pasma 1–4 (< 99%): ok. 0,45 mln komórek (B1–B3 + resztki); render z cache
  istniejących podglądów częściowo, zapis rzędu godzin.
- Pasmo 5 (≥ 99%): ok. 7 mln komórek. Render ~5,4 mln brakujących wycinków
  (~17 h przy ~90/s), części po ≤ 60 tys. komórek (`--shard`). Zapis zależy od
  liczby różnic; w przebiegach starej biblioteki 2–38% komórek ≥ 99% nie
  miało jednomyślności 7/7 — przy regule z tabeli dałoby to ok. 0,2–1 mln
  zapisów 0,50 (do przeglądu). **Bramka pasma 5 musi pokazać tę liczbę przed
  zgodą operatora.**
- Pamięć: cache części ≤ ~0,8 GB; jedna część naraz; bez równoległych zapisów.

## Zadania

### Etap A — implementacja (bez zapisu w bazie poza testami)

#### TASK-0858 — decyzja RGB v2 i indeks pasm w podglądzie

- Goal: `apply-preview --policy rgb-v2` liczy propozycje dokładnie jak
  `scripts/recognize_grid_audit_symbols.py` (`AuditRgbClassifier.candidates` na
  wycinku z kontrolą SHA, `decide(vote_batch(...))` jako potwierdzenie,
  `candidate_is_tentative`), z checkpointem i biblioteką przypiętymi jak w
  handoffie (`library.json`, SHA `1731869d…`).
- Scope: nowy podkomenda/flaga w `evaluate_symbol_reference_library.py`;
  odczytowy eksport indeksu pasm (komórka → obecny symbol, pierwotna pewność,
  pasmo, obecne źródło) per symbol, porcjami; wybór zakresu z indeksu
  (`--band`, `--symbol`, `--shard`); manifest z regułą „zapis tylko przy
  różnicy”; podgląd HTML z próbką ≤ 40 komórek na parę (obecny → nowy, status).
- Acceptance: na zamrożonym snapshocie `approved-v2` (SHA `572722c8…`) port daje
  te same propozycje i statusy co obecna implementacja (≥ 5688/5788 zgodnych z
  etykietami, identyczne per komórka); testy jednostkowe reguły zapisu z tabeli;
  indeks pasm zmierzony dla wszystkich ośmiu symboli (liczby do planu).
- Tests: `services/worker/tests/test_audit_rgb_classifier.py`,
  `test_evaluate_symbol_reference_library_script.py` (nowe przypadki),
  `test_grid_audit_feedback_evaluation.py`.

#### TASK-0859 — kontrakt zapisu `symbol-rgb-v2` w writerze

- Goal: writer zapisuje rewizję `symbol-rgb-v2` z wpisem `rgbV2` i pewnością
  0,99/0,50; `apply-verify` i `apply-revert` obsługują nową wersję;
  `SIDE_EFFECT` na komórce spoza celów kończy planszę jako `stale:side_effect`.
- Scope: `reference_library_writer.py` (parametr polityki zamiast stałych),
  `evaluate_symbol_reference_library.py` (`apply`, `apply-verify`,
  `apply-revert`), wpis D-496 w `DECISION_LOG.md`.
- Acceptance: testy writera dla obu statusów, celu na komórce starej biblioteki,
  przypadku bez zmiany (brak celu), side-effect jako stale; test PG
  (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`) zapisu i cofnięcia jednej planszy.
- Tests: `test_symbol_reference_library_writer.py` + integracyjny PG.

#### TASK-0860 — źródło „RGB v2” w filtrze Admina

- Goal: Admin → Weryfikacja symboli → „Źródło predykcji” ma opcję
  „RGB v2” (oraz „RGB v2 — do przeglądu”), dotychczasowe opcje bez zmian.
- Scope: `SymbolCellReviewPredictionSource` + filtr w
  `image_symbol_review_repository.py`, OpenAPI, wygenerowany klient, wrapper,
  test żądania, Admin `symbol-review-workspace.tsx`.
- Acceptance: `npm run openapi:check`, testy API i Admina, ręczny podgląd filtra.

#### TASK-0861 — trwały sterownik pasm

- Goal: skrypt w repo (`scripts/run_symbol_rgb_bands.ps1`, proponowany)
  wykonuje dla zadanego pasma osiem symboli po kolei (podgląd → stop na
  bramce operatora → zapis → `apply-verify`), wznawialny po części,
  z logiem i raportem pasma (`report.json`: liczby zmian, do przeglądu,
  stale, czas).
- Acceptance: suchy przebieg na pasmie < 60% w trybie tylko podgląd;
  instrukcja wznowienia w runbooku.

### Etap B — przebiegi (każde pasmo osobnym taskiem, stop na bramce)

| Task | Pasmo | Bramka przed zapisem |
| --- | --- | --- |
| TASK-0862 | < 60% | podgląd 8 symboli + próbki; zgoda operatora |
| TASK-0863 | 60–80% | j.w. |
| TASK-0864 | 80–90% | j.w. |
| TASK-0865 | 90–99% | j.w. |
| TASK-0866 | 99–100% | j.w. + liczba zapisów 0,50 i szacunek czasu |

Każdy: zapis per symbol, `apply-verify` każdej części, raport w Outcome,
`CURRENT_STATE.md`. Stare przebiegi TASK-0832/0833 zamykane jako zastąpione
(bez wznowienia), stan opisany w ich Outcome.

## Mapa wymaganie → task → kryterium

| Wymaganie | Task | Kryterium |
| --- | --- | --- |
| 1 RGB v2 | 0858 | identyczność ze snapshotem `approved-v2` |
| 2 wszystkie komórki | 0858, 0862–0866 | indeks pasm obejmuje model + starą bibliotekę |
| 3 kolejność pasm | 0861, 0862–0866 | sterownik i taski w tej kolejności |
| 4 zapis przy różnicy | 0858, 0859 | testy tabeli przykładów |
| 5 niepewne 0,50 | 0859 | test statusu tentative |
| 6 podgląd i zgoda | 0861, 0862–0866 | stop na bramce, HTML próbek |

## Ryzyka i zakres wyłączony

- Pasmo 5 może dać setki tysięcy komórek 0,50 (obciążenie przeglądu) — decyzja
  na bramce TASK-0866 (np. nie obniżać pewnych komórek modelu ≥ 99% bez zmiany
  symbolu).
- Przyspieszenie `_with_render_specs` (~75 s na rundę) poza zakresem; osobna
  propozycja zadania.
- Bez treningu i zmiany checkpointu CNN, bez zatwierdzania komórek, bez zmian
  geometrii, bez wznawiania starych manifestów.
- Testy: wszystkie powyżej **planowane**, żaden nie był jeszcze uruchomiony
  w ramach tego planu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0858 | claude-opus-5-5 | high | Port metody z dowodem identyczności na snapshocie i nowy indeks pasm; błąd zmienia wyniki na milionach komórek. | Nie (audyt wstrzymany przez operatora 2026-10-01; na prośbę: claude-opus-5-5, high) |
| TASK-0859 | claude-opus-5-5 | high | Nowy kontrakt zapisu i ochrona danych w transakcji planszy. | Nie (j.w.; zalecany przy włączeniu audytu: claude-opus-5-5, high) |
| TASK-0860 | claude-sonnet-5-5 | medium | Rozszerzenie istniejącego filtra wg ustalonego przepływu API → OpenAPI → klient → Admin. | Nie |
| TASK-0861 | claude-sonnet-5-5 | medium | Sterownik według istniejących wzorców przebiegów, bez logiki domenowej. | Nie |
| TASK-0862 | claude-opus-5-5 | medium | Przebieg danych z bramką; ocena próbek i raport. | Nie |
| TASK-0863 | claude-opus-5-5 | medium | Jak wyżej, kolejne pasmo. | Nie |
| TASK-0864 | claude-opus-5-5 | medium | Jak wyżej, kolejne pasmo. | Nie |
| TASK-0865 | claude-opus-5-5 | medium | Jak wyżej, kolejne pasmo. | Nie |
| TASK-0866 | claude-opus-5-5 | high | Największy zbiór, decyzja o skali zapisów 0,50 na bramce. | Nie |

Dostępność modeli i poziomów rozumowania jest warunkowa — potwierdzana przed
uruchomieniem każdego taska.
