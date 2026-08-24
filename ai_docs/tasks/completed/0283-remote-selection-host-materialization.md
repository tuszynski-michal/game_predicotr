---
title: TASK-0283 - Host action queue i atomowa materializacja
status: done
owner: Codex
version: 0.7
---

## Cel

Zaimplementować TASK 11 z planu zdalnej ręcznej selekcji: przekształcać
zweryfikowany host-internal JPEG w należący do partii plik `seq_*`, zachowując
spójność bazy, filesystemu i journalu po crashu w dowolnym trwałym punkcie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (TASK 11 i R-001/R-003/R-005)
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0282-remote-selection-streaming-transfer.md`

## Zakres

- trwałe enqueue host action po zweryfikowaniu uploadu;
- claim z PostgreSQL lease, `SKIP LOCKED`, bounded retry i backoff;
- ponowne sprawdzenie bieżącej generacji, decyzji `SELECT` i checksummy;
- host-internal journal, same-volume temp, flush i atomowa publikacja `seq_*`;
- wyłączne ownership celu bez nadpisywania obcego lub zmienionego pliku;
- atomowe przejście transferu i pliku do `materialized`/`synced` po zgodności
  finalnego pliku;
- reconciliacja kolejki, wygasłego lease oraz crash windows;
- testy jednostkowe, PostgreSQL, fault injection, bezpieczeństwa i restartu.

## Poza zakresem

- `DESELECT`, usuwanie, kwarantanna i GC;
- finalizacja całej partii oraz output/trace v1;
- ciężki job domenowy i nowa kolejka Redis/Celery;
- pełny workspace zdalnej selekcji.

## Invarianty

- `synced` wymaga finalnego pliku o zgodnej checksumie i bieżącej generacji;
- stara generacja nie może zostać opublikowana;
- istniejący cel bez zgodnego journalu ownership nigdy nie jest nadpisywany;
- retry i dwaj executorzy prowadzą do jednego wyniku albo kontrolowanego konfliktu;
- crash nie powoduje false success ani utraty verified temp;
- ścieżki publiczne nie ujawniają host base path;
- końcowy plik nie jest finalnym manifestem partii — finalizacja pozostaje TASK 15.

## Kryteria odbioru

- każdy z fault points przed/po temp, journal, rename i commit jest odzyskiwalny;
- dwa claimery nie wykonują tej samej aktywnej akcji;
- poprawny retry/adopcja kończy się jednym `seq_*` i zgodnym `synced`;
- foreign target, zmieniony own target, reparse i stale generation są blokowane;
- testy API/repozytorium, PostgreSQL, Ruff/mypy i testy hosta przechodzą;
- dokumentacja stanu i bezpieczeństwa opisuje faktycznie wdrożone zachowanie.

## Outcome

- Verified upload i status enqueue'ują idempotentną akcję `materialize`, a
  bounded reconciliation general workera odtwarza brakujące akcje po restarcie.
- PostgreSQL claim używa `SKIP LOCKED`, lease/fencing, backoff i odzyskanie
  wygasłego `processing`; terminalna porażka nie resetuje automatycznie prób.
- Host materializer ponownie sprawdza generację i checksumę, używa przypiętych
  ścieżek, same-volume working file, `fsync`, checksumowanego journalu oraz
  wyłącznej publikacji. Finalny DB `synced` powstaje dopiero po zgodności celu.
- Fault suite obejmuje pięć granic filesystemu, retry/adopcję, foreign i changed
  target, stale generation, fencing, status/startup reconciliation oraz 100
  plików. PostgreSQL potwierdził exactly-one claim dwóch executorów i atomowy
  commit projekcji.
- Zmienione moduły przeszły Ruff i testy; Reviewer ma publiczny status `synced`
  bez ścieżki. Bramka dała 131 testów API, 14 testów lifecycle workera, 92
  testy Reviewera i test dwóch claimerów PostgreSQL. Pełny mypy z dependency
  graph dwukrotnie przekroczył 60-sekundowy limit bez wyniku; po naprawie
  wykrytego zawężenia lease tokenu izolowana kontrola 9 zmienionych modułów
  zakończyła się bez błędów. Pełny Ruff nadal wskazuje wcześniejsze pliki
  `0045/0046` i test symboli; wszystkie zmienione pliki są czyste.
- Nie wdrożono deselect/remove ani finalizacji partii. Obowiązuje checkpoint
  właściciela przed TASK 12.
