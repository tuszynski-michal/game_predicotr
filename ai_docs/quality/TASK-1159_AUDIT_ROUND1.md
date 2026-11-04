Werdykt: REVISE

**Audytor:** claude-opus-5-5/high · **Runda:** 1 · **Baza:** `c7ed8afe1913292d3fe5f7f23cb133f077ac84e2` (v1.7.563) · **Zakres:** tylko T5/TASK-1159. Obejmuje odczyty current/frozen, zwarty panel i istniejący ludzki zapis geometrii, opcjonalne v4 (polityka, przypisania A/B/BUFFER, odczyt historii), diagnostykę wejścia v2 i renderer HTML. Akceptacja ujścia T6 i partial-A należy do T6.

To przegląd wyłącznie statyczny: Read/Glob/Grep na pakiecie z 10 części i kilka celowanych odczytów kontekstu (`game_storage_routing.py`, `full_board_calibration_evidence.py`, router assignment). Niczego nie zmieniałem. Nie uruchamiałem testów, usług, bazy ani sieci. Wyniki wykonawcy traktuję jako deklaracje, a nie dowód.

## P0
Brak.

## P1

**P1-1. Bieżąca kwalifikacja w publicznym GET assignment czyta tabelę należącą do gry w niepowiązanej sesji katalogu, a błąd wywraca istniejący endpoint.**
- **Gdzie:**
  - `services/api/src/game_predictor_api/main.py:2480-2492`: `status_reader` dostaje sesję katalogu. Komentarz w kodzie mówi, że ta sesja „must not enter GameStorageRouter”, a nie ma ani `game_storage_scope`, ani `bind`.
  - `services/api/src/game_predictor_api/storage/grid_recognition_status.py:44-51`: wywołuje `_automatic_evidence`.
  - `storage/full_board_calibration_evidence.py:35`: `session.get(GridTrainingCohortModel, …)`. `grid_training_cohorts` jest tabelą gry według `game_data_v2_manifest_v16.py:17`.
  - `neural_grid_operation_qualification.py` (`_automatic_evidence`, ok. :208): łapie tylko `OSError/ValueError/KeyError/TypeError`, a błąd SQLAlchemy/DBAPI przechodzi dalej.
  - `grid_recognition_status.py:21-29`: brak gry albo `shape_geometry_configuration` niebędące stringiem rzuca `GridModelRegistryError`. Dotyczy to też błędów `from_catalogue`/`model_capabilities`.
  - `application/grid_model_registry.py:153`: wywołanie bez żadnej degradacji.
- **Skutek:** na ścieżce, na której automat faktycznie jest „qualified” (raport v5 z kalibracją tej gry), odczyt omija kontrakt routingu gry. Kończy się błędem i rollbackiem (500) albo czytaniem z niewłaściwego schematu, zależnie od `store_schema` gry. Do tego dodatkowa projekcja może zablokować wcześniej działający `getGameGridModelAssignment`, z którego korzystają podsumowanie przypisania, `GridCohortPreview` (baza i rodzina) i preflight importu. To regresja dostępności i naruszenie zakresu sesji/roli.
- **Dlaczego testy tego nie łapią:** test HTTP podmienia `status_reader` na stałą (`test_grid_model_registry.py`). Test jednostkowy łata `session.get` i dochodzi tylko do „unqualified”. Ścieżka `load_frozen_assessment` nie jest wykonywana w żadnym teście.
- **Minimalna poprawka:**
  - Wykonać `read_game_recognition_status` w osobnej sesji z `game_storage_scope(game)` i `GameStorageRouter().bind(..., intent=READ)`, w trybie tylko do odczytu.
  - Każdy wyjątek projekcji (poza błędami programistycznymi) mapować na `recognitionStatus = {evaluation/automatic: "unavailable", reasonCodes:[kod]}`, a nie na błąd całego GET.
  - Dodać test PG przez prawdziwą zależność `main.py`: gra v2 z raportem v5 z kalibracją → `automatic=qualified`, sesja katalogu pozostaje niepowiązana. Do tego przypadek gry bez konfiguracji V3 → 200 i `unavailable`.

