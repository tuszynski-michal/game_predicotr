# Audyt TASK-0950 — Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

Werdykt: REVISE
Audytor: Codex, gpt-6-astra, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...a7f9fe27d9a726dc220117d274e4fa52aa8eb273 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano regułę własności, sprzątanie starego zdjęcia, przenoszenie komórek, migrację oraz raport API i Adminu. Podstawowy scenariusz zastąpienia odrzuconego slotu ma test integracyjny i wspólną implementację dla API oraz workera. Pozostają trzy błędy: pomijanie audytu sekwencji chronionych w imporcie neural, nieobsługiwane przeniesienie komórek spoza kadru oraz błędne przypisanie pochodzenia wcześniejszego zatwierdzenia.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/images/pipeline_store.py:453` — Ochrona `has_protected_lateral_owner` nadal wykonuje `continue` przed wspólną regułą własności. Dla importu `neural-auto-crop-v1` lub `lateralPartialGeometry`, gdy żywy właściciel innego zdjęcia ma zatwierdzoną geometrię, kwalifikację częściową albo decyzje człowieka, nowa plansza nie otrzymuje wymaganego `superseded` i nie powstaje alternatywa `superseded_existing_owner_kept`. Raport oparty na alternatywach zaniża wtedy „Pominięte”. Należy zachować ochronę właściciela, ale zapewnić wymagany zapis pominięcia dla innego zdjęcia; wyjątek tej samej checksumy powinien zachować dotychczasowe zachowanie. Jest to również konflikt wskazany w tasku jako wymagający rozstrzygnięcia, którego `Outcome` obecnie nie rozpoznaje.

- [P0-2] `services/api/src/game_predictor_api/domain/image_symbol_reviews.py:850` — Nowy `handoff_from_rejected_board` pomija tylko kontrolę numeru rewizji. Nadal wymaga kompletu wcześniejszych cropów, jeśli nowa plansza nie ma kwalifikacji częściowej. Przy zastąpieniu odrzuconej planszy zawierającej komórki `outside` pełnym zdjęciem stara historia nie spełnia tego warunku: `image_symbol_review_repository.py:2694` wyklucza komórki bez `crop_sample_id`. Walidacja podnosi `SYMBOL_CELL_REVIEW_CELLS_INCOMPLETE`, zanim dojdzie do obsługi przeniesienia, i przerywa transakcję importu. Należy dopuścić niepełną historię cropów przy przejęciu od odrzuconej planszy, nadal walidując komplet nowych komórek oraz zachowując decyzje logiczne pozycji wcześniej pozbawionych obrazu.

- [P0-3] `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2755` — Wybór proweniencji zatwierdzenia zakłada, że równość `approved_crop.geometry_revision` i rewizji nowej planszy oznacza zatwierdzenie bieżących pikseli. Nowe przejęcie dopuszcza jednak jednakowe numery rewizji różnych plansz, np. `0 → 0`. Jeżeli komórka starej planszy była zatwierdzona, a zamiennik ma inne piksele, domena zachowuje stare zatwierdzenie jako historię, lecz ta gałąź przypisuje mu `approved_source_geometry_revision_id`, specyfikację renderu i checksumę wyrenderowanych pikseli nowego zdjęcia. Powstaje niespójny zapis dowodowy starego zatwierdzenia. Należy rozpoznawać rzeczywiste przeniesienie zatwierdzenia na identyczne piksele na podstawie tożsamości cropa lub jawnego wyniku domenowego, zamiast samego numeru rewizji.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| B przejmuje odrzucone S, zachowuje dobre plansze A i zapisuje alternatywy dla pominiętych | niespełnione | Podstawowy wariant pokrywa `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:133`; wariant chronionego właściciela omija wymagany zapis — P0-1. |
| Odrzucony slot A przechodzi do `superseded`, bramka jest przeliczana, dobre plansze materializowane | spełnione | Implementacja i asercje w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:133`; ocena statyczna. |
| Ponowne przetworzenie tej samej checksumy zachowuje dotychczasową regułę | spełnione | `services/api/tests/test_sequence_takeover.py:81` oraz wariant `same-photo` w `services/api/tests/integration/test_image_batch_store.py:2961`; ocena statyczna. |
| Raport pokazuje zastąpione i pominięte sekwencje | niespełnione | Kontrakt HTTP sprawdzany w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:235`, lecz pominięcia z P0-1 nie trafiają do raportu. |
| Przejęcie odrzuconej przyciętej planszy zachowuje komórki i historię | niespełnione | P0-2 i P0-3. Test w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:243` nie obejmuje komórek `outside` ani proweniencji zatwierdzeń przy jednakowych rewizjach. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3.

## Proponowane testy

W `services/api/tests/integration/test_replacement_photo_takeover_postgres.py` dodać:

- Import B z polityką `neural-auto-crop-v1`, gdy A ma żywe plansze z ręcznie zatwierdzoną geometrią. Sprawdzić zachowanie właściciela, alternatywy i dokładny licznik pominięć.
- Odrzucenie planszy A z komórkami `outside`, następnie import pełnej planszy B. Sprawdzić udane przejęcie, komplet komórek, zachowanie sugestii człowieka i zgodność liczników.
- Zatwierdzenie pojedynczej komórki A przy rewizji 0, odrzucenie planszy i zastąpienie innymi pikselami B przy rewizji 0. Sprawdzić stan `pending` oraz zachowanie wszystkich pól `approved_*` starego zatwierdzenia.

Komenda po poprawkach, w środowisku testowym PostgreSQL opisanym w tasku:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_replacement_photo_takeover_postgres.py services/api/tests/test_sequence_takeover.py -q
```

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, właściwe fragmenty planu, wymagań i decyzji oraz zmiany implementacji, migracji, kontraktu, klienta, UI i testów. Prześledzono również istniejące ścieżki ochrony workera, przeliczania bramki i synchronizacji komórek.

Nie uruchamiano testów, migracji ani usług. Wyniki zapisane w `Outcome` są deklaracjami wykonawcy, bez niezależnego potwierdzenia w tym audycie. Znaleziska wynikają z analizy przepływu kodu.