---
title: Current state archive 2026Q4
status: archive
last_updated: 2026-10-09
---

# Current State — archiwum 2026Q4

Archiwum sekcji przeniesionych z `ai_docs/process/CURRENT_STATE.md` przy
wprowadzeniu okna kroczącego (TASK-0938, wejściowy HEAD `8629be40`). Zakres: 91 sekcji, które zaczynały się w źródle powyżej sekcji „D-470 / D-471” (wiersz 2455), czyli wpisy datowane 2026-10-01 .. 2026-10-09 (IV kwartał).
Tekst sekcji jest przeniesiony bez zmian (byte-identyczny), w kolejności z pliku
źródłowego (najnowsze na górze, starsze tory na dole); nowsze sekcje `done`
ponad limit 10 dopisuj na początku najnowszego pliku archiwum. Aktualny stan:
[CURRENT_STATE.md](../process/CURRENT_STATE.md).

### TASK-0936 — rozwinięcie super symbolu i koszt per pozycja (done)

- Commit v1.7.280 / 8629be40e01d49a230ec703d27b89057d37d6d73.
- `wild_super_spins.evaluate_series_board`: `k` kolumn z X na planszy
  oryginalnej; przekształcenie tylko przy `k ≥ minimum(X)` (kolumny
  wypełnione X, przykrycie usuwa symbole pod spodem); linie na planszy
  rozwiniętej, sztuki na oryginalnej, wygrane liniowe X zastąpione
  `payout_line(X, k) × liczba linii`; `payout_kind`: w serii `provisional`
  bez super symbolu, przy nieświeżym stanie (wtedy wszystkie plansze gry,
  także bazowe — decyzja leada wg planu) albo z jakąkolwiek nieznaną komórką;
  `exact` tylko dla pełnej planszy. Lustro TS `packages/shared-ts/src/super-game.ts`;
  16 złotych przypadków `wildSuperSpinsScenario` w Pythonie i TS. D-537.
- Projekcja per pozycja (`domain/sequence_mode_projection.py`) z zapytania
  znaczników (jeden snapshot): koszt 0 w serii, trigger z kosztem normalnym;
  §D sumuje koszt per pozycja, wyniki prowizoryczne poza bilansem z osobną
  sumą i licznikiem; `superSpinRanges`/`superSpinCost` w podsumowaniu (Admin,
  udostępnienie, panel, zapisane wyniki); wykres, piny i wkład liczone z tych
  zakresów; modal pokazuje planszę rozwiniętą i wiersz rozwinięcia.
  Kalkulator, szczegół planszy i panel czytają w jednym snapshocie
  `REPEATABLE READ` (dla wszystkich gier; 777 bajt w bajt bez zmian —
  test regresji ze skrótami z v1.7.279).
- Audyt Codex gpt-6-astra / high: runda 1 REVISE (3 × P0: koszt darmowych
  spinów w wykresie i pinach, wkład przy starcie w serii, wspólny snapshot),
  runda 2 PASS, P2 miniatury zaakceptowane (`ai_docs/quality/TASK-0936_AUDIT_gpt-6-astra*.md`).
  Worker 118, API 305 + PG 13, shared-ts 65, board-search-ui 94 + 62, Admin
  733 + 188, Reviewer 240 + 40, klient 105, `openapi:check`, typecheck
  (mypy 851), lint, format, fixture PASS.
- Etap S-C zamknięty. Następne: TASK-0938/0939 (etap T), TASK-0937 (pilot,
  wymaga etykiet operatora).

### TASK-0935 — oznaczenie supergry w wyszukiwaniu plansz (done)

- Commit v1.7.278 / bf0dd8617b449da7109b4b438f46b6ea7433bb3c.
- API: wyniki wyszukiwania i wiersze przybliżonej wygranej niosą opcjonalne
  `superGame` (`trigger` | `in_series`, `spinIndex`, `seriesLength`,
  `superSymbolCode`, `completeness`, `runVerification`, w Adminie `seriesId`),
  a każda odpowiedź `superGameState { fresh, inputVersion, generationInputVersion }`;
  jedno zapytanie SQL (LATERAL po serii pokrywającej pozycję) daje znacznik i
  świeżość z jednego snapshotu. Trasy publiczne (udostępnienie, panel) bez
  `seriesId` (osobny model / `response_model_exclude`, strażnik parametrów).
  Zamrożone wyniki panelu bez znaczników; skróty treści 777 bez zmian.
- UI (`board-search-ui`): złote wyróżnienie kart i wierszy, etykiety
  „Supergra: trigger / spin k/len, symbol X / super symbol do zdefiniowania”,
  dopiski o serii niekompletnej i triggerze z predykcji, baner dla całego
  wyniku (także pustego) przy `fresh = false`; link „Zdefiniuj super symbol”
  / „Pokaż serię” tylko gdy źródło danych deklaruje `superGameSeriesHref`
  (Admin), Reviewer i panel tylko etykieta. Cache wyszukiwania Reviewera
  pomijany dla odpowiedzi ze znacznikiem lub nieświeżych.
- Audyt Codex gpt-6-astra / medium: REVISE (P0 baner przy pustym wyniku,
  P1 brak akapitu w `ADMIN_APP.md`, P2 cache), wszystko naprawione w jednej
  rundzie (`ai_docs/quality/TASK-0935_AUDIT_gpt-6-astra.md`). API 281 PASS,
  PG 35 + 8 + 2, board-search-ui 85 + 60, Reviewer 240 + 40, Admin 733 + 188,
  klient 104, typecheck (mypy 850 plików), lint, format PASS.
- Etap S-B zamknięty (TASK-0933–0935). Następny: S-C / TASK-0936.
### TASK-0934 — sekcja „Supergry” w Adminie (done)

- Commit v1.7.277 / 9a2bbc685e2763553ce31b621c5e3c112e78e671.
- Nowa sekcja gry `super-games` (tylko dla gier z rodzajem supergry):
  lista serii z kursorem, filtrami (kompletność, weryfikacja przebiegu,
  symbol zdefiniowany) i licznikiem „do zdefiniowania”; „Przelicz serie” z
  baner „Serie w trakcie przeliczania” (polling stanu co 5 s); widok serii
  z karuzelą trigger + wszystkie pozycje (karty „brak planszy”, retriggery),
  komórki symbolu uruchamiającego podświetlone, modal linii; wybór super
  symbolu (tylko zwykłe symbole, cyfry `1`–`9`/`0`, `Enter`), zapis z
  `expectedRevision` (409 → odświeżenie bez nadpisania), „Wyczyść symbol”.
  Link z wyszukiwania: `?workspace=games&game=<id>&section=super-games&series=<id>`.
- Odpowiedzi zapisu związane z cyklem otwarcia serii (także nawigacja
  historią), strony listy z generacją ładowania, lista odświeżana po zmianie
  symbolu zgodnie z filtrem, obraz planszy związany z rewizją szczegółu.
- Audyt Codex gpt-6.1-sol (zamiast gpt-6-astra: „at capacity”): runda 1
  REVISE (3 × P0 opóźnione odpowiedzi/filtry/strony, P1 mapowanie cyfr —
  decyzja: cyfry = lista zwykłych symboli z selecta), runda 2 jeden P0
  (historia przeglądarki) naprawiony; `ai_docs/quality/TASK-0934_AUDIT_gpt-6.1-sol*.md`.
  Admin 733/733, interakcje jsdom 19/19 (`npm run test:geometry`), typecheck,
  lint, prettier PASS. Bez uruchomienia na żywym API.
- Otwarte drobne: polling także przy ukrytej karcie; kwoty w modalu linii
  jako „N kr.” (formatter złotówek nieeksportowany z `board-search-ui`).
### TASK-0933 — wyprowadzanie serii supergry i API serii (done)

- Commit v1.7.276 / 221e43ed0c645c218e84b2bee34785608ef04f1d.
- Migracja `0152_super_game_series` (manifest v6 = v5 + 4 tabele gry:
  `super_game_series`, tabela robocza generacji, stan wyprowadzania, audyt
  super symbolu; partycje i RLS dla istniejących gier; strażnik schematu
  wymaga `0152`). D-536.
- Licznik `input_version` per gra podbijany w tej samej transakcji w 10
  punktach zapisu (lista w kodzie, test statyczny w obie strony, test PG na
  12 realnych operacjach z rollbackiem); nieaktualność = porównanie z wersją
  generacji. Job `super_game_series_derive` (lane general, dedup na grę)
  buduje generację partiami (5000 pozycji / 500 serii), publikuje w jednej
  transakcji pod `FOR UPDATE`, odrzuca kandydata przy zmianie wersji.
  2000 pozycji / 30 serii: ~1 s, szczyt pamięci 0,27 MB.
- API `/api/v1/admin/games/{gameId}/super-game-series` (lista z kursorem i
  filtrami, `/derive`, `/{seriesId}/boards`, `PUT /{seriesId}/super-symbol`
  z CAS, `/state`); OpenAPI, klient i wrappery; etykieta joba w Adminie.
  Pole `superGameState` w odpowiedziach wyszukiwania przeniesione do
  TASK-0935 (decyzja leada po audycie).
- Audyt Codex gpt-6-astra / high (pierwszy audyt przez CLI): runda 1 REVISE
  (P0: brak podbicia przy zmianie `expected_layout_count`, kompletność na
  końcu sekwencji; P1: testy punktów zapisu, `superGameState`), poprawki w
  jednej rundzie, runda 2 w `ai_docs/quality/TASK-0933_AUDIT_gpt-6-astra.md`.
  Runda 2 i 3 (zawężone): cztery P0 współbieżności (odczyt parametrów pod
  blokadą stanu; wyścig blokady czyszczenia — wyłączenie usunięte, job
  blokuje jak każdy; odczyty w snapshocie RR), wszystkie naprawione i pokryte
  testami PG; commit po rundzie 3 bez kolejnej rundy (reguła szybkiego
  audytu, decyzja leada). Raporty rund w `ai_docs/quality/`.
- Wdrożenie u operatora: stop API/worker/Admin → `npm run db:migrate` (0152,
  manifest v5→v6) → start → `POST …/derive` dla Mumii (komórki sprzed
  migracji nie podbiły licznika).

### TASK-0940 — zielona bramka `npm run quality` (done)

- Commit v1.7.273 / 60ba1f74de09d82d159f42bf9706240dcb662123.
- Pełna bramka zielona: format (Prettier `endOfLine: auto` dla checkoutu
  autocrlf), openapi, lint, typecheck (mypy 836 plików po naprawie
  konfiguracji i 79 realnych błędów typów bez ogólnych ignore), testy JS,
  snapshot/fixture; API pytest z PostgreSQL 2725 PASS, worker 2781 PASS.
- Naprawy u źródła: współdzielony `services/test_support/` (helper V7,
  `require_local_corpus`), `services/api/tests/conftest.py` (loggery po
  Alembic), tabele `semi_automatic_selection_v7_*` jako `POST_V5_SHARED`
  w manifeście v5, `EXPECTED_PUBLIC_TABLES` i testy PG dostosowane do
  migracji bez downgrade (0148–0150), testy zaktualizowane do bieżących
  reguł z cytatem taska (TASK-0925, 0882, 0885, 0805, v0.10.298…).
- Łańcuch sum dowodów `ai_docs/quality/*.json` przepięty z CRLF na LF do
  punktu stałego (78 plików, tylko wartości sha256); nowy checker
  `scripts/check_quality_evidence_digests.py` + tabela
  `evidence-digest-references.json` + test workera pilnują dryfu.
- Audyt claude-opus-5-5 / high: runda 1 REVISE (P0: skip ukrywał błąd
  łańcucha), runda 2 jedna P1 (punkt stały), domknięta i zweryfikowana
  (`ai_docs/quality/TASK-0940_AUDIT_claude-opus-5-5.md`).
- Odłożone jawnie: 3 testy historycznych migracji (skip z powodem), testy
  korpusów M5 bez korpusu, test junction tylko w worktree.
- Następny etap: S-B (TASK-0933 → 0934/0935), zgodnie z poleceniem operatora.

### TASK-0932 — ewaluator `payout-v4-wild-count` (done)

- Commit v1.7.270 / 123953086aa11ba8454489298b1b4f1015128d4c.
- `services/worker/.../domain/payout.py`: symbole z rolą uruchamiającą poza
  liniami; Wild bez zmian (ta sama komórka jako różne symbole na różnych
  liniach, same Wildy nie wygrywają); nowe `count_matches` (największa
  reguła ≤ liczbie sztuk, komórki `0` nie liczone); suma linie + sztuki.
  Wersja per gra: bez triggera wyniki i wersja identyczne z v3 (777 bez
  zmian), z triggerem `payout-v4-wild-count`. Lustrzany ewaluator TS
  `packages/shared-ts/src/payout.ts`; 10 złotych przypadków v4 w
  `domain-fixtures` wykonywanych w Pythonie i TS.
- API: `countMatches[]` w szczególe planszy i wierszach przybliżonej wygranej;
  `rulesVersionId` (draft/published tej samej gry) w modalu linii i
  przybliżonej wygranej Adminu; udostępnienie i panel publiczny odrzucają
  parametr (422), proxy Reviewera 403. UI: select „Wersja reguł” tylko w
  Adminie, sekcja „Sztuki na planszy”, „w tym sztuki” w wierszach.
- Nieobjęte (jawny follow-up): prekomputacja v4 (job wypłat, `layout_payouts`,
  snapshot mobilny) — strażnik `PAYOUT_ALGORITHM_GAME_MISMATCH` odrzuca job
  v3 dla gry z triggerem; `create_payout_job` nadal tylko v3. Panel
  zarządzania (format v1) nie pokazuje rozbicia na sztuki, wypłata wiersza
  je zawiera.
- Audyt claude-fable-5-1 / high: PASS, 4 × P2 naprawione, 4 odstępstwa
  zaakceptowane (`ai_docs/quality/TASK-0932_AUDIT_claude-fable-5-1.md`).
  Worker 88, API 101, shared-ts 46, board-search-ui 80+51, Admin 679/679,
  `openapi:check` aktualne. Istniejące wcześniej: 2 testy kontraktowe
  Reviewera, `main.py:2005` mypy.
- Etap S-A zamknięty. Operator może testować Wild na drafcie Mumii
  (instrukcja w Outcome TASK-0931 i TASK-0932) po wdrożeniu migracji 0151.
  Operator 2026-10-08: migracja 0151, `npm install` i `worker:poll` wykonane;
  zaakceptował TASK-0940 (zielona bramka) i polecił przejść od razu do etapu
  S-B bez pytań o zgodę; TASK-0938/0939 po S-B.

### TASK-0931 — Wild, „Uruchamia supergrę” i rodzaj supergry (done)

- Commit v1.7.268 / 1aef5870ee22287b0e17f1278276cddf7793a9b5.
- Migracja `0151_super_game_roles` (addytywna): `symbols.super_game_trigger_count`
  (null/3/4/5) i `games.super_game_kind` (domyślnie `none`); strażnik
  schematu startowego wymaga teraz `0151`. Rejestr rodzajów supergry w
  `services/worker/.../domain/super_games/` (`none`, `wild_super_spins`:
  10 spinów, +10 przy retriggerze, koszt 0).
- Domena: zmiana ról Wild/trigger dozwolona tylko bez opublikowanej lub
  zarchiwizowanej wersji reguł; rola trigger wymaga rodzaju gry ≠ `none`
  (`SUPER_GAME_KIND_REQUIRED`, `SUPER_GAME_KIND_IN_USE`); symbol trigger ma
  `minimum_match_length = null`, a jego wypłaty znaczą liczbę sztuk
  2…rows×columns (rosnące); przy zyskaniu roli minimum w draftach jest
  czyszczone w tej samej transakcji. 777 bez zmian zachowania.
- API: pola w schematach gry i symbolu (`superGameTriggerCount` wymagane,
  `superGameKind`), `GET /api/v1/admin/super-game-kinds`, OpenAPI i klient
  zregenerowane, wrapper `listSuperGameKinds`, request testy. Admin: etykieta
  „Wild”, checkbox „Uruchamia supergrę” + select 3/4/5, select „Supergra”
  w tworzeniu i edycji gry, pola „sztuk na planszy” w regułach.
- Audyt claude-fable-5-1 / high: PASS, 4 × P2 naprawione, 8 odstępstw
  zaakceptowanych (`ai_docs/quality/TASK-0931_AUDIT_claude-fable-5-1.md`).
  Pytest skupiony 72 PASS, PG katalog 4 PASS, cykl migracji na bazie
  jednorazowej OK, `openapi:check` aktualne, Admin 679/679, Reviewer
  typecheck PASS.
- Wdrożenie u operatora (po merge): zatrzymać API/Admin, `npm run db:migrate`
  (0147→0151 na bazie operatora wymaga osobnej zgody, patrz TASK-0928),
  restart. Nie publikować reguł Mumii przed TASK-0932 (stary ewaluator liczy
  Mumię jako symbol liniowy). Instrukcja operatora w Outcome taska.

### TASK-0929 — skill audytu krzyżowego i sekcja „Audyt krzyżowy” (done)

