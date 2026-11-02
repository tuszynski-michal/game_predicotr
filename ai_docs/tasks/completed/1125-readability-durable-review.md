---
title: Trwały pilot, skan i przegląd jakości symboli
status: done
last_updated: 2026-11-02
---

# TASK-1125 — Trwały pilot, skan i przegląd jakości symboli

## Status

`done`

## Goal

Udostępnić trwały przepływ pilot → etykiety człowieka → jawny fit → bramka i odbiór → pełny skan oraz przegląd podejrzanych symboli.

## Dependencies / entry conditions

A1 zamknięty (v1.7.517, 9e466d70; hash zapisany w v1.7.518). Cały plan i koszt zaakceptowane. Narzędzia powstają na izolowanych fixture'ach; bez uruchamiania operatorowego pilota, fitu, skanu, usług i migracji bazy operatora.

## Recommended execution

gpt-6.1-sol / high. Trwały pion bazy, API, klienta i UI. Niezależny audyt claude-opus-5-5 / high przed commitem. Niedostępność konfiguracji albo sprzeczność wymagań zatrzymuje zależny zakres.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md` — sekcja weryfikacji komórek i nowy model jakości
- `ai_docs/architecture/API_CONTRACT.md` — sekcja symbol-cell-reviews i addytywne readability
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- D-578: `ai_docs/process/decisions/DECISION_LOG_2026.md#d-578--niezależny-detektor-jakości-777-a2-na-zamrożonym-kandydacie-nr-5`

## Scope

- Trwałe runy, inventory, identity, etykiety oraz model i jego odbiór; Alembic i manifest magazynu.
- Istniejące durable jobs, checkpoint na źródło, bounded processing, idempotencja i restart.
- Pilot bez gotowego modelu; maksymalnie 600 próbek i osobna niezależna audit200 przed fit.
- Dwa niezależne nullable labels; unreadable przez istniejącą mutację, readable nie zatwierdza symbolu.
- Pion API/OpenAPI/generated client/wrapper/request test i Admin „Podejrzane symbole”, raport/CSV.

## Acceptance criteria

- [x] Przygotowanie pilota i zapis etykiet działają bez detektora.
- [x] Fit wymaga zamrożonych etykiet i pełnej izolowanej puli; scan wymaga PASS i jawnego odbioru przypiętego modelu.
- [x] Wszystkie aktualne cropy, także approved/pewne, podlegają inventory skanu bez filtra confidence.
- [x] Identity source/crop/geometry guard odrzuca drift, wynik staje się stale; brak źródła, outside i geometria mają osobne przyczyny.
- [x] Retry/lost response/restart nie duplikują runów, etykiet ani wyników; checkpoint po źródle.
- [x] UI rozdziela stare/nowe unreadable, nałożenie/czytelność i obsługuje grupowe decyzje, crop/zoom/źródło.
- [x] Raport liczy pola/plansze/źródła i eksportuje CSV; overlap+readable nie kwalifikuje wymiany.
- [x] Testy pionu/lint/typecheck, kontrakt klienta, mapa kodu, docs i audyt rozliczone.

## Technical notes

Po zmianie tożsamości pikseli pilota blokujemy nowy skan także po wcześniejszym odbiorze (konserwatywna interpretacja zaakceptowana przez leada po P2-2). Wszystkie nasze zapisy, przetwarzanie źródła i lazy-stale używają wspólnej EXCLUSIVE sequence ownership lock przed rowlocks. GET listy/CSV ma jawny WRITE intent dla metadanych stale; historia ocen pozostaje w append-only receiptach komend.

Bezpieczne założenie wykonawcze: przygotowanie pilota nie wymaga detektora; frozen ekstraktor A1 może przygotować cechy. Fit jest oddzielną komendą operatora. Natural audit200 pochodzi wyłącznie z nieoznaczonej puli rodzin spoza pilota oraz bazowego TRAIN/VAL; raport nie ekstrapoluje szumu na całą grę. Brak puli/minimów kończy się STOP. Etykiety niepewne są null osobno dla headów. Zapis unreadable nie przenosi etykiet na zmienione piksele.

