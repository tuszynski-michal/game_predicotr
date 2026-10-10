# TASK-0972 — D-542, D-543, dokumentacja i odbiór cofania korekt i zamiennika

## Status

`blocked` — czeka na zgodę operatora na scalenie, migrację 0154 i odbiór 69004.

Uwaga 2026-10-10: slot 69004 z planu już nie istnieje (patrz `Outcome`); odbiór
cofnięcia wykonuje się na nowej korekcie wskazanej przez operatora.

## Goal

Decyzje D-542 i D-543 oraz dokumenty opisują cofanie korekt, odrzucanie i zamiennik; operator wykonuje migrację `0154` po scaleniu za zgodą, a odbiór potwierdza cofnięcie slotu 69004 i jedno przejęcie sekwencji przez zdjęcie zastępcze, wykonane przez operatora.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, etap R4.

## Dependencies / entry conditions

- TASK-0966–0971 ukończone; zgoda operatora na scalenie i push.

## Recommended execution

`claude-sonnet-5-5`, reasoning `low`: dokumentacja i odczytowy odbiór. Eskalacja: rozbieżność stanu bazy z oczekiwanym → zatrzymaj i zgłoś. Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- D-542 (pełny wpis w `DECISION_LOG_2026.md`, indeks, okno pięciu wpisów): cofanie ostatniej korekty, status `reverted`, fizyczne usuwanie w przypadku B z audytem, reguła `assignment_source`, zmiana D-462 w zakresie „bez usuwania historii” dla wierszy utworzonych przez cofany zapis.
- D-543: odrzucanie slotu/planszy po imporcie (status `rejected` slotu, bramka bez zmian), reguła przejęcia sekwencji przez zdjęcie zastępcze (zmienia D-238), sprzątanie starego zdjęcia.
- `DATA_MODEL.md` (tabela audytu, status, kolumna zdarzeń), `API_CONTRACT.md` (trasy cofania i odrzucania), `IMAGE_INGESTION.md` (reguła przejęcia sekwencji), wymagania Reviewera, `README.md` (link do planu), status planu.
- Instrukcja operatora: stop API/worker/Admin/Reviewer → scalenie → `npm run db:migrate` → start → cofnięcie w Reviewerze.
- Odczytowy pomiar N1: ile korekt importu `092ff7a4-…` jest `revertable` i jakie są powody blokad.
- Odbiór po cofnięciu 69004 przez operatora (odczyt): slot `pending`, brak planszy `378a273f-…`, sąsiedzi 69006–69012 na rewizji źródła 0, rewizja 1 `reverted`, wiersz audytu.
- Odbiór zamiennika po imporcie operatora (odczyt): odrzucony slot `superseded`, nowa plansza właścicielem sekwencji, stare zdjęcie przeliczone, raport importu z „Zastąpione sekwencje”.

## Out of scope

- Wykonywanie cofnięcia lub migracji przez agenta.

## Acceptance criteria

- [x] `npm run docs:check` zielone; D-542 i D-543 w indeksie i oknie.
- [ ] Odbiór 69004 i zamiennika opisany w `Outcome` z wynikami zapytań odczytowych.

## Verification

```powershell
npm run docs:check
# odczyt stanu bazy operatora: psql SELECT, bez zapisów
```

## Risks / open questions

- Operator może najpierw ponownie poprawić 69004; wtedy cofnięcie dotyczy nowszego zapisu albo jest blokowane — odnotuj w `Outcome`.

## Outcome

Wykonawca: claude-opus-5-5 (lead, subagent), 2026-10-10. Status `blocked`:
czeka na zgodę operatora na scalenie i push, migrację `0154` i odbiór.

### Scalenie gałęzi integracyjnej i przenumerowanie (v1.7.306)

- Commit scalający v1.7.306 / 853052a1e1fcc4024dc468547224058ec7c4132f
  (rodzice: v1.7.296 `530c1d17` tej gałęzi i v1.7.305 `9d011460` gałęzi
  integracyjnej; w trakcie pracy czubek integracji przesunął się z v1.7.299 na
  v1.7.305, więc scalenie objęło też TASK-0961–0965 i D-540/D-541).
- Przenumerowanie (kolizje z innymi torami): TASK-0945–0951 → TASK-0966–0972
  (pliki tasków, raporty audytów `ai_docs/quality/TASK-0966…0971_AUDIT_*`,
  plan, CURRENT_STATE, README, komentarze kodu i testów), D-538/D-539 →
  D-542/D-543, migracja `0153_geometry_correction_revert` →
  `0154_geometry_correction_revert` (`down_revision =
  0153_merge_compact_super_games`, `EXPECTED_ALEMBIC_HEAD`, testy heada).
  Własne TASK-0945–0950 gałęzi integracyjnej (panel) bez zmian.