- Commit v1.7.267 / 6323939f41d93501a537463eb82ce127ab1f04b3.
- `scripts/audit_task.ps1` (PowerShell 5.1, ASCII, limity czasu, UTF-8)
  składa brief taska (plik taska, fragment planu, `Verification results`,
  diffy ograniczone `-Paths`, pliki nieśledzone) do ignorowanego
  `artifacts/audits/` i uruchamia audytora tylko do odczytu (`codex exec
  --sandbox read-only` lub `claude -p --permission-mode plan`); raport trafia
  do `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` tylko z wierszem werdyktu.
  Bez CLI na PATH tryb „tylko brief” (kod 0). Skille `.claude/skills/audit-task`
  i `.codex/skills/claude-audit`; szablon `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.
- `AGENTS.md`: sekcja „Audyt krzyżowy” (rodziny modeli, zastępstwo subagentem
  Claude do czasu CLI, jedna runda audytu + jedna poprawek, otwarte P0/P1
  blokują commit, wyjątek czasowy 600 s dla przebiegu audytu); punkt 8
  „Po kodowaniu” ujednolicony.
- Audyt claude-opus-5-5 / high: runda 1 REVISE (2 × P1: `-Paths` z przecinkami,
  wstrzyknięcie przez `-Model` na shimach `.cmd`; 5 × P2), po poprawkach
  runda 2 PASS; 3 × P2 naprawione przez leada. Prawdziwe CLI `codex`/`claude`
  nie są zainstalowane: operator instaluje i loguje je sam, potem jeden
  przebieg bez `-DryRun` z zapisem wersji.
- Etap P zamknięty. Trwa TASK-0931 (etap S-A).

### TASK-0930 — klawisz `0` dla dziesiątego symbolu w weryfikacji symboli (done)

- Commit v1.7.266 / ad058e23a487a70f543636c6b024d779006c9bdb.
- W weryfikacji symboli `0` wybiera dziesiąty aktywny symbol (Mumia) jako
  `Symbol do zatwierdzenia`; etykiety w selekcie i pasku skrótów pokazują `0`.
  Nowe helpery `extendedDigitShortcutIndex/Label` w `apps/admin/src/lib`;
  wyszukiwanie plansz bez zmian (`0` = nieznany).
- Admin: testy 668 PASS, typecheck i lint PASS. Audyt niezależny
  claude-opus-5-5 / medium: PASS, 4 × P2 naprawione przed commitem
  (`ai_docs/quality/TASK-0930_AUDIT_claude-opus-5-5.md`); uwaga o opisie w
  `symbol-catalog.tsx` przekazana do TASK-0931.
- Etap S-0 zamknięty. Równolegle trwają TASK-0929 (etap P) i TASK-0931 (S-A).

### TASK-0927 — Integrated acceptance and operator guide (done)

- Final requirement/evidence matrix covers the accepted T1–T7 implementation.
  Focused backend31 and broader94, isolated application-role PostgreSQL3 with
  true child-process reads, shared49 interactions/77 units, local25 and public13
  rendered tests, generated requests5, contract drift, scoped quality/types and
  final isolated Admin/Reviewer builds pass. Independent astra/high PASS.
- Real Chrome touch emulation at390px checks six complete flow stages without
  horizontal overflow using actual shared React/CSS. Management controls use
  existing theme variables and44px touch targets. This is mock-data browser
  evidence, not physical Android or live-public acceptance.
- Full Reviewer233/235 pass; two pre-existing source-contract failures reproduce
  on baseline and remain outside scope. The five former loopback failures pass
  with test-only permissions. No unresolved delivery P0–P2.
- Durable browser runner and operator guide are committed. Additive migration
  graph, binary backup, restricted role and manual service/link rollout are
  explicit. Physical phone/live ingress/reboot and production timings remain
  operator checks. No user services, production migration/data, deployment,
  hosting, Redis, push or merge. Commit receipt follows actual branch history.

### TASK-0926 — Complete recipient panel (done)

- Shared hierarchy, cards, game search/save/correction, immutable result and
  journal components plus management CSS serve both thin local Admin wrapper
  and the dedicated Reviewer /management gate. Local link controls stay local.
- Generated public adapter and machine-bound transport preserve the originating
  session identity for requests/assets. Journal displays retained human labels
  locally and online while receipts retain stable UUID actor identity.
- Session termination blocks new reads/writes and obsolete callbacks without
  discarding mounted drafts, acknowledged history or uncertain operation
  identities. Per-session/per-tab recovery prevents mixing browser tabs/links.
- Focused rendered recipient and existing local/shared/Reviewer regressions,
  scoped format/lint/types and independent astra/high PASS are recorded in
  completed Outcome; no unresolved P0–P2. Next T7 integrated acceptance.
- Completion v1.7.258 / ce64a194e4c7a806c59df25e90b2b174666321b4. No live service lifecycle,
  production migration/data operation, deployment or accounts.

### TASK-0925 — Panel sessions and48/72-hour links (done)

- Independent multi-game capability sessions, separate code/token/cookie and
  stable sessionUUID actor. Local-only link creation/list/revoke, five failed
  codes lock access. New lifetimes1/4/8/24/48/72h, default8; old one-game shares
  gain48/72h options without changing scope or existing expiry timestamps.
- Allowlisted public API and Reviewer management proxy check expected session
  identity, machine/game ancestry and live association for current operations.
  Retained history remains scoped without requiring a live game. Public data
  excludes storage paths, secrets and internal review IDs.
- Mutation flush and locked session revalidation precede commit. Access failure
  cannot become stale-success. Shared ingress retention protects active panel
  and board-search links when the final Reviewer assignment closes.
- Bounded request/response streams, origin checks, dedicated secure cookie;
  obsolete401 responses cannot clear a newer session in another browser tab.
- Additive0150 migration and startup schema guard aligned. Backend/OpenAPI,
  generated client, wrappers and request tests update together. Focused evidence
  and independent astra/high PASS are recorded in completed Outcome.
- Completion v1.7.257 / a829b2e5a90f3c7c09c696ec3ca83bce44ce0213. Next T6 / TASK-0926.
  No live services/tunnel, production migration/data writes or deployment.

### TASK-0924 — Stake overview and retained history (done)

- Selected machine/game loads six compact cards, saved board/pins/date and
  at most two cancellable current refreshes. Full immutable chart/rows load only
  on Open/history; rows paginate50 and journal defaults20. No eager point charts.
- Search draft reuses T3, explicit host Save and confirmed slot-only Clear.
  Per-tab recovery keeps exact UUID/body/CAS through response loss and reload.
  Conflicts retain the draft; acknowledged retry advances only its own revision.
- Cards and visible saved result share scope/revision gates. Late refresh cannot
  undo Save/Clear; old lost-response receipts retain newer data and mark stale
  with recheck instruction. Capability changes preserve dirty draft read-only.
- Frozen history preserves prior numeric values; current editor uses fresh
  fixed-stake rules and explicitly labels global current-data corrections.
  Internal and outer tab/popstate navigation guards preserve cancelled drafts.
- Focused interactions19 plus existing management4 PASS, direct Admin types and
  scoped lint/format PASS; final broader evidence is in completed task Outcome.
  Independent sol/high review PASS, no unresolved P0–P2.
- Completion v1.7.256 /71931a1b8fdf5830f761736ca26f1666acc14d5b. Next T5 / TASK-0925.
  No backend contract change, service lifecycle, production migration or build.

### TASK-0923 — Shared search with explicit Save (done)

- Optional fixed stake, trusted saved start/query/range, controlled0–6 spin pins
  and explicit Save callback preserve existing default consumers. Browsing,
  hover and pins never autosave. Save failure retains draft and blocks duplicates.
- Stable scope protects drafts from background snapshots and obsolete responses;
  delayed symbols cannot overwrite edits. Dirty composition/range/pins warn on
  page exit and expose a host navigation guard. Current symbol corrections stay
  immediate and trigger calculation refresh; both modals use fresh spin cost.
- Focused managed interactions10 PASS; all shared interactions49 and unit77
  PASS. Scoped formatting/lint/shared and direct Admin/Reviewer types pass.
  Independent sol/high review PASS; no unresolved P0–P2.
- Completion v1.7.255 /85a8914dc2195e986f4c807c4a0cb468e9f312de. Next T4 / TASK-0924.
  Sandbox SWC route typegen AccessDenied is recorded; no routes changed.
  No service lifecycle, production data writes or full build; builds remain T7.

### TASK-0922 — Durable stake selections (done)

- Six independent slots, server-validated search contexts, compact immutable
  deduplicated results, Save/Clear/Refresh and paginated retained journal.
  Existing calculator and human writer supply current data; correction/audit
  and slot/result/receipt/audit commit atomically. Additive migration0149.
- READ COMMITTED receipt visibility; bounded read-only RR snapshot on the same
  application-role engine with NullPool. Stored history reads avoid current
  game routing; trusted same-slot/context/start can be edited by another actor.
- API/calculator/search regressions95 PASS, real app-role PostgreSQL1 PASS
  (19.57s), wrappers4 PASS, scoped mypy8/lint/format/types and contract drift PASS.
  Independent astra/high review PASS, no P0–P2. PG verifies lost-response retries,
  CAS, rollback, zero hits, coherent races, stale results and process restart.
- Completion v1.7.253 / 1a93bc521316c92eaaed8443e26e2f382a72c25a.
  No live services/data, full build or public rollout.
  Earlier V7 ownership omissions remain outside scope. Next T3 / TASK-0923.

### TASK-0921 — Management points and machines (done)

- Local Panel Administracyjny tab has editable point/machine hierarchy,
  active-game assignments and archive/restore with retained detached history.
  Additive migration0148 creates shared metadata and immutable audit/receipts.
- UUID/actor/target/body checks, point-first locks and expected revisions protect
  retries and concurrent writes. Commit precedes HTTP success; per-tab pending
  commands survive reload and ambiguous5xx without losing retry identity.
- Backend/actual PostgreSQL app-role5 PASS, rendered UI4, wrapper request1,
  Admin/client types, scoped Ruff/mypy/ESLint pass. Independent sol/high review
  has no open P0–P2. PostgreSQL verifies fresh-process reload and concurrency.
- Earlier unmapped V7 tables still fail the broad ownership gate; new shared
  tables are classified. Full transitive mypy reaches unrelated worker errors;
  scoped changed modules pass. No user service lifecycle or production migration.
- Completion v1.7.252 / c708c6e63d8ee00c8a879b0beab4ed73a62fcd62.
  TASK-0928 concurrently consumed v1.7.251. Next TASK-0922 / T2, whole plan authorized.

### TASK-0921–0927 — Management panel implementation (done)

- User explicitly started the complete accepted T1–T7 plan on2026-10-07.
  D-533; delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md and dedicated requirements/
  architecture/MANAGEMENT_PANEL.md. Point → machine → active game → six stakes.
- Explicit Save only; draft pins/browsing, confirmed slot-only Clear, immutable
  prior results and retained journal, current recalculation, UUID/revision guards.
  Whole-panel named recipient, local link administration,48/72h plus old shares.
- Executors/reviewers follow accepted model table. T1–T7 implemented, audited and delivered; operator rollout remains manual.
- Startup schema guard now requires `0150_management_sessions`; the earlier
  T2 guard required `0149_management_stake_saves`. Fix v1.7.254 / `3cb140dd874ffd6378c009aa1152a9001fed6b48`;
  schema-readiness tests 12/12 PASS. API was not started.
- T2 mutations use READ COMMITTED for UUID-lock retry visibility. A bounded
  read-only REPEATABLE READ application-role session captures coherent numeric
  snapshots; primary transaction commits result/slot/receipt/audit atomically.
  Baseline branch v1.7.250 /88d5019c7e436e5bd2895220d8fe0187f9ea177a;
  pre-existing modified CURRENT_STATE/completed task receipts remain user-owned.
- No API/Admin lifecycle, production migration/data edits, hosting, push/merge,
  model activation or destructive operation is included. Live rollout user-run.

### TASK-0920 — pełna integracja V7 na głównym branchu (done)

- v1.1-vision-lab-hybrid-geometry now contains the complete calibrated V7
  engine, independent progress, output picker, full editable draft coverage,
  quick explicit approval and saved-folder review. 131 product/test files
  integrated three-way from b087ad08b62992c54f5e26191e6408d287b64273;
  later main work and pre-existing working metadata retained.
- Immutable migration branches join at 0147_merge_v7_main; no online upgrade
  or gate activation. Merged backend/OpenAPI/generated client/wrapper agree.
- Snapshot suites: 814 PASS. Fresh main processes: API 62, writer/recovery 75,
  rendered UI 62 PASS; strict changed-source mypy (46), Admin/client types,
  scoped lint/format and contract drift PASS. Offline graph/DDL verified.
- D-532; V7_BRANCH_INTEGRATION_PLAN.md;
  completed/0920-v7-main-branch-integration.md contains Outcome and manual steps.
- No data/profile/acceptance transfer, JPEG writes, service lifecycle, SQL
  upgrade, monitoring, activation, full build or push. Main runtime needs the
  user-run migration and its own verified configuration; existing WT untouched.
- Completion v1.7.250; full commit hash recorded after committing.

### TASK-0919 — wejście do działającego półautomatu V7 (done)

- Main3000 offers "Otwórz półautomat V7" to working calibration Admin3020.
  Main API8000 remains blocked/v1; pilot8020 is active/v2. Local-only navigation
  transfers no game/run identities and preserves existing main run/crop flows.
- Focused helper/form/contract tests 19/19, rendered regressions 6/6 and
  Prettier/scoped ESLint/full Admin types PASS. Remount/browser-free SSR verified.
- Actual user's URL3000 ->3020 has enabled source/output pickers, saved folders,
  estimated draft JPEG and neighbour correction. Main reload preserves entry;
  no run start or decision. Existing file-name coverage: 3135/3135 and 3190/3190.
- D-531; V7_MAIN_PANEL_TEST_ENTRY_PLAN.md; completed/0919-v7-main-panel-test-entry.md.
  Evidence artifacts/v7-main-panel-entry-20261007/. No service lifecycle, model
  activation, data transfer, merge, monitoring, push/deployment or full build.
- Completion v1.7.249; actual hash recorded after commit.

### TASK-0904 — indexed symbol confidence reads (done)

- Shared confidence-filtered SQL now exposes the existing partial index's
  `source_available` predicate. NULL/outside semantics, filters, stable order,
  page caps and 20 s/15 s runtime guards are unchanged; no migration needed.
- Exact 777 / Wiśnia / pending / below 60% / limit 2500 GET: HTTP 503 at
  20.207 s before, HTTP 200 with 939 items at 4.574 s after (later 0.312 s).
  Read-only 500 + 439 pagination matches the complete page without duplicates.
- Actual Admin browser view shows all 939 pending items and rendered crops.
  Focused 51/51, PostgreSQL cancellation 1/1, scoped Ruff and strict mypy PASS.
  Related suites: 140 PASS, one pre-existing 5 s-test/20 s-config mismatch.
  Full transitive mypy reaches 120 s with unrelated logging/geometry errors;
  scoped checks pass. Existing timeout policy and tests were not weakened.
- Saved source verified in fresh test/client processes; no agent API/Admin
  lifecycle operation, domain data write, push or merge. Evidence and screenshot:
  artifacts/symbol-review-list-timeout-20261007/. Completion v1.7.248;
  full hash is recorded after commit.

### TASK-0903 — user-controlled API and Admin (done)

- User revoked agent-managed API/Admin lifecycle. AGENTS.md now requires a
  separate explicit current request for any agent start, stop or restart;
  generic repair/testing and historical restart approval do not grant it.
- Verified this chat's API launcher 15980 and server 29900, then stopped only
  those processes. Both are absent; port 8000 was free after cleanup.
  Admin, workers, import jobs, data and configuration were left untouched.
- Local operation guide preserves `npm run api:dev` / `npm run admin:dev`
  in user-owned terminals. No replacement server was launched for verification.
- Documentation and process/listener checks only; no product-code change,
  migration, tests requiring service startup, push or merge.
- Completion v1.7.247; full commit hash recorded after commit.

### TASK-0910 — audited import report performance plan (done)

- Proposed plan: IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md. Eight dependent
  tasks cover immutable source/geometry indexes, single-request validation,
  range-bound canonical/job queries, game-scoped staging catalog, local
  cross-process source locking, fast API/Admin views and acceptance/rollout.
- Explicit user authorization for gpt-6-astra / high audit. Seven P1/P2 design
  findings were incorporated; final independent review has no open P0–P2.
  Review: IMPORT_REPORT_PERFORMANCE_ASTRA_REVIEW_20261007.md.
- Existing file-only audit measured 19.870 s manifest validation and 3.606 s
  source hashing. The proposed 2 s overview / 5 s canonical targets are not
  measured HTTP/SQL results. Live SQL/HTTP and restart/race tests remain gates.
- Plan is proposed for independent Claude Code review and user acceptance;
  model assignments do not authorize implementation. No product code, data,
  migration, service restart, training, cleanup, activation, push or merge.
- Documentation path checks: 38 valid links; eight tasks/eight model rows.
  Initial commit v1.7.245; de62ef98ff5131102b417afdd3cd2564d7526ecc.
  Numbering/format follow-up v1.7.246; hash recorded after commit.

### TASK-0902 — read-only owner lookup during unrelated maintenance (done)

- The exact Mumie staging and completed preflight belong exclusively to Mumie.
  Its active store is writable; the failing owner probe accidentally requests
  WRITE on the independent 777v2 store, which remains `migrating`.
- Known owner SELECTs are typed reads. RLS, explicit game predicates,
  ambiguity detection and generic unknown-SQL WRITE fences remain unchanged.
  Isolated application-role PostgreSQL 25/25 and routing/import 64/64 PASS;
  scoped Ruff format/lint and strict mypy (implementation and test) PASS.
- Controlled API restart loads the committed source; health HTTP 200.
  Authorized staging `27d385b1-1580-4ece-b815-2667da19a1b7` created exactly
  one Mumie import `d82d9aba-d59c-46f7-9ee8-8a7415565e3d`. Fresh-process
  HTTP GET 200 and scoped retention read confirm its durable Mumie ownership.
- Start took about 71 s, outlasting the diagnostic client's 55 s timeout.
  Server audit confirms success; the durable job survived response loss.
  It remains `created` in the running general worker's queue; full processing
  was not awaited. Preflight takes about 32–35 s for this large neural manifest.
- Neither 777 game was provisioned, activated, reassigned or deleted; their
  statuses remain original 777 `active`, 777v2 `migrating`. No schema/API shape
  change, model activation, cleanup, push or merge.
- Evidence: artifacts/mumie-import-409-20261007/. Completion v1.7.244;
  full commit hash recorded after commit.

### TASK-0899 — fast quality overview and independent grid (done)

- User rejected the 45-second timeout. Page entry now requests SQL-only
  current-owner logical approvals; exact cohort preparation is explicit at
  training intent. Counts do not claim pixel attestation/training eligibility.
  Grid controls mount independently of symbol loading/errors/preparation.
- D-529; plan MODEL_QUALITY_OVERVIEW_FIX_PLAN_20261007.md. Fresh-process
  read-only HTTP overview: 200 in 0.922 s, 29201 logical approvals across
  6146 boards / 1384 sources. No image reads or production writes.
- Exact preview runs only at explicit training intent and retains checksum,
  source protection and freeze guards. UI has cancellation and no arbitrary
  45-second timeout. OpenAPI and generated-client contracts agree.
- Python 64/64, Admin helpers/contracts 17/17, rendered interactions 8/8 and
  client 76/76 PASS; scoped lint/format/types and API/client drift PASS.
  Isolated Admin build PASS in 31.7 s; live build directory untouched.
- Existing API reload serves overview: HTTP 200 in 0.937 s; generated-client
  metadata reads below 0.5 s each. No manual restart/deployment was performed.
  Test browser showed independent grid but network failures also affected game
  catalog/RSC; complete live UI walkthrough is unconfirmed. Rendered grid-state
  preservation, errors, cancellation and training confirmation tests PASS.
- No production mutation, migration, training, activation, cleanup, push or merge.
  Evidence: artifacts/model-quality-overview-20261007/verification.json.
- Completion v1.7.242; full commit hash recorded after commit.

### TASK-0900 — five GiB image storage reserve (done)

- Default hard reserve for managed image operations is 5 GiB after the existing
  conservative estimate, with exactly 5 GiB remaining permitted. Warning at
  80 GiB, automatic GC at 60 GiB and browser staging's physical 512 MiB reserve
  remain unchanged.
- Capacity admission and automatic/manual storage-GC manifests now use the same
  runtime threshold. Focused policies/configuration: 70 PASS; browser import
  capacity integration: 4 PASS; scoped Ruff and policy mypy PASS.
- API, Docker and PostgreSQL were unavailable during diagnosis. The shown
  `GAME_STORAGE_WRITE_UNAVAILABLE` is a separate non-active game storage
  status; no registry mutation, restart or import retry was performed. Read it
  after controlled service start before attempting recovery.
- Completion version/hash pending commit.

### TASK-0898 — bounded model-quality loading (done)

- Exact cohort reads group sources into up to seven execution-scoped RGB
  frames shared by atomic protection/descriptor checks. No per-cell JPEG
  decode or PNG round trip. Original SQL order, manifest and eligibility stay.
  UI reads have 45-second timeout/retry, cancellation and late-response guards;
  pending reinference preview no longer blocks quality or enables an empty action.
- Fresh-process read-only Mumie preview: 32.610 s; full FastAPI GET: HTTP 200,
  39.843 s. Both select 6303 samples / 3074 boards / 813 sources, same checksum
  138a43d3290d0fcc983d57cccfeb1aabcd41647edb08b6d1182bdd18cd11c7c8.
- Python regressions 104/104 plus last changed-branch 28/28; Admin helpers/
  contracts 14/14 and rendered interactions 4/4 PASS. Scoped lint/format/types
  PASS; Admin build PASS (18.17 s). Requirements, architecture/API narrative,
  plan and completed task updated. Evidence: artifacts/model-quality-loading-20261007/.
- No production mutation, migration, training, activation, cleanup, restart,
  deployment, push or merge. Exact pixel verification still takes tens of
  seconds; running API/Admin need controlled deployment to load this fix.
- Completion v1.7.241; commit pending.

### TASK-0897 — concurrent symbol review job starts (done)

- MAIN logs confirm start/worker deadlocks at board FK insertion. Start now
  flushes FK references before catalog locking, then refreshes and revalidates
  state/targets. A per-game/idempotency-key advisory lock protects retries only.
  Page selection skips pending/settled cards. API and 10,000 per-job cap stay.
- Real isolated PostgreSQL 4/4, focused backend/API 24/24, Admin interactions
  16/16 and helpers 40/40 PASS. Format/lint/types PASS in the scoped modules;
  dependency-following mypy timed out, local module/protocol mypy PASS. Admin
  build PASS (23.58 s). Wider backend/API: 51 PASS / 1 pre-existing timeout
  assertion failure (5,000 ms expected; HEAD already uses 20,000 ms).
- Requirements, API contract, guide, plan and completed task updated. No
  production mutation, migration, training, cleanup, restart, deployment, push
  or merge. Running API/Admin need a controlled restart to load this fix.
  Evidence: artifacts/symbol-review-concurrent-jobs-20261007/verification.json.
- Completion v1.7.240; full hash is recorded after commit.

### TASK-0896 — collapsible single-row symbol filters (done)

- State/confidence/source options have one full-width row each. Radio filters
  and date have independent accessible sections, initially open. Folding keeps
  filters, drafts, selection and target; Enter on a toggle never submits save.
  Headers retain active count/date. Fullscreen retains folding and gains space.
- Fresh-process interactions 14/14 and focused Admin contracts/helpers 40/40
  PASS; scoped format/lint/types and Admin build PASS (21.12 s). MAIN browser
  confirms desktop single rows, greater crop height after folding, 390 px
  local horizontal/vertical scroll, no document overflow or console errors.
- Requirements, guide, plan and completed task updated. No API/schema or real
  data change, training, cleanup, restart, deployment, push or merge. Evidence:
  artifacts/symbol-review-filter-layout-20261007/. No task blocker.
- Completion v1.7.239; full hash recorded after commit.

### TASK-0895 — clear the target on each symbol save (done)

- `Symbol do zatwierdzenia` clears immediately on every valid save click or
  Enter, after capturing the target for direct/bulk commands. The next save
  requires a fresh selection. Pending, error/cancel, blurry/outside and bulk
  preview retain this rule; submitted commands retain their original target.
- Fresh-process interactions 13/13 and focused Admin contracts/helpers
  40/40 PASS. Scoped format/lint/types PASS; Admin build PASS in 20.17 s.
  Existing frozen-page, filter and reference/quality behavior is preserved.
- D-528, requirements, operator guide, plan and completed task updated. No
  API/schema/layout change or real data decision, migration, training,
  activation, restart, deployment, push or merge. No task blocker.
- Completion v1.7.238; full hash recorded after commit.

### TASK-0894 — unified symbol save and approval (done)

- `Weryfikacja symboli` now has one `Zapisz i zatwierdź` with an explicit
  `Symbol do zatwierdzenia`. Same-label pending becomes approved; another
  selected active class corrects and approves. D-528 applies to all games
  in this workspace, using existing reassign/mark_blurry contracts.
- Missing target/selection blocks save. Keyboard, filter target reset,
  outside/blurry exclusions, crop/revision guards, single direct saves,
  bulk preview/durable job and frozen page retain their protections.
- API domain 32/32, Admin interactions 12/12 and focused Admin 40/40 PASS;
  scoped format/lint/types and Admin production build PASS. MAIN browser
  check confirms same-Q save is enabled and the two old buttons are absent.
- No API shape/schema changes or decisions on real user crops, migration,
  cleanup, training, activation, deployment, push or merge. Updated plan,
  requirements, contract explanation, guide, inventory and completed task.
- Completion v1.7.237; full commit hash recorded after commit.

### TASK-0893 — symbol-review import folder filter (done)

- `Weryfikacja symboli` has a game-scoped `Katalog importu` selector. It lists
  only image-directory jobs through the existing local job catalog, displays a
  safe label rather than a source path and clears on a game change.
- `importJobId` now binds page, count, direct navigation, keyset cursor and
  filter-scoped bulk selection. V2 has migration `0146` with a matching
  visible-current-cells index; no data migration, cleanup or job dispatch.
- Focused API 35/35, Admin review 40/40 and API-client 75/75 PASS; OpenAPI
  drift check, scoped lint/format/types and Admin production build PASS. The
  wider API suite retains one unrelated 5 s-vs-20 s timeout assertion.
- Completion v1.7.235; full hash recorded after commit.

### TASK-0892 — shared model family requirements (done)

- User requests published Laboratory models in the game creation catalog,
  shared by compatible games such as 777 v3 and 777 v4.
- Scope assumption: record the accepted domain direction, not implement the
  Laboratory, migrate the registry or activate models. Existing profiles and
  per-game runtime remain unchanged until a separate implementation.
- D-527 separates game records, shared families and immutable versions;
  evaluated versions can be explicitly published to the game creation catalog.
  Compatible 777 games pool qualified feedback without copying weights or
  merging boards, sequences and rules. Preserve class mapping, source origins,
  family-wide held-out protection and pinned running jobs.
- Requirements/architecture and MODEL-09/10 now distinguish current per-game
  runtime from future shared integration. Grid/symbol models remain separate.
- Fresh-process documentation review and git diff --check PASS. No code/build
  tests for documentation-only scope. No data operation or model activation.
- Completion v1.7.234; commit hash recorded after commit.

### TASK-0891 — neural preflight presentation (done)

- Actual completed job1e5c0d7d uses Mumie neural Run3/iteration03-f896da7196431be2.
  Read-only immutable manifest analysis:2575 bound photos,23175 full lattices
  eligible for neural-auto-crop-v1,zero pending slots. All2575 review flags are
  NEURAL_GRID_GATE_UNCALIBRATED, not evidence of failed geometry.
- Assumption: repair UI interpretation only; keep D-523 and source truth.
  Plan: delivery/NEURAL_PREFLIGHT_PRESENTATION_EXECUTION_PLAN.md. Record user
  request for separate shared Laboratory and main DB candidate registration.
- No DB writes, API contract changes, migration, import, training or activation.
- Fixed neural proposal/lifecycle/analysis labels and actual model export.
  Closed neural preview no longer requests all source details (actual manifest
  270.98MB); optional shared-editor labels omit classical pattern calibration.
- Unit68/interaction30 PASS, scoped format/types/lint PASS (four existing
  warnings), final Admin build PASS30.20s. Fresh actual MAIN report after
  controlled API restart shows2575/2575, correct export and enabled import;
  no closed-preview review-source request. Mobile390px has no horizontal overflow.
- API parent19632, health ok; verified old owner40856/7244 stopped. No active
  job in latest30. Explicit source inspection/report validation remain costly;
  pagination is outside this UI repair. Laboratory integration recorded in
  MODEL-09, not implemented. D-526; evidence artifacts/mumie-preflight-diagnosis-20261007/.
- Completion v1.7.233; full hash recorded after commit.

### TASK-0890 — grid diagnostics placement (done)

- User explicitly places grid problems in Korekta cięcia siatki rather than
  extending Import plansz. Assumption: UI move only, existing backend queue
  qualification and neural-auto-crop-v1 remain authoritative.
- Reuse GeometryCompletenessSection in ReviewerAccessLauncher with game-scoped
  jobs and queue refresh; retain MissingBoardsSection in import. D-525 records
  placement and separates whole-image diagnostics from V3 crop availability.
- Plan: delivery/GRID_DIAGNOSTICS_PLACEMENT_EXECUTION_PLAN.md. No DB/API change,
  migration, cleanup, import/preflight dispatch, training or activation.
- Unit47/interaction20 PASS, scoped format/lint/types PASS (existing img warning
  only), final Admin build PASS (24.39s). MAIN import has no diagnostics, folder
  stays visible; correction reload and queue refresh verified. Reused responsive
  controls; proof artifacts/grid-diagnostics-placement-20261007/.
- Historical counters retain whole-image semantics; no crop-readiness claim.
- Completion v1.7.232; full commit hash pending.

### TASK-0889 — import folder recovery and V3 registration (done)

- Diagnosis: GET browser-selections fails with GAME_NOT_FOUND for finalized
  staging owned by deleted game 2a46d3a6-bc56-4a13-8f98-dd51c88df0b2.
  Actual new Mumie folder „1 - 23175 cut” has2575 files, staging b770bcc8.
- Scope: optional retention status is null only for a deleted game; preserve
  staging files/ownership and propagate other storage failures. Panel exposes
  list errors/loading/empty states and refreshes finalized folders before
  report preparation. V3 hides classical registration; V1.1 retains it.
- Accepted repair scope: delivery/IMPORT_FOLDER_RECOVERY_EXECUTION_PLAN.md.
  No new import/preflight, DB migration, cleanup or model activation.
- Backend68 and focused4 PASS; Admin unit66/interaction13 PASS. Scoped
  lint/format/types and final Admin build PASS (35.48s), existing img warning only.
- Real API root40856/listener7244, health ok. Initial10s startup probe expired;
  process subsequently ready, no duplicate API. New folder returned as ready
  and shown with report action after page reload. V3 select absent.
- Actual read-only report:2575 sources,23175 new boards, symbol model ready.
  Fresh report labels configured V3 and hides the obsolete registration metric;
  pinned classical report labels remain. No geometry/import job was started.
- Completion v1.7.231; full commit hash recorded after commit.

### TASK-0888 — current Mumie symbol feedback analysis (done)

- Read-only MAIN analysis:126 current human-approved crops from34 photos,
  versus40 at0886;122 disagree with stored predictions. This deliberately
  edited sample is not population accuracy. All126 approved/current crop
  identities and render checks match. Fourteen preview crops visually reviewed.
- Existing preview selects81 diverse samples from30 photos/62 boards,
  no stale/missing/grid/unreadable exclusions. Q,A,Mumia absent; several
  other classes lack four source families. Freeze readiness is not training
  class/split readiness. No new cohort/job/training/activation performed.
- Active lab R2 ONNX and registry verified:3 Conv layers,RGB64,10 classes.
  Earlier283 human development/84 validation remain;443 bundle files,
  6.64MB verified. Recommend a separate qualified lab candidate combining
  current exact DB feedback with earlier human corpus, without inventing
  approvals or moving held-out sources into training. DB preview alone
  does not combine lab/DB labels; no fresh user annotation request now.
- Most corrections:A→Sarkofag42,K→Faraon22,Mumia→Sarkofag15. Visual sample
  includes blur,glare,gold frames. All disagreement confidence below0.62.
- model-quality.activeModel is hard-coded null although registry is active;
  recorded as a separate presentation gap. Whole-photo versus recording
  split limitation remains explicit. MAIN application code/runtime unchanged.
- Report: quality/MUMIE_SYMBOL_FEEDBACK_ANALYSIS_20261006.md; read-only
  evidence artifacts/mumie-feedback-analysis-20261006/. Completion v1.7.230;
  full hash recorded after commit.

### TASK-0887 — V3 import presentation and application inventory (done)

- MAIN import now shows the real Mumie neural profile as V3, omits classical
  variant arguments, and reports V3 on success. 777 keeps V1.1. V1.0/V1.2
  choices and forced V1.0 UI reprocess are hidden; history/backend retained.
- Responsive picker, existing API only; game/profile remount isolates state.
  Fresh MAIN page/reload and actual 777 picker verified without real upload.
- Import unit66 and interaction8 PASS; Admin types, scoped lint, format and
  production build PASS (34.11s). Existing Next img warning documented.
- MUMIE_MAIN_APP_OPERATOR_GUIDE expanded with exact steps and pooled symbol
  training. Draft APP_V3_FUNCTIONAL_INVENTORY.md records screen changes,
  future shared online panel, neural-grid training gap and misleading legacy
  geometry readiness/completeness descriptions for separate tasks.
- Read-only storage: main51.73GB,777 partitions48.16GB,Mumie71MB. Retained
  restore-test database46.97GB,zero connections; backup13.60GB on D retained.
  Windows C free32.16GiB; Docker VHDX106.04GB. No guaranteed host-space
  recovery without separate compaction. No data cleanup/migration/training,
  activation,push,merge or other function removal performed.
- D-524; evidence artifacts/app-v3-review-20261006/. Other pre-existing dirty
  completion hashes and unrelated folders preserved. Completion v1.7.229;
  full hash recorded after commit.

### TASK-0886 — automatic Mumie import and recoverable symbol verification (done)

- New neural-auto-crop-v1 imports render exact 24-node full bound lattices
  directly into bulk symbol verification. Missing or partial slots defer
  individually without shifting sequence numbers. Predictions remain separate
  from human approval. Legacy policy and 777 UI defaults are preserved.
- Managed reprocess validates neural schema5/v13 evidence, pins the policy
  and retries the same job. Per-sequence owner protection preserves current
  manual grids and symbol decisions; old unreviewed pending remains audited.
- MAIN Mumie recovery: 100 originals, 99 bound sources, 891 current boards,
  13,365 cells, zero failures, ready projection and exact counters. Reprocess
  af474e46-28bc-404d-af1c-07aeb05a165c completed processing 99/99 sources,
  199/199 steps and awaits bulk symbol review. Retrying returns the same job.
  Forty-four captured human geometries and two human cells preserved exactly;
  847 old pending superseded, activation histories unchanged.
- Orphan preparation starts a durable job once and offers explicit resume.
  A late previous-game response cannot overwrite or disable the current view.
  Backfill now completes unavailable historical counts in durable bounded
  batches. Final counts job 13aabb68-aa50-42b7-9176-81552ca9b651 completed;
  revision174 reports 40 approved and 13,325 pending. Current ready counts do
  not rescan. Actual Admin: page2000, 423 Mumia crop previews and working
  counters, bulk approval enabled for image-bearing selections.
- Focused API/worker108, managed21, lateral scoped15, real isolated PG2,
  manual HTTP1, count/handler12, Admin interaction9, SDK request78 passed
  (overlapping suites). Scoped Ruff/format, strict owned-source mypy,
  Admin/SDK types and lint, OpenAPI/SDK checks and final Admin build passed.
  Two unrelated failures reproduced on unchanged HEAD are documented, not
  weakened; full-suite and physical Android/OS reboot are not claimed.
- MAIN API root15292/listener10516 and worker root42784, Admin root33252 are
  controlled and healthy. Reviewer3001 and VisionLab3102 preserved. No new
  migration, cleanup, model training/activation, 777 data operation or push.
- Quality: MUMIE_AUTOMATIC_IMPORT_RECOVERY_20261006.md. Existing operator
  guide now describes bulk verification and 500→2000-photo uploads with pooled
  feedback. One ending photo still needs explicit source-range binding.
  Completion version: v1.7.228; hash recorded after the scoped commit.

### TASK-0885 — neural manual slot symbol save (done)

- Board 1405's selected cell 4 save was blocked by the source-wide projection
  gate and the rebuilding-state mutation gate. D-522 now admits only a current
  human-approved, proposal-bound manual neural lattice and its exact cells.
  Sibling slots, incomplete source, general mutation and legacy gates remain.
- Exact lattice visibility protects outside cells. Real PostgreSQL HTTP test
  covers selected-only approval, outside rollback and fresh-app retry; passed.
  Scoped 143 tests, Ruff/format and strict owned-source mypy passed. Broader
  checks: 84 passed, one pre-existing list-timeout expectation failure untouched.
- Fixed MAIN API root 46320 / listener 47872 is healthy on 8000 after guarded
  restart; initial readiness timeout recovered through checks of the same
  process. Other services preserved. No migration, cleanup, training or guessed
  production label. Operator retries Save on 1405 without changing the grid.
- Completion v1.7.227; full hash recorded after commit. Read-only proof and
  runtime/check receipts are in the main Mumie pilot and deployment artifacts.

### TASK-0884 — approved main-app pilot deployment (done)

- Actual MAIN pilot ready:100 managed originals,99 bound sources,891 pending,
  one unbound ending source. Same importf3ff4258-e561-4031-bc04-227c9dbf51b6
  waiting_for_review/attempt3,199/199,99review/0failed. No human approvals,
  approved geometry,cohorts or symbol_training. First operator review remains.
- Mumie iterationfd5b15b6-e335-410d-9720-5f2d3bd6ec43 activated by
  fa00eaa1-5f19-4675-8102-3f40e042ff7c. Qualified R2crop96/input64 and exact
  neural24-node identity preserved;777 registry/activation unchanged.
- Both histories retained: sourcev1.7.225/820083aed4b3d2dda048c938bd2f3ed410132d95
  and premerge MAINv1.7.222/48b6e0e104e19e915bde30cd89a80d508e81c0b3.
  Completionv1.7.226/full hash is recorded after commit. MAIN branch remains
  v1.1-vision-lab-hybrid-geometry. Independent RGB0878 and old dirty metadata retained.
- Live fixes: owned-listener API readiness, lab checkpoint schema_version,
  optional strict lab cropSize DTO/full generated contract, deferred crop
  producer stage contract. Real exact99-file retry preserved297 prior stages,
  checkpoint/order/digests, same job and existing pending891. No data reset.
- Final API29756/30308,Admin45912,Reviewer48888,worker38536/48684 healthy;
  MAIN ports8000/3000/3001. Vision Lab3102/RGB preserved. UI auto-preview15/15,
 24nodes, symbol-only edit and unsaved-draft reload passed without approval.
- Full13.6GB archive and retained isolated *_test restore passed. Restore filled
  C and blocked30GiB reserve; root acknowledged error and moved verified archive
  to D:\game_predictor_backups\mumie-main-app-pilot-20261006 after both fullSHA.
  Durable pointer/reconciliation passed. No DB deletion/reserve reduction.
  Earlier0143→0145 executor is unattributed; explicit migrationCLI was a no-op.
  Actual isolated migration tests and final head0145/exact777 fences passed.
- Necessary existing topology draft3×5 created through API;spinCost0 is unused
  explicit placeholder. No publication,paylines,payouts or target calculation.
- Install/builds/contracts/types/lint, scoped tests and real100 cold acceptance
  PASS. Readiness3/labworker2/query22/HTTP2/stage5/client88 tests overlap broader
  suites. Independent gpt-6.1-sol/high code/liveSQL review PASS,0 openP0–P2.
  Quality: MUMIE_MAIN_APP_PILOT_ACCEPTANCE_20261006.md; receipts in
  main artifacts/mumie-main-app-pilot-20261006. No push.
- Next: operator review of existing100, then500/2000. No further upload or
  training authorization needed to finish0884. Symbol TRAIN uses pooled human
  corrections; neural-grid refit remains separate. Super/manual10-spin selection
  is a later task proposal, not a pilot blocker. V5/R2pair still FAIL.

### TASK-0883 — pooled correction feedback and pilot acceptance (done)

- Whole-photo protections before existing caps, current human approvals and
  fresh preview/freeze/builder/reuse/first-epoch gates implemented. Legacy
  fingerprints and4000/class,64/source budgets preserved; no auto-training.
- Exact24-node human geometry export and visibility/outside masks retained.
  Initial approval needs no recrop. Checksum/interior/stale approval negatives
  and explicit legacy corner conversion have regression coverage.
- Frozen127 genuine human controls/136 proofs/24 whole sources,10 explicit
  catalog mappings; AI never becomes truth. New production promotion checks
  exact current crop and locks pending controls. OPEN is a real conflict;
  absent comparisons are NO_CONFLICT/0. R2 lab import and777 preserved.
- Root67/feedback53/truth51/installer15 testsPASS, with overlapping suites;
  independent55PASS. Two actual guarded *_test PG testsPASS including cold
  export resume and competing LOGIN update55P03/teardown. API/UI/contract,
  strict owned-scope types, Ruff/format and Admin buildPASS. Full Torch graph
  timed out; scoped check skips only third-party torch/torchvision.
- Prepared controls161files verified in a new process,0 writes to live store.
  Prepared100-photo folder ready; reuse bounded actual100 receipt from0882,
  not a population accuracy claim. Operator guide and concrete0144/0145
  deployment preview ready. Independent gpt-6.1-sol/high audit PASS,0 open P0–P2;
  commitv1.7.225/820083aed4b3d2dda048c938bd2f3ed410132d95.
  Post-commit merge-tree confirms only CURRENT_STATE/DECISION_LOG conflicts;
  MAIN stays clean at48b6e0e104e19e915bde30cd89a80d508e81c0b3.
- OperatorDB remains0143 with0Mumie sources/boards, no activation or restart.
  DB51.64GB/C:82.47GBfree measured read-only; full backup/restore not done.
  Main Admin3000, Reviewer3001, API8000;3102 is Vision Lab. API arguments
  currently have no --reload; stop it before merge/migration regardless.
  RGB0878 previewCLI remains active; safe checkpoint required before0884.

### TASK-0882 — neural folder import and correction (done)

- Frozen geometry_core CPU staging, immutable checkpoint replay, explicit
  source binding and exact24-node board correction implemented. Migration0145
  extends the existing override; missing slots are never compacted.
  Managed source handoff/exclusions work after staging retention.
- Actual Admin Import panel accepts99 review sources and all-unbound source
  handoff; replay recovers the existing job, active new descriptor is rejected.
  Symbols edit on opening; approved geometry and legacy777 defaults preserved.
- Root41 new/120 broader/24 managed-source tests; backend46 core/10legacy,
  client86, independent fresh backend96 PASS (overlapping counts).
  Disposable PostgreSQL1 PASS/0skip,9 invalid nested bindings rejected;
  populated0144→0145, CAS/cold receipt/RLS/guarded downgrade verified.
- UI pure41/final66 and Reviewer15/Admin21 interactions PASS. Types/lint,
  formatting, OpenAPI/SDK checks, strict Mypy root7/backend29 and both builds
  PASS. Mobile touch390/360×844 PASS; physical Android untested.
- Real100 source handler:900 expected,897 valid24-node proposals/13455fullcells,
  99 ordered drafts/1 unbound; five20-source steps below20s. Cold replay0/4
  sameSHA/0infer. Separate memory20 parent124.6MiB/child413.0MiB individualpeaks.
  These are structural counts, not population symbol accuracy.
- Quality: MUMIE_NEURAL_FOLDER_CORRECTION_20261006.md; final proof in main
  artifacts/grid-v3-deployment-20261004/0882-final-proof.json. Independent
  gpt-6.1-sol/high audit PASS,0 openP0–P2;commitv1.7.224/8b37241fdd6eb9d29b35691d4e91f3d6a88cb18e.
  Continue0883 autonomously.
- No operator DB writes, main merge/activation/restart. Live0143 and0Mumie
  sources/boards confirmed read-only. RGB777 previewCLI still active.
  Prepared100-photo upload copies31.17MB preserve sourceSHA/originals.

### TASK-0881 — lab candidate registry and recovery (done)

- Explicit lab_import origin, nullable cohort only for lab and immutable
  candidate inventory/preview/VALIDATE import. No invented training epochs
  or human cohort; runtime keeps qualified R2 RGB96→64 and T1.05.
- Append-only deactivate and latest-state resolver prevent bootstrap/older
  activation revival. Receipt replay survives restart/response loss; cancel,
  retry and expired-lease recovery synchronize the import iteration.
  Cleanup fails closed before deleting the current disabled-state history.
- Backend/OpenAPI/generated client/wrapper/Admin request vertical completed.
  Operator commands persist exact inputs; authenticated retries retain receipts.
- 64 backend/worker, 83 client, 14 UI and 1 isolated PostgreSQL tests PASS.
  Actual 0143→0144 upgrade preserves production rows and verifies RLS,
  import/publication, cold-process replay and guarded downgrade.
- Ruff/format30, scoped Mypy23, UI/client lint/types, contract/drift and both
  builds PASS. Broad composition Mypy was bounded at120s; fresh API/CLI
  imports PASS. Independent gpt-6.1-sol/high audit:0 openP0–P2.
  Proof: main artifacts/grid-v3-deployment-20261004/0881-final-proof.json.
- No operator DB writes, main merge, activation or service restart.
  Commitv1.7.223/669cd5325140312e9da270bcd3c2ff194b875655 verified with
  show/stat and remaining status. Continue0882 next.

### TASK-0880 — qualified R2 RGB pilot adapter (done)

- Full source quad RGB96, padding0.0, float antialias96→64, opset17.
  Existing777 preprocessing/padding/fingerprints preserved.
- 77 focused +108 broader regression tests PASS; Ruff15files/scopedmypy8 PASS.
  Fresh manual/production runtime entrypoints work without Torch. Independent
  audit PASS,0 openP0–P2, original9352pins and actual405source cells verified.
- Candidate5e0489…a480 / manifest721257…a5c2; prepared managed package and
  package-render-preflight.json in main artifacts/mumie-main-app-pilot-20261006.
  Zero pixel/class differences, input7.15e-7/logit1.91e-6; no population accuracy.
- No DB/activation/main deployment. Next0881 registry;0882 folder/correction;
  0883 feedback/acceptance;0884 concrete migration/activation preview.
- Oddzielny commitv1.7.222 / e8de3b18d389207a5ceaa5d171e8a9e14d46c346.
  Potwierdzono show/stat i status; stare dirty metadata zachowane.

### TASK-0879–0884 — jawny pilot Mumii w głównej aplikacji

- Operator wybrał rekomendowany R2 RGB i zlecił integrację folderów, korekty
  siatek/symboli oraz naukę z zatwierdzonych poprawek. D-521; plan
  MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md. Bez nowych oznaczeń teraz.
- R2 RGB eligibility5b6af3…4ac7c, ONNX e4f9b2…37095, T1.05, human34=34/34
  wybranych kontroli. R2 pair i V5 nadal FAIL; nie jest to accuracy całego filmu.
- Wykryta istotna różnica preprocessing: lab używa bilinear antialias96→64,
  produkcja uint8 INTER_AREA. TASK0880 zachowa wersjonowane wejście modelu.
- Potrzebne jawne lab-origin w istniejącym registry, neural staging/pending,
  pełne24nodes w korekcie oraz osobne kwalifikowanie targets z feedbacku.
  Plan0144 po obecnym0143 wymaga gotowego preview przed operacją na bazie.
- Worktree HEADv1.7.220/4afedc11682cb7d378363710c78467c19d3bb12a;
  MAINv1.7.222/48b6e0e104e19e915bde30cd89a80d508e81c0b3.
  Przy scaleniu zachować nowszy RGB0878 i jego checkpoint, zatrzymać reload.
  Numery0873–0878 na MAIN zajęte; nowa integracja ma0879–0884.
- TASK0879: plan i taski zapisane, niezależny review PASS,0 openP0–P2.
  Uściślono source-level korektę przed sequence, brak compaction i whole-photo
  split z trwałą ochroną held-out byte/pixel aliases przed nowym DB TRAIN.
  Preflight405 real crops/3photos PASS: input max7.153e-7, logit max1.908e-6,
 0 class differences,40.17s. To parity wejścia, nie accuracy pełnego folderu.
  Oddzielny commitv1.7.221/2ac7a36bdf7894021de0d7c4118649efa025945e.
  Potwierdzony show/stat i status; następny TASK0880.
  Adapter0880 implemented and qualified; DB/runtime activation not performed. Old dirty metadata remains outside staging.

### TASK-0872 — większy izolowany RGB Mumii (done; candidate rejected)

- TASK-0871 zakończony i odebrany; HEAD `v1.7.219` /
  `d61d6981f1c68960d9c1ecb776303643b047421f` potwierdzony z historią.
- Manifest `58a064…d36b` opublikowany: R2 development327 + 1726 nowych high/high
  AI cropów, w tym Mumia109. Human84/diagnostic9/AI22 i human26/human8 zachowane.
  Pełny freeze 93.78 s; fresh-process verify 70.81 s, wszystkie 2000 quadów
  ponownie wyrenderowane. Cache źródeł i parent statów usuwa wcześniejsze timeouty.
- D-506: nowy jawny lokalny kontrakt wielu pakietów, jeden model RGB,
  20 epok / 7200 s / 50000 kroków. Stare generation1–4/API/limit100 bez zmian.
  Własny symbol_protocol_digest w lokalnym Request wiąże checkpoint; HYBRID
  protocol_digest pozostaje None. Manifest wymaga jednego zamrożonego run root.
- Pełny niezależny preflight kodu/danych PASS. Jedyny run `5302ac…8093` zakończył
  20 epok / 1360 kroków; best1, validation83/84. Pierwsza próba PID44912,
  631.21 s; fresh resume checkpoint20 PID7892, nadal1360 kroków, razem695.96 s.
  Real CPU ONNX parity PASS (max2.861e-6). Bez DB, Super i aktywacji.
- Ocena `efcdc9…5ee`: V5 odrzucony; 10/18 porównań według klas nie przechodzi.
  New19=16/19, held22=19/22, human8=6/8; human34 razem29/34 wobec R2 RGB34/34.
  Human84=83/84, old18=18/18, diagnostic9=9/9. Więcej AI nie poprawiło jakości;
  etapu0873 nie uruchamiać z tym kandydatem. Niezależny actual inference audit
  obu baseline RGB i V5 odtwarza wszystkie18 bramek; 11480 pinów sprawdzonych.
  To wybrane kontrole regresji, nie accuracy całego filmu.
- Próba anulowania ujawniła opóźniony stop w dawnym trainerze. Nowy lokalny
  LargeRgbRunManager honoruje go przy kolejnym batchu; 15 runner tests PASS.
  Stare kontrakty zachowane. Niezależny strict scoped mypy nowych3modułów PASS.
- 42 focused adapter/run/legacy tests PASS i 18 numerical training/resume tests
  PASS dla generation1–5. Dokładny R2 receipt, protected groups, resigned inputs,
  restart/budżety/fencing, defensive cache i Windows case/reparse guards pokryte.
- Final Ruff lint/format 5 modułów i 3 testów PASS. Real cp9/globalStep612
  odtworzony w dwóch procesach: identyczny batch32/images/logits/optimizer/model/RNG.
  Proof `1d4b43…06d9`, batch digest `3bd0b2…7ea3`, ledger i model niezmienione.
  Auditor w nowym procesie odtworzył sampler/augmentację/labels/generator.
  Preflight/model/ocena/replay PASS, bez otwartych P0–P2; V5 nadal REJECTED.
- Raport: ai_docs/quality/MUMIE_LARGE_RGB_EXPERIMENT_20261006.md.
  Hipoteza dalszej pracy: feedback draw share spadł z33.79% do6.84% mimo weight4;
  AI stanowi81.79% drawów. Kolejny osobno opisany eksperyment powinien kontrolować
  udział human/AI i ekspozycję zdjęć. Brak potrzeby nowych folderów/oznaczeń teraz.
- Pliki: trzy nowe moduły symbol_large_*, dwa opcjonalne reuse hooks, testy
  i dokumentacja protokołu. Wcześniejsze dirty metadata wyłączyć ze stagingu.
  Oddzielny commit `v1.7.220`; pełny hash dopisać po commicie. Cały zaakceptowany
  plan kończy bieżący etap na niespełnionym warunku C. Bez refitu/aktywacji/DB.

### TASK-0871 — większy zbiór Mumii (done)

- Po v1.7.218 większy trening nie został uruchomiony. Poprzednio podany czas
  był szacunkiem; aktualna kontrola procesów potwierdziła brak aktywnego CNN Mumii.
- Rozpoczęto przygotowanie większej deterministycznej serii z trzeciego filmu.
  Wyrenderowano 2000/2000 nowych kandydatów w 20 pakietach po 100; 916.50 s.
  Selection `12645e…69ff`, SHA `afcb8b…89fe`; 41 zdjęć, maksymalnie 54/zdjęcie.
  Pełny union 526 dawnych rastrów i 9351 pinów zachowany. Oba blind review
  zakończone: 2000 indywidualnych ocen każdy, własne fresh-process checks PASS.
- Fresh-process selection odtworzony bez zmian w 47.06 s; packet0 ponownie
  zweryfikowany w 36.62 s. Kontroler zakończył pracę; brak aktywnego CNN.
  Fresh aggregate odtwarza ID/pointer/bajty w 14.86 s. Qualification `8a57f6…8ac8`
  ma 11472 piny, 1726 high/high accepted i 274 rejected; Mumia 109.
  To liczności danych z AI, nie pomiar accuracy. Bez targetów Super/human approvals.
- 12 focused tests PASS; Ruff/format 4 i mypy 3 helperów PASS. Niezależny audyt
  wszystkich 2000 source/quad/pixels/montages i 40 review/20 proofs PASS;
  14 dodatkowych detached negative guards PASS. Końcowy niezależny audyt PASS,
  brak otwartych P0–P2. Oddzielny commit `v1.7.219`; hash dopisany po commicie.
- Zachować pierwszy film, human26/human8, validation/diagnostic i dawne AI audit
  poza nowym development. Bez zmian historii człowieka, modeli i aplikacji.
- Zaakceptowany zakres autonomiczny: MUMIE_LARGE_TRAINING_EXECUTION_PLAN_20261006.md.
  Najpierw przygotowanie i dwa blind review; CNN dopiero po kwalifikacji 0872.
  Bieżąca decyzja nie obejmuje DB, migracji, usuwania, merge, push ani aktywacji.
- Wcześniejsze brudne metadane wyłączyć ze stagingu. Po commicie kontynuować 0872.

### TASK-0870 — osobna diagnostyka RGB (done)

- Eligibility `5b6af3…4ac7c`: wszystkie dziewięć bramek RGB według klas i grup
  przechodzi (human84/18/19/9, held22/4, nowe control3/directed5/all8).
  Sprawdzono 9352 oryginalne piny oraz powiązania modeli, temperatur i metryk
  z niezmiennymi dowodami. Diagnostyka używa dokładnie dwóch eksportów RGB.
- 60 zdjęć / 8100 identycznych wycinków; porcje po 20 zdjęć, limit kroku 120 s.
  Czasy: 26.20 / 20.44 / 24.16 s. Osobny sidecar RGB zawiera 33 zmiany klas;
  liczba wyników poniżej progu pewności 0.9 spadła z 704 do 490 (o 214).
  To nie jest pomiar poprawności całego filmu. Nowych oznaczeń zapisano 0.
  Nowe osiem przykładów: RGB 8/8; łącznie 34/34 na dwóch wybranych zestawach.
- Powtórna inferencja obu CNN odtworzyła 60 zdjęć / 8100 wycinków bez różnic
  w logitach. Czasy porcji: 26.38 / 33.66 / 45.14 s. Replay: 9474 piny,
  digest `b3f13c…b6f1f`, siedem grup kontroli negatywnych PASS.
  Wznowienie porównania: 18.30 s, 0 nowych zdjęć. Wznowienie weryfikacji:
  35.50 s, 0 nowych zdjęć; 60 markerów, digest i bajty raportu identyczne.
  Ścisła walidacja wyników, quadów, pikseli, modeli i historii odrzuca zmiany.
- Niezależny końcowy audyt artefaktów, replay, wznowienia i dokumentacji PASS.
  Obie wcześniejsze uwagi poprawione i sprawdzone; brak otwartych P0–P2.
  17 testów inferencji PASS; cztery helpery: Ruff, formatowanie i typy PASS.
  TASK-0869 osobno: 43 testy PASS.
- Human8 revision8, human26 revision27 i oba wcześniejsze zestawy 61 wyników
  zachowane. V4 pozostaje kwalifikowaną parą; R2 combined gate=false,
  sidecar odrzuconej pary nadal nie istnieje. Bez treningu, refitu ani aktywacji.
- DoD, pięć kryteriów i kroki 1–4 zaakceptowanego planu spełnione.
  Raport: MUMIE_RGB_ONLY_DIAGNOSTIC_20261006.md. Commit `v1.7.218`.
  Wcześniejsze zmiany metadanych wyłączone ze stagingu. Etap 0869–0870 ukończony.
  Bez zmian API/UI/schematu/DB, migracji, usuwania, Super, merge, push i wdrożenia.
  Użytkownik nie musi powtarzać ośmiu oznaczeń.

### TASK-0869 — nowe osiem zatwierdzeń Mumii (done)

- Exact human8/revision8 z pełnym history/receipt/dictionary/source/quad/PNG.
  Pierwszy film poza symboldevelopment312/327,0photo/pixel overlap.
  Category nadaje własne caseIDs; join pełnym bindingiem, previous_case_id zachowane.
- Actual sześć ONNX:control3 wszyscy3/3;directed5 V3 RGB5/gray2/fuzja2,
  V4 5/3/5,R2 5/3/4. All8 RGB8 każda generacja,gray5/6/6,fuzja5/8/7.
  R2 RGB noweperclass/group gates PASS; wcześniejszehuman26 RGB26/26,łącznie34/34
  na dwóch wybranych zestawach. Nie jest to accuracy całego katalogu.
- Zero accepted AI/humanconflicts;7dawnychunresolved rozstrzygnięte przez człowieka,
  52pozostałe AI-only. Żadnych nadpisanych ocen, pseudo-zgód ani training/refit.
- Proof9d02a5…c5833, actual75.09s/fresh81.67s byte-identical.
  Replay11.86s:9349pins,rerender8,5negativeguards PASS,setSHAd715e61…da9d51.
  Human26 i oba61-output sets zachowane;43pytest,2helperRuff/format/types PASS.
- Independent final audit PASS,0openP0–P2;DoD/sixcriteria/plan1–4.
  Quality MUMIE_FIRST_HUMAN_CHECK_20261006.md;commit `v1.7.217`.
- Accepted MUMIE_FIRST_HUMAN_CONTINUATION_20261006.md:po audit/commicie kontynuować
 0870 conditional RGB-only diagnostic istniejących8100, bez nowej pary/aktywacji.
  QualifiedV4/rejectedR2combined bez zmian. Bez DB/Super/API/UI/merge/push/deploy.
  Wcześniejsze dirty metadata wyłączyć ze stagingu. Nie potrzeba kolejnych8/folderu.

### TASK-0868 — drugi izolowany eksperyment Mumii (done)

- Etap0867–0868 wykonany bez interakcji operatora; oba taski mają osobne commity.
- Dwa blind review100 exactPNG/20anchors:76high/high;327development=283human+44AI
  wobec312/AI29 w V4. Audit22, human84/diag9 oraz human19/5unreadable zachowane.
  Human26 całe zdjęcia/decoded aliases i pierwszy film wykluczone z development.
- Jedna para gen4,seed20261005,20ep/280steps:RGB633.28s/best8,gray606.19s/best6.
  Calibration/best tylko human84. Oba controlled workery zakończone, brak retry.
- Pairdbe76d…7e815:human84=83/84,old18=18/18,new19=19/19,diag9=9/9 dla każdej
  gałęzi/fuzji; wszystkie dotychczasowe perclass gates PASS. AI22/44 agreement100%.
- Held2eaefe…41820:RGB25/26→26/26;gray i fuzja26/26→25/26, nowy błąd Ra→J
  w directed4 (board4/field11,seq_27118-27126.jpg). Combined human gate FAIL.
  R2 RGB zachowany eksperymentalnie, V4 pozostaje qualified pair; brak aktywacji.
- Transfer pierwszego filmu:control47/47 każda gałąź;directedRGB6/gray5/fuzja5
  z6 wobec V4 6/5/6. AI agreement nie zastępuje human accuracy.
- Brak R2 sidecara8100:actual max-photos1 odrzucony stabilnym failed-gate guardem.
  Stare61 wyniki/model/raster/history bez zmian; brak refit/extra run/nowej pary.
- Independent ONNX/checkpoint196 rastrów:classes identyczne,maxabs3.8147e-6.
  Actual pair/held fresh replay byte-identical;final replay powtórzony9332pins
  i4negativeguards PASS, setSHA12bc79f…6238c. Helpers15 Ruff/format/types PASS.
- Focused50PASS/1 dawny obsolete registry assertion(gen3invalid wobecgen3/4),
  niezmieniony i opisany poza zakresem. Independent final audit PASS,0openP0–P2.
- Read-only kolejka8/revision0:directPNG0.125s/proxy0.094s;raw60/human26 zachowane.
  Nie potrzeba nowych katalogów. Bez DB/Super/migracji/usuwania/merge/push/deploy.
- DoD/sevencriteria/plan1–5 fulfilled;quality MUMIE_AI_ROUND2_20261006.md.
  Commit `v1.7.216`; wcześniejsze metadata wyłączone ze stagingu.

### TASK-0867 — autonomiczny blind AI audit pierwszej próby (done)

- Dwa niezależne review60 PNG/20human kotwic: 53 high/high readable,7 unresolved.
  Control50: V3 RGB46/gray45/fuzja45 z47; V4 wszystkie47/47.
  Directed10: V3 5/0/0 z6; V4 6/5/6 z6. AI agreement, nie human accuracy.
- Priorytet8 exact cropów; original60 i wcześniejsze26 approve zachowane.
  Gold frame3 present/51absent/6unresolved; zero Super/human pseudo-label writes.
  Pierwszy film poza symbol development; geometria wcześniej częściowo trenowana.
- Proof5fd1d19…8590a; fresh replay8748pins/20anchors i4negativeguards PASS.
  30pytest,6helpers Ruff/format/scoped strict mypy PASS; independent audit PASS.
- Saved runtime z bytebackupem; owned API2740/UI26388 gotowe po restarcie.
  Exact8 direct/proxy0.297/0.266s, revision0; galerie/editor200. API8000 nietknięte.
- DoD/sixcriteria/plan1–3 spełnione; quality MUMIE_AUTONOMOUS_AI_AUDIT_20261006.md.
  Commit `v1.7.215`; wcześniejsze metadata wyłączone ze stagingu.
- Natychmiast kontynuować TASK-0868: nowy cohort i jedna V4-R2 para. Kolejka8
  nie blokuje. Bez DB/Super/aktywacji/merge/push/wdrożenia.

### TASK-0866 — większa próba transferu z istniejących katalogów (done)

- Trzy katalogi potwierdzone: 2580/2052/2844 zdjęcia. Nie potrzeba kolejnego
  folderu ani ponownego potwierdzenia nagrań. Pierwszy film ma 0 source overlap
  z actual development312; strict exclusions: 6 duplikatów,66 wykluczonych,
  2508 eligible,60 równomiernych zdjęć z whole-photo guardami.
- Frozen V3/V4: 8100 identycznych cropów,540 plansz,0 unavailable,100 zmian
  klasy,disagreements89→54,lowconfidence461→472. Accuracy=null. Geometria była
  częściowo trenowana na tym filmie; wcześniejsze diagnostic9 użyte w regresji.
- Ready packet 4af49619…7f9d91: 50 kontroli wybranych przed inference i10
  odrębnych kierowanych przypadków,60 zdjęć,0 missing,revision0/trainable=false,
  bez pseudo-zgód. Edytor http://127.0.0.1:3102/symbols/batch; korekta symbolu
  bez zmiany dobrej siatki. Poprzednie26/revision27 i61 oryginalnych wyników zachowane.
- Saved runtime z byte backupem; API23640/UI35108 owned/ready po restarcie.
  Read-only direct/proxy60PNG:0.516/0.297s,galerie/editor200. API8000 nietknięte.
- 71 focused pytest; seven helper Ruff/format/scoped strict mypy PASS. Nowy
  proces:8539 inputSHA/372 outputfiles identyczne,rerender8100,actualONNX60,
  4 negatives PASS. Niezależny final audit PASS, bez otwartychP0–P2.
- DoD/7criteria/plan1–5 spełnione; quality MUMIE_CROSS_RECORDING_20261006.md.
  Commit `v1.7.214`; branch feat/grid-engine-v3, wcześniejsze metadata pominięte.
  Bez nowych training/calibration/activation,DB/Super/merge/push/wdrożenia.
- Wymagana następna interakcja: oznaczenie gotowych60 cropów. Potem human
  evaluation frozen pary,control50 i directed10 osobno; first film pozostaje
  poza development. Nie powtarzać wcześniejszych26 oznaczeń.

### TASK-0865 — ocena modeli na nowych oznaczeniach człowieka (done)

-26 latest approve/revision27 qualified exact pack, pełne history/receipt/source
  i dictionary guards; jedna historyczna decyzja zastąpiona. Bez wpisów agenta.
-22 withheld: V3 RGB19/gray18/fuzja18; V4 RGB21/gray22/fuzja22. Wszystkie10
  klas obecne.4 oddzielne diagnostic: V3 4/0/2, V4 4/4/4. Wynik22/22 jest
  teraz względem człowieka.0 konfliktów AI/human, RGB myli A z Faraonem.
- Wszystkie26 crop/pełne-photo SHA poza development312; bez treningu,
  recalibration/threshold/epoch selection. Same-film/kierowany dobór nadal
  ograniczają wnioski; nie accuracy całego folderu ani niezależnego filmu.
- Actual ONNX4 z frozen preprocess/settings zgodne z dawnymi propozycjami;
  qualified40.22s i nowy proces43.61s reprodukują identyczny raport7d3c0e…b38d9.
 5771 input SHA, w tym oryginalne61output SHA, bez zmian.4 negative checks PASS.
-46 pytest, helper Ruff/format/scoped strict mypy PASS; niezależny audit
  source render26/ONNX/metrics/isolation/hash PASS, bez otwartychP0–P2.
  DoD/7 acceptance criteria/plan1–5 spełnione; raport MUMIE_HUMAN_AUDIT_20261006.md.
- Commit `v1.7.213`; feat/grid-engine-v3, wcześniejsze obce metadata pominięte.
  Bez zmian aplikacji/API/UI/runtime, DB/Super/aktywacji/merge/push/wdrożenia.
- Następny etap: większa human-referenced próba z nagrania wyłączonego z V4
  po kwalifikacji lokalizacji; sprawdzić istniejące katalogi przed pytaniem
  o nowy. Obecne26 zachować jako ocenę zamrożonego modelu; nie powtarzać oznaczeń.

### TASK-0864 — autonomiczny przegląd AI i eksperyment Mumii (done)

- D-505: jawna zgoda na nocny trening/wewnętrzne AI. Dwa blind review79 exact
  crops z20 kotwicami klas; consensus high/high, pełne source/review provenance.
- Nowe24 decyzje:19 approve z oryginalną historią/priorytetem i5 unreadable
  wyłączonych z AI. Oryginalnehuman264/84/9 i18 korekt bez zmian.29 AI targets
  i22 photo-disjoint AI audit z tego samego filmu, osobny format/purpose/gen4.
-312 unikalnych development,423 draws/epoch; human feedback37 ma wagę4,
  AI29 wagę1. Audit22 nie uczestniczy w treningu/wyborze/calibration.
- Jedna para RGB/gray:20epok/280steps, attempt1, best8/6;535.908/604.668s.
  Walidacja83/84 każda/fuzja, old18=18/18, new19=19/19 po treningu, diag9=9/9.
  Wszystkie human perclass gates i ONNX parity84/gałąź PASS.
- V3 przed treningiem new19: RGB15/gray4/fuzja10. AI audit22:21/22 RGB,
  22/22 gray/fuzja względem V3 19/18/18; to AI agreement, nie human accuracy.
-8100 identycznych cropów/540 siatek:39 zmian klas, disagreements37→22,
  lowconfidence424→454. Accuracy=null; wynik mieszany, brak aktywacji.
  Porcje20/20/20, nowy proces0 powtórzeń,61 output/5673 input SHA bez zmian.
-85 pytest +14 artifact checks, Ruff/format/scoped mypy PASS. Osobne audyty
  kodu/danych i re-render wszystkich8100 pól PASS, bez otwartychP0–P2.
  DoD/9 acceptance criteria/plan1–7 spełnione; raport MUMIE_AI_OVERNIGHT_20261006.md.
- Commit `v1.7.212`. Praca na feat/grid-engine-v3; wcześniejsze obce metadata
  pominięte. Bez DB/migracji/usuwania, Super targets, grid approvals, aktywacji,
  merge/push/wdrożenia.10 AI obserwacji złotej ramki nie są targetami Super.
- Granica człowieka:26 pending crops (22 withheld +4 uncertain),
  http://127.0.0.1:3102/symbols/batch; portal
  http://127.0.0.1:8108/overnight-symbol-review/review.html. Saved runtime i lab
  API45388/UI36508 ownership/ready PASS. Nie potrzeba nowego folderu/30 na klasę.

### TASK-0863 — trzeci niezależny katalog Mumii (done)

- Follow-up `v1.7.211`: instrukcja restart/status używa zweryfikowanego
  absolutnego bundled PowerShell7. Program Files\\PowerShell7 nie istnieje
  na tym hoście; nowy proces potwierdza ownership API/UI i gotowość portów.
- Nowy24517–50112 cut:2844 źródła,0 byte duplicates/overlap,60 równomiernie
  wybranych zdjęć. Qualified V3; wykluczone2699 tożsamości/30 photo pixels.
- Wykryto540/540 plansz zgodnie z nazwami,8100/8100 pól/propozycji;
 0 count anomalies/pól poza obrazem.424 niepewnych i37 disagreements.
  Brak etykiet tego filmu: accuracy=null; zgodność liczby nie zatwierdza siatek.
-24 exact PNG z15 zdjęć,10 klas,0/24 ocenionych. D-504 zachowuje bieżące
  base approval/history i exact case gates po pełnej kwalifikacji; UI bez
  hashowania2052 niepowiązanych feedback photos. Preview API/proxy
  0.110/0.109s, HTTP/browser PASS. Skróty1–9/0, symbol bez zmiany siatki.
- Saved runtime i kontrolowany restart labu przez PowerShell7 PASS;
  API25800/UI23928. Driver25/25/10 zakończony. Nowy proces:0 powtórzeń,
  270 identycznych plików i original pins bez zmian.42+36 pytest,
  Ruff/format/scoped mypy PASS; własny odrębny review bez P0–P2, DoD spełnione.
- Commit `v1.7.210` / `92b3bd8a316fa80f4428d045d29fabf773e8c4a2`; raport MUMIE_THIRD_RECORDING_20261006.md.
  Granica człowieka: http://127.0.0.1:3102/symbols/batch — oznaczyć24 wycinki.
  Portal: http://127.0.0.1:8108/third-symbol-review-priority/review.html.
  Nie potrzeba nowego folderu/30 na klasę. Brak DB/aktywacji/Super/merge/push/wdrożenia.

### TASK-0862 — lokalizacja przeniesionych zdjęć Mumii (done)

- Operator wskazał C:\Users\tuszy\Documents\mumie. Wszystkie 2 052 SHA
  folderu481537–500000 cut są identyczne z qualified inventory.
  Nowy trzeci katalog24517–50112 cut zawiera2 844 zdjęcia z odrębnego filmu.
- D-503 zapisuje deklarację odrębnych filmów dla każdego nowego katalogu;
  nie wymaga powtarzania pytania. Przeniesione stare katalogi zachowują tożsamość.
- Create-only sidecar lokalizacji zachowuje manifest/run/split i pełną kontrolę
  SHA/re-render. Fresh-process verify i identyczny retry PASS, bez zmian zdjęć.
- 29 nowych/kwalifikacyjnych +28 regresyjnych pytest PASS; Ruff/mypy PASS.
  Osobny review bez otwartych P0–P2. Commit `v1.7.208`.
  Dalej wznowienie0861 i diagnostyczna partia60 zdjęć0863. Bez DB/aktywacji.

### TASK-0861 — ograniczona para feedback generacji3 (done)

- RGB/gray zakończone:20epok/200kroków, wybór epok
  11/11; jeden run każdej gałęzi.
  Ten sam RGB run wznowiono po0862; wcześniejszy błąd i budżet zachowane.
- Walidacja RGB/gray/fuzja: 83/83/83/84; gate wszystkich klas
  względem V1=True. Pozostaje dawny konflikt referencji K/Q.
  ONNX parity84/gałąź PASS. Unikalne264 development,318 losowań weight4.
- Feedback 18/18/18/18 to użyte targety treningu.
  Diagnostic 9/9/9/9: dwie klasy, ocena po wyborze epoki;
  nie jest ślepym testem starszych modeli ani accuracy nowego filmu.
- Dwa świeże procesy odtwarzają identyczny dowód/kalibrację; SHA/etykiety,
  wcześniejsze modele i magazyny zachowane. Worker PID-y zakończone.
  43 wcześniejsze focused pytest i Ruff/scoped mypy PASS;0862 dodał29+28 regresji.
- Odrębny review bez P0–P2; DoD/plan0861 spełnione. Commit `v1.7.209`.
  Raport MUMIE_SYMBOL_FEEDBACK_TRAINING_20261006.md. Kontynuować0863:
 60 nowych zdjęć24517–50112 z2844; brak DB/aktywacji/merge/push/wdrożenia.

### TASK-0860 — kwalifikacja 18 korekt symboli Mumii (done)

- Operator potwierdził niezależność nowego nagrania od walidacji. D-502
  kwalifikuje wyłącznie dokładny raster symbolu; nie zatwierdza planszy ani geometrii.
- Immutable pack c1392fb1…3f8b60 zawiera 18 decyzji i PNG z 17 zdjęć.
  Pochodny manifest 0cff2a15…1e3de4: 264 development, 84 validation,
  9 diagnostic_test. Wszystkie 10 klas pozostaje w development/validation.
- Cały nowy folder (2 052 pliki) i znane aliasy pozostają w jednej części.
  Pierwsza rodzina nagrania jest wyłączona z nowego treningu; diagnostyka
  obejmuje tylko Mumię/Sfinksa i nie jest ślepym testem wcześniejszych modeli.
- 20 nowych +42 regresyjne pytest PASS; Ruff, scoped strict mypy PASS.
  Realny verify/retry w nowych procesach daje ten sam manifest i SHA oryginałów.
  Pierwsza analiza mypy bibliotek przekroczyła 120 s; procesy zakończył runner.
- Pierwotne decyzje trainable=false i adapter D-498 zachowane; API/UI bez zmian.
  Bez DB, aktywacji, merge/push/wdrożenia. Osobny review bez otwartych P0–P2.
- Commit: `v1.7.206`. Dalej TASK-0861: jedna para RGB/gray generation3,
  feedback weight4 i dokładne resume; aktualne polecenie obejmuje kontynuację.

### TASK-0859 — poprawka RGB 777 i ukończone 18 korekt Mumii (done)

- Przeczytano wskazany handoff RGB/feedback z głównego checkoutu. Mumie już
  używają pełnego RGB i SpatialSymbolCnn; 18 PNG ma exact preprocessing parity.
  Różnica to głowica RGB 777 versus dotychczasowa gray-dominant fuzja Mumii.
- Operator ukończył 18/18 decyzji approve, revision18. Zweryfikowano klasę,
  UUID, byte/pixel SHA i identyczne propozycje; bez ponownego oznaczania.
- Na trudnych18: V1 RGB/gray/fuzja11/10/10; V2 10/13/11. RGB V1 psuje
  Mumię, gray V2 psuje J względem V1. Wszystkie warianty83/84 na dawnej
  walidacji. Sama podmiana gałęzi nie rozwiązuje błędu i nie uzasadnia aktywacji.
- Zapisano bramkę dalszej oceny: mniej błędów ogółem bez regresji klasy,
  identyczne źródła/piksele/etykiety i niezależny split. Bez accuracy gry
  z celowo wybranych18. Raport MUMIE_RGB_FEEDBACK_TRANSFER_20261005.md.
- 29 pytest PASS; ponowny proces daje identyczny dowód199f2b58…ff53f84.
  Wszystkie wejścia SHA i realne decyzje zachowane. Bez DB, treningu,
  aktywacji, restartów, merge/push/wdrożenia i nowych zależności.
- Następny zakres: osobna kwalifikacja dokładnych korekt i splitu do nowej
  iteracji, potem ograniczony trening i przegląd nowych pomyłek. D-501 raw
  crop-review nadal trainable=false; nie udaje akceptacji pełnej geometrii.
  Nie potrzeba teraz kolejnych30 zwykłych przypisań ani ponownej deklaracji nagrań.
- Osobny commit: `v1.7.205`.

### TASK-0858 — korekta symboli z partii Mumii (done)

- Operator zgłosił brak edycji w galerii 18 przypadków. Źródła są poza
  obecnym katalogiem lab. Dodajemy dokładny crop-review do istniejącego API
  i edytora, z oddzielną trwałą historią i zatwierdzonym słownikiem D-498.
- Założenie D-501: wybór klasy zatwierdza wyłącznie widoczne wycięcie;
  nie pełną geometrię, sekwencję ani próbkę treningową. Bez DB/migracji,
  treningu, aktywacji, produkcyjnego wdrożenia i zmian pierwotnych etykiet.
- Plan: ai_docs/delivery/MUMIE_BATCH_SYMBOL_CORRECTION_20261005.md.
- Działający edytor http://127.0.0.1:3102/symbols/batch: wybór wycinka,
  paleta dziesięciu istniejących klas, skróty 1–9/0 i jawny zapis bez zmiany
  siatki. Desktop ma panel obok galerii; telefon — nad nią. Galeria 8108
  prowadzi do konkretnego wycinka. Miniatury pozostają zamrożone po zapisie.
- Referencja 48341730f870b38590286bffa7ff289649cd8c73f9fcc0907c81ac3c16754c54;
  18 bezstratnych PNG RGB96. Odczyt API/proxy 0,203/0,172 s. Realny zbiór
  nadal ma zero nowych decyzji; stare rev591/rev63 i SHA bez zmian.
- Osobny trwały magazyn batch_crop_review; CAS, exact retry i restart
  potwierdzone na izolowanym fixture. Saved runtime.json i launcher
  odtwarzają lab z nowego procesu. API/UI 8102/3102 gotowe po restarcie.
- Weryfikacja: backend 56, UI 62, klient 15 PASS; Ruff/mypy, OpenAPI/client
  drift, lint/typecheck i build PASS. Browser/390×844 bez overflow, guziki 44px.
  Audyt: ai_docs/quality/MUMIE_BATCH_SYMBOL_CORRECTION_20261005.md.
- Commit: `v1.7.204`.
- Następna konieczna interakcja: operator wybiera prawdziwe klasy w 18
  wycinkach. Potem osobna kwalifikacja/ocena; trening nie uruchamia się sam.

### TASK-0857 — odporność modeli symboli Mumii (done)

- Dwie ograniczone próby V2: po 20 epok/160 kroków, walidacja 83/84,
  development 255/255, czas 70,63/78,93 s. ONNX parity wszystkich 84 cropów,
  max błąd 2,861e-6. D-500; plan odporności ukończony.
- Te same 600 zdjęć/5396 plansz/80940 wycięć, identyczne piksele i geometria.
  V2: 16024 niepewnych (19,80%) i 4047 rozbieżności (5,00%); V1: 15626/3494.
  Brak wykazanej przewagi V2; obie wersje pozostają testowe, bez accuracy.
- 36 pytest, Ruff/format i scoped mypy PASS. Świeży proces: 0 powtórzeń,
  2404 pliki V2/737389437 bajtów i V1 bez zmian. Oryginalne magazyny bez zmian,
  kontrolowane procesy zakończone. Szerszy mypy: wcześniejsze błędy API/timeout.
- 18 konkretnych przypadków do rzeczywistej oceny człowieka:
  `http://127.0.0.1:8108/symbol-review-priority/review.html`. Przegląd tylko do
  odczytu; dalsza poprawa potrzebuje etykiet podświetlenia/linii/białego znacznika
  i potwierdzenia geometrii. Nie potrzeba kolejnej rutynowej zgody na testy.
