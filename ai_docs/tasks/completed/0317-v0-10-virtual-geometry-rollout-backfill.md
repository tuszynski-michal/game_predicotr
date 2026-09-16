---
title: TASK-0317 — bezpieczny rollout i backfill wirtualnej geometrii
status: done
version: 0.10.9
last_updated: 2026-08-29
---

# Cel

Domknąć bezpieczne przejście z fundamentu `virtual_source` do operacyjnego
rolloutu: dodać bounded, wznawialną walidację danych gry oraz umożliwić ręczny
zapis poprawionej geometrii wirtualnej bez materializowania board/cell PNG.

# Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md` — D-254–D-260
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0312-v0-10-virtual-geometry-pipeline-integration.md`
- `ai_docs/tasks/completed/0314-v0-10-geometry-verification-workspace.md`

# Zakres

- trwały, idempotentny job walidacji rolloutu jednej gry w general lane;
- bounded skan źródeł i bieżących właścicieli z checkpointem po source image ID;
- jawny status `not_started/processing/ready/failed` i kontrolowane wznowienie;
- walidacja kompletnej source geometry oraz proweniencji `virtual_source` bez
  automatycznej konwersji rekordów legacy;
- ręczny preview i zapis `virtual_source` przez source-direct renderer;
- append-only source geometry oraz board geometry revision bez board/cell PNG;
- zachowanie etykiet człowieka i unieważnienie proweniencji nowego cropa do
  czasu jego ponownego zatwierdzenia;
- odblokowanie zapisu w lokalnym workspace Reviewera po gotowym rolloutcie;
- OpenAPI, wygenerowany klient, testy i dokumentacja.

# Poza zakresem

- automatyczna promocja trybu gry;
- przepisywanie historycznych `legacy_file` na `virtual_source`;
- usuwanie historycznych cropów;
- zmiana algorytmu Structured OpenCV lub modelu symboli;
- zdalne udostępnienie nowych endpointów.

# Invarianty

- decyzja człowieka i canonical owner zawsze wygrywają;
- manualny zapis virtual nie tworzy trwałych bitmap;
- każda rewizja obejmuje pełny attested prefiks slotów jednego źródła;
- retry identycznej komendy i joba nie tworzy duplikatów;
- `ready` nie zmienia `geometry_mode` ani `cell_asset_mode`;
- źródło, topologia, rewizje i checksumy są sprawdzane pod blokadą przed zapisem;
- legacy Reviewer zachowuje dotychczasowe zachowanie.

# Kryteria odbioru

- job można przerwać i wznowić od ostatniego source image ID;
- drugi start aktywnego joba zwraca ten sam job;
- niekompletna proweniencja kończy się kontrolowanym `failed` z identyfikatorem
  problematycznego źródła;
- dziesięć i sto źródeł przechodzi ten sam bounded mechanizm bez duplikatów;
- ręczna korekta virtual zapisuje source/board/cell provenance bez PNG;
- konflikt rewizji/checksummy jest fail-closed;
- tryb legacy i fingerprint historyczny pozostają bez zmian.

# Outcome

- Dodano trwały `image_geometry_rollout_backfill` w general lane, status/start
  API i checkpoint po ostatnim źródle. Ponowny start aktywnej operacji zwraca
  ten sam job, a nowy job po kontrolowanej awarii korzysta z trwałego kursora.
- Walidacja skanuje najwyżej 100 źródeł na transakcję, sprawdza source geometry,
  obserwacje, bieżące komórki i ręczne rewizje virtual. Legacy pozostaje
  niezmienione. Kontrolowany błąd zapisuje kod oraz identyfikator źródła.
- Po stanie `ready` lokalny Reviewer wykonuje preview i ręczny zapis
  `virtual_source` bez trwałych board/cell PNG. Zapis tworzy append-only source
  i board geometry revision, aktualizuje bieżące checksum-bound render specy,
  zachowuje etykiety człowieka i pozostawia nowy crop poza treningiem do czasu
  ponownego zatwierdzenia.
- Odtworzenie bieżącej projekcji właściciela podczas walidacji umożliwia pracę
  także bez historycznego board PNG. Zdalna powierzchnia Reviewera nie została
  rozszerzona.
- Backend/OpenAPI pozostaje źródłem kontraktu; klient Admina został
  zregenerowany, a Admin pokazuje czytelną nazwę nowego typu joba.

## Weryfikacja

- Ruff zmienionych modułów i testów: pass.
- Testy API/domeny/workera rolloutu i geometrii: `14 passed`.
- Testy domeny i API jobów: `38 passed`.
- Testy kontraktu workspace'u geometrii Reviewera: `10 passed`.
- TypeScript typecheck Admina i Reviewera: pass.
- ESLint Admina i Reviewera: pass.
- OpenAPI i wygenerowany klient: pass.
- Produkcyjne buildy Admina i Reviewera: pass.
- Pełny Python mypy nadal raportuje istniejące, niezwiązane błędy m.in. w
  `virtual_cell_previews.py`, `image_imports.py` i `image_job_repository.py`;
  żaden raportowany błąd nie wskazuje modułu dodanego przez TASK-0317.
- Pełny zestaw Reviewera ma jeden istniejący, niezwiązany błąd regresji
  zdalnej ręcznej selekcji malejącej; testy nowego workflow geometrii przechodzą.

Nie uruchamiano operacyjnego backfillu na danych użytkownika, nie zmieniano
trybu rolloutu gry i nie rozpoczęto TASK-0318.
