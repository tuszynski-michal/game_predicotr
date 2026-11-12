---
title: Szybki zapis geometrii przy kohortach i wycofywanie kohort
status: accepted
last_updated: 2026-11-12
---

# Szybki zapis geometrii przy kohortach i wycofywanie kohort

Plan na prośbę operatora (2026-11-12), zaakceptowany 2026-11-12 („zacznij”, praca w osobnym worktree). Dwie części: (A) wyzwalacz kohort
bez pełnego przeszukiwania tabeli członków, (B) wycofywanie kohort, które nie
chronią żadnego modelu. Plan nie upoważnia do migracji bazy operatora,
restartu usług, wycofania konkretnej kohorty ani scalenia.

## 1. Stan obecny (fakty z pomiarów 2026-11-12)

- Zapis „Zapisz geometrię i dalej” w Reviewerze trwa 25–33 s. Pomiar:
  pełny zapis kodem API (`VirtualGridGeometryService.save_review_item`) w
  transakcji wycofanej ROLLBACK: 33,4 s, z czego 28,4 s to 8 wywołań
  `UPDATE image_symbol_review_cells SET source_geometry_revision_id …` w
  `storage/image_geometry_completeness_state_repository.py::apply_board_repoint`
  (przepięcie pozostałych 8 plansz zdjęcia na nową rewizję źródła,
  TASK-0807), a 3,4 s zapis komórek poprawianej planszy.
- Przyczyna: wyzwalacz `grid_cohort_currentness` →
  `game_data_v2.grid_cohort_notice_v1` (Alembic `0163_grid_training_cohorts.py`,
  13 tabel `NOTICE_TABLES`, BEFORE INSERT/UPDATE/DELETE FOR EACH ROW) szuka
  członków kohort warunkiem `source_id = … OR board_ids @> ARRAY[…] OR
  review_ids @> … OR cell_ids @> …` na `grid_training_cohort_members`.
- Tabele mają `FORCE ROW LEVEL SECURITY` z polityką `game_scope_v1`
  (`game_id = current_game_id_v1()`). Rola API `game_predictor_app` nie
  omija RLS; operator `@>` dla `uuid[]` nie jest `LEAKPROOF`, więc planner nie
  używa indeksów GIN `ix_grid_cohort_*_ids` i robi Seq Scan.
  Zmierzone: ten sam odczyt jako `game_predictor_app` 163 ms (Seq Scan, 6129
  wierszy odrzuconych, 18 425 buforów), jako superużytkownik 2–4 ms (Bitmap
  Index Scan). Około 135 komórek × ~0,2 s ≈ 27 s.
- Koszt rośnie z każdą kohortą. Stan bazy: 5 kohort Mumie A2, 6134
  członków, łącznie 821 475 `cell_ids`, 1355 `board_ids`, 1355 `review_ids`,
  43 149 zdarzeń `currentness_notice`:

  | Kohorta | Utworzona | Członkowie | Model uczony na kohorcie |
  |---|---|---|---|
  | `862f79ce` | 2026-11-02 | 788 | `0ce39122` |
  | `8c4d3ab4` | 2026-11-03 | 788 | `3ed60010` (zachowany do powrotu, D-604) |
  | `dae22c06` | 2026-11-08 | 479 | `9992a316` |
  | `ea423f8a` | 2026-11-10 | 1479 | `1be01f29` |
  | `7bfdd5c1` | 2026-11-12 | 2600 | `bf327cfa` (default i przypisanie Mumie A2) |

- Odbiorcy zdarzeń: trigger z `0166_grid_model_evaluation.py`
  (`grid_cohort_notice_mark`, AFTER INSERT WHEN `kind='currentness_notice'`)
  → `public.grid_model_cohort_notice_marks` → `notice_count` w
  `storage/grid_model_evaluation_repository.py` i bariera publikacji w
  `application/grid_model_publication.py:170-178`. Zdarzenia chronią więc
  publikację modelu ocenionego na kohorcie, której dowody się zmieniły.
- Członków zapisują: `application/grid_training_cohort_commands.py`
  `prepare()` (INSERT…SELECT, puste tablice) i `_capture()` (ustawia
  `board_ids`, `review_ids`, `cell_ids` w statusie `preparing`);
  `storage/grid_reinference_retention.py::detach_grid_source_links` ustawia
  `live_source_image_id = NULL`. Brak DELETE w kodzie aplikacji.