- Raport `ai_docs/quality/MUMIE_SYMBOL_ROBUSTNESS_20261005.md`; osobny commit
  `v1.7.203`, pełny hash po commicie. Na `feat/grid-engine-v3`.
- Bez DB, aktywacji, Super, push/merge/wdrożenia i kolejnych losowych prób.

### TASK-0856 — większa niezależna partia Mumii (done)

-600 zdjęć z2052,5396 plansz i80940 propozycji. Manifest9068f31a…9199dac.
 15626 niepewnych modeli,3494 disagreement; bez accuracy/zgód za człowieka.
- Poprawiono końcówkę499996–500004 w folderze do500000:5 plansz, pominięty
  jeden nadmiarowy kandydat, jawny konflikt nazwy. Oryginalny plik bez zmian.
- Trwałe per-photo wyniki, kompletne SHA, root lock, porcje25/115s. Restart
  w nowym procesie:2404 pliki/737005906 bajtów identyczne, zero powtórzeń.
-28 pytest, Ruff/format/mypy i własny review PASS. Oryginały geometrii,
  symboli i run-state bez zmian. Driver/PID zakończone, bez orphanów.
- Przegląd `http://127.0.0.1:8108/symbol-batch-600/review.html`; HTTP/browser
  smoke PASS. Raport `ai_docs/quality/MUMIE_SYMBOL_BATCH_20261005.md`.
