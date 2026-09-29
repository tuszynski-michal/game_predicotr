---
title: Cell-level symbol verification and single grid-correction queue
status: accepted
last_updated: 2026-09-29
---

# Plan: weryfikacja per komórka i jedna kolejka korekty cięcia siatki

Decyzja właścicielska: `ai_docs/process/DECISION_LOG.md` D-462. Operator
zaakceptował plan 2026-09-29 wraz z rekomendacjami P1–P4 (sekcja 6) i zlecił
wykonanie wyłącznie etapu A. Etapy B i C wymagają osobnego polecenia; zapis
danych w T8 wymaga dodatkowo osobnej zgody po preview.

## 1. Stan obecny (fakty z kodu i odczytu bazy 2026-09-29)

| # | Miejsce | Blokada |
|---|---|---|
| B1 | `storage/board_search_projection_repository.py::_payload_from_records` | Plansza `pending` w wyszukiwarce i „Przybliżonej wygranej” używa wyłącznie predykcji modelu; zweryfikowane komórki są ignorowane (gra `7`: 22 340 komórek na 18 478 planszach). |
| B2 | `storage/image_symbol_review_repository.py::SqlAlchemySymbolCellReviewMutationRepository.apply_board_mutations` | Projekcja wyszukiwania jest synchronizowana tylko przy rozstrzygnięciu całej planszy. |
| B3 | `domain/image_symbol_reviews.py::derive_symbol_cell_board_resolution(geometry_approved=...)` wołane w `apply_board_mutations` i `synchronize_board_from_cells` | 15/15 zweryfikowanych komórek nie domyka planszy bez `recognized_boards.approved_geometry_revision == geometry_revision` (361 813 plansz bez akceptacji; szybka akceptacja użyta 63 razy). |
| B4 | `apps/reviewer/src/features/access/local-reviewer-workspace.tsx` | Dwa tryby 3001: „Walidacja gotowych siatek” (całe zdjęcie, zakładki Do walidacji/Do poprawy/Wszystkie, „Zatwierdź całe zdjęcie”) i „Niepełne siatki…” (`OperationalReviewWorkspace`). |
| B5 | `domain/image_symbol_reviews.py::invalidate_symbol_cell_reviews_for_geometry` | Ścieżka niekwalifikowana zostawia `approved` przy zmienionym cropie (456 komórek / 113 plansz zatwierdzonych na starym cropie). |
| B6 | `services/worker/.../images/pending_grid_reinference.py` | Ochrona przed automatycznym przecięciem opiera się tylko na `approved_geometry_revision IS NULL`, nie na decyzjach człowieka w komórkach. |

Istniejące i zachowane: komórka jest źródłem decyzji (`image_symbol_review_cells`);
`mark_symbol_cell_grid_issue` cofa weryfikację jednej komórki; kolejka
`SqlAlchemyImageGridReviewRepository.list_grid_reviews` już łączy plansze z
bieżącym `grid_issue` i sloty `image_board_geometry_pending`; ręczny zapis
geometrii per plansza ustawia `approved_geometry_revision`; trening jest per
komórka.

## 2. Reguły docelowe

- **R1** Źródłem prawdy jest komórka. Dowód = `review_state=approved`, o ile
  zatwierdzone piksele są bieżącymi pikselami albo akceptacja nie ma
  tożsamości pikseli (pozycja bez obrazu, D-451). Numer rewizji geometrii nie
  decyduje (R10). Decyzja całej planszy (`board_decision`) to zbiór decyzji
  komórek.
- **R2** Status planszy jest pochodny: domyka się automatycznie przy komplecie
  zweryfikowanych komórek, pełnej widoczności i jednoznacznej sekwencji. Brak
  bramki zatwierdzonej geometrii.
- **R3** Kalkulacje:

| Kalkulacja | Wymagany zestaw | Zachowanie |
|---|---|---|
| Wyszukaj planszę | pojedyncze komórki | dowód = pewny symbol bez alternatyw; bez dowodu = predykcja; `pending` z `grid_issue`/`unreadable`/`partial_visibility`, pole bez pikseli źródła bez ręcznej decyzji (poza zatwierdzonym `outside`) i zatwierdzone `?` = brak dowodu |
| Przybliżona wygrana | ta sama projekcja | ta sama nakładka; nieznane obsługuje `payout-v3-unknown-prefix-stop` |
| Layout → dataset → snapshot → target | komplet komórek planszy | tylko plansza rozstrzygnięta wg R2; brak = brak layoutu; `pending_partial` nigdy (D-451) |
| Trening symboli | komórka | bez zmian |
| Kalibracja geometrii | `approved_geometry_revision` | bez zmian; nie jest bramką symboli |

