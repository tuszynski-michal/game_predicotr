# TASK-0724 — Ponowna weryfikacja tylko zmienionych cropów

## Status

done

## Goal

Po zapisie nowej geometrii komórka zachowuje weryfikację wyłącznie przy
niezmienionej tożsamości cropa; zmieniony crop wraca do `pending` z
poprzednim symbolem człowieka jako podpowiedzią.

## Context

`invalidate_symbol_cell_reviews_for_geometry` w ścieżce niekwalifikowanej
zostawia `approved` przy zmienionym cropie (B5; 456 komórek / 113 plansz).
D-462 R6, R7.

## Dependencies / entry conditions

TASK-0723 done.

## Recommended execution

claude-opus-5-5, high — ryzyko utraty lub fałszywego zachowania weryfikacji
na dwóch ścieżkach geometrii. Audyt: claude-opus-5-5, high.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/architecture/DATA_MODEL.md` (projekcja komórek, korekta geometrii)
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Jedna reguła dla ścieżki kwalifikowanej i niekwalifikowanej oraz dla
  `virtual_source` (`_replace_current_cells`,
  `_reset_grid_issue_after_virtual_recrop`).
- Warstwa repozytorium nie przywraca `approved` dla zmienionego cropa.
- Zapis geometrii usuwa `grid_issue` ze wszystkich komórek planszy (R5).
- Niezmieniony crop: akceptacja przepięta na bieżącą rewizję, aby stan
  pozostał `current` (także dla kohorty treningowej).
- Aktualizacja `DATA_MODEL.md`.

## Out of scope

- Migracja 456 istniejących komórek (TASK-0728).
- Zapis slotu `virtual_source` i kolejka (etap B).

## Acceptance criteria

- [x] Niezmieniony crop (`crop_checksum_sha256`; dla `virtual_source`
      dodatkowo `rendered_pixel_checksum_sha256`) → `approved` zachowane, a
      `approved_crop_*` i `approved_geometry_revision` wskazują bieżącą
      tożsamość.
- [x] Zmieniony crop → `pending`, `grid_issue` usunięte, poprzedni symbol
      człowieka jako `assigned_symbol_id`, stara akceptacja w evencie.
- [x] Plansza wcześniej `accepted` z komórką o zmienionym cropie przestaje być
      kompletna (brak layoutu); niezmienione komórki dalej w projekcji.
- [x] Po zapisie geometrii żadna komórka planszy nie ma `grid_issue`.
- [x] Testy domeny i integracyjne dla `legacy_file` i `virtual_source`;
      lint, mypy.

## Technical notes

Tożsamość cropa: istniejące porównanie `crop_checksum_sha256` używane w
`geometry_changed`/`unchanged_available_indices`; dla `virtual_source`
dodatkowo `rendered_pixel_checksum_sha256`, jeśli dostępne. Podpowiedź
poprzedniego symbolu: `assigned_symbol_id` z decyzji człowieka,
`review_state=pending`, `assignment_source` zachowane jako ślad pochodzenia.

## Expected files

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py` —
  `invalidate_symbol_cell_reviews_for_geometry`.
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
  — gałąź `geometry_changed` w `_synchronize` (~2600).
- `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py`
  — `_replace_current_cells`, `_reset_grid_issue_after_virtual_recrop`.
- Testy: `services/api/tests/test_image_symbol_reviews_domain.py`,
  `services/api/tests/test_image_symbol_review_virtual_source.py`,
  `services/api/tests/integration/test_verified_cell_search_projection.py`.
  Świadoma zmiana kontraktu: asercje w
  `services/api/tests/integration/test_image_batch_store.py` (~1515–1523),
  że akceptacja przetrwa zmieniony crop. Ten sam test
  (`test_symbol_cell_mutations_close_and_reopen_one_board_atomically`) pada
  już na HEAD przy ~1559, bo `grid_issue` przetrwa zapis geometrii (R5), a
  przy ~1630 oczekuje domknięcia z akceptacji starych cropów, co od
  TASK-0723 (R10) jest niemożliwe — T4 aktualizuje go tak, aby zmienione
  komórki zostały ponownie zatwierdzone przed oczekiwaniem `corrected`.

## Test cases

- Zmiana geometrii zmieniająca wszystkie cropy → wszystkie zatwierdzone
  komórki `pending` z podpowiedzią.
