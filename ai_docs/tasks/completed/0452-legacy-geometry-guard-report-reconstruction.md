---
title: Legacy geometry guard report reconstruction
status: done
version: v0.10.163
---

# Cel

Udostępnić bezpieczną, audytową rekonstrukcję board-level raportu v2 dla
historycznego failed importu z raportem v1, aby kolejka decyzji mogła wskazać
dokładne sloty bez mutowania źródłowego joba.

# Zakres

- osobny job walidacyjny związany z grą, stagingiem, źródłowym guard jobem i
  checksumą raportu v1,
- ponowne wykonanie wyłącznie przypiętej próbki na snapshotach źródłowego joba,
- content-addressed raport v2 oraz immutable descriptor rekonstrukcji,
- odczyt pochodnego raportu przez istniejącą kolejkę decyzji,
- retry i utrata odpowiedzi bez tworzenia rozbieżnych raportów,
- testy driftu źródła, raportu, manifestów i niezmienności failed joba.

# Poza zakresem

- UI wyboru full/partial/rejected,
- automatyczne decyzje dla ośmiu plansz,
- wznowienie importu `86128f3c…`,
- zmiana progu 98% albo snapshotów źródłowego joba.

# Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md` (D-339, D-341)
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0449-board-level-large-import-guard-report.md`
- `ai_docs/tasks/completed/0450-pre-import-geometry-guard-decisions.md`

# Definition of Done

- źródłowy raport v1 i failed job pozostają bajtowo oraz domenowo niezmienione,
- rekonstrukcja używa dokładnej listy checksum i snapshotów źródłowego joba,
- wynik v2 jest content-addressed, immutable i ma jawne pochodzenie od v1,
- kolejka akceptuje wyłącznie zgodny zakończony wynik rekonstrukcji,
- ponowienie identycznego polecenia zwraca ten sam job/artefakt,
- skoncentrowane testy, Ruff, OpenAPI oraz typecheck Admina są zielone,
- dokumentacja i `CURRENT_STATE.md` opisują wynik.

# Outcome

- Dodano osobny job `validate` dla rekonstrukcji historycznego raportu bramki
  v1. Jego wejście jest związane ze źródłowym failed importem, stagingiem oraz
  checksumami raportu i obu manifestów.
- Handler ładuje managed-original manifest wyłącznie w trybie read-only,
  odtwarza historyczne snapshoty źródłowego joba i wykonuje dokładnie listę
  `selectedSourceChecksums`. Nie mutuje failed joba ani jego raportu.
- Raport v2 jest zapisywany content-addressed i zawiera checksumę poprzednika.
  Kolejka decyzji używa wyłącznie zakończonej, zgodnej rekonstrukcji i ponownie
  weryfikuje artefakt oraz proweniencję.
- Naprawiono rozróżnienie checksumy browser stagingu od checksumy pochodnego
  managed manifestu przy ładowaniu manifestu decyzji schema v7.
- Weryfikacja: 136 skoncentrowanych testów API/workera, Ruff, OpenAPI check oraz
  typecheck klienta i Admina zakończyły się sukcesem. Python mypy został
  ponownie przerwany po 60 sekundach bez wyniku, zgodnie z limitem procesu.
- Nie uruchomiono rekonstrukcji dla `86128f3c…`, nie zapisano decyzji operatora
  i nie utworzono nowego importu.
