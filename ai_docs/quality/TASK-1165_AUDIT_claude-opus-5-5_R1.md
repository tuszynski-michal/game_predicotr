# Audyt TASK-1165 — Niezależne etykiety zawartości
Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: 1629b8be89f3f6dc72e83cd00b058d0545702da4 plus frozen58 uncommitted, 2026-11-08
Runda: 1
SHA pakietu: b5d403085a11923bf1dde81e419954561bb20826d2a9f5a8c71c606635024bfa
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie
Rewizje, CAS, ślepy pomiar, oracle, selekcja świeżego REG i ścieżka geometrii A są statycznie spójne z kontraktem, a legacy bez opt-in zachowuje dotychczasowy format. Jeden błąd blokuje przyjęcie: etykieta na jednej z kopii o tych samych pikselach przerywa cały capture i prepare wyjątkiem, którego capture nie obsługuje, zamiast zostać rozstrzygnięta per kopia.

## Znaleziska
### P0
Brak.

### P1
- [P1-1] services/api/src/game_predictor_api/storage/grid_cell_content_pins.py:42 — **Wyzwalacz:** `content_pin` szuka etykiety po pixel SHA i pozycji, ale rzuca `ContentError`, gdy `sourceId` albo byte SHA należą do drugiej kopii. `ContentError` dziedziczy po `ValueError`, a nie po `GridCohortError`, więc omija `except GridCohortError` w `grid_training_cohort_evidence.py:458`. Pętla po wszystkich pinach w `prepare_split` obejmuje też aliasy i bufory, o ile kopia przejdzie `own_target`. Istniejąca gałąź `GRID_CALIBRATION_GT_ALIAS_CONFLICT` pokazuje, że stan dwóch kopii z etykietami jest przewidziany; nie mierzyłem jego częstości w danych.
  **Skutek:** prepare z `contentSamplingPolicy` kończy się 409 dla całej populacji, a preview nie zwraca `not_evaluable` (`storage/grid_cell_content.py:103-106` nie łapie `ContentError`). Nowa rewizja przez drugą kopię tylko przenosi konflikt na pierwszą, więc operator nie ma wyjścia. Narusza to kontrakt zadania („Source UUID i byte SHA pozostają provenance”, klucz to pixel SHA) i ochronę kopii.
  **Naprawa:** rozstrzygnąć alias po tożsamości pikseli. Albo przypiąć etykietę z jawnym provenance i odpowiednio złagodzić porównania `sourceId`/`sourceSha256` w `grid_cell_content_reference.py:116-117`, albo pominąć pin dla kopii niereprezentatywnej z policzonym powodem. `ContentError` nie może opuszczać capture; preview ma zwracać `not_evaluable`.

### P2
- [P2-1] services/api/src/game_predictor_api/domain/grid_cell_content.py:107 — Quad poza źródłem podnosi `ValidationError` dopiero przy budowie rewizji w repozytorium (`storage/grid_cell_content.py:251`). Brak handlera daje HTTP 500 zamiast 422/409 przy zwykłej pomyłce operatora. Naprawa: mapować błąd na `ContentError` z kodem i dodać test żądania.
- [P2-2] services/api/src/game_predictor_api/api/grid_cell_content.py:73 — Zwykły GET `content-references` w trakcie `pass2` zwraca `measuredNodes` i komórki z `pass1`. Kontrakt umieszcza ten odczyt poza ślepym pomiarem, więc ślepotę zapewnia tylko przyszły edytor T5. Naprawa: 409 dla planszy objętej niezamrożoną sesją albo jawnie opisana granica.
- [P2-3] services/api/src/game_predictor_api/storage/grid_cell_content.py:525 — Readiness zamrożonej kohorty czyta najnowszą żywą etykietę, a nie piny manifestu. Kohorta bez `contentAnnotation` może więc pokazać `evaluable`, choć worker dostanie brak referencji. Naprawa: raportować też pokrycie pinami albo nazwać wynik postępem oznaczania.
- [P2-4] services/api/src/game_predictor_api/storage/grid_cell_content.py:746 — `blockedBoards` liczy każdy stan różny od `checked`, także `not_evaluable` planszy bez komórek visible. Taka legalna plansza blokuje sesję jak przycięcie przez renderer. Naprawa: rozdzielić liczniki i świadomie zdecydować o polityce.