- Samodzielna dalsza praca: jasne J/K z zielonymi liniami ujawniły błędy
  modeli. Kontynuujemy TASK-0857, plan `MUMIE_SYMBOL_ROBUSTNESS_20261005.md`.
  Bez DB, aktywacji, Super, push/merge i wdrożenia.
- Osobny commit `v1.7.202`, pełny hash dopisany po commicie.

### TASK-0855 — dwa pierwsze modele symboli Mumii (done)

- RGB/gray od zera: po20 epok,255 development/84 validation z osobnych nagrań.
  Oba83/84 (98.81%), Mumia8/8; najlepsze epoki14/11. Mała walidacja, nie final_test.
- Kalibracja i fuzja wykonane; fuzja nie poprawia accuracy. ONNX obu modeli:
  parity84/84, max błąd3.8147e-6. Wagi, historia/logits i raporty zachowane.
- Jeden konfliktK/Q (crop wygląda jakQ) i niepewny Faraon do późniejszej korekty.
  Bez zmiany etykiet. Modelowa zgodność nie wykrywa każdej błędnej referencji.
- Trwały istniejący RunManager, budżety/restart/RNG/checkpoint i admission.
  RGB wznowiony po błędzie CUDA z tym samym budżetem; fixed pooling ekwiwalentny
  dla64px, test regresji PASS. Użyto55.36s/49.35s z1800s,161/160 kroków.
