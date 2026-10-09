---
title: Management panel requirements
status: accepted
last_updated: 2026-10-09
---

# Management panel — D-533

## Point-page selection clarification — D-539

Only a point opens a nested view. Its machine grid remains visible after a
machine is selected; that tile is highlighted and its games/stakes appear below
the same list. Stake selection also keeps the machine grid visible. Dirty-draft
confirmation and URL/reload recovery remain. The correction execution plan is
proposed; historical restore and exact layout sizes await its acceptance.
See [correction plan](../delivery/ADMIN_PANEL_LAYOUT_CORRECTION_PLAN_20261009.md).

## Accepted compact redesign — D-538

The [compact execution plan](../delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md)
supersedes structural retention and UI rules below where indicated.
TASK-0940–0943 implement hierarchical point → machine → game/stake navigation
with Home/back, maximum320px clickable tiles, sibling edit/delete icons and
atomic modal machine name/game assignments. Tile content and corner actions
use consistent16px insets while preserving the maximum320px width and44px
touch targets. Six compact stakes restore the
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

Machine name and final game assignments save atomically. Omitting game
assignments preserves them; removing an existing assignment requires the
preview confirmation. A changed scope or saved stake invalidates the preview.
Wrong actor/body/scope and expired tokens cannot delete anything. Old mutation
retries fail explicitly after scoped deletion; retrying the successful delete
returns its minimal receipt, including after a later parent deletion.

Compact pin metadata includes nullable required investment and machine cash.
Spin zero is all-zero; unavailable pins have no invented investment/cash.
Old metadata is recovered from the frozen result without changing the database
or reinterpreting the historical result using current game rules.

User accepted the complete
[execution plan](../delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md), which owns
task breakdown and rollout gates. This module is named **Panel Administracyjny**.

## Points, machines and available games

Points have editable name/city/street and compact tiles. Machines have editable
names and belong to a point. Machine game assignments are editable and drawn
only from current `active` catalog games. Draft/archived games cannot receive
new operations. Historical archive fields remain compatible; structural
delete/detach follows D-538. Names are display values, not identifiers.

## Saved machine/game/stake view

Select a game above six independent stake cards (20,10,6,4,2,1.20 PLN descending).
Compact cards show the stake, saved state and existing symbol thumbnails (with
a code or `?` fallback). Selecting a card opens its search draft. A saved card
restores the start/query/range/pins without choosing a search hit. Only the
selected machine/game loads six bounded summaries. The selected stake shows
quick pinned rows; its chart, full payout table and journal open on demand.

Search uses existing search/approximate-win/payline editor. Fixed stake comes
from the card. Board browsing and0–6 pin choices are draft-only; **Zapisz układ**
persists the start sequence, query, range and pins. **Nowy układ** resets only
the draft. **Zapisz zmiany** updates the current start; **Zastąp układ** needs
confirmation for a different start. **Usuń zapisany układ** needs confirmation
and clears only the current slot, retaining its ordinary journal. Unsaved
navigation warns. Human symbol corrections retain immediate-write semantics
and alter current global game data, not a local copy.

Stake results use the same per-position projection as the Admin approximate
win (TASK-0936, D-537): spins inside a published super game series are free
(cost 0) and evaluated with the series board evaluation, the trigger board and
every other position cost the rules' spin cost, and provisional series payouts
are shown apart (count and sum) and stay outside the balance. The live preview
returns the calculation a save would freeze, read in one snapshot; the board
detail of the panel is read in its own REPEATABLE READ snapshot too. When the
series generation is stale, every evaluated board is provisional. A frozen
result keeps format 1: its summary stores the free spin ranges
(`superSpinRanges`, `superSpinCost`) and non-zero provisional fields only when
present, so restored charts, pins and stake labels stay exact for a super game
while results and content digests of a game without a super game kind (777)
stay byte-identical. Frozen history written earlier is never recalculated.

Show prior result while checking; current data changes recalculate and journal
before/after without replacing the start sequence. Pins identify spin positions,
not screen coordinates; invalid positions are marked unavailable. Failures mark
the previous result stale. Historic numeric chart/table/start symbols/rules are
immutable; editing a historic entry's board explicitly edits current data.

## Journal and concurrent writes

The collapsed persistent journal records time/actor/query/start sequence,
search including no hits, save/replace/clear, saved range/pins, corrections with
before/after, result changes and structural management edits. Page size20 by
default. Structural scope deletion follows D-538; ordinary slot Clear retains
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
