---
title: Skip unavailable optional page geometry anchors
status: done
last_updated: 2026-09-06
---

# TASK-0481 — Pomijanie niedostępnych opcjonalnych kotwic geometrii

## Goal

Nie blokować nowego preflightu geometrii przez historyczną ręczną korektę,
której obraz został prawidłowo usunięty wraz ze starym stagingiem, zachowując
fail-closed dla kotwic jawnie przypiętych do bazowego profilu rejestracji.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0435-v0-10-cold-start-staging-anchor.md`

## Scope

- Rozróżnić wymagane kotwice bazowego profilu od opcjonalnych kotwic
  dołączanych z historycznych ręcznych override'ów gry.
- Dołączać opcjonalny override tylko wtedy, gdy jego JPEG istnieje w bieżącym
  checksum-bound stagingu albo w managed originals.
- Brak opcjonalnego JPEG-a ma pominąć wyłącznie tę kotwicę. Nie może zmienić
  progów, utworzyć syntetycznej geometrii ani zaakceptować źródła bez dowodu.
- Brak jawnie przypiętej kotwicy bazowej nadal kończy się
  `IMAGE_PAGE_GEOMETRY_ANCHOR_UNAVAILABLE`.
- Dodać test odtwarzający błąd joba
  `1681dd2a-27b8-425d-b2f2-192be89e0b07`.

## Definition of Done

- Nowy staging nie upada przez osierocony opcjonalny override innego źródła.
- Override bieżącego stagingu nadal może uruchomić cold-start.
- Historyczna dostępna kotwica nadal jest używana.
- Historyczna wymagana kotwica bazowego profilu nadal jest fail-closed.
- Testy i lint zmienionego workera przechodzą.
- Ten sam staging można wznowić bez ponownego uploadu.

## Outcome

- Bazowy profil rejestracji nadal zachowuje wszystkie jawnie przypięte kotwice
  i pozostaje fail-closed, gdy ich JPEG nie jest dostępny.
- Ręczne override'y gry są dołączane jako dodatkowe kotwice tylko wtedy, gdy
  odpowiadający checksum-bound JPEG istnieje w bieżącym stagingu albo managed
  originals.
- Dodano regresję potwierdzającą, że osierocony opcjonalny override prowadzi do
  zwykłego `review_required`, a nie technicznego błędu całego preflightu.
- Na rzeczywistym stagingu `6b9de344-bce1-4d6f-84d8-a04c9e5f6903` ten sam job
  `1681dd2a-27b8-425d-b2f2-192be89e0b07` wznowiono bez ponownego uploadu.
  Zakończył się bez błędu: 2531 źródeł zarejestrowano, a 80 pozostawiono do
  ręcznej korekty.
- Skoncentrowane testy preflightu i rejestracji: 28 passed; Ruff check i format
  check przeszły.

## Commit

`v0.10.195 - skip unavailable optional geometry anchors`
