---
title: Restore sealed geometry guard state
status: done
version: v0.10.210
---

# Cel

Po ponownym otwarciu raportu odtworzyć trwały, aktualny manifest rozliczeń
problematycznych plansz oraz przypięty preflight geometrii, aby operator mógł
jawnie uruchomić nowy import bez ponownego rozliczania tych samych plansz.

# Zakres

- kolejka rozliczeń zwraca aktualny zapieczętowany manifest tylko wtedy, gdy
  dokładnie odpowiada najnowszym decyzjom,
- kolejka zwraca także przypięty job preflightu geometrii strony,
- Admin odtwarza oba trwałe warunki po `Pokaż raport`, reloadzie i ponownym
  otwarciu stagingu,
- zmiana którejkolwiek decyzji unieważnia wcześniejszy manifest,
- przycisk startu pozostaje zablokowany przy niepełnym albo niezgodnym stanie.

# Poza zakresem

- automatyczne uruchomienie importu,
- zmiana decyzji operatora, failed joba, stagingu lub plików użytkownika,
- migracja bazy danych,
- zmiana detektora, croppera albo progów geometrii.

# Relevant docs

- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0493-multi-board-geometry-guard-editing.md`
- `ai_docs/tasks/completed/0494-streamline-geometry-guard-editor.md`

# Testy

- kolejka przed sealem nie zwraca manifestu,
- kolejka po seal zwraca dokładny manifest i przypięty preflight,
- nowa rewizja decyzji unieważnia manifest do czasu ponownego seal,
- odpowiedź HTTP udostępnia oba elementy trwałego kontekstu,
- Admin odtwarza stan po ponownym pobraniu raportu i nie opiera gotowości na
  stanie wyłącznie pamięciowym.

# Definition of Done

- odświeżenie raportu nie cofa napisu `manifest gotowy`,
- przy kompletnym, zgodnym manifeście oraz ukończonym preflighcie przycisk
  `Rozpocznij nowy import z rozliczeniami` jest aktywny,
- zmieniony lub niepełny stan nadal blokuje start fail-closed,
- API, OpenAPI, wygenerowany klient i Admin mają jeden spójny kontrakt,
- testy zmienionego pionu, lint, typecheck i build są zielone,
- dokumentacja opisuje trwałe odtwarzanie stanu.

# Outcome

- Kolejka rozliczeń wylicza checksumę z najnowszych rewizji i odtwarza tylko
  dokładnie odpowiadający jej, istniejący manifest. Nowsza decyzja natychmiast
  powoduje brak aktualnego manifestu aż do kolejnego jawnego seal.
- Descriptor geometrii failed importu odtwarza przypięty job preflightu.
  Odpowiedź API zwraca `currentResolutionManifest` oraz
  `pageGeometryPreflightJob`, bez uruchamiania nowych obliczeń.
- Admin synchronizuje oba trwałe elementy po pobraniu kolejki. Ponowne
  `Pokaż raport` tego samego stagingu nie zeruje zgodnego kontekstu, a pełny
  reload odbudowuje go z API.
- Wspólna czysta funkcja warunków startu jest używana przez handler i stan
  `disabled`, dzięki czemu oba miejsca nie mogą się rozjechać.
- Nie uruchomiono importu, nie zmieniono danych użytkownika i nie wykonano
  migracji.

## Weryfikacja

- testy API zmienionego pionu: 43/43,
- pełne testy Admina: 420/420,
- testy skoncentrowane odtwarzania stanu: 15/15,
- Ruff i skoncentrowany mypy domeny: bez błędów,
- typecheck Admina i klienta API: bez błędów,
- lint Admina: bez błędów,
- kontrola OpenAPI i wygenerowanego klienta: bez różnic,
- produkcyjny build Admina: zakończony poprawnie,
- Prettier i Ruff format dla zmienionych plików: bez różnic.

Pełny/transytywny mypy nadal wskazuje wcześniejsze problemy niezwiązane z tym
taskiem: brak markerów `py.typed` pakietu workera oraz istniejące błędy m.in. w
`jobs.py`, `image_reviews.py` i dalszej części `image_imports.py`. Zmieniony
moduł domenowy przeszedł osobny odczyt mypy.