Migracje 0170/0171 pochodziły z równoległego toru grid-corrections; przed końcem A2 weszły już do main (a06fe75e, v1.7.522). Nie dodają manifestów v20/v21. Nasza migracja 0172 ma rzeczywisty poprzednik 0169, a wolny manifest v20 dziedziczy v19; nowe numery nie importują obcych tasków. Przyszła integracja wymaga ponownego preflight grafu Alembic i manifestów po aktualizacji main.

## Expected files

Nowe moduły readability w domain/application/storage/schemas/api i worker/symbols, migracja Alembic, nowy manifest oraz testy. Istniejące: jobs.py, worker cli/store, main.py, routing/lifecycle/catalog/retention importy manifestu, OpenAPI/generated klient/wrapper, katalog/nawigacja Admina, dokumentacja i mapa kodu.

## Verification

Python `D:/game_predicotr/.venv/Scripts/python.exe`, node_modules głównego checkoutu; cwd worktree i PYTHONPATH jego services. Testy pionu, ruff/mypy, request tests, Admin lint/typecheck, isolated PostgreSQL migracja i restart, code-map/docs. Każda skończona komenda z timeoutem ≤120 s, audyt ≤480 s.

## Risks / open questions

Empiryczna skuteczność pozostaje niezmierzona bez operatorowych etykiet i jawnego uruchomienia. API/Admin/worker wymagają później migracji oraz restartu operatora. Bez merge/push/aktywacji.

## Outcome

Commit: v1.7.519 (hash dopisuje kolejny commit).

### Changed

- Migracja 0172 i manifest v20: cztery routowane, game-scoped tabele z RLS, indeksami, FK RESTRICT i guardem downgrade. Bez migracji bazy operatora.
- Pilot działa bez detektora. TEST jest wybierany przed resztą, assignments i proweniencja rodzin są zamrożone przed etykietami. Bazowe TRAIN/VAL oraz chronione TEST/REG i znane nagrania są sprawdzane w obu kierunkach. Osobna audit200 ma receipt sprzed etykiet i nie opisuje całej gry.
- Jawne fit, PASS, odbiór modelu oraz skan są osobnymi komendami. Odbiór wiąże rewizję i fingerprint modelu. Cechy nie zawierają top1; metryka confident-overlay używa ponownie obliczonego top1 frozen kandydata 5 i checksum-bound kalibracji, nigdy confidence historycznego importu.
- Inwentarz i wyniki zapisują checkpoint po źródle; dekodowanie raz na źródło, ekstrakcja w porcjach do 128 (135 pól daje 128+7). Dzierżawa joba jest sprawdzana przed zapisem; store synchronizuje failure/cancel/recovery. Crop/source/geometry identity i bieżąca geometria są sprawdzane przed mutacją oraz fitem.
- Admin „Podejrzane symbole”: stare/nowe, typ problemu, niezależna czytelność/overlap, niepewność, crop/zoom/źródło, grupowe komendy do 250, pola/plansze/źródła i CSV. Readable nie zatwierdza symbolu ani nie usuwa quality_issue; unreadable używa istniejącej mutacji. Trwały browser outbox zachowuje targety, rewizje i klucz także po remount.
- Pełen backend/OpenAPI/generated klient/wrapper/request test. Nowe trasy pozostają w obszarze symbol-cell-reviews, bez zmian starych tras.

### Verification results

