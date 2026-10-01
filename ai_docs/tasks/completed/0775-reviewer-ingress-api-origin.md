---
title: TASK-0775 — Reviewer uruchamiany przez kontroler tunelu łączy się z API, które go uruchomiło
status: done
last_updated: 2026-09-30
---

# TASK-0775 — Reviewer uruchamiany przez kontroler tunelu łączy się z API, które go uruchomiło

## Status

`done`

## Goal

Produkcyjny Reviewer uruchamiany przez `ensure_online_reviewer_ingress`
proxy-uje do tego API, które go uruchomiło, także gdy API działa na
nie-domyślnym porcie.

## Context

Odbiór etapu B (2026-09-30): API testowe z worktree działało na `8010`, a
Reviewer uruchomiony przez kontroler tunelu dziedziczył środowisko API bez
`REVIEWER_INTERNAL_API_ORIGIN`, więc proxy-ował do domyślnego `8000`
(główna instancja, bez nowych tras). Odblokowanie linku kończyło się
`{"detail":"Not Found"}`.

## Scope

- `application/reviewer_ingress.py`: `ReviewerIngressService(api_origin=…)`;
  domyślny runner ustawia `REVIEWER_INTERNAL_API_ORIGIN` w środowisku
  kontrolera, chyba że operator ustawił go jawnie (wartość operatora wygrywa).
- `main.py`: API przekazuje własny adres (`http://host:port`, IPv6 w
  nawiasach).

## Acceptance criteria

- [x] Reviewer uruchomiony przez kontroler z API na `8010` odblokowuje link i
  serwuje dane (odbiór ręczny przez loopback i przez tunel).
- [x] Jawna wartość `REVIEWER_INTERNAL_API_ORIGIN` operatora nie jest
  nadpisywana (test).

## Outcome

### Changed

- `services/api/src/game_predictor_api/application/reviewer_ingress.py`,
  `main.py`, test `test_reviewer_ingress.py` (nowy przypadek: domyślny runner
  przekazuje adres API, wartość operatora zachowana).

### Verification results

- `test_reviewer_ingress.py` 10/10, ruff i mypy czyste.
- Odbiór: po restarcie API `8010` i ponownym starcie ingressu przez
  „Utwórz link” odbiorca odblokował link na `127.0.0.1:3001`, wyszukał
  plansze (przycięte widoki przez proxy), policzył zakres (268 wierszy),
  otworzył okno planszy (8 linii, bez poprawiania pól); dziennik w Adminie
  pokazał trzy wpisy, a odtworzenie wpisu „Plansza z liniami” ustawiło wzór,
  limit 5, zakres 2500 i otworzyło okno planszy #170659. Przez publiczny
  tunel: bramka 200, błędny kod 401 (licznik prób zapisany), trasa Admina
  403.