## P2 (maks. 5)

1. **Reviewer może pokazać automatyczne zatwierdzenie jako zapisane.**
   - **Gdzie:** `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx` (blok `reviewAll` „Geometria: …”, ok. :447-456).
   - **Skutek:** `approvedGeometryRevision === geometryRevision` wyświetla „ma zapisane zatwierdzenie” także dla zatwierdzeń `system:`/`worker:`, które czytnik odrzuca (`approval()` → `HUMAN_APPROVAL_REQUIRED`). Operator może pominąć wymagany ręczny zapis dobrej siatki, a licznik pełnych zdjęć zostaje 0 bez wyjaśnienia.
   - **Poprawka:** neutralny tekst („zapis geometrii nie oznacza etykiety ludzkiej; zapisz ręcznie”) albo pole typu aktora z API.

2. **Margines w HTML dla rekordu ekranu v2 jest mylący.**
   - **Gdzie:** `services/worker/src/game_predictor_worker/images/comparison_input_diagnostics.py:113`.
   - **Skutek:** dla `attempt="redetect"` (wejście ekranu) karta planszy pokazuje margines planszy z presetu, choć tego wejścia on nie dotyczy.
   - **Poprawka:** dla `stage` ekranu pokazać `margin=None` i etykietę „wejście ekranu”.

3. **Diagnostyka v2 w rendererze nie sprawdza numeru sekwencji.**
   - **Gdzie:** `comparison_input_diagnostics.py:98`.
   - **Skutek:** rekord v2 jest wiązany tylko po źródle i pozycji, bez `sequence_number`. Po zmianie atestu zakresu ta sama pozycja może zostać pokazana przy innej planszy.
   - **Poprawka:** dodać sekwencję do rekordu v2 albo do wpisu indeksu i porównywać ją jak w v1.

4. **Panel uczenia: wyścig odczytów i zbędna blokada startu.**
   - **Gdzie:** `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx`, `previewExclusions` (ok. :511).
   - **Skutek:** `++readSequence.current` unieważnia trwający `refresh()` (listę i stan przebiegu), a przycisk „Sprawdź zakres/podział” nie jest blokowany przy `refreshing`. Dodatkowo `refresh()` w trybie legacy nie aktualizuje `previewedOptions`. Po powrocie z `screen+grid` do `grid-only` start zostaje zablokowany do ręcznego „Sprawdź”.
   - **Poprawka:** `disabled={disabled || refreshing}`, osobny licznik sekwencji dla podglądu i `setPreviewedOptions(optionsKey)` po udanym odczycie legacy.

5. **Brak testu regresji tożsamości legacy przez prawdziwy router.**
   - **Skutek:** wykluczenie `policyVersion`/`validationAssignments` w routerze jest poprawne statycznie. Nie ma jednak testu, w którym zapisane przed T5 polecenie (bez nowych kluczy) jest ponawiane przez HTTP bez `GRID_LEARNING_IDEMPOTENCY_CONFLICT` i z tym samym `previewSha256`.
   - **Poprawka:** test API, który zasila serwis zapisanym poleceniem legacy i ponawia je przez `POST`.

## Pokrycie kryteriów

