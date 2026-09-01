---
title: Compact page geometry editor layout
status: done
version: "0.10.76"
---

# TASK-0375 — Compact page geometry editor layout

## Goal

Keep geometry handles visually small at every zoom level and give the source
image the full workspace width while preserving all existing geometry actions.

## Scope

- scale SVG handle radii inversely to the rendered image scale;
- reduce the visible handle and stroke size;
- move the former side controls above the full-width image;
- preserve save, batch submit, reset, zoom and all placement modes;
- add a regression contract test.

## Outcome

The editor now renders seven-pixel handles independently of zoom and uses a
single-column layout. Existing geometry contracts and mutations are unchanged.

## Verification

- `node --test apps/admin/test/page-geometry-correction-panel-contract.test.mjs`
- Admin lint and typecheck for the changed workspace.