- Status kohorty (0163): `preparing, preview_ready, materializing,
  ready_to_freeze, frozen, failed, canceled`; przejścia wymusza
  `grid_cohort_immutable_v1`. Pojęcie wycofania nie istnieje.
- Manifest magazynu gry: `game-data-v2-manifest-v22`; ostatnia migracja
  `0185_grid_gate_noise_tolerance`. Wzorzec dodawania tabeli gry z partycjami
  i RLS: `storage/grid_cell_content_migration.py` (`guard`, `manifest`,
  `protect`).

## 2. Cel

1. Zapis jednej planszy w Reviewerze wraca do ≤ 3 s na danych operatora i
   nie rośnie z liczbą kohort.
2. Każda zmiana, która dziś tworzy `currentness_notice`, tworzy go nadal dla
   tych samych kohort (bez utraty ochrony publikacji).
3. Operator może wycofać kohortę, która nie chroni żadnego modelu, i
   przywrócić ją bez utraty danych; wycofana kohorta nie obciąża zapisu.

## 3. Decyzje (proponowana D-605)

1. **Tabela wyszukiwania członkostwa (A).** Nowa tabela gry
   `game_data_v2.grid_training_cohort_member_refs` (proponowana):
   `game_id uuid, cohort_id uuid, ref_kind text CHECK IN ('source','board',
   'review','cell'), ref_id uuid`, PK `(game_id, ref_kind, ref_id,
   cohort_id)`, FK `(game_id, cohort_id)` → `grid_training_cohorts`,
   `PARTITION BY LIST(game_id)`, RLS `game_scope_v1`, wpis w manifeście v23.
   Zawiera dokładnie te pary, które dziś wynikają z `source_id`, `board_ids`,
   `review_ids`, `cell_ids` członków kohort niewycofanych.
2. **Nowy wyzwalacz.** `grid_cohort_notice_v2` zastępuje treść wyszukiwania:
   zbiera do 8 par `(ref_kind, ref_id)` (bieżące i poprzednie: sid, bid, rid,
   cid) i szuka `WHERE game_id = gid AND (ref_kind, ref_id) IN (…)` tylko
   równością `uuid`/`text` (operatory `LEAKPROOF`), więc PK jest używany także
   pod RLS. Logika klasyfikacji, wczesnych wyjść i treść dokumentu zdarzenia
   (`table`, `operation`, `classification`, `reasonCode`) pozostają bez zmian.
   `grid_cohort_notice_v1` zostaje w bazie dla historii, nieużywana.
3. **Spójność tablic i refs.** Refs zapisuje ten sam kod i ta sama transakcja
   co tablice (`prepare()` → `source`, `_capture()` → `board/review/cell`).
   Strażnik bazy: dla kohorty niewycofanej zbiór refs = zbiór z tablic;
   odchylenie wykrywa test i weryfikacja migracji (nie po cichu).
4. **Wycofanie (B).** Nowy status `retired`; przejścia `frozen → retired`
   (retire) i `retired → frozen` (restore), tylko te. Retire usuwa refs
   kohorty (członkowie, strony, manifest i zdarzenia zostają bez zmian).
   Restore odbudowuje refs z tablic członków i wstawia jedno zdarzenie
   `currentness_notice` z `reasonCode = 'COHORT_RETIREMENT_GAP'`: w czasie
   wycofania zmiany nie były śledzone, więc ocena powiązana z kohortą
   wymaga ponownej oceny przed publikacją (fail-closed).
5. **Kohorta chroniona (nie do wycofania).** Kohorta nie może być wycofana,
   gdy którakolwiek wersja modelu z `grid_model_versions.manifest_json
   ->>'cohortId' = cohort_id`:
   - jest w `grid_model_default`,
   - jest w bieżącym `game_grid_model_assignments` dowolnej gry,
   - ma publikację w `grid_model_publications` bez wycofania,
   albo gdy kohorta jest w `input_payload` (`cohort_id`, `shared_cohorts`)
   joba treningu/oceny w statusie innym niż końcowy, albo ma otwartą
   `grid_cell_content_sessions`. Reguła jest czystą funkcją domenową z
   jawnymi powodami blokady.
6. **Użycie wycofanej kohorty.** Nowy trening, ocena, publikacja, przypisanie
   i powrót do modelu z wycofanej kohorty są blokowane kodem
   `GRID_COHORT_RETIRED`. Odczyt historii, manifestów i raportów działa.