- Kwalifikowana zmiana z częścią niezmienionych cropów → tylko zmienione
  `pending` (scenariusz 6).
- `Zła siatka` na zweryfikowanej komórce → tylko ona `pending` + `grid_issue`.
- `virtual_source`: niezmieniony render zachowuje akceptację (przepiętą),
  zmieniony wraca do `pending` z podpowiedzią.
- Po zapisie geometrii żadna komórka planszy nie ma `grid_issue`, a plansza
  znika z listy „Do poprawy siatki”.

## Verification

Katalog: root repozytorium; każdy krok z timeoutem 120 s.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_domain.py services/api/tests/test_image_symbol_review_virtual_source.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_verified_cell_search_projection.py -q
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Repozytorium ma warstwę przywracającą decyzje człowieka po recropie; zmiana
  musi objąć obie warstwy spójnie.

## Outcome

### Changed

- Domain `invalidate_symbol_cell_reviews_for_geometry`: for an `approved`
  cell the approved pixels decide — the same pixels keep the verification
  rebound to the new identity; other pixels (including an already stale
  approval) give a pending human suggestion with the old approval as
  history. A saved geometry resolves `grid_issue` (suggestion only for the
  same pixels). Pending human decisions keep their pixel-bound flags only
  for the same pixels; model suggestions follow the current prediction.
- `SymbolCellReviewWriteThroughCoordinator._synchronize`: no repository
  override of domain recrop decisions (only positions that gain pixels keep
  the human label as a suggestion); approved asset provenance is rebound for
  every rebound approval; partial visibility keeps a human suggestion with
  `partial_visibility`; `_outside_human_decision_values` resolves a grid
  report only for a new geometry and keeps logical decisions without pixels;
  unavailable qualified cells lose `grid_issue` only on a geometry change.
- `virtual_grid_geometry_repository`: `_recheck_after_virtual_recrop` (R5/R6
  for manual `virtual_source` saves) with the write-through verification
  mapping `_verification_v2`; `_reopen_resolved_revision` reopens every
  resolved board before any manual geometry; both saves close boards again
  with `synchronize_board_from_cells`.
- Docs: `DATA_MODEL.md` (recrop rules and exceptions), `ADMIN_APP.md`
  (D-462 paragraph), plan (T5 note about sibling reopening).

### Verification results

- Unit: domain (incl. stale approval, pixel-bound flags, qualified partial
  recrop), virtual repository (ORM-model regression test for the P0 path,
  unconditional reopen), source visibility (incl. outside grid report kept
  until a new geometry): all PASS.
- PostgreSQL: `test_verified_cell_search_projection.py` (3) and
  `test_image_batch_store.py::test_symbol_cell_mutations_close_and_reopen_one_board_atomically`
  (red on HEAD, now green after re-approving changed crops and asserting the
  cleared grid queue) and the bulk-operation test PASS.
- Full API unit suite: 23 failed / 1550 passed — the same 22 failures as the
  clean-HEAD worktree plus the user's uncommitted approximate-win limit
  change; no failure caused by this task.
- Ruff check/format PASS; mypy shows no errors in changed files.
- Audit claude-opus-5-5 (subagent, reasoning level inherited): cycle 1 —
  1× P0 (strict verification mapping in the virtual save), 2× P1 (stale
  approval revived, virtual save not reopening), 3× P2; cycle 2 — all
  closed, one new P2 (outside grid report cleared by any synchronization)
  fixed; final check „Brak uwag P0–P2”.

### Not completed

- No PostgreSQL test of a manual `virtual_source` save exists in the repo;
  the regression is covered by an ORM-model test of `_replace_current_cells`
  (counts and the post-save closure are not asserted there).
- Observation: on a partially visible position a pending human `unreadable`
  with unchanged pixels becomes `partial_visibility` (neither is evidence).
- Observation: a qualified recrop treats an approval equal to the new pixels
  but different from the previous crop as changed (safe variant).
- `test_image_batch_store.py` still has pre-existing drift in
  `write_through_tracks` (~805) and `manual_deferred_geometry` (fixture
  quad) — separate task.

### Documentation updates

- `DATA_MODEL.md`, `ADMIN_APP.md`, plan, `CURRENT_STATE.md`.

### Recommended next task

- Stage A is complete; stage B (TASK-0725–0727) and stage C (TASK-0728–0729)
  need an explicit operator command; TASK-0728 apply additionally needs
  consent after preview.
