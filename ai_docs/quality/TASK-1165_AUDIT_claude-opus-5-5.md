# Audyt TASK-1165 — Niezależne etykiety zawartości
Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: frozen59 i baza 1629b8be89f3f6dc72e83cd00b058d0545702da4, 2026-11-08
Runda: 2
SHA pakietu: 175883b389e4e2de6bcf8acff92d5fd26925bc7c68902494577d2beef9878ea5
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie
P1-1 jest zamknięte: kopia o tych samych pikselach dostaje osobny pin odbiorcy, a konflikt jest rozstrzygany per plansza i nie przerywa populacji. P2-1, P2-3 i P2-4 również zamknięto. P2-2 pozostaje przyjętą granicą ekspozycji. Dwa nowe P2 dotyczą konsumentów poprawki, oba działają fail-closed i nie blokują przyjęcia.

## Znaleziska
### P0
Brak.

### P1
Brak.

### P2
- [P2-2] `services/api/src/game_predictor_api/api/grid_cell_content.py:73` — Zwykły GET `content-references` nadal może ujawnić wcześniejsze adnotacje podczas `pass2`.
  **Skutek:** ślepotę zapewnia tylko izolowany edytor T5.
  **Naprawa:** brak zmian w T2. Granica jest jawnie przyjęta w D-590 (`DECISION_LOG_2026.md:47-50`); T5 musi jej dotrzymać.
- [P2-5] `services/api/src/game_predictor_api/domain/grid_cell_content.py:235` (nowe) — `content_readiness_views` najpierw liczy żywy postęp (linia 285), a `content_readiness` rzuca `CONTENT_FRAME_CONFLICT` przy innej sekwencji najnowszej etykiety. Wyzwalaczem może być zapis przez kopię z własnym targetem i inną sekwencją, którą `require_board` przepuszcza, albo korekta sekwencji po zamrożeniu.
  **Skutek:** jeden żywy konflikt daje 409 dla całej odpowiedzi readiness, więc poprawne `frozenPinCoverage` staje się niedostępne. Piny i worker pozostają nienaruszone. Ścieżki nie wykonywałem, a częstości nie mierzyłem.
  **Naprawa:** w widoku live liczyć konflikt per plansza jako nierozstrzygnięty, z jawną przyczyną, a pokrycie pinami liczyć niezależnie.
- [P2-6] `services/api/src/game_predictor_api/storage/grid_cell_content_pins.py:152` (nowe) — `content_pin` nie sprawdza `live_source_image_id`, a `require_current_content_pin` wymaga wartości niepustej. Po usunięciu źródła adnotacji, które D-590 dopuszcza, kopia przechodzi capture i dostaje pin, a currentness zgłasza `CONTENT_REFERENCE_STALE`.
  **Skutek:** prepare wygląda poprawnie, a blokada pojawia się dopiero przy kontroli członka kohorty. Wyjściem jest nowa rewizja przez aktualną kopię; błąd nie wskazuje tej przyczyny.
  **Naprawa:** ujednolicić regułę w obu miejscach: pominąć taki pin z policzonym powodem albo dopuścić odłączone źródło przy dowodzie pikseli.

## Pokrycie kryteriów akceptacji
| Kryterium | Status | Dowód |
|---|---|---|
| Niezależne rewizje, zatwierdzony aktor, sourceSHA | spełnione | Pochodzenie adnotacji jest niezmienne; pokrycie z R1 bez regresji |
| Blind A/powtarzalność; ≥30/10, caps | spełnione | Pokrycie z R1; zastrzeżenie w P2-2 |
| Oracle blokuje przycinanie przez renderer | spełnione | `oracle_qualification`; `clipped` i `render_unavailable` dają `render_contract_blocked` |
| Role/kopie/sesje/bufory/rodowód/ekspozycja; seed | spełnione | `content_capture_counts` nie zmienia ról; `same_content_frame`; `contentTargetSource`; seed bez zmian |
| Unknown>10%; REG≥5 pełnych | spełnione | Pełne zdjęcie wymaga `eligible_boards == 9`, kopie liczone raz |
| Niedobory policzone | spełnione | `contentReasonCounts`, `contentReferenceFailures`, `canonicalBoards`; granica widoku live w P2-5 |
| Trwałość, replay, PostgreSQL, kontrakt, audyt | niezweryfikowane | Kod i testy przeczytane, niewykonane; wyniki PG są deklaracją wykonawcy |