- 11 nowych testów +14 regresji runów, Ruff/format/Mypy i własny review PASS.
  Wszystkie SHA oryginałów niezmienione. Commit `v1.7.201`, hash po commicie.
- Raport `ai_docs/quality/MUMIE_SYMBOL_MODELS_20261005.md`; plan0854/55 ukończony.
  Modele testowe, bez aktywacji, DB, wdrożenia i Super. Kolejny zakres: większa
  niezależna partia inferencji i korekta wykrytych konfliktów.

### TASK-0854 — kwalifikowany split symboli Mumii (done)

- Potwierdzenie operatora rozstrzyga pochodzenie trzech grup; bez dalszego pytania.
- D-498: 339 aktualnych etykiet, development255/validation84, 10 klas w obu
  częściach. Pełne komponenty starego/obecnego grafu; bez duplikatów między częściami.
- Osobny niezmienny manifest `d5dc865287ca2d4583b450ccdca84f6186e16ac86922dc6f95ebea3930151589`.
  Rewalidacja cropów, grafu, źródeł i magazynów. Oryginały i D-496 bez zmian.
- 32 pytest, Ruff/format/Mypy i restart/retry PASS; własny review bez P0–P2.
  Commit `v1.7.200`; hash dopisany po commicie. Raport kwalifikacji poniżej.
- Plan `ai_docs/delivery/MUMIE_SYMBOL_TRAINING_20261005.md` obejmuje dalszy
  TASK-0855: dwa ograniczone runy RGB/gray od zera. Bez DB/aktywacji/wdrożenia.

### TASK-0853 — aktualne etykiety Mumii (done)

- Operator zakończył przypisania i zlecił pracę bez swojej obecności.
  339 świeżych decyzji D-496: wszystkie 10 klas, 27 Mumii. 30 nie jest bramką.
- Niezmienny pakiet 339 PNG i historii, 13 zdjęć / 3 komponenty; żadnych
  identycznych pikselowo duplikatów ani sprzecznych klas. 244 dawne decyzje
  poza próbkami. Trainable=false, bez assignments i nadpisania magazynów.
- 20 testów, Ruff/format/Mypy PASS; verify i retry w nowych procesach PASS.
  SHA geometrii i symboli niezmienione. Pakiet 341 plików / 9 219 147 bajtów,
  ID `7fb60ce3edc52081d5f9cf016083a8cd6b048766db30d8df8b008fca0dccb1c8`.
- Wszystkie rodziny Mumii unresolved/missing; brak splitu symboli, stary
  split geometrii stale. Pytanie o relację trzech nagrań pending; nie potrzeba
  teraz kolejnych przypisań klas. Dwa główne komponenty mają wszystkie 10 klas.
- Plan `ai_docs/delivery/MUMIE_SYMBOL_PREPARATION_20261005.md`.
  Nie osłabiamy bramek T06b; bez treningu do rozstrzygnięcia pochodzenia.
  Brak oddzielnych etykiet ramki Super; bez zgadywania, DB lub aktywacji.
- Raport `ai_docs/quality/MUMIE_SYMBOL_PREPARATION_20261005.md`.
  Osobny commit `v1.7.199`; pełny hash zostanie dopisany po commicie.
  Zastane metadane pozostają poza commitem. Bez restartu API/UI i wdrożenia.

### TASK-0852 — szybkość zapisu i poczekalnia 2000 (done)

- Operator zgłosił wielominutową blokadę po przypisaniu symboli i doprecyzował
  zamrożenie miniatur do odświeżenia. Jeden odczyt do 2000 cropów; potwierdzony
  zapis oznacza pola bez ponownego pobierania strony. Następny wybór podczas
  zapisu jest dostępny; kolejny submit wymaga receipt. D-497.
- Istniejący kontrakt rozszerzany addytywnie; domyślny podgląd 30 i zapis do
  30 pozostają. Budżet PNG 48 MiB; stare tokeny nigdy nie są odnawiane lokalnie.
- Zachowujemy bieżące etykiety człowieka. Bez zmian DB, treningu, aktywacji,
  shadow, push/merge. Weryfikacja realnych danych tylko odczytowa.
- 73 Python + 37 UI + 5 klienta PASS; format/lint/typy/OpenAPI/drift/build PASS.
  2000 realnych cropów: 5,464 s, 32,34 MiB base64. Restart API/UI 8102/3102
  z trwałej konfiguracji, PID 18980/18320, ready. Sumy etykiet i siatek identyczne.
  Browser: 2000 kafelków, 64 loaded/enabled, zero błędów. Własny audyt PASS.
- Raport `ai_docs/quality/SYMBOL_REVIEW_PERFORMANCE_20261005.md`.
  Task `ai_docs/tasks/completed/0852-symbol-review-save-and-queue-performance.md`.
  Osobny commit `v1.7.198`; pełny hash dopisywany po commicie. Zastane metadane
  innych tasków pozostają poza commitem. Pierwszy odczyt nadal trwa kilka sekund.

### TASK-0851 — wersja etykiet symboli Mumii (done)

- Operator 2026-10-05 zaakceptował kontrakt i potwierdził dwa różne nagrania.
  Deklaracja dotyczy wskazanych folderów; nie nadaje rodzinom verified.
- Wykonano: niezmienna referencja zgód i dawnych ról, opcjonalna konfiguracja
  istniejącego magazynu/API/edytora, 31 zdjęć / 279 plansz / 4185 komórek.
  Oryginalny split pozostaje stale. Bez nowego AnnotationStore i bez osłabienia
  starego workflow. Brak automatycznych etykiet i kwalifikacji treningu.
- Decyzja D-496. Main Mumie pozostaje pusty. Bez DB/migracji/materializacji/
  aktywacji/shadow/push/merge. Następna interakcja: przypisanie klas przez człowieka.
- Wersja `dab77630f3518604add168c2baeed124dc9c5010d8ea483201a5be8cb77da1fc`,
  523 chronione źródła, słownik v1, pełna oryginalna historia. Wszystkie dawne
  sumy niezmienione; zero nowych etykiet, 706 dotychczasowych zachowanych.
- 63 testy PASS; format/lint/typy/OpenAPI/build/TypeScript PASS. Restart i HTTP
  pierwszej/ostatniej strony oraz pełnej planszy PASS. Browser smoke: 15 aktywnych
  wyborów bez zmiany siatki. API/UI 8102/3102 gotowe; własny 8105 zatrzymany.
  Trwały launcher/config, PID/czas startu zapisane. Bez restartu komputera.
- Raport `ai_docs/quality/MUMIE_SYMBOL_DATASET_VERSION_20261005.md`.
  Task `ai_docs/tasks/completed/0851-mumie-symbol-label-dataset-version.md`.
  Osobny commit `v1.7.197` na `feat/grid-engine-v3`; hash dopisany po commicie.
  Zastane metadane pozostają poza commitem. Nie uruchomiono uczenia symboli.

### TASK-0850 — Mumie: iteracja 5 i dane do interakcji (done)

- Operator 2026-10-05 zlecił pracę do momentu wymagającego jego interakcji.
  Jedna iteracja 5 presetu F na nowych zatwierdzeniach, testy i przygotowanie
  cropów. Bez importu plansz do głównej gry, DB, migracji i aktywacji.
- Iteracja 5 runu 3 zakończona, preset F: 25 train / 6 holdout z 31 zdjęć,
  11 nowych. 900,75 s GPU, 1831 kroków, zużycie 4718,62/14400 s.
  Każdy kandydat przeszedł strażnik 777, ale pogorszył Mumie image-macro
  względem 0,0022076230. Poprzedni model zachowany, bez ONNX/propozycji/aktywacji.
- Oba foldery verify PASS w nowych procesach: po 200 zdjęć i 11 osobnych kontroli,
  każdy model 211 wyników na folder. Bez ponownej inferencji i deklaracji accuracy.
- 4185 cropów z 31 kompletnych zdjęć, 236 nakładek, partie 50/50/50/50/36.
  Słownik labu 10 klas zatwierdzony; zero etykiet obecnych 31 zdjęć.
  Dawne 20 ról, rewizja 591, fingerprint zgód i stan symboli niezmienione.
- 31 testów fine-tune/batches/folder CLI PASS; build/TypeScript labu PASS.
  Główna gra: 10 symboli, 0 layouts/source_images/recognized_boards/dataset_versions.
- Faktyczny edytor symboli blokuje `HOLDOUT_POLICY_UNRESOLVED`: dawny split
  pilota stale. Nie nadpisano splitu ani nie wyłączono guardów. Nowe własne
  procesy 8102/3102 zatrzymane, 8105 przywrócony (root 42788), 31/236 PASS.
- Granica interakcji: pytanie o pochodzenie obu folderów i akceptację
  `ai_docs/delivery/MUMIE_SYMBOL_DATASET_VERSION_20261005.md` (draft).
  TASK-0851 planned, niewykonany; wszystkie rodziny pozostają unresolved.
- Raport: `ai_docs/quality/MUMIE_CURRENT_APPROVALS_20261005.md`.
  Task: `ai_docs/tasks/completed/0850-mumie-train-current-approvals-and-prepare-review.md`.
  Osobny commit `v1.7.196`, hash dopisywany po commicie. Zastane metadane
  pozostają poza commitem. Bez DB/migracji/materializacji/shadow/push/merge.

### TASK-0849 — Omyłkowy duplikat Mumie usunięty (done)

- Operator jawnie zlecił archiwizację i trwałe usunięcie `mumie-1`
  (`12180d9f-6c1a-43a9-a480-4056d2da81a9`). Oryginalne `mumie` i `777`
  pozostają chronione.
- Preview bez danych użytkownika; wznowiono istniejący provisioning 9/64
  do 64/64 bez ręcznego SQL. Archiwizacja przez API 204; końcowy preview
  bez blockerów. Usunięcie istniejącym CLI, 64/64, receipt `done`.
- Nowy proces: PASS; duplikat daje 404, zero katalogu, registry i partycji.
  Snapshoty katalogów, magazynów, symboli i fingerprintów jobów oryginalnych
  gier są zgodne. Zdjęcia zachowane; bez restartów usług, treningu i shadow.
- Raport: `ai_docs/quality/MUMIE_DUPLICATE_REMOVAL_20261005.md`.
  Task: `ai_docs/tasks/completed/0849-remove-accidental-mumie-duplicate.md`.
  Osobny commit `v1.7.195`; hash dopisany po zapisie. Zastane metadane poza
  commitem; brak push/merge.
### TASK-0851 — analiza nowych korekt symboli i przekazanie metody (done)

- Operator zlecił analizę swoich nowych korekt audytu 777 i dopracowanie
  mechanizmu oraz notatkę do Claude Code.
- Ocena wyłącznie aktualnych zatwierdzonych pikseli; osobne źródła do oceny
  kandydata. Niezmienione propozycje zatwierdzone Save to słabszy dowód.
- Bez aktywacji/treningu CNN, masowego zapisu, zmian geometrii ani wznowienia
  zatrzymanych TASK-0832/0833. Zmiana metody zależy od niezależnych wyników.
- Snapshot tylko do odczytu: 5788 zatwierdzonych pól / 578 zdjęć, SHA cropów PASS.
  RGB: 100 rozbieżności; w aktualnym przeglądzie RGB 44/3780 (98,84% zgodności).
  Cytryna 0/556, Śliwka 1/584, Arbuz 1/429; główny problem Winogron/Siedem.
- Wariant nowych wzorców zmniejsza test 21 → 18 błędów, ale Cytryna 2 → 5.
  Odrzucony; kontrola regresji każdej klasy pozostawia obecną politykę D-494.
- Nowy ewaluator scripts/evaluate_grid_audit_feedback.py; 28 testów PASS,
  Ruff i scoped Mypy PASS. Nowy proces evaluate: retain_rgb_v2.
  Raport: artifacts/grid-audit-feedback-20261005/approved-v2/.
- Historia 5788 decyzji: zero masowych zatwierdzeń; exporter odrzuca je w przyszłości.
- Notatka dla Claude Code: ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md.
  Zakres globalnego pending-only adaptera pozostaje odrębny; bez publikacji.
- Task 0851 w completed; commit `v1.7.197` /
  `fbef9096a1c937ad4884e745b48dc57bffa815af` (hash dopisany po commicie).

### TASK-0850 — cofnięcie ostatniego zapisu planszy 388128 (done)

- Operator polecił cofnięcie jednej ostatnio zapisanej planszy: p00683,
  revision 2, receipt 0f3009c7-2923-4574-b130-e1cac7103f2a.
- Zakres: poprzednie narożniki i 15 zatwierdzeń tego samego zapisu.
  Przed zapisem wszystkie pola pending / requires_review. Historia pozostaje.
- Zapis kompensujący revision 3 / receipt efc87ae4-6eae-4803-9fd3-0a4980707c84:
  poprzednie narożniki przywrócone; 15 pól pending / requires_review.
- Nowy audyt silent-grid-777-20261004-undo-p00683-20261005t160416 jest kopią
  aktualnej wersji po TASK-0849; rebase wyłącznie p00683. Wcześniejszy rebase
  p00545 oraz wszystkie 975 pozycji i 917 propozycji zachowane.
- Świeży proces i UI PASS: p00683 / 388128 pierwsza w kolejce, 15/15 podpowiedzi,
  402 open / 573 corrected. Pozostałe geometrie i decyzje niezmienione.
- Ruff pomocnika PASS. Dowody: artifacts/grid-audit-undo-20261005/p00683/.
  Task 0850 w completed; commit `v1.7.196` /
  `8c16dcf16b67a8f5f61b44c9624509148a85f9e5` (hash dopisany po commicie).
- Bez zmian aplikacji, schematu, treningu ani usuwania danych.

### TASK-0849 — cofnięcie ostatniego zapisu planszy 431508 (done)

- Operator polecił cofnięcie ostatniego zapisu; odczyt wskazuje p00545,
  revision 2, receipt 9b4c8f0f-23cb-4643-9c97-79710bb977a1.
- Zakres obejmuje poprzednie narożniki i 15 zatwierdzeń tego zapisu.
  Wcześniejszy stan wszystkich pól: pending. Historia ma pozostać.
- Istniejący zapis kompensujący: revision 3 / receipt
  4c2e9a09-b1af-4b3f-99b9-9d3467ff6ae6. Poprzednie narożniki przywrócone;
  15 pól pending/requires_review, poprzednia aprobata 2 wyłącznie w historii.
- Nowy niezmienny audyt silent-grid-777-20261004-undo-p00545-20261005t130216:
  rebase tylko p00545, wszystkie 975 pozycji i 917 propozycji zachowane.
  Oryginalny audyt niezmieniony; SHA PNG zgodny dla nowych rewizji kontekstu.
- Nowy proces i UI PASS: p00545 / 431508 pierwsza, 15/15 propozycji RGB,
  kolejka 482 open / 493 corrected. Pozostałe geometrie i decyzje zachowane.
- 40 regresji API PASS, Ruff pomocników PASS. Dowody:
  artifacts/grid-audit-undo-20261005/p00545/; task 0849 w completed.
- Bez nowego UI, schematu, endpointu, treningu ani usuwania danych.
- Commit `v1.7.195` / `eb19e28aa796c259820d18c4b891f9d68068ac1b`
  (hash dopisany po commicie).

### TASK-0848 — V3-D scalony i zmigrowany na main (done)

- Wdrożono z `C:\Users\tuszy\Documents\game_predicotr` na
  `v1.1-vision-lab-hybrid-geometry`, po zgodzie operatora i koordynacji TASK-0847.
- Kandydat `v1.7.192` / `a5119244c0af32ef2cf3132550ba115f1f5c960d`;
  końcowy `v1.7.193` / `6fb6b8f2ed026d17418e4dfc3d9dcce8cf7c9b90`.
  Zachowano RGB TASK-0847 `v1.7.192` / `8a42380bc9b6d13d125c5eab2873c8c58076134f`.
- Baza na `0143_merge_share_grid_shadow` (no-op join 0141/0142), guard zgodny.
  Dwie wcześniejsze gry aktywne, manifest v5, rewizje magazynów +1.
  Parent i dwa children shadow ENABLE/FORCE RLS; rzeczywiście zero historii.
  Role compliant, brak aktywnych jobów/lifecycle w kontroli po migracji.
- 43 testy pierwszej integracji i 34 po RGB PASS; klient 82 PASS;
  regresje Reviewera 21 PASS, typy/lint/scoped Mypy PASS. Kontrakt wygenerowany.
  Zależności aktualne. Build Admin 21,25 s i Reviewer 14,11 s PASS z main.
- API 8000, Admin 3000, Reviewer 3001 gotowe; worker general z 7 wątkami.
  Odczyt HTTP i trwałego stanu PASS w nowym procesie. Pierwszy probe API
  przekroczył 10 s; gotowość potwierdzono bez drugiej kopii, bez gwarancji 10 s.
  Galerie 8105/8107 bez restartu; brak starych procesów i duplikatu workera.