7. **Operacja jak inne komendy kohort.** Podgląd (`preview`, token i
   powody blokady) → wykonanie z tokenem i `idempotencyKey`, zapis w
   `grid_training_cohort_commands`. Panel Admin pokazuje listę kohort z
   modelem, statusem ochrony i akcjami „Wycofaj” / „Przywróć”.

Odrzucone: wyłączenie wyzwalacza (utrata ochrony publikacji); kolejka
asynchroniczna (nowy konsument, okno nieaktualności, ten sam zysk);
`SECURITY DEFINER` z właścicielem-superużytkownikiem (omija RLS całej
funkcji, gorsza granica bezpieczeństwa); usuwanie kohort (zrywa rodowód i
audyt modeli); oznaczenie `@>` jako `LEAKPROOF` (zmiana katalogu systemowego).

## 4. Zakres i poza zakresem

W zakresie: migracja `0186`, nowy wyzwalacz, zapis refs, status `retired`,
reguła ochrony, API preview/execute, Admin UI, testy, dokumentacja
(`DATA_MODEL.md`, `VISION_LAB.md`, D-605).

Poza zakresem: zapis w tle w Reviewerze (osobny task po pomiarze),
przepisanie `apply_board_repoint`, wycofanie konkretnych kohort na danych
operatora (osobna zgoda po wdrożeniu), migracja bazy operatora i restart
usług (operator), zmiana defaultu lub przypisań modeli.

## 5. Taski

### TASK-1190 — Szybkie wyszukiwanie członkostwa kohort w wyzwalaczu

**Goal:** zapis geometrii planszy jako rola API nie skanuje tabeli członków;
zbiór zdarzeń `currentness_notice` jest identyczny jak przed zmianą.

**Dependencies:** `main` na `v1.7.616` lub nowszym, baza testowa PostgreSQL.

**Scope:**
1. Migracja `services/api/alembic/versions/0186_grid_cohort_member_refs.py`
   (proponowana), w jednym pliku także schemat statusu `retired` dla
   TASK-1191, żeby wdrożenie miało jedną migrację:
   - guard manifestu v22, tabela `grid_training_cohort_member_refs` z
     partycjami istniejących gier i RLS (wzorzec `grid_cell_content_migration`),
     manifest v22 → v23 (`storage/game_data_v2_manifest_v23.py`, proponowany)
     i rejestracja tabeli w tworzeniu partycji nowej gry
     (`storage/game_partition_lifecycle.py`);
   - backfill refs z istniejących członków wszystkich kohort (stan obecny
     ≈ 830 tys. wierszy; `INSERT … SELECT unnest(…) ON CONFLICT DO NOTHING`
     per gra i rodzaj), potem kontrola liczebności: liczba refs każdego
     rodzaju = liczba różnych par z tablic; niezgodność przerywa migrację;
   - `grid_cohort_notice_v2` i podmiana funkcji w 13 wyzwalaczach
     `grid_cohort_currentness` (+ partycje);
   - CHECK statusu z `retired` i reguła przejść w `grid_cohort_immutable_v1`
     (`frozen ↔ retired`); strażnik refs: INSERT/DELETE refs tylko gdy
     kohorta `preparing` (zapis z `_capture`) albo w transakcji komendy
     retire/restore (ustawienie lokalne `game_predictor.cohort_refs_command`).
   - downgrade: przywrócenie `grid_cohort_notice_v1` w wyzwalaczach, CHECK
     bez `retired` (odmowa, gdy istnieje kohorta `retired`), DROP tabeli
     refs, manifest v23 → v22.
2. Zapis refs w `application/grid_training_cohort_commands.py` (`prepare`,
   `_capture`) w tej samej transakcji co tablice.
3. Model ORM tabeli refs (proponowany w `storage/grid_training_cohort_models.py`
   albo istniejącym module modeli kohort).

**Acceptance criteria:**
- [ ] Na danych testowych z ≥ 3 kohortami zapis geometrii planszy przez
  `save_review_item` jako `game_predictor_app` daje te same wiersze
  `grid_training_cohort_events` (cohort_id, kind, board/review/cell/source,
  `document`) co `grid_cohort_notice_v1` dla tych samych zmian.
