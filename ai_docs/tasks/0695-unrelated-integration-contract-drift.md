---
title: TASK-0695 — dryf kontraktów testów integracyjnych
status: todo
last_updated: 2026-09-26
---

# TASK-0695 — dryf kontraktów testów integracyjnych

## Status

`todo`

## Goal

Rozstrzygnąć niezwiązane z usunięciem legacy rozjazdy między testami a
bieżącym zachowaniem API i domeny, bez automatycznego osłabienia asercji.

## Context

Po naprawie V2 fixture raport importu zwraca
`LAYOUT_IMPORT_EXPECTED_COUNT_MISMATCH`, a test oczekuje
`LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION`. Test M2 Admin HTTP wysyła pola
`mobileCode`, `code`, `imagePath`, `displayOrder`, `status` do symbol endpointu
i dostaje 422 `extra_forbidden` zamiast oczekiwanego 201.

Dodatkowe znalezisko konfiguracji jakości: `pyproject.toml` ustawia
`mypy_path = "services/api/src;services/worker/src"`, lecz parser konfiguracji
mypy 1.17.1 rozdziela ścieżki przecinkiem lub dwukropkiem. Średnik jest
obsługiwany w Windows dla zmiennej środowiskowej `MYPYPATH`. Skutkiem jest
41 błędów importów przy kontroli trzech testów, także we właściwym `.venv`.
Naprawić konfigurację trwale i sprawdzić z nowego procesu; nie reinstalować
Pythona na podstawie błędu startu w sandboxie.

### Grupowanie dodatkowych znalezisk

- Kontrakty fixture: `test_parallel_review_decisions_persist_one_canonical_owner_and_supersede_loser`
  tworzy dwóch pending właścicieli jednej sekwencji, co narusza constraint
  z 0069. Zachowano czerwony test; nie zmieniać statusu na rejected tylko
  dla zielonego wyniku, ponieważ zmieniłoby to semantykę rewizji/eventów.
- Kontrakt joba (P2, niezależny audit): `image_geometry_rollout_backfill_repository.py`
  emituje schemaVersion=3, ale `domain/jobs.py::create_job` nie dopuszcza tej
  wersji dla IMAGE_GEOMETRY_ROLLOUT_BACKFILL. Rzeczywisty endpoint zwraca422.
  Sprawdzić handler i dodać regresję schema3; nie obniżać payload do schema1.
- Typy/konfiguracja: poza separatorem mypy, image-batch ma8 zastanych
  błędów typów (Sequence concat, zmienne Optional/object, reuse modelu),
  a release workflow6 (`Path / Optional[str]` i nietrafione ignore).
  Nie wyciszać ich szerokim ignore ani przypisywać automatycznie migracji0125.

## Dependencies / entry conditions

Ustalić obowiązujący kontrakt z wymagań i OpenAPI, potem zdecydować, czy
poprawy wymaga test, czy produkcja.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning
`medium`. Rozbieżność produktowa wymaga decyzji przed zmianą API.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`

## Scope

- Zweryfikować i naprawić rozbieżności, każdą z regresją zgodną z
  właścicielskim kontraktem.
- Poprawić konfigurację wyszukiwania modułów mypy bez ignorowania błędów typów.

## Out of scope

Migracja 0125 i przebudowa fixture V2 z TASK-0694.

## Acceptance criteria

- [ ] Oba scenariusze przechodzą na izolowanej bazie po 0125.
- [ ] Dodatkowe grupy mają własne regresje i zapis rozstrzygnięcia kontraktu.
- [ ] Jeżeli zmieni się API, backend, OpenAPI, wygenerowany klient i test
      żądania pozostają jednym spójnym pionem.

## Outcome

Wypełnia agent po pracy.
