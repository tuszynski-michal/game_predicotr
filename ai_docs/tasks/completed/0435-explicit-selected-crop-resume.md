---
title: TASK-0435 Explicit selected crop resume and compact previews
status: done
last_updated: 2026-09-04
---

# TASK-0435 — Explicit selected crop resume and compact previews

## Problem

After reload the crop workspace immediately requests access through a persisted
directory handle. Browser permission cannot safely be requested outside a user
gesture, leaving the workspace busy and its actions disabled. Atlas previews
also load automatically and use more resolution than the overview requires.

## Scope

- restore only lightweight session metadata on page load,
- require an explicit click before reopening the persisted directory,
- load preview atlases only after an explicit operator action,
- reduce preview dimensions and WebP quality,
- allow leaving the workspace and selecting another directory,
- stop background preparation safely between files when leaving.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Definition of Done

- reload does not request directory permission or decode previews,
- the resume button is enabled from persisted metadata,
- previews load only after clicking their dedicated action,
- leaving preserves results but returns to directory selection,
- preparation cannot repopulate an exited workspace,
- focused tests, lint, typecheck and Admin build pass.

## Outcome

- Reload now restores only lightweight IndexedDB metadata and presents an
  enabled `Wznów zapisany katalog` action. Directory permission is requested
  only from that explicit click.
- Preview atlases are opt-in through `Wczytaj miniaturki`; tiles were reduced
  to 120×80 and WebP quality 0.58 without changing final JPEG quality.
- `Wyjdź i wybierz inny katalog` aborts preparation between files, revokes
  preview URLs and returns to setup while preserving journaled outputs.
- Admin tests `387/387`, typecheck, ESLint, scoped Prettier and production build
  pass.