- [ ] `EXPLAIN` zapytania wyzwalacza jako `game_predictor_app` nie zawiera
  `Seq Scan` na refs ani na members.
- [ ] Backfill: liczba refs = liczba par z tablic dla każdej kohorty i
  rodzaju; migracja w górę i w dół na kopii testowej.
- [ ] Nowa kohorta (prepare → capture → freeze) ma kompletne refs.
- [ ] Brak zmian w zachowaniu `apply_board_repoint`, freeze i materializacji.

**Test cases:** równoważność v1/v2 dla każdej z 13 tabel (INSERT, UPDATE
kolumny dowodowej, UPDATE bez zmiany dowodu → brak zdarzenia, DELETE);
kohorta `preparing` przed capture; dwie kohorty z tą samą komórką → dwa
zdarzenia (DISTINCT jak dziś); RLS: inna gra nie widzi refs; regresja
`test_grid_model_evaluation_bridge_postgres.py` (notice → marks → proof).

**Verification:**

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration -k "cohort or grid_model_evaluation_bridge or game_storage_routing" -q   # timeout 600 s, uprzedzić
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_training_cohort_storage.py -q
npm run python:lint; npm run python:typecheck
npm run db:baseline:verify   # cykl migracji, timeout 600 s, uprzedzić
```

Pomiar na danych operatora (po jego migracji, osobna zgoda): pełny zapis
`save_review_item` w transakcji ROLLBACK jako `game_predictor_app` ≤ 3 s.

**Risks:** backfill ≈ 830 tys. wierszy w transakcji migracji (szacunek
30–120 s, do zmierzenia na kopii); `0163` testy asertują tekst SQL
(`tests/test_grid_training_cohort_storage.py:217, :245`) — aktualizować
świadomie.

### TASK-1191 — Wycofanie i przywrócenie kohorty (backend i API)

**Goal:** operator może przez API zobaczyć podgląd i wycofać lub przywrócić
kohortę zgodnie z regułą ochrony; wycofana kohorta nie jest używana do
treningu, oceny, publikacji ani przypisania.

**Dependencies:** TASK-1190 (schemat `retired`, tabela refs).

**Scope:**
1. Domena (proponowany `domain/grid_cohort_retirement.py`): czysta funkcja
   `retirement_decision(cohort, protections) -> allowed | blocked(reasons)`;
   powody: `COHORT_NOT_FROZEN`, `COHORT_MODEL_DEFAULT`,
   `COHORT_MODEL_ASSIGNED`, `COHORT_MODEL_PUBLISHED`, `COHORT_JOB_ACTIVE`,
   `COHORT_CONTENT_SESSION_OPEN`.
2. Storage: odczyt ochrony (default, przypisania, publikacje, joby, sesje);
   retire = blokada `grid_training_cohorts` FOR UPDATE + ponowna ocena reguły
   + DELETE refs + status; restore = INSERT refs z tablic + status `frozen` +
   zdarzenie `COHORT_RETIREMENT_GAP`. Jedna transakcja na komendę.
3. Bariery `GRID_COHORT_RETIRED`: start treningu
   (`application/grid_training_runs.py`), ocena, publikacja
   (`application/grid_model_publication.py`), przypisanie/default/powrót.
4. API w `api/grid_training_cohorts.py`:
   `POST /grid-training-cohorts/{cohort_id}/retire/preview`, `…/retire`,
   `…/restore/preview`, `…/restore` (proponowane; wzorzec istniejących
   `freeze`/`cancel`), `GET /grid-training-cohorts` zwraca status, model i
   powody ochrony. Pion: schematy, OpenAPI, klient, wrapper, test żądania.

**Acceptance criteria:**
- [ ] Kohorta `8c4d3ab4`/`7bfdd5c1`-podobna (model default, przypisany lub
  opublikowany) → podgląd `blocked` z powodem; retire odrzucony 409.
- [ ] Kohorta bez ochrony → retire usuwa jej refs, status `retired`;
  zapis geometrii jej komórki nie tworzy zdarzenia.
- [ ] Restore przywraca refs (równe tablicom) i tworzy jedno zdarzenie
  `COHORT_RETIREMENT_GAP`; publikacja oceny tej kohorty wymaga ponownej oceny.
- [ ] Trening/ocena/publikacja/przypisanie modelu z wycofanej kohorty → 409
  `GRID_COHORT_RETIRED`; odczyt historii działa.
- [ ] Wyścig: przypisanie modelu w trakcie retire → retire odrzucony
  (ponowna ocena pod blokadą); replay tego samego `idempotencyKey` zwraca
  ten sam wynik.

**Verification:** testy jednostkowe domeny, integracyjne PostgreSQL komend i
barier, `npm run openapi:generate`, `npm run openapi:check`, test żądania w
`packages/admin-api-client/test`, lint/typecheck.

### TASK-1192 — Panel kohort w Adminie

**Goal:** operator widzi kohorty z modelem i ochroną oraz wycofuje lub
przywraca kohortę przez podgląd z potwierdzeniem.

**Dependencies:** TASK-1191.

**Scope:** sekcja „Kohorty” w panelu uczenia siatek
(`apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx`
lub nowy komponent obok `grid-cohort-preview.tsx`): tabela (kohorta, data,
członkowie, model, status, ochrona), przycisk „Wycofaj” / „Przywróć”, modal
podglądu z powodami blokady i efektem („zmiany siatek przestaną oznaczać tę
kohortę”, „przywrócenie wymaga ponownej oceny modelu”), wykonanie z tokenem.
Aktualizacja `DATA_MODEL.md`, `VISION_LAB.md`, D-605.

**Acceptance criteria:**
- [ ] Kohorta chroniona: przycisk nieaktywny, widoczny powód.
- [ ] Podgląd → potwierdzenie → odświeżony status; błąd 409 pokazany bez
  zmiany listy.
- [ ] Test interakcji w `apps/admin/test-interactions` i `npm run typecheck`,
  `npm run lint` dla `@game-predictor/admin`.

## 6. Mapa wymaganie → task → test

| Wymaganie | Task | Kryterium |
|---|---|---|
| Zapis ≤ 3 s, niezależny od liczby kohort | 1190 | EXPLAIN bez Seq Scan, pomiar ROLLBACK |
| Ta sama ochrona publikacji | 1190 | Równoważność zdarzeń v1/v2 |
| Wycofanie bez utraty danych | 1191 | Retire/restore, refs = tablice |
| Brak użycia wycofanej kohorty | 1191 | 409 `GRID_COHORT_RETIRED` |
| Obsługa przez operatora | 1192 | Test interakcji panelu |

## 7. Wdrożenie (operator, osobne zgody)

1. Akceptacja wyniku i zgoda na scalenie do `main` (push w zgodzie).
2. Stop API/Admin/Reviewer/workerów → `npm run db:migrate` (backfill refs,
   czas do zmierzenia) → start.
3. Pomiar zapisu jednej planszy w Reviewerze.
4. Osobna decyzja, które kohorty wycofać. Według stanu z 2026-11-12
   kandydaci to `862f79ce`, `dae22c06`, `ea423f8a`, o ile ich modele
   (`0ce39122`, `9992a316`, `1be01f29`) nie są opublikowane ani przypisane;
   `8c4d3ab4` (`3ed60010`) i `7bfdd5c1` (`bf327cfa`) są chronione.

## 8. Ryzyka i niewiadome

- Czas backfillu na danych operatora nieznany (szacunek 30–120 s); zmierzyć
  na kopii testowej przed wdrożeniem.
- Czy `grid_model_publications` ma pojęcie wycofania publikacji — wykonawca
  TASK-1191 ustala z kodu i, jeśli go brak, każda publikacja chroni.
- Pozostały koszt zapisu (bez wyzwalacza) szacowany na 1–3 s; jeśli pomiar
  pokaże więcej, przyczyna jest poza tym planem (np. `apply_board_repoint`).
- Koszt prac: trzy taski, migracja z backfillem, pion API i UI, trzy audyty;
  rząd wielkości kilku godzin pracy agenta.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1190 | claude-opus-5-5 | high | Migracja z RLS, partycjami, backfillem i równoważnością wyzwalacza; ryzyko danych i ochrony publikacji. | gpt-6.1-sol/high — audyt zmian Claude |
| TASK-1191 | claude-opus-5-5 | high | Reguła ochrony modeli, bariery w kilku modułach, wyścigi i pion API. | gpt-6.1-sol/high — audyt zmian Claude |
| TASK-1192 | claude-opus-5-5 | medium | UI według istniejących wzorców panelu i gotowego kontraktu API. | gpt-6.1-sol/medium — audyt zmian Claude |
