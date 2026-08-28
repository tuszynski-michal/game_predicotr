---
title: Paged symbol review workspace
status: done
last_updated: 2026-08-27
---

# TASK-0299 — Paged symbol review workspace

## Goal

Replace infinite scrolling and page read-ahead in Symbol Verification with one
explicit 500-crop page that is refilled after successful decisions.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Raise the bounded symbol-cell page limit to 500.
- Keep exactly one metadata page in Admin memory; remove read-ahead, sentinels
  and adjacent-page caches.
- Provide explicit previous/next navigation and retain the current keyset
  request so a successful decision reloads the same logical page and fills its
  tail back to 500 current records.
- Default the workspace to `pending`.
- Keep only page-local explicit selection and remove selection of an invisible
  filter snapshot from the UI.
- Disable decision controls while preview, start, direct mutation or durable
  operation is active.

## Invariants

- The list remains keyset-based and never materializes the full filter.
- Refill uses the same page anchor and current server state rather than merging
  client-cached records or trusting submitted IDs.
- Multi-cell decisions retain the durable worker path; a single crop retains
  the direct atomic endpoint.
- Thumbnail bytes remain checksum-bound and browser-cacheable. Removing the
  metadata page cache must not regress image transfer.

## Acceptance

- At most 500 crop metadata records are retained and rendered.
- Successful direct or bulk decisions reload the same page and return up to
  500 still-matching records without duplicates.
- Initial state is `Oczekujące`.
- The toolbar offers one `Zaznacz całą stronę` action and no whole-filter
  selection.
- Previous/next requests cannot overlap decisions or one another.

## Outcome

- API oraz Admin używają jednej keysetowej strony maksymalnie 500 cropów.
  Infinite scroll, sentinele, read-ahead i cache sąsiednich odpowiedzi zostały
  usunięte.
- Po udanej decyzji ta sama pozycja strony jest pobierana ponownie od swojego
  kursora wejściowego. Serwer usuwa rekordy niepasujące już do filtra i
  dopełnia odpowiedź kolejnymi aktualnymi rekordami do 500.
- Domyślny stan to `pending`. UI udostępnia tylko jawne zaznaczenie pojedynczych
  kart albo całej bieżącej strony; nie tworzy snapshotu niewidocznego filtra.
- Podczas mutacji, preview, aktywnego joba lub nawigacji zablokowane są karty,
  filtry, decyzje i przyciski stron.
- Zachowano checksum-bound immutable cache miniaturek WebP, ponieważ nie jest
  cache'em metadanych strony i ogranicza ponowny transfer obrazów.
- Zweryfikowano 10 testów API, 283 testy Admina, 46 testów klienta, Ruff,
  TypeScript, lint zmienionych plików, OpenAPI/generowany klient oraz
  produkcyjny build Admina.
