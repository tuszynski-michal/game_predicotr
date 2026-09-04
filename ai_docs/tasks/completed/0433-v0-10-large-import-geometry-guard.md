# TASK-0433: Ochrona dużych importów geometrii v0.10

Status: done

## Cel

Zatrzymać systemową regresję geometrii przed materializacją tysięcy elementów ręcznej korekty oraz rozdzielić w Adminie diagnostykę strony 3×3 od siatki symboli 3×5.

## Zakres

- Dla importu v0.10 od 100 źródeł lub 500 plansz wykonać deterministyczną próbę źródeł z początku, środka, końca i dostępnych bucketów geometrii.
- Uruchomić próbę tym samym produkcyjnym torem do końcowych 15 cropów.
- Wynik poniżej 98% zakończyć kodem `IMAGE_GEOMETRY_SYSTEMIC_REGRESSION` przed materializacją domenową i przed utworzeniem masowej kolejki pending.
- Przypiąć wynik ochronny i jego checksumę do joba/checkpointu tak, aby retry i restart nie zmieniały próby.
- Pokazać w Adminie źródło geometrii, checksumę/preflight, pokrycie, wersję profilu i silnika komórek oraz wynik ochronny.
- Rozdzielić liczniki strony 3×3 i siatki symboli 3×5 oraz doprecyzować nazwę kolejki.
- Zachować zasadę: korekta jednej planszy nie trenuje profilu; tylko jawnie zaakceptowane kompletne źródła 9-quad mogą wejść do kohorty profilu.

## Poza zakresem

- Operacje na danych gry `777`, utworzenie reprocessu albo cleanup historycznego joba.
- Obniżanie progów fixed v19.
- Automatyczne uczenie na ręcznych korektach pojedynczych plansz.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0431-v0-10-pinned-page-geometry-reprocess.md`
- `ai_docs/tasks/completed/0432-v0-10-grid-profile-end-to-end-gate.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- Duży import z wynikiem końcowej geometrii poniżej 98% kończy się przed masową materializacją stabilnym kodem błędu.
- Dobór próbki jest deterministyczny i obejmuje granice zakresu oraz dostępne buckety.
- Restart/retry odtwarza tę samą próbkę i wynik checksumy.
- Mały import zachowuje dotychczasowy przepływ.
- Admin pokazuje oddzielnie stronę 3×3 i wewnętrzną siatkę 3×5.
- Test regresyjny dowodzi, że słaby wynik nie tworzy kolejki manualnej.

## Outcome

- Dodano niezmienny raport `image-geometry-systemic-guard-v1` dla importów od
  100 źródeł lub 500 plansz. Deterministyczna próba do 25 źródeł obejmuje
  granice, środek, równomierne pozycje i dostępne buckety geometrii.
- Próba używa produkcyjnych adapterów do końcowych cropów 3×5 bez writera
  `board_cell_geometry_pending`. Wynik poniżej 98% albo naruszenie niezmiennika
  kończy się `IMAGE_GEOMETRY_SYSTEMIC_REGRESSION` przed `register_files`.
- Raport wiąże job, checksumę managed originals, checksumę manifestu strony,
  fingerprint pipeline'u i źródła próby. Checkpoint oraz każdy późniejszy
  checkpoint zachowują wynik dla retry, restartu i diagnostyki.
- Nowe browserowe importy i managed reprocessy przypinają snapshot polityki
  ochronnej oraz jego wpływ w fingerprint pipeline'u. Historyczne joby bez
  snapshotu zachowują wcześniejszy replay.
- Progress API udostępnia typowany wynik ochrony. Zaktualizowano OpenAPI i
  wygenerowany klient TypeScript.
- Admin przed startem pokazuje manifest/preflight, pokrycie, profil, silnik
  komórek i oczekiwany stan ochrony, a historia pokazuje rzeczywisty wynik 3×3
  i 3×5. Launcher Reviewera rozdziela liczniki obu domen i używa nazwy
  „Niepełne siatki symboli 3×5 do ręcznej korekty”.
- Zachowano istniejący hard gate profilu wymagający kompletnego źródła dziewięciu
  quadów; ręczna korekta jednej planszy nie uruchamia treningu.
- Weryfikacja: 83 skoncentrowane testy API/workera, dodatkowe 52 testy importu
  i kontraktu OpenAPI oraz 382 testy Admina przeszły. Przeszły również Ruff,
  format, typecheck Admina i klienta API, kontrola OpenAPI oraz produkcyjny build
  Admina. Skoncentrowany `mypy` nadal raportuje wyłącznie dwa wcześniejsze błędy
  poza zakresem w `schemas/image_reviews.py:328` i
  `storage/virtual_grid_geometry_repository.py:325`.
- Nie wykonano reprocessu, cleanupu ani innej operacji na danych gry `777`.