- `0152_management_compact_panel` dotyka wyłącznie tabel `public.management_*`
  (bez `game_data_v2`), więc manifest v7 nie wymagał uzgodnienia.
- Świadome zmiany testów wynikające z nowego heada: `test_schema_readiness`
  (head `0154`, test scalenia czyta `0153_merge_compact_super_games`, `0153`
  na liście odrzucanych), `test_compact_super_game_merge_postgres` (po
  `upgrade head` manifest v7), `_application_role_database` (rewizje z
  `0152_super_game_series`, ale bez `0154` dostają historyczny manifest v6),
  downgrade testu migracji cofania do `0153_merge_compact_super_games`.
- Konflikty: CURRENT_STATE i archiwum Q4 (okno 10 sekcji, nadmiar przeniesiony
  do archiwum bez edycji), ADMIN_APP, sekcja kompletności geometrii w Adminie
  i jej test (odchudzona sekcja TASK-0964 zachowuje raport `sequenceOwnership`
  D-543), CSS i testy interakcji Reviewera (obie strony), `schema_readiness`;
  OpenAPI, klient i mapa kodu zregenerowane.
- Zmiana produktu wymuszona scaleniem: lokalny Reviewer w zakresie gry
  (TASK-0962) nie ma `importJobId`, a lista „Ostatnie korekty” jest per import.
  Lista pokazuje teraz import planszy widocznej w kolejce i zostaje na
  ostatnim imporcie po opróżnieniu kolejki; komunikat pustej listy bez słowa
  „import” (kontrakt TASK-0962). Nowy test interakcji.

### Dokumentacja (v1.7.307)

- D-542 i D-543: pełne wpisy na początku `decisions/DECISION_LOG_2026.md`,
  wiersze indeksu i pełne kopie w `DECISION_LOG.md` (okno: D-543, D-542,
  D-541, D-539, D-538). Zawierają decyzje leada z Outcome TASK-0966–0971:
  zatwierdzenie przechodzi na `N + 1`, węższy `PINNED` dla A,
  `HISTORY_INCOMPLETE` i `RENDERER_UNAVAILABLE`, trwałe zdarzenia odrzuceń
  slotów, unikalne w grze klucze idempotencji cofnięć, reguła własności
  D-543 z ochroną lateralną, globalna kolejność blokad z blokadą własności
  czytelnik/pisarz, zmiana D-462 dla wierszy tworzonych przez cofany zapis.
- `DATA_MODEL.md`, `ADMIN_APP.md` (D-542/D-543, lista w zakresie gry),
  `API_CONTRACT.md` i `IMAGE_INGESTION.md` wskazują decyzje; plan ma status
  „implemented, awaiting operator migration and acceptance”; README z linkiem
  do instrukcji.
- Instrukcja operatora `ai_docs/guides/GEOMETRY_CORRECTION_REVERT_OPERATOR.md`.

### Pomiar N1 (odczyt bazy operatora, 2026-10-10)

Tylko `SELECT` w transakcjach `READ ONLY` (`docker exec … psql`, schemat
`game_data_v2`). Baza operatora: `0153_merge_compact_super_games`. Nowy kod
nie mógł działać (brak `0154`), więc warunki zostały przybliżone SQL-em według
reguł z D-542 (bez `HISTORY_INCOMPLETE`, renderera i dokładnej tożsamości
predykcji dla A).

- **Import `092ff7a4-e652-4273-9c0a-a30e38ebd8cc`:** 0 zdarzeń
  `geometry_saved`, 0 slotów odroczonych (26 154 pozycji przeglądu zostaje).
  Slot `378a273f-…` (sekwencja 69004) nie istnieje: zdjęcie
  `seq_69004-69012.jpg` usunięto 2026-10-09 w partii 1 wymiany 275 zdjęć Mumii
  (`ai_docs/quality/MUMIE_SOURCE_REPLACEMENT_20261009.md`, TASK-0960), a
  sekwencje 69004–69012 wróciły 2026-10-10 08:49 UTC w imporcie
  `344ce332-acda-4ebe-bf80-fc116f8d7e17` jako 9 plansz `pending` (pozycje 0–8,
  jedno źródło). **N1 dla tego importu = 0; cofnięcia 69004 nie da się wykonać.**
  To rozbieżność stanu bazy z planem (eskalacja zgłoszona leadowi).
