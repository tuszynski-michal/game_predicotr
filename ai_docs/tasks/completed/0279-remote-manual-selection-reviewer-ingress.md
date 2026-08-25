---
title: TASK-0279 - Osobna powierzchnia Reviewera i reuse ingressu
status: done
owner: Codex
version: 0.7
---

# Cel

Udostępnić bezpieczny shell zdalnej ręcznej selekcji zdjęć przez istniejącą
aplikację Reviewer i jeden współdzielony Quick Tunnel, bez wystawiania Admina,
API ani istniejącego scope `game/import`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (sekcje 10-18 i TASK 7)
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/tasks/completed/0278-remote-manual-selection-access-and-writer-lease.md`

## Zakres

- route Reviewera `/manual-selection` z osobną bramką kodu i odczytem context;
- same-origin proxy `/selection-api` z zamkniętą allowlistą endpointów TASK 6;
- publiczne cookie `gp_remote_selection_token` o ścieżce `/selection-api`,
  tłumaczone na host-only cookie FastAPI bez ujawniania tokenu w JSON;
- walidacja Origin/Fetch Metadata, limit 128 KiB, filtrowanie nagłówków i CSP;
- stały nagłówek intencji proxy wymagany przez publiczne route FastAPI;
- użycie istniejącego Reviewer/Quick Tunnel lifecycle bez drugiego procesu;
- dynamiczny URL `/manual-selection?session=<UUID>` dla tej samej trwałej
  sesji po zmianie publicznego originu tunelu;
- testy allow/deny, cookie, scope isolation, loopback proxy i regresji Reviewera.

## Poza zakresem

- remote source adapter, IndexedDB outbox i workspace z TASK 8;
- control operations, upload binarny, kolekcje, partie i materializacja;
- panel monitoringu Admina z TASK 14;
- uruchamianie rzeczywistego publicznego Quick Tunnel w automatycznych testach.

## Invarianty

- tylko jeden istniejący proces Reviewera i jeden współdzielony ingress;
- link zawiera wyłącznie opaque session ID, nigdy kod ani token;
- token nie jest dostępny dla JavaScriptu, URL-a, logów ani publicznego JSON;
- `/selection-api` nie przepuszcza route Admina, Reviewera `game/import`, jobów,
  storage, eksportów ani wydań;
- publiczny host ignoruje legacy `mode=local`;
- FastAPI, Admin, PostgreSQL i worker pozostają na loopback bez publicznego CORS;
- limit control requestu pozostaje 128 KiB; binary upload nie powstaje w TASK 7;
- feature flag usuwa shell i allowlistę bez kasowania sesji lub audytu.

## Plan wykonania

1. Zamrozić zamkniętą politykę proxy i negatywną macierz route.
2. Dodać tłumaczenie cookie, origin/size policy i loopback transport.
3. Dodać shell/gate `/manual-selection` z context, heartbeat i takeover.
4. Podłączyć sesje Admina do istniejącego ingressu i dynamicznego URL-a.
5. Uruchomić testy, build i security review; zaktualizować dokumentację.

## Outcome

- Dodano izolowany shell `/manual-selection`, same-origin proxy
  `/selection-api`, purpose-scoped cookie translation i zamkniętą allowlistę
  czterech operacji control-plane.
- CSP, Origin/Fetch Metadata, JSON-only transport, limit request/response
  128 KiB, filtrowanie nagłówków i stała intencja backendu działają fail-closed.
- Admin reużywa jeden istniejący Reviewer/Quick Tunnel, zwraca dynamiczny URL
  tej samej sesji i może zawsze wykonać revoke niezależnie od stanu ingressu.
- Reviewer: 62/62 testów, lint, typecheck i production build. API: 9/9 testów
  route sesji, 28/28 access/ingress oraz 62/62 lifecycle/security/contract.
  Ruff, format, OpenAPI i generated client są zielone. Lokalny production E2E
  potwierdził route, gate, konsolę i finalny CSP.
- Mypy grafu API ujawnia dwa wcześniejsze błędy typów w niezwiązanym
  `symbol_model_iteration_repository.py` i wewnętrzny błąd narzędzia; zakresu
  nie rozszerzono. Workspace, operacje i upload pozostają dla TASK 8+.
