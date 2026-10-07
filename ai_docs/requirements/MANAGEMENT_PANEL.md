---
title: Management panel requirements
status: accepted
last_updated: 2026-10-07
---

# Management panel — D-533

User accepted the complete
[execution plan](../delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md), which owns
task breakdown and rollout gates. This module is named **Panel Administracyjny**.

## Points, machines and available games

Points have editable name/city/street and compact tiles. Machines have editable
names and belong to a point. Machine game assignments are editable and drawn
only from current `active` catalog games. Draft/archived games cannot receive
new operations. Detach/archive retains saves/history; restore/reattach restores
access. Names are display values, not identifiers. No hard deletion UI.

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
default. No journal deletion. Local actor versus named share link suffices; user
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