- Shadow false; nie uruchomiono jego inferencji, treningu, aktywacji modelu,
  importu stagingu, downgrade, usuwania danych ani push. Zastane metadane
  odtworzone poza commitem; stashe zachowane jako odzyskiwalne kopie.
- Raport: `ai_docs/quality/GRID_V3_SHADOW_DEPLOYMENT_20261005.md`.
  Task: `ai_docs/tasks/completed/0848-grid-shadow-integration-deployment.md`.
  Główny commit `v1.7.194` / `73ae0b6fe82d397fefed24a3f1656ba805c50d6c`
  (hash dopisany po commicie).

### TASK-0805 — V3-D: shadow w aplikacji (done, domyślnie wyłączony)

- Operator jawnie uruchomił etap 2026-10-05. Kontrakt wykonawczy:
  `ai_docs/delivery/GRID_V3_SHADOW_CONTRACT_20261005.md`; TASK-0805.
- Jeden pion na zmaterializowanych źródłach, domyślnie wyłączony, z jobem
  VALIDATE ograniczonym do 20 źródeł, osobnymi wynikami i ręczną korektą.
  Mumie bez kalibracji pozostają propozycją do przeglądu. 225 zdjęć w stagingu
  nadal wymaga preflightu i materializacji źródeł.
- Neutralny rdzeń, manifest v5 i RLS, API/OpenAPI/klient i Admin/Reviewer.
  Claude z pierwotnej tabeli niedostępny; jawnie przypisano gpt-6.1-sol high
  oraz audyt gpt-6-astra high. Delegacja w ramach uruchomionego etapu.
- TASK-0805 nie obejmował migracji operatora ani merge/wdrożenia. Zgoda
  na integrację i migrację udzielona później w TASK-0848; brak zgody na
  przebieg shadow, trening, push i aktywację domyślnego silnika.
  Main zawiera 0141; 0143 łączy ją z 0142 przygotowaną w tym tasku.
- Admin i Reviewer budują się poprawnie. Audyt statyczny zamknięty bez
  pozostałych P0–P2. Nowe testy workera 20 PASS, regresje labu 38 PASS,
  klient 79 PASS; testy backendu i UI, typy i OpenAPI PASS.
  Raport: `ai_docs/quality/GRID_V3_SHADOW_IMPLEMENTATION_20261005.md`.
- Po osobnej zgodzie operatora 2026-10-05 testy PostgreSQL: 4 PASS (RLS,
  migracja/downgrade, odczyt w nowym procesie i współbieżność blokad).
  Tymczasowe bazy i role usunięto, brak pozostałości potwierdzono odczytem.
  Bez zmian bazy operatora. Poprawki loading/empty i rozmiarów kontrolek
  potwierdzono 8 testami interakcji Admina, typami/lintem i końcowym buildem.
- Mobilny smoke Edge Chromium 360/390 × 844 PASS: dotyk wybiera zdjęcie,
  pole i symbol, brak poziomego overflow, zero zapisów i wyjątków.
  Fizycznego Androida nie testowano; testowe procesy przeglądarki zakończone.
- Końcowy audyt gpt-6-astra high bez P0–P2, kryteria taska/plan/DoD zamknięte.
  Task: `ai_docs/tasks/completed/0805-grid-geometry-shadow-integration.md`.
  Commit `v1.7.191`; pełny hash po commicie. Etap kodowy zakończony;
  wdrożenie z migracją zakończono później w TASK-0848. Shadow pozostaje
  wyłączony; odbiór inferencji na danych operatora jest osobny.

### TASK-0846 — Mumie: drugi folder (done)

- Operator wskazał `C:\Users\tuszy\Documents\mumie wybrane\481537- 500000 cut`
  po ocenie pierwszego porównania jako niemal identycznego. Folder ma 2052 pliki.
- Wykonano 200 unikalnych zdjęć równomiernie po zakresie; istniejące modele
  iteracji 2 i 3, CPU, ten sam adapter. Zero kopii i znanych SHA.
  Inny folder nie dowodzi innej rodziny. 422 wyniki z kontrolnymi 11.
- Wyniki w `artifacts/mumie-folder-test-20261005/second-481537-500000`;
  wcześniejszy test pozostaje niezmieniony. Kontrolne 11 zdjęć oceniane osobno,
  nie jako nowe referencje drugiego folderu. Bez treningu/DB/migracji/V3-D.
- Oba modele: 199 zdjęć z 9 planszami, jedno z 6, zero błędów struktury.
  Ostatnie zdjęcie zawiera pięć rzeczywistych plansz; obie iteracje tworzą
  fałszywą szóstą na tle. `seq_485704-485712` ma uciętą górę pierwszej planszy;
  2 cropy iteracji 2 i 3 cropy iteracji 3 poza obrazem. Brak dowodu przewagi.
- Mediana różnicy 43128 węzłów 0,327794 px, P95 0,794990 px. Bez accuracy.
  20 par nakładek, największe różnice i cropy obu trudnych przypadków obejrzane.
- 7 testów PASS, nowy proces odzyskuje po 211 wyników bez inferencji;
  ponowne finish/audit/verify PASS. Galeria: filtry 200/11/2 i wycinki PASS.
  Podgląd: `http://127.0.0.1:8108/second-481537-500000/case-review.html`.
- Task i plan: `ai_docs/tasks/completed/0846-mumie-second-folder-test.md`.
  Raport: `ai_docs/quality/MUMIE_SECOND_FOLDER_TEST_20261005.md`.
  Następny zakres: referencje niepełnych ekranów i pustych miejsc, dopuszczenie
  do uczenia po zatwierdzeniach. Commit `v1.7.190`; hash po commicie.

### TASK-0845 — Mumie: test rzeczywistego folderu (done)

- Operator wskazał `C:\Users\tuszy\Documents\mumie wybrane\1 - 23175 cut`
  (2580 JPEG-ów) i upoważnił wykonawcę do doboru części. Test objął
  200 zdjęć równomiernie po zakresie 55–23175, bez SHA kompletnych zdjęć labu.
  Wykluczono 6 identycznych kopii i 5 znanych źródeł; 2569 kwalifikujących się.
- Aktualna rewizja anotacji 591: 31 kompletnych zdjęć Mumii, 11 nowych względem
  iteracji 4. Te 11 oceniono osobno, bez dalszego treningu.
- Porównanie eksportów iteracji 2 i 3 na CPU, istniejące dekodowanie i D-483.
  Wyniki folderu są propozycjami. Bez accuracy na nieoznaczonych zdjęciach,
  bez treningu, DB, migracji, aktywacji i V3-D. Plan:
  `ai_docs/delivery/MUMIE_REAL_FOLDER_TEST_20261005.md`.
- 422 wyniki (211 na model), każde zdjęcie folderu ma po 9 wykrytych plansz;
  zero błędów struktury i pól poza obrazem. Przegląd 20 par nakładek oraz dwóch
  arkuszy wycinków nie pokazał oczywistych przesunięć; nie oceniono ręcznie
  wszystkich pól. Podgląd: `artifacts/mumie-folder-test-20261005/review.html`,
  lokalnie `http://127.0.0.1:8108/review.html` (serwer PID 41152, bez autostartu).
- Nowe 11: oba modele 11/11 zdjęć, 99/99 plansz według D-483. Wszystkie 99
  referencji to zatwierdzone, niezmienione propozycje iteracji 3. Jej niemal
  zerowy błąd nie jest niezależnym dowodem przewagi. Zatwierdzenia zachowano.
- 7 testów PASS, Ruff check/format PASS, Mypy strict jednego modułu PASS;
  wznowienie w nowych procesach: pending=0, recovered=211 na model; verify,
  ponowny finish i audit PASS. Galeria: nawigacja, filtry i wycinki sprawdzone.
- Raport: `ai_docs/quality/MUMIE_REAL_FOLDER_TEST_20261005.md`. Następny zakres:
  niezależna ocena reprezentatywnych cięć i dobór rzeczywistych błędów, zamiast
  automatycznego etykietowania całego folderu. Bez treningu symboli/ramki Super.
- Commit `v1.7.189` / `7ac2fb53ebb6deec3edcf65b1c34d685f70f0a65`
  (hash dopisany po commicie). Numer 0845 wybrano, ponieważ
  0844 zajęto równolegle w głównym checkoutcie. Bez scalenia do checkoutu
  z trwającym zadaniem 0844 i bez push.

### TASK-0847 — poprawne wejście RGB i propozycje sieci w audycie siatek (done)

- Operator zgłosił Śliwka → Arbuz/Pomarańcz oraz Cytryna → Pomarańcz.
- Odczyt czterech plansz odtworzył trzy śliwki w p00519; ich opis barwy
  zdominowało tło. Kod głosowania jest zgodny z Claude, lecz jakość na nowym
  cięciu i przy słabszych propozycjach wymaga osobnej kontroli.
- Próby samej barwy i dopasowania nie usunęły błędów. Głowica istniejącego
  modelu na RGB zgodnym z treningiem daje 120/120 w dwóch małych próbkach
  ocenionych wzrokowo przez agenta; biblioteka 115/120. Nie jest to truth operatora.
- Audyt używa propozycji głowicy RGB i dodatkowego potwierdzenia przez
  ścisłą bibliotekę. Brak zgodności ma `?`. Addytywna wersja algorytmu w API.
  Wagi CNN, wzorce, zatwierdzenia i zatrzymane TASK-0832/0833 bez mutacji.
- Wszystkie 496 otwartych plansz mają 7440 propozycji: 5662 potwierdzone przez
  bibliotekę, 1778 z `?`. 479 poprawionych plansz bez zapisów. Biblioteka SHA bez zmian.
- Nowy proces: `processed=0`, `coveredOpenBoards=496`; API v2 i UI p00519 odebrane
  bez Save. Osobna karta zachowuje poprzedni widok operatora.
- Python 79 + końcowe 15 worker PASS (jeden dodatkowy przypadek); klient 81 PASS,
  Ruff/format, scoped strict Mypy, OpenAPI/client oraz TS klienta i Reviewera PASS.
  Pełny Mypy trafił na niezwiązane błędy share-query/limit czasu; poza zakresem.
- Task i plan: `ai_docs/tasks/completed/0847-grid-audit-rgb-symbol-proposals.md`.
- Commit: `v1.7.192`, `8a42380bc9b6d13d125c5eab2873c8c58076134f`.
- Następny krok: przegląd propozycji przez operatora. Bez treningu/aktywacji,
  migracji, restartów usług, push/merge lub wznowienia TASK-0832/0833.

### TASK-0846 — wstępnie wybrane propozycje symboli audytu (done)

- Operator 2026-10-05 zlecił propozycje także dla niepewnych pól oraz wstępny
  wybór, aby poprawiać tylko błędne symbole przed zapisem. D-493 zmienia D-491.
- Audyt wstępnie wybiera nowe propozycje; niepewne mają `?`. Ręczny wybór,
  usunięcie i „Nie wiem” mają pierwszeństwo. Nowe cięcie usuwa stare automatyczne
  wybory. Zapis czeka na katalog/propozycje i zatwierdza widoczne symbole dopiero
  po kliknięciu operatora. Zwykłe korekty zachowują poprzednie zachowanie.
- Biblioteka/model pozostają zamrożone. Trzy rundy przeliczyły 569 otwartych
  plansz. Odbiór: wszystkie 525 nadal otwarte z 975 (450 już poprawionych),
  6073 pewne i 1802 niepewne propozycje, zero pustych pól. Nowy proces potwierdził
  pokrycie 525/525 bez ponownego rozpoznawania; sumy wszystkich plików sprawdzone.
- 397 testów PASS, format/lint, scoped strict Mypy, TypeScript, OpenAPI/klient
  i build PASS. Lokalny Reviewer zrestartowany; p00474/p00475 odebrane w UI,
  bez zapisu operatora. Nie sprawdzano fizycznego Androida ani restartu komputera.
- Plan i task: `ai_docs/tasks/completed/0846-grid-audit-preselected-symbol-proposals.md`.
- Commit: `v1.7.190`, `222be446718c4655b51fe4bb54de0a3f3baeb045`.
- Następny krok: operator przegląda wszystkie propozycje i zmienia błędne przed
  zapisem. TASK-0845 i zastane zmiany pozostają poza zakresem; bez push/merge.

### TASK-0845 — korekty symboli przez link i przegląd operatora (done)

- Operator 2026-10-05 zlecił poprawianie symboli przez udostępnioną
  wyszukiwarkę, oznaczenia przy wyszukiwaniu/stawce oraz szybki przegląd
  zmian także dalszych plansz w zakresie do 100 000 spinów.
- Operator potwierdził Q1/Q2: zastosowanie od razu i edycja również
  zatwierdzonych plansz. D-492 rozszerza D-471/D-473; bieżące plansze
  operacyjne są edytowalne lokalnie i online.
- Zapis korzysta ze wspólnego writera i atomowego audytu linku. Kontekst
  wyszukiwania/stawki jest jawny; dokładne ponowienie działa po restarcie.
  Historia pozostaje po usunięciu wyszukiwania i revoke. Przegląd sprawdza
  rewizję i SHA planszy, a nowsza zmiana ponownie otwiera kolejkę.
- Admin pokazuje liczniki przy wzorze oraz listę wszystkich zmienionych
  plansz linku. Klik otwiera edytor z historią i wyróżnieniem pól; zamknięcie
  nie zatwierdza przeglądu. Lista nie pobiera całego zakresu 100 000 plansz.
- Testy nowego pionu i regresje, lint, scoped strict Mypy, TypeScript,
  OpenAPI i oba buildy przeszły. Odbiór na danych testowych w Chromium:
  1280×900 i 390×844, bez poziomego overflow, przyciski przeglądu ≥44 px.
  PostgreSQL potwierdził nowy proces, utratę odpowiedzi, rollback audytu
  i revoke równoległe z zapisem. Szczegóły oraz wcześniejsze błędy szerszych
  kontroli (typy grupowania i podwójny React testów Admina) są w Outcome.
- Plan: `ai_docs/delivery/BOARD_SEARCH_SHARE_SYMBOL_CORRECTIONS_PLAN.md`.
  Task: `ai_docs/tasks/completed/0845-board-search-share-symbol-corrections.md`.
- Implementacja: `v1.7.190`, `c61c1e65f87e89e7669507cb902e6348fe3cc48e`.
- Operator zlecił scalenie 2026-10-05 do `v1.1-vision-lab-hybrid-geometry`
  oraz usunięcie worktree i gałęzi `codex/share-symbol-corrections` po scaleniu.
  Zachowano TASK-0846 i niezacommitowane zmiany operatora; konflikty dotyczyły
  tylko dokumentacji. Kontrakt obu funkcji połączył się zgodnie z backendem.
- Commit scalający: `v1.7.191` — `317a07c91bc1429804187d7cc7eebd1a47691770`.
- Logi w `artifacts/task0845-checks/` i `artifacts/task0845-merge/` głównego
  katalogu. Bez wdrożenia, migracji bazy operatora, restartu usług i push.
  Odbiór fizycznego Androida i publicznego tunelu pozostaje do wdrożenia.

- Po scaleniu: 63 testy API/regresji, izolowany PostgreSQL, 80 klienta,
  214 Reviewera, 39 interakcji shared i 1 kolejki operatora PASS. OpenAPI,
  klient i TypeScript czterech workspace PASS; timeout zbiorczy zastąpiono
  mniejszymi grupami. Bez ponownego builda działających aplikacji.
- Cleanup zakończony: worktree `share-symbol-corrections` zarchiwizowano
  przez aplikację i usunięto z dysku/rejestru Git. Scalona gałąź
  `codex/share-symbol-corrections` usunięta przez `git branch -d`.
  Zachowano odzyskiwalny snapshot aplikacji, logi oraz pozostałe worktree.

### TASK-0844 — nowe symbole proponowanych siatek audytu (done)

- Operator 2026-10-05 zlecił przeliczenie symboli otwartych propozycji siatek
  777 i pokazanie wyłącznie nowych podpowiedzi przed własnym przeglądem.
- Jawny zakres: korekta istniejących plansz; bez treningu i nowych importów
  V3 (D-489). Wynik biblioteki jest podpowiedzią, nie decyzją człowieka.
- Przeliczono 917/917 otwartych plansz: 10 425 nowych podpowiedzi i 3330
  pustych pól do ręcznego rozpoznania. 58 poprawionych plansz pominięto.
  Kolejka i decyzje człowieka nie zmieniły się podczas przeliczenia.
- Trwałe sidecary mają SHA-256 i dokładny kontekst podglądu. Biblioteka ma
  5653 referencje; wykluczono 192 referencje pochodzące z tego audytu.
  Restart CLI potwierdził 917 wyników, `processed=0`, bez ponownej kalkulacji.
- Reviewer 3001 przebudowano i uruchomiono. Odbiór UI: p00271 ma 10/15 nowych
  podpowiedzi, bez zaznaczonych decyzji symboli. Zmiana cięcia ukrywa wynik.
- Weryfikacja: testy API/CLI, biblioteki, Reviewera i klienta; lint, format,
  scoped strict Mypy, TypeScript, OpenAPI oraz build Reviewera. Szczegóły
  i instrukcja wznowienia w Outcome taska.
- Task i plan: `ai_docs/tasks/completed/0844-grid-audit-new-symbol-suggestions.md`.
- Commit: `v1.7.189`, `a6789285ecfbaa0ca0d94ff3016df6fab8f75d1c`.

### TASK-0842 — Mumie: wznowienie i partie danych (done)

- Operator 2026-10-04 polecił niezależnie dokończyć import i rozpocząć uczenie
  Mumii. Plan `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md` obejmuje jedną
  iterację 4 presetu F i przygotowanie danych. Bez uruchomienia TASK-0805.
- Run 3 zakończył iterację 4, próba 4, GPU worker PID 39560. Trening 901 s w istniejącym
  budżecie 14 400 s. Jawne założenie: jedna próba na tych samych 16 zdjęciach
  treningowych i 4 odłożonych (`--allow-same-data`), bez automatycznego
  powtarzania i bez etykietowania propozycji jako prawdy. Wszystkie trzy kandydaty
  przeszły strażnik 777, ale pogorszyły holdout Mumii (0,003296 →
  0,00351 / 0,00346 / 0,00358). F zachował poprzedni model. Bez nowego ONNX
  i propozycji. Zużycie runu 3602/14400 s, pozostało 10798 s.
- Sprawdzone SHA 225/225 plików folderu Mumii: wszystkie są w katalogu labu.
  Nowy eksport partii `afc4f0d7…fd816` w `artifacts/mumie-training-20261004/batches`:
  236 zdjęć, partie 50/50/50/50/36, 20 kompletnych, 216 do przeglądu,
  2700 nieoznaczonych wycinków z 180 zatwierdzonych plansz. Checksumy odczytane
  w nowym procesie. Powtórne uruchomienie odzyskało identyczny artefakt w 12,17 s.
  Bez zmian zatwierdzeń i bez zapisu do bazy.
- Istnieje zatwierdzony słownik Mumii (10 symboli) i 244 wcześniejsze decyzje
  z 2026-09-28. Wszystkie mają aktualne rewizje siatek, ale 0 dotyczy obecnie
  kompletnych zdjęć V3 i 0 pochodzi z nowego przypisywania D-489. Nie użyto ich
  do treningu symboli. 5 testów, Ruff check/format i Mypy PASS.
- Proponowana krótka nazwa: „Super”. Złota ramka wskazuje symbol wybrany do
  supergry; trzy mumie same nie ujawniają jego klasy. Stan ramki nie jest
  klasą symbolu ani Jokerem. Uczenie ramki i mechanika wypłat pozostają osobne.
- Raport: `ai_docs/quality/MUMIE_TRAINING_RESUME_20261004.md`.
  Następny zlecony zakres: TASK-0843 — wgranie do głównej aplikacji przez API.
  Commit TASK-0842: `v1.7.187` / `9f234575bb7d9090f311d5550a6264bcd7ed7ec2`
  (hash dopisany po commicie).

### TASK-0843 — Mumie w głównej aplikacji (done: upload i preflight)

- Zlecony addytywny import przez istniejące API. Gra draft z profilem Mumii,
  225 źródłowych JPEG-ów, zachowane zakresy `seq_*`. Bez wypłat, etykietowania
  za operatora, aktywacji nowego modelu, shadow i migracji.
- Nowy CLI `scripts/run_mumie_image_import.py` ma osobne kroki upload/advance/status,
  trwały raport, kontrolę SHA wejścia i ograniczone żądania. Historycznego CLI
  `verified_v19` nie uruchamiać. Rewizje bazy i modele pozostają takie jak wdrożone.
- Gra Mumie: `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`, draft,
  `grid_profile_mumie_v1`. Staging `becad72f-200d-4ba1-8d35-464b19d8f299`
  sfinalizowany: 225/225 plików, 61 768 538 bajtów. Upload 13,62 s.
  Stan trwały: `artifacts/mumie-import-20261004/state.json`.
- Geometry job `3e0151c8-b9ff-4da1-b96d-72af4cb01912` completed:
  225 źródeł, 0 failed, 225 review. Preflight wskazuje 2025 nowych pozycji,
  `IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED`. Import plansz nie został uruchomiony;
  kompletne wgranie źródeł nie oznacza materializacji plansz.
- TASK-0830 udostępnia wybór profilu, ale jawnie nie podłącza sieci do importu.
  Sieć działa w labie; główna aplikacja nadal wymaga przeglądu geometrii.
  V3-D/TASK-0805 pozostaje niewykonany bez wyraźnego polecenia operatora.
- Wznowienie w nowym procesie odzyskało ten sam gameId, uploadId i geometryJobId,
  bez nowego transferu i bez duplikatów. Kontekst `gameId` jest trwale dodany
  do wszystkich żądań stagingu/jobów; nie było potrzeby zmiany API ani migracji.
- Raport: `ai_docs/quality/MUMIE_PRODUCTION_UPLOAD_20261004.md`.
- Testy requestów 5/5 PASS, Ruff check/format PASS, Mypy strict CLI PASS
  (1 moduł, bez kontroli importowanych zależności). Commit TASK-0843: `v1.7.188`,
  `476bdc268e366720337299fb843666ec865fd9be` (hash dopisany po commicie). Bez push.
- Commity 187–188 scalone fast-forward do `v1.1-vision-lab-hybrid-geometry`
  w ramach wcześniejszej zgody operatora. Bez zmian kodu uruchamianych usług
  i bez nowego wdrożenia/migracji. Zastane zmiany pozostają poza commitami.


### TASK-0841 — edycja symboli po otwarciu planszy audytu (done)

- Commit: `v1.7.186` / `65ce8f212cc5f2b3930251b6539f8787dcf8df13`
  (wpis hash po commicie).
- Kolejka audytu używa skrótów katalogu (777: `1` Wiśnia, `5` Śliwka,
  `6` Arbuz); `9` oznacza „Nie wiem”. Dalsze symbole dostają `0`, potem litery.
- Podgląd startuje bez czekania na pełne zdjęcie canvas; pierwsze pole mające
  piksele jest zaznaczone po podglądzie. Opóźniony katalog uruchamia paletę bez
  ponownego podglądu. Zaznaczenie niczego nie przypisuje ani nie zapisuje.
- Dwa testy regresji odtworzyły brak podglądu przed poprawką. Po poprawce:
  interakcje Reviewera 18/18, jednostkowe 208/208, lint, typecheck,
  formatowanie pięciu plików i build poprawne. Build w worktree ostrzega
  o dodatkowym lockfile przy wykrywaniu root; nie wpływa na wynik.
- Nowe ustawienia edytora są opcjonalne; zwykła korekta zachowuje dotychczasowe
  zachowanie. Bez zmian API, migracji i zapisu na żywej bazie.
