# TASK-0365 — Atomowy start preflightu i importu browser stagingu

Status: done

## Cel

Usunąć blokadę tworzenia preflightu geometrii i importu dla gotowego browser
stagingu bez zmiany algorytmu geometrii, półautomatu ani kontraktu sekwencji.

## Zakres

- utworzenie source-bound joba i ustawienie retencji stagingu na `in_use` w
  jednej transakcji,
- zachowanie odświeżenia retencji dla odzyskanego, już zatwierdzonego joba,
- brak dodatkowego przycisku ustalania sekwencji; `seq_<start>-<end>` pozostaje
  automatycznym źródłem zakresu i oczekiwanej liczby plansz,
- brak zmian w silniku geometrii i w procesie półautomatycznym.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- nowy preflight i nowy import nie otwierają drugiej transakcji zapisującej FK
  do niezatwierdzonego joba,
- idempotentne odzyskanie joba nadal chroni staging,
- test endpointu blokuje regresję do przedwczesnego `mark_in_use`,
- test domenowy potwierdza wybór atomowej ścieżki repozytorium,
- oba wskazane stagingi przechodzą transakcyjny probe z rollbackiem.

## Outcome

- `JobService` kieruje joby z `source_selection_id` do atomowego zapisu.
- Repozytorium SQL zapisuje job i aktualizuje `browser_selection_retention_states`
  w tej samej sesji oraz transakcji.
- Endpointy startu importu i preflightu wywołują osobne `mark_in_use` wyłącznie
  przy odzyskaniu istniejącego joba.
- Testy skoncentrowane: `44 passed`; Ruff: bez błędów.
- Probe na stagingach `b167c5ea-27d7-4403-aa49-9444990fdad3` oraz
  `20123bda-a82d-40fd-a619-8c0a9231c86d` potwierdził atomowe przypięcie; obie
  transakcje zostały wycofane i nie zmieniły danych użytkownika.