## Pokrycie kryteriów akceptacji
| Kryterium | Status | Dowód |
|---|---|---|
| Niezależne rewizje, zatwierdzony aktor, sourceSHA | spełnione | `ContentRevision.provenance`, aktor z `request.state`, `write`/CAS, migracja 0182 |
| Blind A/powtarzalność bez propozycji; ≥30/10, caps | spełnione | `repeatability_report`, `session_view`, `content_pin` dla A; zastrzeżenie w P2-2 |
| Oracle blokuje przy przycinaniu przez renderer | spełnione | `content_oracle` z faktycznym `padded_source_quad` po float32; `qualificationState` wymagane przez pin A |
| Role/kopie/sesje/bufory/rodowód/ekspozycja; seed | niespełnione | Filtry poprzedzają seed20261108 i kopie liczone są raz, ale P1-1 przerywa capture |
| Unknown>10%; REG≥5 pełnych | spełnione | `fresh_regression_preview`, `content_readiness`, mianownik całego komponentu |
| Niedobory policzone | spełnione | `missingFullPhotos`, `unresolvedPhotos`, `reasonCounts`, `not_evaluated` |
| Trwałość, replay, PostgreSQL, kontrakt, audyt | niezweryfikowane | Kod receipts/CAS/RLS/triggerów i testy przeczytane, niewykonane; kryterium otwarte; P1-1 wymaga kolejnej rundy |

## Listy zamknięte i otwarte
Zamknięte: Brak.
Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4

## Proponowane testy
- Integracja PostgreSQL: dwie kopie o tych samych pikselach, obie z własnym targetem, etykieta na jednej; prepare i preview bez nieobsłużonego `ContentError`, deterministyczny wynik kopii, spójny reader workera.
- Test żądania: quad poza źródłem daje typowany błąd.
- Sesja z planszą bez komórek visible: oczekiwany `qualificationState`.

## Zakres przeglądu i ograniczenia
**Przeczytane z zamrożonych snapshotów:**
- Grupa A w całości: D590, sampling, migracja, reader i oracle.
- Grupa B: hunki split, prepare, currentness i workera; aktywne pętle `GridBoardDataset`/`CohortPhotos`; asercje pipeline 311–435; test PostgreSQL 60–181. Setup pipeline 76–238 nie był czytany.
- Grupa C: pełne DTO i endpointy, wrapper z testem żądania, manifest v22, lifecycle, retencja, allowlista, handler, migracja 0182.
- Pozostałe zakresy `storage/grid_cell_content.py`.

**Sprawdzone tylko częściowo lub poza planem:**
- Niezmienione w pakiecie fragmenty czytane z worktree: `Point`, `GridCohortError`, `own_target`, `frame`.
- OpenAPI tylko przez obecność 10 `operationId` i `contentSamplingPolicy`.

**Niezbadane:**
- Pozostałe hunki `sdk.gen.ts`, `types.gen.ts`, `generated/index.ts`, `models.py`, `router.py`, `image_reviews.py`, `application/*`.
- Treść `test_grid_cell_content.py`, `test_grid_content_sampling.py` i testu workera.
- Czy lokalny Reviewer dostaje `local-owner`, czego wymaga opis kontraktu.

**Ograniczenia:** nie uruchamiałem testów, usług, bazy ani kodu. Wyniki w raporcie wykonawcy nie zostały potwierdzone. Nie sprawdzałem SHA plików. Kryteria T3–T5 oraz rzeczywista kwalifikacja operatora są poza tym audytem.