- Poprawka scalona fast-forward do `v1.1-vision-lab-hybrid-geometry`.
  Reviewer z głównego checkoutu przebudowany (17,27 s) i zrestartowany;
  launcher PID 3432, HTTP 200. Pierwszy polling z timeoutem 1 s na request
  nie potwierdził gotowości; odczyt logów i nowy odczyt HTTP potwierdziły
  działanie tej samej kopii (bez ponownego startu).
- Odbiór w świeżo otwartej planszy 423759: podgląd 15/15, pierwsze pole
  zaznaczone, paleta `1–9` widoczna. Klawisze `1`, `5`, `6`, `9` zweryfikowane
  bez ruszania siatki i ręcznego preview. Testowy wybór usunięto bez zapisu.
  Screenshot: `artifacts/grid-v3-deployment-20261004/task0841-live.jpg`.
- Wyniki odbioru i własny hash dopisane po commicie; brak push. Zastane zmiany
  użytkownika w wygenerowanym kliencie oraz package-lock zachowane.

### Wdrożenie silnika siatek V3 — migracja 0140 i kolejka audytu działają (2026-10-04)

- Commit zamknięcia wdrożenia: `v1.7.185` /
  `fcc53b06df0526504f31b5c5edcc97bda1d2fe10` (wpis hash po commicie).
- Operator zakończył przypisywanie symboli i zatwierdził scalenie oraz wdrożenie
  kroku 1 handoffu. Gałąź `feat/grid-engine-v3` scalona bez konfliktów do
  `v1.1-vision-lab-hybrid-geometry`: `v1.7.184` /
  `67e02e8b512eb396e6fbf0f790b8746b12dd70de`.
- API 8000, Admin 3000, Reviewer 3001 i worker general zatrzymane przed
  scaleniem. Odczyt bazy przed wdrożeniem: `0139_source_image_geometry_completeness`.
  Migracja `0140_grid_engine_profiles` wykonana; rola aplikacyjna zgodna.
  `npm install` zakończone, Admin i Reviewer przebudowane. Usługi 8000/3000/3001
  odpowiadają HTTP 200. API działa jak wcześniej z `--reload` z głównego checkoutu.
- TASK-0830 wdrożony: oba profile mają model i manifest `available` (SHA-256
  zgodne). Odbiór formularza Admina: „777 v2” i „Mumie” pokazują „Model dostępny”;
  formularz zamknięto bez tworzenia gry i bez zmiany konfiguracji 777.
  Implementacja: `v1.7.181` / `e61ee6c6941dd569d1f04087244877ccd6ca3f91`.
- TASK-0840 wdrożony: kontrola w transakcji `REPEATABLE READ READ ONLY` na `0140`
  wykazała 975 aktualnych propozycji, 237 plansz z decyzjami symboli (490 pól),
  zero nieaktualnych. Artefaktu nie nadpisano. API zwraca 975 otwartych pozycji;
  Reviewer pokazuje planszę 171127, siatkę sieci i 15/15 podglądów cropów.
  Nie zapisano żadnej korekty. Implementacja: `v1.7.183` /
  `b7d649952980bb8f7b107eebc50a81e082084b78`.
- Weryfikacja scalenia: API 50/50; interakcje Reviewera 16/16; testy jednostkowe
  Admina 624/624, Reviewera 207/207, klienta 78/78; typecheck tych trzech części,
  lint i oba buildy poprawne. Lint Admina ma cztery wcześniejsze ostrzeżenia.
  OpenAPI Admina zgodne z backendem. Użyto npm 11.19.0 z instalacji Node dla
  kontroli i buildów; `npm.cmd` wskazuje globalne npm 12.0.2 poza zakresem engines.
- Worker general przywrócony z wcześniejszym budżetem 7 wątków. Pierwsze zatrzymanie
  miało timeout finalizacji statusu; procesy rzeczywiście zakończono, a następnie
  `--mark-lane-stopped` zakończyło się poprawnie z nowego procesu przed startem.
  Logi i zapis PID: `.runtime/grid-v3-deployment-services.json` i artefakty
  `artifacts/grid-v3-deployment-20261004/`. Lokalne zmiany zastane przed wdrożeniem
  zachowano; `package-lock.json` ma identyczną sumę przed i po instalacji.
- Zakres obejmuje TASK-0830 i TASK-0840. Plan symboli Mumii nadal `proposed`;
  TASK-0805 (shadow) nie został uruchomiony. Brak zgody na usuwanie danych.
- Następnie: operator poprawia plansze w kolejce audytu; pierwszy zapis korekty
  na żywej bazie pozostaje do odbioru podczas jego pracy. Nie wykonano restartu
  Windows ani pełnego zestawu testów PostgreSQL; brak potrzeby ponawiania
  wcześniej wykonanych testów migracji na bazach testowych.

### TASK-0835 — konflikt rewizji przy zapisie korekty siatki (done)

- Zapis w „Korekcie cięcia siatki” kończył się `IMAGE_GRID_REVIEW_REVISION_CONFLICT`
  dla plansz z komórkami przypiętymi do starszego renderera (import 777: wszystkie
  `v1`, bieżący `v4`). Po TASK-0815 serwis wiązał kontekst z bieżącym rendererem,
  a repozytorium porównywało go z kontekstem z bazy. `_require_same_context` pomija
  teraz wersję extractora; rewizje, źródło i geometria nadal muszą się zgadzać.
- Testy `test_virtual_grid_geometry.py` 27/27. API przeładowane (`--reload`).
  Brak testu zapisu na żywej bazie.

### TASK-0834 — skróty klawiszowe symboli w korekcie siatki (done)

- Paleta symboli korekty (Reviewer 3001) używa tych samych klawiszy co Weryfikacja
  symboli (1–9, 0, litery wg kolejności katalogu gry): klawisz wybiera symbol
  zaznaczonego pola, a przycisk palety pokazuje swój klawisz. „? Nie wiem” i
  „Usuń wybór” bez skrótu.
- Interakcje 9/9, typecheck i lint czyste. Reviewer przebudowany i zrestartowany;
  brak odbioru na żywo.

### TASK-0827 — poprawianie planszy z wyników wyszukiwania (done)

- Karta „Wyniki wyszukiwania” ma przycisk „Pokaż planszę”: otwiera to samo okno z liniami
  wypłat co tabela przybliżonej wygranej, z „Popraw symbole”. Z wyników okno nie
  ma numeru spinu; wygrana i spójność linii pochodzą z odczytu planszy.
- Po zapisanej poprawce zamknięcie okna ponawia wyszukiwanie (zaznaczony wynik
  zostaje). Bez zmian API.
- Interakcje 38/38, typecheck i lint czyste. **Brak odbioru na żywo**: wymagany
  `reviewer:build` i restart.

### TASK-0825 — opcja „Nie wiem” w palecie symboli korekty siatki (done, D-488)

- Paleta ma przycisk „? Nie wiem”: pole zasłonięte lub widoczne we fragmencie można
  zapisać bez zgadywania. `cellSymbols[].symbolId = null` oznacza komórkę jako
  nieczytelną (`mark_unreadable`, oczekująca, bez etykiety); symbol dalej daje
  `reassign`. Kafelek pokazuje „?”, „Usuń wybór” przywraca podpowiedź.
- Zmiana kontraktu API (nullowalny `symbolId`), OpenAPI i klient wygenerowane.
- Testy API 42/42, interakcje Reviewera 12/12, typecheck, lint i `check:generated`
  czyste. **Brak odbioru na żywo**: wymagany restart API i `reviewer:build`.

### TASK-0826 — trwałe usunięcie zarchiwizowanej gry V2 (done)

- Na prośbę operatora (2026-10-02) usunięto z bazy deweloperskiej dwie testowe,
  zarchiwizowane gry „Mumie” (`mums`, `mums-test-1`): partycje `game_data_v2`,
  symbole, wersje zasad, zadania i rekordy gier. W bazie pozostaje jedna gra:
  777 (`draft`), nienaruszona (63 partycje, 590 zadań).
- Nowa komenda `scripts/delete_archived_v2_game.py` (podgląd tylko do odczytu,
  blokady, potwierdzenie + SHA, wznawianie) nad istniejącym lifecycle `delete`;
  opis w `LOCAL_OPERATION_GUIDE.md`. Admin nadal tylko archiwizuje.
- Na dysku pozostały niereferencjonowane pliki obu gier (ok. 8 MB w
  `imports/browser-selections` i jeden manifest geometrii); lista w Outcome
  zadania. Scalono do `v1.1-vision-lab-hybrid-geometry` jako `v1.7.168`
  (numer zadania zmieniony z TASK-0812 na TASK-0826, bo 0812 i 0824 zajęte).

### TASK-0822 — klikalne kafelki i wybór symbolu w korekcie siatki (done, D-488)

- Ekran „Korekta cięcia siatki” (Reviewer 3001): kafelek podglądu z pikselami
  jest przyciskiem, pod podglądem jest paleta aktywnych symboli gry. Kafelek
  pokazuje podpowiedź (kursywa) albo wybór operatora (pogrubienie, zielone
  tło); „Usuń wybór” cofa wybór. Zapis siatki wysyła wyłącznie wybrane pola
  (`cellSymbols`); pola bez pikseli nie są klikalne.
- Podpowiedzi są pobierane po każdym aktualnym podglądzie; ich błąd nie
  blokuje korekty ani zapisu. Dialog korekty w przeglądzie operacyjnym nie ma
  palety (poza zakresem planu).
- Testy: interakcje Reviewera 11/11 (2 nowe), jednostkowe 200/200 (1 nowy),
  typecheck i lint czyste.
- **Brak odbioru na żywo.** Po scaleniu wymagany restart API i
  `npm run reviewer:build`. Plan
  `GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md` jest wykonany w całości.

### TASK-0821 — podpowiedzi symboli dla cięcia w korekcie siatki (done, D-488)

- `GET /admin/image-reviews/{reviewItemId}/correction-symbols`
  (`getImageGridReviewCorrectionSymbols`): symbole zapisane na bieżących
  komórkach planszy zgłoszonej — przypisany, a przy jego braku predykcja.
- `POST …/board-cell-geometry-pending/{pendingId}/geometry-symbol-preview`
  (`previewPendingBoardCellGeometrySymbols`): predykcja przypiętego modelu dla
  podanego cięcia planszy odroczonej; brak modelu → pusta lista. Oba endpointy
  niczego nie zapisują. Nowy POST jest na allowliście proxy Reviewera i
  serwerowej allowliście originu 3001 (`security/local_admin.py`).
- Testy: serwis 56/56, żądania API (pending 13, grid review, security 6),
  PostgreSQL 1/1, klient 76/76, Reviewer 199/199; `openapi --check` i
  `check:generated` aktualne.

### TASK-0820 — zapis symboli operatora przy zapisie siatki (done, D-488)

- `createImageGridReviewGeometryRevision` i
  `resolvePendingBoardCellGeometryManually` przyjmują opcjonalne `cellSymbols`
  (`cellIndex`, `symbolId`). Wskazane pola są zatwierdzane istniejącą akcją
  `REASSIGN` (`approved`, `human`) dla nowego cropa, w transakcji zapisu
  geometrii; powtórzenie tym samym kluczem stosuje przypisania ponownie.
- Błąd przypisania (pole bez bieżącego cropa, nieaktywny symbol, zdublowany
  indeks) wycofuje cały zapis. Zapis bez `cellSymbols` działa jak dotąd.
- Testy: serwis 53/53, test PostgreSQL przypisań 1/1 (izolowana baza testowa),
  żądania API 13/13, klient 76/76, Reviewer 199/199, typecheck Reviewera.
  `test_grid_review_openapi_is_topology_aware_and_checksum_bound` pada także
  na niezmienionej gałęzi (oczekuje `minItems` komórek) — poza zakresem.
- Plan: `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`; dalej
  TASK-0821 (podpowiedzi) i TASK-0822 (UI).

### TASK-0819 — podgląd korekty siatki dla niepełnych plansz, jeden widok cropów (done)

- Zgłoszenie operatora: podgląd niepełnej planszy kończył się
  `IMAGE_GRID_REVIEW_VIRTUAL_CELLS_INCOMPLETE`. Kontrola arkusza podglądu
  wymagała braku renderu dla każdego pola z maski, a renderer od D-434/D-435
  zachowuje pola częściowo widoczne. Teraz wymagane są tylko pola spoza maski;
  pola z maski mogą mieć render. Dwa czerwone testy podglądu częściowego
  opisywały stare zachowanie i zostały zaktualizowane.
- Reviewer pokazuje jeden widok cropów (kafelki); usunięto zdublowany obraz
  zbiorczy bez odstępów.
- Testy API korekty siatki 50/50, interakcje geometrii Reviewera 9/9,
  typecheck i lint Reviewera czyste. Wymagany restart API i przebudowa
  Reviewera; brak odbioru na żywo.
- Otwarte: przypisywanie symboli w korekcie siatki (klikalne kafelki, podgląd
  predykcji) wymaga planu i zmiany D-462 — korekta dziś nie zatwierdza symboli.

### Scalenie toru odczytów wyszukiwarki i dziennika linku (2026-10-02)

- `v1.7.163`: gałąź `claude/board-default-symbols-refresh-ff0843` scalona do
  `v1.1-vision-lab-hybrid-geometry` (TASK-0814, 0816, 0817, 0818; D-486,
  D-487). Jej commity `v1.7.158`–`v1.7.162` mają numery sprzed scalenia;
  `v1.7.158` na gałęzi integracyjnej to TASK-0815 (korekta siatki).
- Po scaleniu: `npm install`, `npm run reviewer:build` i restart instancji
  API, aby zapis stawki odbiorcy (D-487) i grupowanie dziennika zadziałały.

### TASK-0817 — stawka odbiorcy na wykresach dziennika linku (done)

- D-487: strona linku zgłasza stawkę każdego pokazanego zakresu
  (`GET …/approximate-win/stake`), API zapisuje ją jako wpis zakresu ze
  `stakeGrosze`, a wykres w dzienniku Admina jest rysowany w tej stawce.
  Bez migracji. Starsze wpisy: „stawka nieznana (wykres w stawce bazowej)”.
- Do działania u odbiorców potrzebne są przebudowany Reviewer
  (`npm run reviewer:build`) i restart API po scaleniu.

### TASK-0816 — dziennik linku grupuje te same wzory (done)

- D-486: `listBoardSearchShareQueries` z `groupByPattern=true` zwraca jeden
  wpis na wzór z `occurrenceTimes`; `deleteBoardSearchShareQuery` z
  `wholePattern=true` usuwa wszystkie wyszukiwania wzoru. Dziennik w Adminie
  pokazuje czasy po przecinku i przycisk „Usuń wszystkie (N)”.
- Przy okazji naprawiony nieaktualny test interakcji dziennika
  (`board-search-share-panel.test.mjs` oczekiwał kontraktu sprzed D-478).

### TASK-0814 — hurtowe odświeżenie nieaktualnych odczytów wyszukiwarki (done)

- 2026-10-02 operator zgłosił, że „Pokaż planszę” dla #486288 pokazywało
  schemat z domyślnymi grafikami symboli zamiast zdjęcia do czasu ręcznego
  „Odśwież odczyt tej planszy”. Przyczyna: odczyt wyszukiwarki zapisany przed
  bieżącą siatką planszy (`documentStale`, TASK-0773). Gra 777 miała 62 142
  takich plansz (wszystkie `pending`) z 499 997.
- Nowy `scripts/refresh_stale_board_search_documents.py --game-id …` liczy
  je bez zapisu, a z `--apply` odświeża każdą tą samą synchronizacją co
  przycisk w oknie, partiami po jednej transakcji; ponowne uruchomienie
  wznawia pracę. Commit `v1.7.158` / `cd36d0a2`.
- Wynik uruchomienia na bazie deweloperskiej (2026-10-02): próba 200 plansz
  i pełny przebieg 61 942 — razem 62 142 odświeżone, 0 usuniętych z
  wyszukiwarki, 0 nadal nieaktualnych; kontrolny podgląd po przebiegu: 0.
- Przyczyna zaległości: jednorazowa ponowna weryfikacja siatek 777 z
  2026-09-25 (`system:grid-reverify-777-v1`), wykonana zanim zapis siatki
  zaczął synchronizować projekcję wyszukiwarki (`v1.7.51`, 2026-09-29;
  przepinanie sąsiednich plansz — `v1.7.145`). Żadna nieaktualna plansza nie
  miała siatki zapisanej po 2026-09-25, więc poprawka kodu nie była potrzebna.

### TASK-0818 — plansze „częściowa (potwierdzone minimum)” do korekty siatki (done)

- Decyzja operatora 2026-10-02: plansze z nieznanymi polami oznaczonymi
  `unreadable` albo `partial_visibility` trafiają do kolejki „korekta cięcia
  siatki”. `scripts/route_partial_boards_to_grid_correction.py` (podgląd,
  `--apply`) zgłasza te pola jako „zła siatka” istniejącą decyzją pola.
  Commit `v1.7.159` / `104f9d81` (numer sprzed scalenia; zadanie
  przenumerowane z 0815 z powodu kolizji z torem korekty siatki).
- 777: skierowano 219 plansz (179 + 40), 0 pominiętych; kolejka korekty ma
  331 plansz w 20 importach. 7 plansz bez rekordu pola pozostało bez zmian.
  Skierowanie jest jednorazowe; nowe przypadki wymagają ponownego uruchomienia.
### TASK-0815 — ręczna korekta siatki po bumpie kontraktu renderera (done)

- Zgłoszenie operatora: każda zmiana siatki w „Korekcie cięcia siatki” kończyła
  się `IMAGE_VIRTUAL_CELL_EXTRACTOR_MISMATCH`. Kontekst korekty brał wersję
  extractora z render speców istniejących komórek (albo ze snapshotu rolloutu
  joba), a renderer po TASK-0660/0661/0663 ma `…-source-direct-v4`, więc
  odrzucał plansze zaimportowane wcześniej.
- `VirtualGridGeometryService` wiąże teraz konfigurację renderu z bieżącym
  rendererem (pojedyncza plansza, zapis źródła/odroczonego slotu, konwersja
  legacy); pozostałe przypięte pola (preprocessing, interpolacja, rozmiar,
  padding) bez zmian. Bez zmian API, schematu i danych.
- Test regresyjny przechodzi; plik testów 48/50 — dwa przypadki
  `test_qualified_partial_preview_…` padają także bez tej zmiany (poza
  zakresem). Wymagany restart API; brak odbioru na żywym Reviewerze.

### TASK-0782 — zmiana kolejności symboli w katalogu (done)

- Gałąź `feat/symbol-display-order` (worktree `worktrees/symbol-display-order`)
  od `v1.7.56`. `PATCH` symbolu przyjmuje `displayOrder`; katalog symboli w
  Adminie ma przyciski „↑/↓”, które przenumerowują listę `0..n-1`. Skróty 1–9
  weryfikacji symboli i wyszukiwarki plansz podążają za kolejnością. Operator
  zamienia „7” i „gwiazdę” w grze 777 w panelu; snapshot mobilny dostanie nową
  kolejność przy kolejnym `snapshot:generate`.
- Commit `v1.7.57` / `5ab34453` na gałęzi `feat/symbol-display-order`
  (numer sprzed scalenia; zadanie przenumerowane z 0730 z powodu kolizji).
  Scalone do `v1.1-vision-lab-hybrid-geometry` commitem `v1.7.132`.

### Hybrydowy silnik siatek V3 — plan zaakceptowany, etap V3-0 w toku (2026-10-01)