- **R4** Jedna kolejka korekty: `image_board_geometry_pending` w stanie
  `pending` (wszystkie) ∪ plansze z ≥1 bieżącą komórką `grid_issue`. Klucz
  `(source_image_id, position_index)`; wiele zgłoszeń = jedna pozycja;
  rodzeństwo ze zdjęcia nie trafia do kolejki.
- **R5** Zapis geometrii kończy korektę i usuwa zgłoszenia `grid_issue` tej
  planszy; nie weryfikuje symboli.
- **R6** Po zmianie geometrii: niezmieniona tożsamość cropa zachowuje
  weryfikację (akceptacja przepięta na bieżącą rewizję); zmieniona wraca do
  `pending` (poprzedni symbol człowieka jako podpowiedź, stara akceptacja w
  audycie). Dotyczy `legacy_file` i `virtual_source`. Inne plansze zdjęcia
  bez zmian.
- **R7** „Zła siatka” na zweryfikowanej komórce = `pending` + `grid_issue`
  tylko tej komórki; `Zatwierdź` na komórce z `grid_issue` wycofuje zgłoszenie.
- **R8** Każda zmiana wiersza komórki (mutacja operatora, write-through po
  geometrii/predykcji/rozstrzygnięciu, `_replace_current_cells`) aktualizuje
  projekcję planszy w tej samej transakcji; brak cache serwerowego; Admin nie używa ponownie wyniku
  „Przybliżonej wygranej” z pamięci przy ponownym otwarciu.
- **R9** Automatyczne przecięcie (`_run_v1` i `_run_v2`) nie dotyka planszy z
  decyzją człowieka na komórce.
- **R10** Akceptacja, dla której tożsamość pikseli akceptacji jest różna od bieżącej
  (`virtual_source`: `approved_rendered_pixel_checksum_sha256` ≠
  `rendered_pixel_checksum_sha256`; pozostałe: `approved_crop_checksum_sha256`
  ≠ `crop_checksum_sha256`),
  nie jest dowodem ani warunkiem domknięcia planszy (reguła odczytu, bez
  zmiany danych; dane naprawia T8). Odczyt 2026-09-29: 456 komórek / 113
  plansz.

Założenia i wyłączenia: A1 bramka geometrii stron przed importem poza zakresem; A2 zdalny
Reviewer bez zmian; A3 bez DDL poza ewentualnym indeksem wydajnościowym. A4 ponowne otwarcie planszy
przez walidację ciągłości importu (`pipeline_store.py`,
`synchronize_after_board_reopened`) nadal resetuje komórki — znane ryzyko,
poza etapem A (wymaga rozstrzygnięcia, bo dotyczy niejednoznacznej sekwencji).

### Poza zakresem

Bramka geometrii stron przed importem, zdalny Reviewer, kalibracja geometrii,
ranking wyszukiwania, archiwum legacy, trening, usunięcie kolumn/tabel/historii.

## 3. Etapy i taski

### Etap A — reguły backendu i świeżość danych

- **T1 / TASK-0721** — D-462, wymagania i model danych.
- **T2 / TASK-0722** — nakładka zweryfikowanych komórek w projekcji,
  synchronizacja po każdej mutacji komórki, klient bez ponownego użycia wyniku.
- **T3 / TASK-0723** — rozstrzyganie planszy wyłącznie z komórek; ochrona
  automatycznego przecięcia.
- **T4 / TASK-0724** — reguła R6/R7 po zmianie geometrii.

### Etap B — wspólna kolejka i ekran 3001

- **T5 / TASK-0725** — widok `correction` kolejki (R4), `reportedCellIndices`,
  zapis ograniczony do slotu dla odroczonej planszy `virtual_source`. Od
  TASK-0724 zapis źródła `virtual_source` ponownie otwiera każdą rozstrzygniętą
  planszę zdjęcia i domyka ją z komórek; ograniczenie zapisu do slotu musi
  wykluczyć rodzeństwo z tego kroku.
- **T6 / TASK-0726** — jeden ekran „Korekta cięcia siatki” (jedna plansza,
  zapis → następna); zmiana nazw w Adminie.
- **T7 / TASK-0727** — usunięcie `grid-reviews` UI, endpointów szybkiej
  akceptacji, allowlisty i widoków `needs_validation`/`all`; OpenAPI + klient.

### Etap C — migracja i odbiór

- **T8 / TASK-0728** — preview i (po zgodzie) apply: backfill projekcji dla
  plansz z decyzjami człowieka, 456 komórek do ponownej weryfikacji,
  domknięcie plansz 15/15; zero nowych weryfikacji.