## Listy zamknięte i otwarte
Zamknięte: P1-1, P2-1, P2-3, P2-4
Otwarte: P2-2, P2-5, P2-6

Dowody zamknięcia:
- **P1-1:**
  - `content_pin` porównuje znormalizowany frame i sekwencję, a oryginalne pochodzenie zostawia nietknięte i dopina `contentTargetSource`.
  - `capture` łapie `ContentError` (`grid_training_cohort_evidence.py:458`), preview zwraca `not_evaluable` (`storage/grid_cell_content.py:94`), a `constrain_content_regression` zlicza konflikty.
  - `frozen_content_reference` wymaga zgodności pina z rzeczywistym źródłem. `sourceIdentity` pochodzi z `frozen["source"]`, a etykiety przechodzą do manifestu w całości.
  - Test PG uczciwie obejmuje jednego właściciela i jedną kopię wykluczoną przez `own_target`; pin kopii jest projektowany osobno.
- **P2-1:** `require_content_bounds` ma ten sam predykat co walidator modelu i działa przed budową rewizji w `write` oraz `blind_write`. Test HTTP oczekuje 422 z kodem `CONTENT_QUAD_OUTSIDE_SOURCE`.
- **P2-3:** Pola najwyższego poziomu pochodzą z pokrycia pinami, a `annotationProgress` jest osobne. Schemat, OpenAPI, typy SDK i test żądania to rozróżniają.
- **P2-4:** `blockedBoards` liczy tylko realną blokadę renderera, `notEvaluableBoards` jest osobne, a priorytet stanów opisuje D-590 (linie 65-70). Etykiety negatywne TRAIN pozostają legalne.

## Proponowane testy
- Żywa rewizja z inną sekwencją po zamrożeniu: readiness zwraca pokrycie pinami i policzony konflikt.
- Pin kopii po odłączeniu źródła adnotacji: spójny wynik capture i currentness.
- Bezpośrednia asercja `contentReferenceFailures` w `constrain_content_regression`. Obecna asercja preview z konfliktem daje `not_evaluable` także z powodu niedoboru zdjęć, więc nie dowodzi liczenia.

## Zakres przeglądu i ograniczenia
**Przeczytane z zamrożonych snapshotów:**
- D-590 w całości i pełny test `test_grid_content_alias_pipeline.py`.
- `corrections.patch` w liniach 293–532, 660–1090 i 1445–koniec.
- Fragmenty: DTO readiness i sesji, `ContentSource`, walidator `ContentRevision`, `domain/grid_content_sampling.py`, reszta `grid_cell_content_pins.py`, `split_mapping`, oracle workera, `require_board`, pętla currentness i materializacja `sourceIdentity`.
- Funkcje produkcyjne podane inline w pakiecie.

**Sprawdzone częściowo lub poza zamrożonym drzewem:**
- `manifest.json` (nagłówek, początkowe wpisy i `reviewRanges`), grepy konsumentów pól pina.
- `AGENTS.md` (pierwsze 150 linii) oraz grep w żywym `domain/grid_correction_split.py`.

**Niezbadane:**
- Pozostałe hunki generowanych plików SDK, dokumentacja poza D-590 oraz niezmienione SQL, schematy i RLS.
- Pełny `_prepare` i wybór reprezentanta. Reprezentant bez etykiet jest statycznie liczony jako `unresolved`, ale wyboru nie badałem.
- Semantyka zastępczego `attested_start + position` przy częściowej atestacji. Błędne dopasowanie obniżałoby tylko licznik znanych pól; zdjęcie częściowe nie może być kompletne.

**Ograniczenia:** nie uruchamiałem testów, usług, bazy ani kodu. Wyników wykonawcy nie potwierdzałem, nie liczyłem też SHA plików. Kryteria T3–T5 oraz rzeczywista kwalifikacja operatora są poza tym audytem.