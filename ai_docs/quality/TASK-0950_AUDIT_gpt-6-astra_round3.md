# Audyt TASK-0950 — Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

Werdykt: REVISE
Audytor: Codex, gpt-6-astra, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...a7f9fe27d9a726dc220117d274e4fa52aa8eb273 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 3

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Wspólna blokada gry usuwa poprzednio wskazane zakleszczenie dwóch równoległych przejęć; dodano odpowiedni test PostgreSQL. Zmiana wprowadza jednak odwrotną kolejność blokad przy mutacjach symboli, które zamykają albo ponownie otwierają planszę. Ten konflikt może przerwać zapis decyzji użytkownika lub równoległy import i blokuje commit.

## Znaleziska

### P0

- [P0-5] `services/api/src/game_predictor_api/storage/image_review_repository.py:1770` — Nowa blokada `sequence-ownership` jest pobierana również przez wywołania, które już trzymają blokadę sekwencji.

  `apply_board_mutations` najpierw blokuje sekwencję (`services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:1200`, implementacja `:1484`), następnie wiersze i stan projekcji. Później oznaczenie komórki jako `MARK_GRID_ISSUE` lub `MARK_UNREADABLE` na rozstrzygniętej planszy wywołuje `reopen_for_symbol_cell_issue` (`:1317`), które dochodzi do nowej blokady gry. Analogiczna ścieżka występuje przy zatwierdzeniu ostatniej komórki i rozstrzygnięciu planszy (`:1354`).

  Możliwy przeplot: transakcja decyzji komórki trzyma blokadę sekwencji S; równoległy import pobiera blokadę gry i czeka na S (`services/worker/src/game_predictor_worker/images/pipeline_store.py:413`); decyzja komórki próbuje następnie pobrać blokadę gry. Powstaje cykl oczekiwania, a PostgreSQL przerywa jedną transakcję. Taką samą przeciwną kolejność ma zapis geometrii (`services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:408`).

  Należy zapewnić pobieranie blokady gry przed blokadami sekwencji i wierszy we wszystkich ścieżkach mutacji, które mogą wywołać rozstrzygnięcie lub ponowne otwarcie planszy. Dodać test wymuszający opisany przeplot. Deklaracja, że mutacje symboli nie pobierają tej blokady, nie odpowiada rzeczywistemu łańcuchowi wywołań.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| B przejmuje odrzucone S, zachowuje osiem dobrych plansz A i zapisuje alternatywy | spełnione | Scenariusz i asercje: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:160`; ocena statyczna. |
| Slot A przechodzi do `superseded`, bramka jest przeliczana i dobre plansze materializowane | spełnione | `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:204`; ocena statyczna wariantu sekwencyjnego. |
| Ta sama checksuma zachowuje dotychczasową regułę | spełnione | Wariant `same-photo`: `services/api/tests/integration/test_image_batch_store.py:2961`. |
| Raport importu pokazuje zastąpione i pominięte sekwencje | spełnione | Test odpowiedzi HTTP w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:160`; UI: `apps/admin/src/features/imports/geometry-completeness-section.tsx:418`. |
| Naprawa współbieżności zachowuje poprawność istniejących zapisów | niespełnione | Odwrócenie kolejności blokad opisane w P0-5. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1** — Chroniony właściciel innego zdjęcia przechodzi przez ścieżkę zapisującą pominięcie. Dowód: `services/worker/src/game_predictor_worker/images/pipeline_store.py:461`; regresja: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:442`.
- **P0-2** — Przejęcie dopuszcza niepełną historię cropów i przywraca dostępność komórek. Dowód: `services/api/src/game_predictor_api/domain/image_symbol_reviews.py:853`, `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:3102`; regresja: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:524`.
- **P0-3** — Proweniencja zatwierdzenia zależy od tożsamości cropa. Dowód: `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2758`; regresja: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:577`.
- **P0-4** — Dwa przejęcia pobierają wspólną blokadę przed blokadami źródeł. Dowód: `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:408`, `services/worker/src/game_predictor_worker/images/pipeline_store.py:413`; regresja: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:653`.

Otwarte: **P0-5**.

## Proponowane testy

W `services/api/tests/integration/test_replacement_photo_takeover_postgres.py` dodać dwa scenariusze z niezależnymi sesjami PostgreSQL i kontrolowanym przeplotem:

- Oznaczenie komórki zatwierdzonej planszy jako `MARK_GRID_ISSUE` równolegle z importem obejmującym tę samą sekwencję.
- Zatwierdzenie ostatniej komórki planszy równolegle z zapisem geometrii albo importem.

Sprawdzić brak zakleszczenia oraz spójność decyzji komórek, właściciela sekwencji i liczników.

Komenda w środowisku testowym opisanym w tasku:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_replacement_photo_takeover_postgres.py services/api/tests/test_lateral_lock_order.py -q
```

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, zakres i poprawki taska, odpowiednie fragmenty planu, wymagań i architektury. Sprawdzono regułę własności, sprzątanie bramek, synchronizację komórek, zmiany migracji, kontrakt raportu, klienta, UI oraz testy. Prześledzono kolejność blokad importu, zapisu geometrii i mutacji symboli.

`git diff --check` zakończył się bez błędów. Nie uruchamiano testów, migracji ani usług. Wyniki testów w `Outcome` są deklaracjami wykonawcy; P0-5 wynika z analizy kodu i nie był odtwarzany na bazie.