- **T9 / TASK-0729** — odbiór całości.

Szczegóły tasków etapu A są w plikach zadań. Taski etapów B i C zostaną
rozpisane według TASK_TEMPLATE przed ich uruchomieniem.

## 4. Mapa scenariusz → task

| Scenariusz | Task |
|---|---|
| 1 Jedna komórka zweryfikowana | T2, T3 |
| 2 Inna komórka ze złym cięciem | T2, T4 |
| 3 Algorytm odrzuca jedną planszę | T5 |
| 4 „Zła siatka” z weryfikacji | T5 |
| 5 Wiele zgłoszeń jednej planszy | T5 |
| 6 Zapis poprawionej geometrii | T4, T5 |
| 7 15/15 zweryfikowanych | T3 |
| 8 Ekran 3001 | T6 |
| 9 Migracja | T8 |

### Mapa wymaganie → task → test

| Wymaganie | Task | Test / kryterium |
|---|---|---|
| R1, R3, R8, R10 | T2 | unit nakładki; integracja: decyzja, job, zmiana geometrii → dokument |
| R2, R9, R10 | T3 | domena rozstrzygnięcia; integracja 15/15; worker v1/v2 pomija decyzje człowieka |
| R5, R6, R7 | T4 | domena recropu; integracja `legacy_file` i `virtual_source` |
| R4 | T5 | lista `correction`, deduplikacja, rodzeństwo |
| UI 3001 | T6, T7 | testy Reviewera |
| migracja | T8 | preview = apply, idempotencja, zero nowych weryfikacji |

## 5. Ryzyka

- Zapis rewizji źródła `virtual_source` może zmienić tożsamość renderu
  rodzeństwa (bramka testowa T5 przed T6).
- Więcej plansz trafi do layoutów bez akceptacji siatki — zamierzone (R2).
- Dodatkowy upsert projekcji na planszę w jobie masowym.
- Brudny worktree (m.in. TASK-0720) — commity zawierają wyłącznie hunki taska.
- A4: reset komórek przy ponownym otwarciu z walidacji ciągłości.
- Opt-in suite PostgreSQL `test_image_batch_store.py` ma wcześniejszy dryf
  asercji (poza zakresem; zgłoszone osobno); taski dodają własne testy.

## 6. Decyzje operatora (2026-09-29)

- P1 „Przybliżona wygrana” nadal używa predykcji dla niezweryfikowanych komórek.
- P2 456 komórek zatwierdzonych na zmienionym cropie wraca do weryfikacji (T8).
- P3 Zdalny Reviewer poza zakresem.
- P4 Plansze `pending_partial` nie tworzą pełnego layoutu (D-451 bez zmian).

## Przypisanie modeli do zadań

Wykonawca działa w sesji głównej; audytor jest osobnym subagentem Opus 5.5
uruchamianym po każdym tasku (polecenie operatora). Poziomu rozumowania
subagenta nie da się ustawić jawnie z sesji — rekomendacja warunkowa.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-0721 | claude-opus-5-5 | high | Dokumentacja reguł zmieniających nadrzędne decyzje 0.9. | Tak: claude-opus-5-5, high |
| T2 / TASK-0722 | claude-opus-5-5 | high | Projekcja współdzielona przez dwa widoki, synchronizacja w transakcji mutacji. | Tak: claude-opus-5-5, high |
| T3 / TASK-0723 | claude-opus-5-5 | high | Zmiana bramki domenowej wpływa na layouty i snapshot. | Tak: claude-opus-5-5, high |
| T4 / TASK-0724 | claude-opus-5-5 | high | Ryzyko utraty lub fałszywego zachowania weryfikacji na dwóch ścieżkach geometrii. | Tak: claude-opus-5-5, high |
| T5 / TASK-0725 | claude-opus-5-5 | high | Kontrakt API, deduplikacja i zapis slotu `virtual_source`. | Tak: claude-opus-5-5, high |
| T6 / TASK-0726 | claude-opus-5-5 | high | UI na istniejącym edytorze, kontrakt z T5. | Tak: claude-opus-5-5, high |
| T7 / TASK-0727 | claude-opus-5-5 | high | Usunięcie kodu i endpointów z kontrolą konsumentów. | Tak: claude-opus-5-5, high |
| T8 / TASK-0728 | claude-opus-5-5 | high | Operacja na żywych danych z preview i zgodą. | Tak: claude-opus-5-5, high |
| T9 / TASK-0729 | claude-opus-5-5 | high | Odbiór read-only i aktualizacja stanu. | Tak: claude-opus-5-5, high |