- **Cała gra Mumie:** 44 zdarzenia `geometry_saved`, wszystkie w imporcie
  `f3ff4258-e561-4031-bc04-227c9dbf51b6` (2026-10-06 18:49–19:40 UTC, 5 zdjęć),
  wszystkie typu B (rozstrzygnięcie slotu); sloty tego importu: 44 `resolved`,
  847 `superseded`. Szacunek: **0 z 44 cofalnych**. Pierwszy niespełniony
  warunek: `SOURCE_ADVANCED` 39, `CELLS_CHANGED` 5. Warunki niezależnie:
  `CELLS_CHANGED` 44 (zdarzenia komórek po korekcie), `PINNED` 44 (predykcje),
  `SOURCE_ADVANCED` 39, `IMAGE_ADMITTED` 36, `RESOLVED` 18; brak
  `NOT_LATEST`, `SHARED_SOURCE_REVISION` i `SEQUENCE_OWNERSHIP`.
- Wniosek: istniejące korekty są stare i obrośnięte późniejszą pracą; funkcja
  dotyczy świeżych korekt. Odbiór cofnięcia trzeba wykonać na nowej korekcie
  (instrukcja, sekcja 6).

### Weryfikacja

Z katalogu worktree, `PYTHONPATH` worktree, `..\..\.venv\Scripts\python.exe`:

- `check_decision_links.py` — OK (539 wpisów); `check_current_state_window.py`
  — OK; `generate_code_map.py --check` — up to date.
- `export_admin_openapi.py --check` i `check:generated` klienta — current.
- PG (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): po pierwszym scaleniu
  `test_compact_super_game_merge_postgres`, `test_management_receipt_backfill_postgres`,
  `test_geometry_correction_revert_pending_postgres` (migracja `0154` w górę,
  w dół do `0153_merge…`, w górę) — passed; `…_refusals`, `…_board`,
  `test_pending_slot_rejection_postgres`, `test_replacement_photo_takeover_postgres`,
  `test_sequence_ownership_lock_order_postgres`, `test_super_game_series_postgres`,
  `test_virtual_deferred_resolution_postgres`, `test_image_geometry_completeness_gate`
  — 83 passed, 1 failed (niżej); po drugim scaleniu
  `test_image_geometry_completeness_repository`, przejęcie, odrzucenia,
  cofanie slotu, `test_reviewer_operational_geometry_postgres`, scalenie
  panelu — 62 passed.
- Dwa testy cyklu migracji padają identycznie na niezmienionym czubku
  gałęzi integracyjnej `9d011460` (sprawdzone na eksporcie `git archive`):
  `test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`
  i `test_super_game_series_postgres.py::test_migration_downgrade_refuses_decisions_and_round_trips`
  — downgrade przechodzi przez `0152_management_compact_panel`, którego
  downgrade zawsze odmawia. Błąd toru panelu, poza zakresem; do osobnej poprawki.
- Pełne `npm run db:baseline:verify` (cały katalog integracyjny) nie było
  uruchomione w całości (czas); uruchomiono zestawy powyżej.
- Testy jednostkowe API: 2670 passed, 372 skipped; worker: 2822 passed, 43
  skipped; `ruff check` — czysto; `mypy` — Success (872 pliki).
- Klient: 110 pass; Reviewer: `test` 264 pass, `test:geometry` 86 pass,
  typecheck i lint czyste; Admin: typecheck czysty, `test` 730 pass,
  `test:geometry` 206 pass; `npm run reviewer:build` — sukces.

### Dług audytowy i ryzyka

- TASK-0971 (dawny 0950): ponowny audyt Codex po czwartej rundzie poprawek i
  audycie zastępczym Claude (`claude-sonnet-5-5`, PASS); 5 przyjętych ryzyk P2
  (nieczytelny błąd ponownej akceptacji odrzuconej planszy po przejęciu,
  `pipeline_store.py:353` bez blokady własności i `_recompute_liveness_changes`
  blokujące źródło po stanie liczników, możliwe trójstronne zakleszczenie przez
  inne `FOR UPDATE` wierszy joba, rejestr blokad ignorujący savepointy, skan
  kandydatów bramki bez indeksu).
- Dodatkowe rundy poprawek bez ponownego audytu: TASK-0966 (runda 2,
  kohorta), TASK-0968 (test `RENDER_FAILED` dopisany przez leada), TASK-0970
  (runda 4, test `pending_partial`).
- Zmiana „Ostatnie korekty” w zakresie gry (to scalenie) nie ma audytu
  drugiej rodziny.
- Pozostałość: baza testowa `game_predictor_task0760_e7d125df587d_test` — do
  usunięcia przez operatora.

### Pozostało (operator)

1. Zgoda na scalenie i push (`--ff-only` do `v1.1-vision-lab-hybrid-geometry`).
2. Stop API/worker/Admin/Reviewer → `npm install` → `npm run db:migrate`
   (`0154`) → `npm run reviewer:build` → start.
3. Odbiór cofnięcia na nowej korekcie (69004 nie istnieje) i jednego
   przejęcia sekwencji przez zdjęcie zastępcze; wyniki zapytań z sekcji 9
   instrukcji wpisać tutaj, potem status `done`.
