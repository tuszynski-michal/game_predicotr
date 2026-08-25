---
title: TASK-0289 — Bramka bezpieczeństwa zdalnej selekcji
status: done
last_updated: 2026-08-24
---

# TASK-0289 — Bramka bezpieczeństwa zdalnej selekcji

## Status

`done`

## Goal

Udowodnić przed rolloutem, że publiczny scope zdalnej ręcznej selekcji nie
rozszerza dostępu do Admina, Reviewera, innych sesji ani dowolnych ścieżek hosta.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- kompletna macierz route/method deny dla publicznego proxy,
- rate limit i quota operacji oraz bajtów,
- testy izolacji tokenów, cookies, originu, sesji i scope'u,
- corpus ścieżek Windows i harness reparse/TOCTOU,
- wspólna walidacja redakcji audit payloadów,
- formalny, content-addressed raport bramki bez otwartych findingów critical/high.

## Out of scope

- publiczny test przez prawdziwy Quick Tunnel,
- pentest strony trzeciej,
- zmiana globalnej polityki autoryzacji istniejącego Reviewera,
- rollout i benchmark skali należące do TASK 18.

## Acceptance criteria

- [x] Publiczna allowlista jest zamknięta i ma kompletną macierz negatywną.
- [x] Stabilne błędy 401/403/409/413/429 są pokryte testami.
- [x] Rotacja klienta nie resetuje budżetu sesji, a quota bajtów jest fail-closed.
- [x] Token/cookie/origin/revoke/replay i cross-session są sprawdzone negatywnie.
- [x] Corpus Windows, reparse, TOCTOU i obcy plik nie pozwalają wyjść poza scope.
- [x] Logi i audyt odrzucają sekrety oraz absolutne ścieżki na dowolnej głębokości.
- [x] Raport bramki nie ma otwartego findingu critical/high.

## Outcome

Publiczny proxy ma zamkniętą macierz route/method zgodną z OpenAPI, obowiązkowe
same-origin fetch metadata dla mutacji i nie ufa nagłówkom forwarded. UUID-y
klienta/transferu, publiczne odpowiedzi oraz audit payloady są walidowane
fail-closed. Dokładny replay zużywa sesyjny budżet operacji bez utraty
idempotencji.

Raport `ai_docs/quality/remote-manual-selection-security-gate-v1.json` przeszedł
weryfikację z checksumą
`8386c3676422ecb3d98994c854bb7c447f5c5452592990485f7bd9af3e4b4360` i nie ma
otwartego findingu `critical`/`high`.

Weryfikacja:

- Reviewer: `106 passed`; lint i typecheck bez błędów, build produkcyjny zielony
  (pozostaje wcześniejsze ostrzeżenie ESLint `no-img-element`),
- API/filesystem security suites: `183 passed, 1 skipped`; skip dotyczy braku
  uprawnienia Windows do utworzenia symlinka,
- PostgreSQL: `5 passed, 12 deselected` dla cross-scope FK, append-only audit,
  restart/revoke, równoległej rotacji unlock i transfer roundtrip,
- raport security: `11 passed`; jego samodzielny weryfikator, Ruff zmienionych
  plików, Prettier i kontrola OpenAPI są zielone,
- selektywny mypy jest zablokowany wcześniejszym problemem konfiguracji pełnego
  grafu API: brak `py.typed` pakietu workera powoduje 31 błędów poza zmienionymi
  modułami. Nie osłabiono konfiguracji ani testów w ramach TASK-0289.

Nie wykonano publicznego testu Quick Tunnel, pentestu strony trzeciej ani
rolloutu/benchmarku TASK 18. Wymagany checkpoint przed TASK 18 pozostaje jawny.