- 2026-10-01 operator zaakceptował wszystkie pięć decyzji planu
  `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (status
  `accepted`): D-484 bramka kompletności zdjęcia (wymaganie w
  `IMAGE_INGESTION.md`), D-480 geometria produkcyjna 777 jako dane uczące,
  D-481 budżet treningu, D-482 etap D bez etapu C, D-483 metryka nadrzędna.
  Operator uruchomił etap V3-0 (TASK-0806, potem TASK-0807); po etapie STOP.
- Praca w worktree `worktrees/grid-engine-v3`, gałąź `feat/grid-engine-v3`
  od `v1.7.134` / `a6f8635f`. `.venv` worktree to cienkie środowisko z
  plikiem `.pth` wskazującym pakiety głównego checkoutu i edytowalną
  instalacją kodu worktree (obejście zamiast pełnej instalacji zależności).
- Kontrola bazy 2026-10-01 (777): 56 816 zdjęć, 56 710 z kompletem
  rozpoznanych plansz, 99 bez plansz (`processing`), 7 niepełnych; plansze
  z automatyczną rewizją `needs_review` bez zatwierdzenia: 1 729,
  `pending_partial`: 108.
- Pliki zadań: `ai_docs/tasks/0806-image-geometry-completeness-report.md`,
  `ai_docs/tasks/0807-image-geometry-completeness-gate.md`. TASK-0807
  kończy się migracją zweryfikowaną na bazach `*_test`; migracja bazy
  deweloperskiej wymaga osobnej zgody i skoordynowanego przejścia.
- Akceptacja planu, decyzje i pliki zadań: commit `v1.7.135` / `ef5e4079`
  (numer sprzed scalenia; na gałęzi integracyjnej `v1.7.135` to TASK-0797).
- TASK-0806 done (`v1.7.136` / `0bcbff63`): raport kompletności geometrii
  zdjęć tylko do odczytu — trzy endpointy pod
  `/admin/image-review-items/geometry-completeness/{gameId}` (liczniki,
  lista zdjęć niekompletnych, sygnał niskiej jakości symboli) i sekcja
  „Kompletność siatek zdjęć” w „Import plansz”. Stan 777 z raportu: 56 812
  zdjęć, 56 413 kompletnych, 399 niekompletnych (94 z brakującą planszą, 60
  z planszą częściową, 237 z siatką niepotwierdzoną, 8 bez geometrii
  źródła); pozycje: 1 703 niepotwierdzone, 108 częściowych, 842 brakujące,
  0 odroczonych. Odbiór w przeglądarce na instancji worktree (Admin
  `127.0.0.1:3020`, API `127.0.0.1:8020`).
- `v1.7.137` / `a6426f3f`: scalenie gałęzi integracyjnej (migracja `0138`,
  TASK-0784, TASK-0797). Decyzja bramki kompletności ma numer **D-484**
  (D-479 zajął tor „Przybliżonej wygranej”); pozostałe decyzje planu to
  D-480–D-483.
- Otwarte po TASK-0806, do decyzji operatora przy STOP V3-0: (1) 1 703
  plansze na 240 zdjęciach wskazują starą automatyczną rewizję
  `needs_review`, choć zdjęcie ma nowszą ręczną rewizję `accepted`
  (`system:legacy-board-conversion-v1`) — dziś liczone jako niepotwierdzone;
  (2) plansze o statusie `rejected` (10 390) liczą się jak plansze z siatką;
  (3) 99 zdjęć bez żadnej planszy nie ma podglądu pliku w liście.
- 2026-10-02: wykonawca TASK-0807 został przerwany razem z sesją i nie
  zostawił zmian (worktree czysty); zadanie pozostaje `todo`.
- 2026-10-02, ustalenia z bazy (tylko `SELECT`) do pytań operatora:
  (1) z 1 703 plansz na starej rewizji 449 to żywe plansze na 79 zdjęciach
  po konwersji legacy z 2026-10-01 (operator polecił je przepiąć na
  najnowszą rewizję zdjęcia i utrzymać tę regułę), a 1 254 to plansze
  odrzucone; (2) 10 389 z 10 390 plansz `rejected` należy do zduplikowanego
  importu `7d10ae0a` (zastąpione przez `pending_sequence_replaced_by_newer_import`,
  każdy numer ma żywą planszę gdzie indziej, bez komórek); (3) 99 zdjęć bez
  plansz to nieudane pliki importu (88 `IMAGE_STAGE_EXECUTION_FAILED`, 6
  `IMAGE_STAGE_RESULT_INVALID`, 5
  `IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE`); pliki istnieją, 73 mają
  ten sam SHA zaimportowany poprawnie w innym imporcie. Propozycja czekająca
  na potwierdzenie operatora: raport nie liczy pozycji zastąpionych nowszym
  importem, pokazuje kod błędu importu, podgląd po `source_image_id`.
- 2026-10-02: do planu dodano regułę izolacji danych per gra i TASK-0809
  (kontrola izolacji i gotowości na nową grę, bez zmian schematu). Kontrola
  bazy: 63 tabele gry partycjonowane `LIST (game_id)`, 3 gry × 63 partycje,
  RLS na wszystkich, zapytanie jednej gry dotyka tylko jej partycji; żadna
  zmiana schematu nie jest potrzebna dla izolacji.
- 2026-10-02 operator: osobna baza PostgreSQL per gra odrzucona (partycje
  wystarczają); potwierdzony tor TASK-0808 → TASK-0807 → TASK-0809; zgoda
  na migrację `0139`, backfill i potrzebne zatrzymanie usług na bazie
  deweloperskiej przy STOP V3-0. Usunięcie duplikatu `7d10ae0a` nie zostało
  zlecone.
- TASK-0808 done (`v1.7.141`): plansza `rejected` nie jest planszą z
  siatką; stany `superseded` (pozycja i zdjęcie) oraz `import_failed`;
  odczyt pliku źródłowego po `source_image_id`
  (`GET …/geometry-completeness/{gameId}/images/{sourceImageId}/source`);
  `previewReviewItemId` usunięte z listy. Stan 777: 56 812 zdjęć, 55 423
  kompletne, 136 niekompletnych (60 z planszą częściową, 76 z siatką
  niepotwierdzoną — 449 pozycji), 1 253 zastąpione nowszym importem
  (11 232 pozycje), 0 brakujących, 0 `import_failed`.
- 2026-10-02: na gałęzi integracyjnej istniała równoległa korekta planu
  (`v1.7.141` / `06584ad7`: 777 poza zakresem, bramka tylko w labie, budżet
  30 minut, status `proposed`). Operator rozstrzygnął sprzeczność:
  obowiązuje wersja planu z tej gałęzi (`accepted`, D-480–D-484, bramka w
  pipeline produkcyjnym, TASK-0806–0809); korekta jest zastąpiona przy
  scaleniu `v1.7.144`. Pozostałe okna nie pracują już nad V3; gałąź
  integracyjna jest wolna do wdrożenia.
- `v1.7.144` / `76623320`: scalenie gałęzi integracyjnej (do `v1.7.143`).
- TASK-0807 (`v1.7.145` / `17c6a27f`), kod gotowy, wdrożenie na bazie
  deweloperskiej jeszcze niewykonane: migracja `0139` (stan kompletności i
  wyjątek operatora na `source_images`), przeliczanie stanu w transakcji
  każdego zapisu geometrii, bramka w materializacji komórek i projekcji
  wyszukiwarki, przepinanie plansz na najnowszą rewizję źródła, wyjątek
  operatora w Admin API, backfill z podglądem
  (`npm run images:geometry-completeness:backfill`), kolejka w Adminie.
  Rozstrzygnięcia wykonawcze: D-485. Oczekiwany wynik backfillu 777: 55 499
  `geometry_complete`, 60 `geometry_incomplete` (plansze częściowe, mają
  komórki), 1 253 poza bramką; 449 plansz do przepięcia, 0 nieprzepinalnych.
  Zadanie zostaje w `ai_docs/tasks/` ze statusem `in_progress` do czasu
  wdrożenia. Pełny `db:baseline:verify`: 19 testów nie przechodzi także
  przed zadaniem (osobne zadanie porządkowe).
- TASK-0809 done (`v1.7.146` / `063c3970`): test nowej gry obok dużej —
  komplet 63 partycji, kolumny `0139`, bramka i komórki działają od
  pierwszego importu, plany czterech ścieżek dotykają wyłącznie partycji
  tej gry; test strażniczy tabel gry; raport
  `ai_docs/quality/PER_GAME_ISOLATION_20261002.md`. Tabele współdzielone
  pipeline (ok. 0,6 GB) bez podziału. CHECK wyjątku poprawiony na odporny
  na `NULL` przed wdrożeniem.
- **STOP V3-0 osiągnięty 2026-10-02.** Scalenie `v1.7.148` / `fa29cd76` do
  `v1.1-vision-lab-hybrid-geometry`, migracja `0139` zastosowana na bazie
  deweloperskiej, backfill 777 wykonany: 55 499 `geometry_complete`, 60
  `geometry_incomplete`, 1 253 poza bramką, 449 plansz przepiętych na
  najnowszą rewizję źródła, 0 nieprzepinalnych. TASK-0807 done. API `8000`
  i Admin `3000` działają z nowym kodem.
- Do zrobienia przez operatora: 60 zdjęć ze 108 planszami częściowymi czeka
  w kolejce „Kompletność siatek zdjęć” na wyjątek albo uzupełnienie siatek.
- Porządek 2026-10-02 (polecenie operatora):
  - TASK-0810 done (`v1.7.150` / `d3d54da1`): 19 nieaktualnych testów
    integracyjnych PG dostosowanych do magazynu `game_data_v2` i bieżących
    kontraktów; siedem plików przechodzi (21 passed, 1 `xfail(strict)`),
    żaden test nie usunięty. Znaleziony błąd produktu: repozytoria tabel gry
    rozpoznają naruszenie unikalności po nazwie indeksu rodzica, a
    PostgreSQL zgłasza nazwę indeksu partycji (przydziały Reviewera, partie
    przeglądu, decyzje guard geometrii, nadpisania geometrii strony) —
    proponowane TASK-0812 razem z regułą `eol=lf` dla plików wiązanych sumą
    kontrolną i martwym `backfill_legacy_states`. Pełny
    `db:baseline:verify` nie był ponownie uruchamiany.
  - TASK-0811 done (`v1.7.151`): narzędzie
    `npm run images:remove-superseded-import-images` (podgląd, kopia JSONL,
    jedna transakcja, niezmienniki). **Usunięcia nie wykonano**: import
    `7d10ae0a` nie jest czystym duplikatem (6 zdjęć / 51 plansz żyje tylko
    w nim), a pozostałe 1 154 zdjęcia są wskazywane przez 152 865 zdarzeń
    weryfikacji symboli importu `f4ef3449`
    (`previous_source_geometry_revision_id`); podgląd kwalifikuje 0 zdjęć.
  - TASK-0812 done (`v1.7.152`): wspólny `storage/partition_constraints.py`
    rozpoznaje naruszenie unikalności zgłoszone na partycji gry (rodzic z
    `pg_inherits`, dopasowanie kolumn i predykatu do ograniczeń ORM) w
    czterech repozytoriach tabel gry; test przydziałów bez `xfail`;
    `ai_docs/quality/*.json` z `eol=lf` (`test_reviews.py` 7/7 na Windows);
    martwy `backfill_legacy_states` usunięty. Pełny `db:baseline:verify`:
    233 passed, 3 failed — wszystkie trzy przechodzą uruchomione osobno,
    przyczyną jest limit 260 znaków ścieżki Windows w głębokim katalogu
    worktree (dwa potwierdzone `FileNotFoundError`, trzeci niezdiagnozowany).
- 2026-10-02 operator uruchomił etap V3-A (TASK-0800, TASK-0801) po
  TASK-0812; STOP przy przeglądzie plansz w TASK-0801.
- TASK-0800 done (`v1.7.153`): eksport geometrii produkcyjnej 777 tylko do
  odczytu (`scripts/vision_lab_geometry_export.py`, czysty moduł
  `vision_lab/production_geometry.py`). Wynik w
  `game_predictor_vision_data\production-geometry\production-geometry-777-20261002\`
  (1,59 GB, 8 min): 499 460 plansz-kandydatów ze zdjęć `geometry_complete`,
  0 wykluczeń, 24 węzły zgodne z manifestem renderu (odchyłka 0 px).
  Poziomy: G 459 plansz na 101 zdjęciach (198 `local-admin`, 261 zapisanych
  przez Reviewera), S 137 473 na 15 275 zdjęciach, B 361 103 na 40 123
  zdjęciach, 425 niesklasyfikowanych (konwersja legacy bez autora). 24
  rodziny źródeł (katalog joba importu; nagrania nie da się odtworzyć z
  danych). Raport:
  `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`.
- TASK-0801 done (`v1.7.155` / `9df424c5`; numer `v1.7.154` pominięty
  omyłkowo przez orkiestratora, nie istnieje commit o tym numerze): snapshot
  `game_predictor_vision_data\production-geometry-snapshots\3ff448c6…727d`
  (1,83 GB, 6 700 zdjęć, polityka `production-geometry-split-v1`, ziarno
  801): trening 6 000 zdjęć (3 000 S + 3 000 B, 54 000 plansz, 21 rodzin,
  największa 8,7%), development 600 zdjęć z trzech całych rodzin, zbiór
  złoty 102 zdjęcia / 459 plansz G. Filtr zgodności symboli odrzucił 5 669
  zdjęć. Rozłączność i determinizm potwierdzone testami i niezależnym
  skryptem. **Ograniczenie:** wszystkie plansze G leżą w rodzinach widzianych
  w treningu (podzbiór „rodzina niewidziana” jest pusty); rodziny
  developmentu to sąsiednie wycinki tego samego długiego nagrania co część
  rodzin treningowych. Raport:
  `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`.
- **STOP V3-A (2026-10-02).** Czeka na operatora: przegląd 600 plansz (300 S
  + 300 B, ślepy) w narzędziu `label_review` na `http://127.0.0.1:8103`
  (katalog `production-geometry-snapshots\label-review-seed801`); wynik —
  odsetek błędnych etykiet z przedziałem Wilsona — rozstrzyga, czy S i B
  nadają się do treningu. Następny etap V3-B (TASK-0802, TASK-0803) wymaga
  jawnego uruchomienia.
- 2026-10-02 operator: wymusić niezależny podzbiór złoty przed treningiem;
  podobieństwo rodzin (jedno nagranie, ruchoma kamera) jest cechą danych;
  uruchomić etap V3-B z budżetem 3 runy × 4 h GPU (D-481). Przegląd 600
  plansz nie został jeszcze wykonany (0 decyzji) — trening rusza równolegle,
  wynik przeglądu pozostaje warunkiem oceny przydatności etykiet S/B.
- TASK-0813 done (`v1.7.157`): polityka `production-geometry-split-v2`,
  snapshot treningowy **obowiązujący dla V3-B**:
  `production-geometry-snapshots\286f2e37…df59` (1,81 GB). Rodziny
  `0dbd07df` (1-19809) i `299e7c72` wyłączone z treningu: 249 z 459 plansz G
  (54,2%) leży w rodzinach niewidzianych, 210 w widzianych; utrata puli
  treningowej 4,2%. Trening 6 000 zdjęć (3 000 S + 3 000 B, 21 rodzin),
  development 600 zdjęć (rodziny `0dbd07df`, `c0932585`, `299e7c72`), złoty
  102 zdjęcia. Snapshot v1 nietknięty.
- TASK-0823 done (`v1.7.159`; w commicie jako TASK-0814, numer zajęty przez inny tor): druga runda przeglądu etykiet. Wynik
  przeglądu operatora (600 plansz, ślepy, 2026-10-02): B 300/300 dobrych; S
  294 dobre, 5 lekko naciętych, 1 zła — odsetek luźny 0,3% (Wilson 95%:
  0,1–1,9%), ścisły 2,0% (0,9–4,3%); nacięcia skupione na pozycji 2 (prawa
  górna plansza). Etykiety S i B nadają się do treningu.
- D-489 (2026-10-02; pierwotnie zapisane jako D-486, numer zajęty przez inny tor): symbole dla V3 przypisuje operator od nowa po pocięciu
  nową siatką; stare etykiety tylko do porównania po fakcie.
- TASK-0802 w toku (`v1.7.158`): `neural_grid` (dwa stopnie, MobileNetV3-Large
  od zera, 3,3 mln + 3,3 mln parametrów). **Run 1 (preset A)**
  `43933ac8…e2e6` zakończony w 3 h 40 min; najlepsza runda 3. Development
  (600 zdjęć): 92,3% zdjęć kompletnych i poprawnych, 5 349 / 5 400 plansz
  poprawnych, 100% plansz wykrytych, 0 fałszywych; B 99,3% zdjęć, S 85,3%.
  Z 51 „błędnych” plansz 46 ma NME 0,02–0,03 (tuż za tolerancją), skupione
  na pozycjach 2, 3, 5, 8 zdjęć S; przegląd wizualny 14 z nich (w tym obu z
  NME > 0,10): w żadnej etykieta nie jest lepsza od sieci, dwie etykiety są
  przesunięte o kolumnę albo rząd — pułap 92% wynika głównie z błędów
  etykiet S, nie z błędów sieci. ONNX `exports\2cd19738…-round3`: parity
  0,0008 px, CPU 0,18 s na zdjęcie (4 wątki). **Run 2 (preset B)**
  `ff03b1d7…f31d` uruchomiony 2026-10-02 ok. 16:50 na polecenie operatora
  (trzy runy); run 3 (preset C) po nim.
- TASK-0803 done (`v1.7.168`): `hybrid_v3` — bramka zgodności siatek
  odniesienia i `neural_grid` (plansza `confident` tylko przy zgodności;
  plansza tylko z sieci nigdy). Kalibracja na development dla modelu runu 1:
  IoU 0,90, tolerancja węzłów 0,04, reszta 0,005 → 90,3% zdjęć `confident`
  (B 98,0%, S 82,7%), 7 błędnych plansz `confident` względem etykiety
  (0,13%; wszystkie na S). Z 49 plansz S uznanych przez metrykę za błędne
  bramka kieruje do przeglądu 42. Ograniczenia: na B odniesienie = etykieta
  (mierzy zgodność), na S brak pierwotnego wyniku silnika produkcyjnego —
  propozycja dopisania go eksporterem przed TASK-0804; progi związane z
  modelem runu 1, do powtórzenia po kolejnych runach. Raport:
  `ai_docs/quality/GRID_V3_HYBRID_GATE_20261002.md`.
- 2026-10-02 operator: run 2 (preset B) zostaje; run 3 ma przygotować sieć
  do gry Mumie (nowe ustawienie — wymaga kompletnych siatek Mumii, zmiany
  roli Mumii w D-456 i zgody na wagi startowe; czeka na decyzje operatora).
- D-490 (2026-10-02): run 3 = nowy preset D (777 + Mumie, Blazing, Gang,
  wagi ImageNet); zmiana D-456; wymagania symboli premium Mumii zapisane.
- TASK-0824 done (`v1.7.170`): wspomagana anotacja kompletnych zdjęć labu —
  strona `http://127.0.0.1:8105` (start:
  `scripts\vision_lab_assisted_annotation.ps1 -Action Start`), zapis przez
  istniejący magazyn anotacji (`assisted_photos`), propozycje sieci runu 1
  dla 319 zdjęć (Mumie 236, Blazing 37, Gang 46; 9 propozycji na każdym
  zdjęciu Mumii i Blazing, Gang słabszy), eksport kompletnych zdjęć z
  adapterem do czytnika `neural_grid`. **Czeka na operatora:** przegląd i
  korekta siatek (Mumie pierwsze). Następne zadania: snapshot łączony i
  preset D (po anotacji), ocena runu 2, TASK-0804.
- Run 2 `neural_grid` (preset B, `ff03b1d7…f31d`) zakończony: najlepsza
  runda 9, development 92,2% zdjęć kompletnych i poprawnych, 0 fałszywych
  plansz — bez różnicy względem runu 1 (92,3%). Ocena i eksport runu 2 do
  wykonania przed TASK-0804.
- D-490 zmienione 2026-10-02: Blazing i Gang wypadają z tej tury; run 3 to
  iteracyjne doszkalanie modelu runu 1 na Mumiach w łącznym budżecie 4 h.
- TASK-0825 done (`v1.7.172`): preset D (doszkalanie, fingerprint
  `b94a9627…cbd9`), komenda
  `python -m game_predictor_worker.vision_lab.neural_grid_finetune iterate`,
  holdout Mumii (co piąte zdjęcie według skrótu SHA, trwały), strażnik 777
  (development ≥ run 1 − 0,5 pkt proc.), nowe propozycje po każdej
  iteracji bez restartu strony, automatyczne zamykanie zdjęć, kolejka tylko
  Mumii. Stan anotacji przy starcie pętli: 10 zdjęć Mumii kompletnych
  (śr. 165 s na zdjęcie); z 90 propozycji runu 1 operator przyjął bez zmian
  14%, poprawił 86% (mediana przesunięcia narożnika 5 px).
- Run 3 (doszkalanie na Mumiach, run `5bc98156…aedc`) — **zakończony
  decyzją operatora 2026-10-04 po 3 iteracjach**, zużyte 2 461 s z 14 400 s
  (reszta zostaje na Gang i Blazing). Iteracja 1 (preset D) odrzucona przez
  strażnik 777; preset E (D-490) przyjął iterację 2 (holdout Mumii NME
  mediana 0,0067 → 0,0046) i iterację 3. Trafność propozycji: porcja 1 na
  modelu runu 1 — 14% plansz przyjętych bez zmian, 165 s na zdjęcie; porcja
  2 na modelu iteracji 2 — 79% bez zmian, 67 s na zdjęcie; 0 plansz
  rysowanych ręcznie. 20 zdjęć Mumii kompletnych (16 trening, 4 holdout).
  Iteracja 3 nie poprawiła holdoutu (image-macro 0,00274 → 0,00330, ok.
  0,2 px), a reguła E wybrała najlepszego kandydata zamiast zachować
  poprzedni stan — luka do poprawy przed kolejną grą. 777: poziom B
  299/300, image-macro 0,00277 (lepsze niż run 1). Plik magazynu anotacji
  przekroczył 64 MB przez kopie podziału w historii — naprawione
  `v1.7.175`, skompaktowany z kopią zapasową. Serwery przeglądu etykiet
  8103/8104 zatrzymane.
- Preset F (`v1.7.177`): od iteracji 4 doszkolony stan jest przyjmowany
  tylko przy poprawie holdoutu względem stanu startowego.
- **TASK-0804 done (`v1.7.178`) — STOP V3-C.** Raport
  `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`. Holdouty
  (gold, Reels, Treasure, holdout Mumii) odczytane po razie przez zamrożone
  modele (ledger `grid-v3-comparison\sealed\ledger.json`). Wyniki: gold 459
  plansz G — silnik produkcyjny (pierwotny wynik) 41,4% poprawnych (wszystkie
  269 braków to plansze bez siatki; 78,8% w skrajnych kolumnach), sieci
  96,5–97,2%; rodziny niewidziane: produkcja 76,3%, sieci 98,0–98,4%; 17
  błędów sieci tuż za tolerancją; fałszywe plansze sieci = przesunięte
  etykiety U (ciche błędy produkcji). Reels 29/30, Treasure 30/30 plansz
  (etykiety częściowe). `hybrid_v3` z odniesieniem = pierwotny wynik
  produkcji: 0 błędnych plansz `confident`, ale bez zysku pokrycia na S.
  CPU ONNX ok. 0,17 s na zdjęcie. **Rekomendacja:** shadow (TASK-0805) z
  modelem runu 1 w ograniczonym zakresie — weryfikacja wyniku produkcji
  bramką, propozycje sieci do przeglądu na zdjęciach oznaczonych przez
  produkcję, bez automatycznej akceptacji plansz tylko z sieci i bez cięcia
  symboli z siatek sieci. Braki: kalibrowana bramka dla plansz tylko z
  sieci, losowa próba zdjęć zaakceptowanych przez produkcję (ciche błędy),
  przegląd 17 plansz przy tolerancji, pełne siatki Reels/Treasure, dane
  Gang, zgodność symboli po cięciu, czas silnika produkcyjnego, rola
  walidacji. Etap V3-D wymaga jawnego uruchomienia przez operatora.
- TASK-0830 (`v1.7.181`, kod gotowy, **niewdrożony**): profile silnika
  siatek w polu „Format strony” (`grid_profile_777_v2` → model runu 1,
  `grid_profile_mumie_v1` → model iteracji 3 doszkalania), rejestr modeli
  w `artifacts\models\grid-engine\…\v1` (zainstalowane, sumy zgodne),
  endpoint `listGridEngineProfiles`, migracja `0140` (rozszerzenie CHECK
  `games`). **Nie scalać do gałęzi integracyjnej przed migracją** — API
  8000 z `--reload` w głównym checkoucie przestałoby startować na bazie
  0139. Wdrożenie (stop usług → scalenie → `db:migrate` → start) po
  zakończeniu przypisywania symboli przez operatora.
- TASK-0831 done (`v1.7.182`): audyt cichych błędów siatek 777 (sieć runu
  1 na 55 499 zdjęciach, tylko odczyt). 3 629 plansz poza tolerancją: 958
  przesunięć okresu (613 kolumna, 344 rząd), 154 duże rozbieżności skali.
  Obejrzane 136: 104 potwierdzone błędy produkcji, 17 błędów sieci (w tym
  cała grupa 231 przesunięć kolumny na pozycji 2 — tam rację ma zapis), 9
  niejasnych. Szacunek: ok. 790–870 błędnych plansz na ok. 740 zdjęciach;
  na przesunięciach z błędem produkcji 253 komórki z decyzją człowieka.
  Raport `ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md`, przegląd
  `http://127.0.0.1:8107` (1 233 pozycje), korekta przez „Zła siatka” w
  weryfikacji symboli → kolejka korekty Reviewera.
- Plan symboli Mumii `ai_docs/delivery/MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`
  (`proposed`, TASK-0832–0839 zarezerwowane) czeka na 5 decyzji operatora.
- Kolizja numeru: TASK-0825 użyty przez dwa tory (doszkalanie Mumii i
  `grid-correction-unknown-symbol`); oba zakończone, pliki mają różne nazwy.
- Otwarte (stan sprzed porządku): 19 testów PG nieprzechodzących niezależnie od etapu
  (`db:baseline:verify`), duplikat importu `7d10ae0a` (1 160 zdjęć, usunięcie
  niezlecone). Następny etap planu: V3-A (TASK-0800, TASK-0801) — wymaga
  jawnego uruchomienia.

Stan sprzed akceptacji (zachowany dla kontekstu):

- Plan uzupełnia etap D planu Vision Lab (T10). Zawierał pięć decyzji
  do potwierdzenia przez operatora (geometria produkcyjna 777 jako dane
  uczące, budżet treningu, kolejność etapów, metryka nadrzędna, bramka
  kompletności zdjęcia w aplikacji).
- Nadrzędna reguła planu: jednostką geometrii jest zdjęcie; żadna plansza
  zdjęcia nie jest cięta na symbole, dopóki wszystkie oczekiwane plansze
  nie mają poprawnej siatki (etap V3-0: TASK-0806 raport i kolejka zdjęć
  niekompletnych, TASK-0807 egzekwowanie w pipeline). Dalej V3-A dane
  (TASK-0800, 0801), V3-B `neural_grid` i `hybrid_v3` (TASK-0802, 0803),
  V3-C ocena (TASK-0804), V3-D shadow (TASK-0805).
- Pliki zadań powstają przy uruchomieniu etapu. Numery TASK-0800–0807 są
  zarezerwowane dla tego planu.

## Koniec archiwum 2026Q4
