---
title: Consistent management tile spacing
status: done
last_updated: 2026-10-09
---

# TASK-0946 — Consistent management tile spacing

## Status

done

## Goal

Provide consistent 16px content and action insets without enlarging compact tiles.

## Context

The operator reported tiles appearing unpadded after integration. Browser baseline
shows point/machine text already inset16px, but action controls inset only4px,
stakes inset12px and legacy tiles have no content padding. Baseline browser10/10
passed because its layout checks did not validate content or control insets.

## Dependencies / entry conditions

Local main v1.7.289, bb1e60173bc7a1fde072088baa89355b74071efb. Preserve existing
operator edits. No service lifecycle or production-data operation is authorized.

## Recommended execution

A narrow CSS correction in the current Codex session; optional recommendation
for handoff: gpt-6.1-sol / medium. Escalate only if spacing needs structural UI
changes. No new execution plan or mandatory additional review for this low-risk
follow-up; use real browser geometry to verify the shared component.

## Relevant docs

- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md (compact grid rules)
- ai_docs/process/DEFINITION_OF_DONE.md

## Scope

- Inset point/machine action controls16px and reserve their width in the choice.
- Stake and legacy tile padding16px; keep the whole active tile clickable.
- Extend existing browser acceptance with rendered content/control bounds.

## Out of scope

Backend, data, migrations, navigation changes, live services and rollout.

## Acceptance criteria

- [x] Text and action controls have at least16px insets, without overlap.
- [x] All tested widths retain max320px tiles and the4/3/2/1 container grid.
- [x] Touch controls remain44px; no overflow or nested buttons.
- [x] Shared browser acceptance passes on390/1440/1920px including six stakes.

## Technical notes

Keep article padding0 for the edge-to-edge choice surface; padding belongs to
its inner button. Actions are siblings. Stake padding uses a selector stronger
than the generic tile reset. Legacy articles receive their own content padding.

## Expected files

- packages/board-search-ui/src/management/management.css (tile selectors).
- scripts/management_browser_flow.mjs (checkLayout and non-flow stake checks).
- This task and CURRENT_STATE rolling window.

## Verification

Run fixture preparation and scripts/verify_management_panel_browser.mjs from
repository root, each under120s. Run scoped Prettier/ESLint and docs:check.
Browser data is mocked; no API/Admin startup or data write is necessary.

## Risks / open questions

The production page reported by the operator was not inspected directly. The
static fixture uses actual shared React and CSS. A live visual check remains
with the operator if their page loads an older build.

## Outcome

### Changed

- Consistent16px insets for action controls, stakes and legacy cards.
- Point/machine choice reserves120px for two44px controls and their gaps;
  the choice surface remains clickable across the whole tile.
- Existing browser acceptance checks rendered content/action insets and overlap;
  all size scenarios now navigate through six stake cards.

### Verification results

- Before correction, browser10/10 passed the earlier geometry checks.
- Regression proof with old4px icon positioning in the disposable fixture:
  new assertion failed at points-flow with Tile controls touch the edge.
- Corrected Chromium10/10 PASS (390/1440/1920px,1/4/40 points,40 machines,
  six stakes); max320px,4/3/2/1 columns,44px targets and no horizontal overflow.
- Fresh screenshot inspected at1440px; controls and content align inside cards.
- Scoped Prettier PASS; node --check PASS.
- Root ESLint attempt found no root eslint.config; it did not check the script.
  Browser runtime and syntax check validate the changed fixture. No TypeScript
  code, API, modules or public symbols changed; no code-map regeneration needed.
- docs:check PASS (36 active tasks,10 done sections, decision links).

### Not completed

No new full build, repeat panel audit, operator migration, service restart or
push. This CSS-only correction reuses prior task0945 build/audit evidence and
adds a bounded fresh browser check. Live operator page remains uninspected.

### Documentation updates

Task and CURRENT_STATE record the correction; the oldest done block moved
unchanged into the Q4 archive. Requirements specify consistent16px tile insets.

### Recommended next task

Operator visual acceptance on the already running panel.

### Commit

v1.7.291 / 1332c91013855f9d519cd0075a94eb8d3d69fe96. Concurrent operator commit v1.7.290 was observed before numbering.