| Kryterium | Ocena statyczna |
|---|---|
| Current vs frozen vs człowiek; brak kalibracji nie blokuje | Częściowo. Projekcja frozen jest poprawna i nie podnosi pinu, UI rozdziela stany. Ścieżka current zawiera **P1-1**. |
| Compact/loading/error/retry, mount tylko GET, odrzucanie nieaktualnych odpowiedzi | Tak (`cancelled`/`readSequence`, test workspace). Zastrzeżenie: P2-4. |
| Ręczny zapis/CAS/retry; nowy prepare ≠ exact retry; v4 i historia | Tak. `start()` czyta zapisany command przed preview. PG4 potwierdza 1/1/1 i ten sam budżet. Snapshot v4 sprawdzany po game/cohort/family/mode/policy/base. |
| Pion API → OpenAPI → SDK → wrapper → test | Tak (delta OpenAPI, `types.gen`, `index.ts`, testy żądań). Nie ujawnia ścieżek ani całych pinów. |
| Diagnostyka v1 bez zmian; v2 strict | Tak. Wymagane są: completed + `reservationSha`, pozycje, preset, pin modelu, OpenCV, `inputRaster` pikseli i obszar. Brak rastra, alias i rezerwacja kończą się `unavailable`. Zastrzeżenia: P2-2, P2-3. |
| HTML: pięć widoków, viewport ≠ input, margin z presetu | Tak. Escape przez `esc` i `\u003c`, viewport 0.7 tylko w `bounds()`. |
| Scoped kontrole, dokumentacja i niezależny audyt | Otwarte (ten audyt). |

**v4 (zgodnie ze zgłoszonym zakresem):**
- Legacy bez nowych pól → v2/v3, te same bajty i retry.
- B nie trafia do `selection_input`; `counts_from_header` liczy tylko A.
- Komponenty pochodzą z `_prepare` i z tych samych strażników `require_source_purpose`/`require_purpose_protection`.
- Preview jest tylko do odczytu; test PG pokazuje brak przyrostu `recording_photo_uses`.
- Ponowne `advance` sprawdza split, politykę, tryb i przypisania przypiętego wiersza.

## Lista otwartych / zamkniętych

- **Otwarte:** P1-1; P2-1 … P2-5. Przy statycznym przeglądzie nie da się zweryfikować wyboru checkpointu tylko z A dla trybu `grid-only` v4 po stronie trenera (kod T4 jest poza pakietem; `selection_input` dotyczy tylko `screen`).
- **Zamknięte (statycznie):**
  - brak podnoszenia frozen pinu przez bieżący odczyt;
  - zamaskowany alias obcego slotu (`foreign_scope`, `completedAttempts=0`);
  - `geometry_saved` przez prawdziwy właściciel/CAS/czytnik, bez measurement;
  - pełne zdjęcie wymaga 9/9;
  - v2 nie pożycza wejścia crop innego slotu (test `crop-0` vs slot 1);
  - historia v4 wymaga split-v4 i tożsamości snapshotu.

## Proponowane testy

1. Test PG przez prawdziwą zależność `main.py`: GET assignment dla gry v2 z raportem v5 z kalibracją → `automatic=qualified`, bez 500 i bez odczytu poza routingiem. Gra bez konfiguracji V3 → 200 i `unavailable`.
2. Retry przez HTTP polecenia legacy zapisanego przed T5 → bez konfliktu, ten sam widok.
3. Reviewer `reviewAll`: plansza z aktorem `system:` nie jest opisana jako zatwierdzona.
4. Renderer: rekord v2 `redetect` (bez marginesu planszy) i rekord v2 z obcą sekwencją → `unavailable`.
5. Panel: kliknięcie „Sprawdź” w trakcie `refresh()` nie gubi listy przebiegów.

## Ograniczenia

- Brak wykonania jakichkolwiek testów, buildów i PG. Czasy i wyniki PASS z weryfikacji nie zostały przeze mnie odtworzone.
- Nie oglądałem HTML ani zdjęć.
- Kontekst modułów T4 (trener, `require_rescue_pin`, `_eligible_inspected`) widziałem tylko we fragmentach. Ocena skutku P1-1 (500 albo odczyt z niewłaściwego schematu) zależy od `store_schema` gry; sam brak powiązania sesji i brak degradacji wynikają wprost z kodu.
- Limit czasu 480 s został przekroczony przez rozmiar pakietu (~435 kB).
