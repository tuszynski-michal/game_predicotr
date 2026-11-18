# TASK-1255 — Zastosowanie i cofnięcie prywatnego modelu siatek

## Status

`done`

## Goal

Jawnie potwierdzone zastosowanie zaliczonego kandydata przełącza wyłącznie
prywatną grę. Cofnięcie wybiera dopuszczoną wersję z jej historii przypisań.

## Dependencies / entry conditions

- TASK-1253 dostarcza flagę prywatności i trwałą własność rodziny.
- TASK-1254 pinuje grę, rewizję przypisania, rodzinę, bazę i jej manifest.
- Uzgodniona decyzja wykonawcza: dla prywatnej gry publikacja i przypisanie
  mają oddzielne potwierdzenia zapisane w jednej transakcji. Prywatną wersję
  publikuje i aktywuje wyłącznie zweryfikowany przebieg zastosowania.

## Recommended execution

`gpt-6.2-sol / high`. Współbieżne polecenia i odtwarzanie zapisanych
potwierdzeń wymagają testów transakcyjnych. Audyt integracyjny
`claude-opus-5-5 / high` przed integracją.

## Relevant docs

- [Zaakceptowany plan, zadanie 3](../../delivery/PRIVATE_GAME_GRID_MODELS_PLAN_20261118.md#3-zastosowanie-i-cofnięcie)
- [Wymagania Admina](../../requirements/ADMIN_APP.md)
- [Kontrakt API](../../architecture/API_CONTRACT.md)
- [Model danych](../../architecture/DATA_MODEL.md)

## Scope

- Podgląd, start, worker i wznowienie zastosowania w prywatnej grze.
- Bramki rejestru i cofnięcie, z zachowaniem własności rodziny.
- Potwierdzenie zakresu i historia w Adminie.
- Weryfikacja odtworzenia potwierdzeń, ochrony starszych importów, wyścigu
  poleceń i zgodności starszego klienta.

## Out of scope

- Migracja lub operacje na bazie operatora, trening GPU, wdrożenie i merge.
- Diagnostyka lub pilot Mumii A2.

## Acceptance criteria

- [x] Prywatny kandydat trafia tylko do gry właściciela, po jawnym potwierdzeniu.
- [x] Wspólna wersja domyślna i przypisanie drugiej gry są niezależne.
- [x] Zmiana rewizji blokuje nieaktualny zamiar przed zapisem, retry odzyskuje
  potwierdzenia po utracie odpowiedzi i restarcie.
- [x] Cofnięcie wymaga dopuszczalnej wersji z historii gry i zgodnej rewizji.
- [x] Nowy import odczytuje bieżące przypisanie, a stary zachowuje preflight.
- [x] HTTP, Admin, migracja na izolowanym PostgreSQL i klient legacy sprawdzone.

## Expected files

- API: `application/grid_correction_apply.py`, `application/grid_model_publication.py`,
  `application/grid_model_registry.py`, `api/grid_correction_apply.py`,
  `schemas/grid_correction_apply.py` i `schemas/grid_model_registry.py`.
- Admin: panele zastosowania, wersji i historii modeli w `features/model-quality/`.
- Testy API i PostgreSQL oraz test interakcji Admina.

## Outcome

Commit: v1.7.682 / `dbd0d686f4225123192462d7d17c202e4e1ec193`.

### Changed

- Podgląd przypina zakres, przypisanie gry i niezmienny dowód oceny.
  Prywatne zastosowanie publikuje i przypisuje w jednej transakcji.
- Rejestr ogranicza prywatne wersje do właścicieli. Cofnięcie korzysta z
  dopuszczonego wpisu historii gry i sprawdza rewizję. Wspólna baza użyta
  wcześniej przez tę grę może wrócić jako jej przypisanie.
- Admin pokazuje zakres prywatny i wiąże potwierdzenie cofnięcia z rewizją
  widoczną przy wyborze wcześniejszej wersji.
- Po przeglądzie P1 sprawdzenie wspólnego zastosowania obejmuje cele, gry
  treningowe i wszystkie ocenione kohorty. Odczytuje flagi publicznego
  katalogu w jednym zapytaniu. Odmowa z bazy i wykrycie konfliktu przed
  zapisem zwracają kod `GRID_APPLY_SHARED_PRIVATE_GAME`.
- Po przeglądzie P2 wyjątek dla wspólnej bazy wymaga wpisu bootstrap lub
  zapisu włączenia prywatności tej wersji z potwierdzonym dowodem. Zwykły
  wpis historii podlega ocenie właściwej dla gry.
- Funkcja SQL w migracji 0193 uwzględnia gry widoczne wyłącznie w kohortach
  oceny. Blokada aktywnych operacji i przyjęcie nowego lub wznawianego joba
  korzystają z tego samego pełnego zakresu.

### Verification results

- Po poprawkach logika zastosowania, HTTP i rejestr 71 testów PASS. Obsługa
  workera 8 testów PASS.
- Panel Admina 69 interakcji, test wysyłanej komendy klienta i TypeScript PASS.
- Ruff, ukierunkowany lint Admina i `docs:check` PASS.
- Ukierunkowany mypy dla dziewięciu modułów PASS. Objął rzeczywiste
  repozytorium SQLAlchemy, mapowania ORM, bazę deklaratywną i typy
  SQLAlchemy. Pozostałe importy zostały ograniczone do zakresu.
- PostgreSQL 55493, osobna baza `_test`, migracja do head i scenariusz
  `test_private_http_apply_twice_then_rollback_without_switching_another_game`
  PASS po poprawkach (71,88 s). Dwie gry, dwa zapisane przebiegi z kontrolowanym wynikiem
  oceny, porównanie rewizji, rywalizujące polecenia, przerwanie transakcji,
  wznowienie, odzyskanie potwierdzeń w nowym procesie i rollback. Drugi
  pozytywny raport zawiera kalibrację v5. Raport produkcyjny v6 z bazą
  niedopuszczoną przez jego bramkę zatrzymał zastosowanie przed publikacją.
- W izolowanym klastrze scenariusz wspólnego zastosowania z grą treningową
  PASS (58,51 s). Po wspólnym treningu A i B włączono prywatność A. Podgląd,
  start, wznowienie i worker B odrzuciły zastosowanie również bez wyboru A
  jako celu. Wymuszony sygnał PostgreSQL przy starcie i wznowieniu dał taki
  sam kod HTTP 409. Publikacja i zmiana modelu domyślnego nie nastąpiły.
- Celowany wariant `test_shared_apply_refuses_a_private_peer_through_http_and_database[cohort]`
  PASS (59,35 s) na nowym izolowanym PostgreSQL 55493 po poprawce P2-3.
  Funkcja SQL zwróciła grę A występującą wyłącznie w kohorcie. Aktywny
  apply B zablokował włączenie prywatności A. Po przerwaniu apply i
  włączeniu prywatności wyzwalacz odmówił ponownego startu i wznowienia.
- Test cofnięcia potwierdził odmowę dla zwykłego wpisu historii bez oceny
  tej gry oraz zgodę dla rzeczywistego wpisu włączenia prywatności.

### Review

- Zbiorczy przegląd Opus 5.5, runda 2, PASS i 0 P0/P1. P1-1, P2-1 oraz
  P2-2 zamknięto. Potwierdzenie dotyczy pakietu
  `a6cfdff06cb652b7195faa8330388ba0d1c099b03da168dee3e45dd57ecde4fe`.
  Poprawkę P2-3 dodano po tym przeglądzie i sprawdzono w osobnym PostgreSQL.
  Przegląd statyczny zakończono po rundzie 2.
  [Raport](../../quality/TASK-1255_AUDIT_claude-opus-5-5.md) i
  [potwierdzenie audytu](../../quality/TASK-1255_AUDIT_claude-opus-5-5.receipt.json).

### Not completed
- Mypy z importami zależności przekroczył limit. Weryfikacja backendu
  opiera się na lint i testach wykonawczych powyżej.
- Trening modeli na GPU i operacje na bazie operatora wymagają osobnych poleceń.

### Documentation updates

- Zaktualizowano kontrakt API oraz wymagania Admina.
