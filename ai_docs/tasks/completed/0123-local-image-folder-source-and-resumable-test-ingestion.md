---
title: TASK-0123 Local image folder source and resumable test ingestion
status: done
last_updated: 2026-07-31
---

# TASK-0123 — Local image folder source and resumable test ingestion

## Status

`done`

## Goal

Dostarczyć pierwszy produkcyjny pion importu zdjęć wersji 0.2: administrator
wybiera lokalny folder natywnym dialogiem Windows, backend waliduje źródło,
worker kopiuje oryginały do kontrolowanego content-addressed storage i zapisuje
deterministyczny manifest, a przerwany import można bezpiecznie wznowić.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` — D-105 i D-111
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kontrolowany, loopback-only dialog wyboru folderu Windows,
- walidacja istnienia, dostępu i obecności obsługiwanych obrazów,
- typowany kontrakt utworzenia joba `image_directory` bez przyjmowania
  dowolnej ścieżki wpisanej w przeglądarce,
- deterministyczny discovery manifest z checksumami i pochodzeniem,
- content-addressed kopia każdego unikalnego oryginału w `data/originals`,
- idempotentne wznowienie po częściowym skopiowaniu plików lub zapisie manifestu,
- podstawowy workflow `Wybierz folder` / `Rozpocznij import` w sekcji gry,
- testy API, workera, kontraktu klienta i Admina.

## Out of scope

- kompletność `expected_layout_count`, brakujące numery i wybór najlepszego
  źródła sekwencji — TASK-0124,
- bootstrap katalogu symboli — TASK-0125,
- masowy import 500 000 rzeczywistych layoutów,
- publiczny lub reviewerowy dostęp do dialogu folderu,
- Excel, CSV i JSONL w podstawowym workflow Admina 0.2,
- automatyczne uruchamianie kolejnego procesu workera z requestu HTTP.

## Assumptions

- dialog działa tylko na lokalnym Windows; testy innych systemów używają
  wstrzykiwanego adaptera,
- wybór jest krótkotrwałym, jednorazowym capability tokenem przechowywanym
  wyłącznie w procesie API; frontend nie tworzy ani nie modyfikuje ścieżki,
- dialog jest uruchamiany jako kontrolowany proces z jawnym timeoutem, a jego
  wynik jest walidowany ponownie bezpośrednio przed utworzeniem joba,
- pipeline fingerprint pochodzi z wersjonowanego manifestu pipeline, nie z UI,
- fizyczny blob może być współdzielony przez identyczne bajty, natomiast manifest
  joba zachowuje własną względną ścieżkę źródłową.

## Acceptance criteria

- [x] przycisk `Wybierz folder` otwiera standardowy dialog Windows,
- [x] anulowanie dialogu nie tworzy joba i nie jest błędem domenowym,
- [x] niedostępny/pusty folder jest odrzucany stabilnym kodem,
- [x] frontend nie może przesłać arbitralnej ścieżki systemowej,
- [x] poprawny wybór tworzy typowany job `image_directory`,
- [x] worker zapisuje deterministyczny manifest i kopiuje oryginały do
  `data/originals/<sha256-prefix>/<sha256>.jpg`,
- [x] identyczne bajty nie tworzą drugiego fizycznego bloba,
- [x] ponowienie po częściowym wykonaniu nie dubluje wpisów manifestu ani plików,
- [x] dalsze przetwarzanie może używać zarządzanych kopii, a nie pierwotnego
  folderu,
- [x] testy, lint, ograniczona kontrola typów i build zmienionych części
  przechodzą.

## Verification

- `pytest` — 16/16 testów API, kontraktu jobów i source ingestion,
- Admin — 99/99 testów, ESLint, TypeScript i produkcyjny build Next.js,
- Admin API client — aktualny OpenAPI, 19/19 testów i TypeScript,
- Ruff — bez błędów w API, workerze i nowych testach,
- mypy — bez błędów w siedmiu zmienionych modułach przy bounded
  `--follow-imports=skip`; pełny graf został dwukrotnie zatrzymany po 60
  sekundach bez wyniku zgodnie z regułą timeoutów,
- parser PowerShell — poprawna składnia natywnego helpera.

## Outcome

- Admin ma nowy podstawowy panel folderowego importu zdjęć z wyborem,
  preflightem, utworzeniem joba i podglądem ostatnich statusów gry.
- Dwa nowe typowane endpointy nie przyjmują ścieżki od przeglądarki. Jednorazowy
  token zatwierdzonego folderu wygasa po 15 minutach i jest konsumowany po
  utworzeniu joba.
- Worker `worker-v5` rozdziela import pliku layoutów od importu zdjęć. Dla zdjęć
  zapisuje niezmienny manifest z pochodzeniem i kopiuje unikalne JPEG-i
  atomowo do content-addressed `data/originals`.
- Checkpoint zapisuje checksumę manifestu i liczbę zarządzanych oryginałów.
  Wznowienie weryfikuje istniejące bloby; test potwierdził ponowienie także po
  usunięciu folderu źródłowego po zakończonej kopii.
- Natywnego dialogu nie otwierano interaktywnie podczas automatycznej
  weryfikacji, aby nie blokować sesji. Jego stały skrypt przeszedł kontrolę
  składni, a anulowanie/wybór są pokryte testowanym adapterem API.
