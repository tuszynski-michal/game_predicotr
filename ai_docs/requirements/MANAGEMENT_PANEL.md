---
title: Management panel requirements
status: accepted
last_updated: 2026-10-08
---

# Management panel — D-533

## Accepted compact redesign — D-536

The [compact execution plan](../delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md)
supersedes structural retention and UI rules below where indicated.
TASK-0940–0943 implement hierarchical point → machine → game/stake navigation
with Home/back, maximum320px clickable tiles, sibling edit/delete icons and
atomic modal machine name/game assignments. Six compact stakes restore the
saved start/query/range/pins. New/reset is draft-only until explicit replacement.
Quick rows use the shared chart's investment/net/machine-cash semantics;
chart, full table and journal are collapsed, with spin/PLN axes when expanded.

Local owner and valid whole-panel recipients may hard-delete a point, machine
or detached machine/game after a scoped expiring preview and confirmation.
This deletes management saves, contexts and journal, including correction
audit entries; actual global corrections and game-owned data remain.
Only a minimal retryable delete receipt persists. Former scoped responses are
redacted and cannot recreate entities. Independent session audit remains.
No archive/hide controls; historical archived API fields stay compatible.
Production migration/deletion requires separate operator confirmation.

User accepted the complete
[execution plan](../delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md), which owns
task breakdown and rollout gates. This module is named **Panel Administracyjny**.

## Points, machines and available games

Points have editable name/city/street and compact tiles. Machines have editable
names and belong to a point. Machine game assignments are editable and drawn
only from current `active` catalog games. Draft/archived games cannot receive
new operations. Historical archive fields remain compatible; structural
delete/detach follows D-536. Names are display values, not identifiers.

## Saved machine/game/stake view

Select a game above six independent stake cards (20,10,6,4,2,1.20 PLN descending).
Cards show board preview/sequence, chart and saved labels, save date, Open/Search
again/Clear. Empty cards are explicit. Only selected machine/game is loaded.

Search uses existing search/approximate-win/payline editor. Fixed stake comes
from the card. Board browsing and0–6 pin choices are draft-only; **Zapisz układ**
persists the start sequence, query, range and pins. Search again preserves the
old save until replacement. Unsaved navigation warns. Confirmed Clear changes
only the current slot, retaining audit. Human symbol corrections retain existing
immediate-write semantics and alter current global game data, not a local copy.

Show prior result while checking; current data changes recalculate and journal
before/after without replacing the start sequence. Pins identify spin positions,
not screen coordinates; invalid positions are marked unavailable. Failures mark
the previous result stale. Historic numeric chart/table/start symbols/rules are
immutable; editing a historic entry's board explicitly edits current data.

## Journal and concurrent writes

Persistent journal below chart/table records time/actor/query/start sequence,
search including no hits, save/replace/clear, saved range/pins, corrections with
before/after, result changes and structural management edits. Page size20 by
default. Structural scope deletion follows D-536; ordinary slot Clear retains
journal. Local actor versus named share link suffices; user
and one recipient, no accounts. Operation UUID plus body binding and expected
revision prevent lost-response duplicates or silent concurrent overwrite.

## Online access and style

Recipient has full management of this module and assigned-game search/correction;
only local administrator creates/revokes links. Entire panel is granted, not
unrelated Admin functions. Separate code, five-failure lockout, opaque protected
cookie, server expiry/revoke. Lifetimes1/4/8/24/48/72h, default8, including existing
board-search shares. Old expiry timestamps and old one-game scope remain.

Current app styles, responsive/touch controls, loading/empty/error states and
duplicate-submit prevention apply. Local PostgreSQL is authoritative; PC must be
available. Existing Reviewer/tunnel serves public module only. Hosting, accounts,
multi-master synchronization and Redis are outside initial implementation.