- 19/19 nowych testów domeny, HTTP, selekcji TEST i przypiętej kalibracji PASS. Pokryte: niezależny TEST, nagranie bazowego TRAIN z nowym SHA, chroniony TEST/REG, exactRGB, null przy braku dowodu confidence, historyczne .99 kontra pinned .2, dryf wszystkich składników identity i 135 pól w dwóch porcjach.
- 4/4 isolated PostgreSQL PASS: pełna migracja base→0172, lost-response dedup, restart po zatwierdzonym źródle bez drugiego decode, rzeczywisty mark_unreadable dokładnie raz, readable zachowuje issue, drift geometrii daje stale/409, odbiór oraz trwały inwentarz skanu po utracie checkpointu. Bazy `game_predictor_task1125_readability_<hex>` są własnymi disposable fixture z weryfikacją OID/markera przed DROP; nie używają danych operatora.
- 29/29 istniejących testów cyklu jobów PASS. 135/135 testów klienta API PASS po wymaganym buildzie pakietu; początkowy brak dist w jednym teście był brakiem przygotowania fixture, bez zmiany testu.
- UI: 24/24 logiki/nawigacji/źródła, 7/7 nowych interakcji, 17/17 istniejących interakcji symbol-review PASS. Scoped typecheck Admina i typecheck/build klienta PASS.
- Mypy wszystkich ośmiu zmienionych modułów z `--follow-imports=silent` PASS. Ruff 21 plików i format --check PASS. Pierwszy szeroki cold-cache mypy przerwano po ciszy; sprawdzono własne PID i brak osieroconych procesów. Końcowa kontrola korzystała z odrębnego cache worktree i nie osłabiała typów.
- OpenAPI semantic diff: żadna stara trasa się nie zmienia; jedyna zmiana starego schematu to dodatkowy JobType. Generator @hey-api/openapi-ts 0.99.0 z lockfile; klient core pozostaje semantycznie bez zmian.
- Cztery kontrole docs PASS (11/11 budżetów; startup 43 423 B), mapa wygenerowana. Audyt Opus 5.5/high PASS po jednej celowanej alternatywie; pierwsza próba zakończyła się timeout450s bez werdyktu. JSON CLI: modelUsage=claude-opus-5-5, is_error=false, subtype=success, duration197407ms. Raport: `ai_docs/quality/TASK-1125_AUDIT_claude-opus-5-5.md`, z jawnymi ograniczeniami odczytu i poniższym rozliczeniem P2.

### Audit reconciliation — jedna runda P2

- P0/P1: brak według audytora. Nie zmieniono jego werdyktu ani oryginalnych znalezisk.
- P2-1: zamknięte. Artefakt jest adresowany fingerprintem, temp jest unikalny i obsługuje długie ścieżki Windows. Test opóźnionego writera potwierdza, że nie może nadpisać zaakceptowanego adresu.
- P2-2: zamknięte. API start i worker inventory wymagają aktualnego pilota; test accepted→geometry drift→nowy scan daje READABILITY_CROP_STALE.
- P2-3: zamknięte. Błąd odczytu źródła jest zapamiętany; test135 pól daje jeden load i135 error.
- P2-4: zamknięte wspólną EXCLUSIVE ownership lock przed blokadami wierszy. Izolowany test rzeczywistego PG blokuje label podczas źródła, potem kończy scan i label bez deadlocku; targety są celowo podane w odwrotnej kolejności.
- P2-5: historia jest zachowana w `symbol_readability_commands.response.command` (pełne body, identity, rewizje), a lazy-stale nie usuwa receiptów. WRITE intent GET i wspólna blokada są jawne w architekturze. Nie pozostawiono otwartego ryzyka deadlocku wskazanego w raporcie.
- Kontrole po poprawkach: 19 testów domeny/HTTP/selekcji/kalibracji/artefaktów, 4 testy isolated PG (w tym nowe scenariusze), mypy8modułów. Bez kolejnego audytu, zgodnie z jedną rundą poprawek i poleceniem leada.

### Not completed

- Nie uruchomiono pilota, fitu, skanu, labelowania ani żadnego joba na danych operatora. Nie zmieniono jego bazy, aktywacji kandydata 5 ani usług. Brak merge/push.
- Rzeczywista skuteczność detektora pozostaje niezmierzona do etykiet i jawnych zgód operatora. Bez fizycznego Androida i operacyjnego odbioru UI.
- Brak Shift/range A3; A2 zachowuje limit 250 targetów jednego requestu.

### Documentation updates

- Wymagania, architektura, DATA_MODEL/API_CONTRACT, CURRENT_STATE i mapa kodu opisują nowy pion.
- Migracje 0170/0171 weszły w międzyczasie do main (a06fe75e/v1.7.522); nie dodają manifestów v20/v21. Nasze 0172→0169 oraz v20→v19 wymagają ponownego preflight grafu i manifestów przed przyszłym merge.
- W worktree utworzono junction node_modules do istniejących zależności głównego checkoutu; odpiąć według merge-to-main przy przyszłym sprzątaniu, bez rekurencyjnego usuwania celu.

### Recommended next task

- TASK-1126 / A3 — Shift w zwykłej weryfikacji i kandydatach, bez automatycznego pilota ani skanu.
