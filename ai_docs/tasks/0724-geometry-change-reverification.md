# TASK-0724 — Ponowna weryfikacja tylko zmienionych cropów

## Status

todo

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

- [ ] Niezmieniony crop (`crop_checksum_sha256`; dla `virtual_source`
      dodatkowo `rendered_pixel_checksum_sha256`) → `approved` zachowane, a
      `approved_crop_*` i `approved_geometry_revision` wskazują bieżącą
      tożsamość.
- [ ] Zmieniony crop → `pending`, `grid_issue` usunięte, poprzedni symbol
      człowieka jako `assigned_symbol_id`, stara akceptacja w evencie.
- [ ] Plansza wcześniej `accepted` z komórką o zmienionym cropie przestaje być
      kompletna (brak layoutu); niezmienione komórki dalej w projekcji.
- [ ] Po zapisie geometrii żadna komórka planszy nie ma `grid_issue`.
- [ ] Testy domeny i integracyjne dla `legacy_file` i `virtual_source`;
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

Wypełnia agent po pracy.
