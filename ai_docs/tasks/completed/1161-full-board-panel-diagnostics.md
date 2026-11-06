---
title: Compact full-board status and actual input diagnostics
status: done
last_updated: 2026-11-04
---

# TASK-1161 — Panel, propozycje i rzeczywiste wejście

## Status

`done`

## Goal

Operator rozróżnia propozycje, automat i zatwierdzenie człowieka w lekkim panelu,
uzupełnia geometrię zwykłych zdjęć i ogląda wiarygodne rzeczywiste wejście w HTML.

## Context

Integracja: dokumentacyjny numer TASK-1159 zmieniono na TASK-1161 po kolizji z zadaniem komunikacji w main. Commit v1.7.564/bc00e2a7 i literalne audyty TASK-1159 zachowują historyczne identyfikatory; zakres i kod są bez zmian.

T5 zaakceptowanego FULL_BOARD_DETECTION_PLAN_20261103. Baza T4 v1.7.563
`c7ed8afe1913292d3fe5f7f23cb133f077ac84e2`, Opus R2 PASS. TASK-1153 już
zintegrowany za zgodą operatora. Dalsze3–4h T5/T6 (łącznie7–8h kontynuacji) jawnie
zatwierdzone2026-11-04 około08:41Warsaw; root koordynuje koszt i audyty. Trzy zastane
record-hash1158 metadata są znane i należą do commita T5.
Po wykryciu brakującego wpięcia v4 koordynator wybrał wariant B: jawny opt-in
w istniejącym shared learning. Użytkownik zatwierdził pozostałe3–5h pełnego wpięcia,
T6 i audytów04.11 około10:41Warsaw (09:41UTC). Oczekiwanie09:59–10:41Warsaw nie było pracą.

## Dependencies / entry conditions

T0–T4 done. Odczytać finalne DTO T3/T4 i ROOT_HANDOFF_DECISIONS, nie realizować
nieaktualnych pytań draftu. Runtime diagnostic z brakującym rzeczywistym rastrem
jest unavailable; nie jest zgodą na inference. Pozostałe akceptacje T6 nie wchodzą tu.

## Recommended execution

`gpt-6.1-sol` / `high`, review `claude-opus-5-5` / `high` uruchamia wyłącznie root.
Niedostępna konfiguracja lub sprzeczność domeny blokuje zależny pion.

## Relevant docs

- AGENTS, README, CURRENT_STATE, DECISION_LOG, PLAN_STANDARD, TASK_TEMPLATE, DoD.
- delivery/FULL_BOARD_DETECTION_PLAN_20261103.md — T5.
- requirements/ADMIN_APP.md, requirements/VISION_LAB.md, architecture/VISION_LAB.md.
- architecture/API_CONTRACT.md, CODE_MAP.md, CODE_MAP_SYMBOLS.md.
- quality/TASK-1157_VERIFICATION.md, quality/TASK-1158_VERIFICATION.md.
- tasks/completed/1153-grid-review-proposals-viewport.md; TASK-1156 Outcome/P2.
- D-585, D-586, D-587 i D-588 w process/decisions/DECISION_LOG_2026.md.
- ignored artifacts/task1159-preflight/TASK1159_DRAFT.md i ROOT_HANDOFF_DECISIONS.md.

## Scope

- Addytywny typed read-model możliwości i current per-game kwalifikacji przy
  istniejącym assignment; frozen state/reasons przy istniejących odczytach wyników.
- Zwarty główny panel i readiness/CTA; zaawansowane szczegóły kalibracji i istniejące
  przygotowanie/freeze kohort innych wymaganych gier bez zmiany punktów/ról.
- Jawny policy-v4 opt-in oraz source→A/B/BUFFER w istniejącym preview/start, z projekcją
  całych komponentów z tego samego constrain/refine. Sealed transport do child prepare,
  snapshot/training/evaluation; legacy bez pól pozostaje v2/v3 z dawnymi hashami/retry.
- Minimalne wejście do istniejącej zwykłej weryfikacji geometrii także dobrych plansz,
  z zachowaniem owner/CAS/receipt i potwierdzeniem geometry_saved→GT/full-photo w readerze.
- Strict diagnosticv2 dla completed requestu i faktycznego rastra, decoder v1 bez zmian;
  HTML oryginał/input/zapisane/baza/kandydat i historyczny raport z zapisanych artefaktów.

## Out of scope

Nowe sieci/trener/kolejki, online endpoint obrazów, fake GT, operator DB/role writes,
diagnostic registration, trening/inferencja modeli, usługi, migracja operatora,
main/merge/push. T4 observation sink i partial-A acceptance należą do T6.

## Acceptance criteria

- [x] Current model/kwalifikacja gry osobno od frozen operation i ludzkiego approval;
  brak kalibracji nie staje się blokadą inaczej dozwolonego treningu/propozycji.
- [x] Compact primary/secondary/gap/loading/error/retry, GET-only mount, stale responses
  odrzucone; zwykłe zdjęcia mają prawdziwą ścieżkę human geometry bez quality holdout.
- [x] Existing manual accept/edit/reject/CAS/retry zachowane; nowy prepare≠exact retry;
  advanced history recovery używa końcowego policy-v4 i już wymaganych gier.
- [x] Pełny typed API→OpenAPI→generated SDK→wrapper/request test; bez raw pin/ścieżek.
- [x] Diagnosticv1 historyczne bytes/semantyka; v2 completed/exact positions/request/
  preset/model/OpenCV/frame/raster zweryfikowane, alias/reserved/missing jawne.
- [x] HTML pięć widoków i brak zgadywania GT/pairing; viewport≠input, margin z presetu.
- [x] Scoped kontrole, docs/map i niezależny audyt przed task-close/commitem.

## Technical notes

Decyzja D588: odczyty publiczne są projekcjami istniejących dowodów; nie tworzą
kwalifikacji, pinów operacji ani wpisów GT. Current per-game state nie aktualizuje
zamrożonych operacji. Nie ujawniamy ścieżek ani całych wewnętrznych pinów.
Główny panel zachowuje kolejność model/dane/start/postęp/wynik/historia. Technical
details, osie/progi/SHA i recovery pozostają w details. FullPhotos0 wskazuje zatwierdzenie
geometrii wszystkich plansz na pełnych zdjęciach; symbole nie są GT geometrii.
V2 nie zastępuje bazowego presetu szerszym: typed override i actual raster są osobno.
Brak wystarczającej artefaktowej tożsamości → unavailable bez odtwarzania dawnego oryginału.

## Expected files

Registry/qualification read-model i schemas; existing reinference/proposals schemas,
OpenAPI/SDK/wrapper/request tests. Admin assignment/learning/cohort/reinference;
Reviewer correction/proposal/editor entry. geometry_core input diagnostics (osobny
proponowany moduł v2), existing renderer/template i synthetic tests. Docs/D588/mapy.
Doprecyzowanie B: domain/grid_validation_purpose.py, storage/grid_correction_split.py,
application/grid_correction_learning.py, schemas/grid_correction_learning.py,
Admin advanced source/component selector i zgodny history recovery; scoped composed
PG istniejącego orchestration, bez realnego treningu.

## Test cases

Game-specific qualified/unqualified/stale vs history; frozen retry; no internal paths;
full-photo deficiency/action; geometry_saved actual reader; no POST mount; stale GET/refresh;
manual receipts/CAS; completed v2 replay/raster mismatch/alias/reservation/no diagnostics;
legacy v1; HTML five views and escaped content. Testy zgodnie rzeczywistą deltą.

## Verification

R1 Opus REVISE: jedna runda poprawek obejmuje izolowany READ-routing bieżącej
projekcji (oddzielna transakcja gry, katalog unbound), degradację wyłącznie
oczekiwanych błędów danych/routingu/DB do unavailable, oraz P2-1–5: neutralny
komunikat ludzkiej weryfikacji, screen margin n/a, archiwalne sequenceNumber
indeksu v2, niezależne sekwencje preview/refresh i rzeczywisty HTTP replay legacy.
Zakres plików uzupełnia integration/test_grid_recognition_status_postgres.py;
pełny nullable capabilities kontrakt i testy pozostają jednym pionem. R1 i jego
snapshot zachowane literalnie; focused R2 uruchamia wyłącznie root.

Scoped pytest/API/disposable PG ≤120s, frontend request/interaction tests, lint/types/build,
OpenAPI freshness, docs/map. Isolated strict WT SDK types raportować jawnie; chronić
main node_modules junction. Brak wyników przed faktycznym wykonaniem.

## Risks / open questions

Jeśli zwykły istniejący edytor nie potrafi przyjąć dobrego slotu, zgłosić konkretną
lukę zamiast fikcyjnego grid_issue. Kompletność wymaga faktycznego GT, nie statusu200.
Kod T4 zawiera zaakceptowane P2; UI ich nie naprawia ani nie ukrywa.

## Outcome

Commit: v1.7.564 / `bc00e2a736a6f5a51a9d2bd590d96d280a95d23a`.

Piony i scoped odbiór gotowe. Wykrytą przed freeze lukę v3/v4 zamyka zaakceptowane
wpięcie B: jawna polityka/assignments, projekcja chronionych grup zdjęć i sealed
transport istniejącym parent/child. Legacyv2/v3, hashe i exactretry zachowane.
ComposedPG1PASS105.92s obejmuje rzeczywiste153syntetyczneGT/21foto, readonlypreview,
capture/materialize/freeze, admission i realny evaluation-cohort reader; backendmodelowy
kontrolowany, bez NN/treningu/raportuPASS. Freshprocess zachowuje piny/manifest i1parent/
1training/1evaluation/ten sam budżet.4własne journale DB/roles0/0 po kontrolowanym cleanup.
R1 Opus REVISE został odczytany i zachowany literalnie. Jedna runda poprawek
zamyka P1 izolowanym READ routingiem oraz P2-1–5; realny PG main/router i legacy
HTTP retry1PASS/34.39s, cleanup3DB/roles0/0; Python42PASS, Admin6PASS,
Reviewer1PASS i wrapper6PASS (per invocation, bez sumowania wcześniejszych).
Oba pełne finalne izolowane buildy, scoped Ruff/ESLint/mypy i kontrakt PASS.
Focused R2 rzeczywisty Opus5.5/high PASS, raport
`../../quality/TASK-1159_AUDIT_claude-opus-5-5.md`; R1 i zamrożone pakiety zachowane.
Brak otwartych P0/P1. R2-P2-1 zaakceptowane: powielony klucz legacy może utrudnić
przyszłą zmianę opcji, ale fail-closed i test regresji chronią obecny retry/start;
nie zmieniamy kodu po audycie. R2-P2-2 zamknięte wyłącznie dokumentacją wymaganego
indeksu v2 i rzeczywistego rastra HWC uint8 w architecture/VISION_LAB, bez producenta.
R2 SHA wszystkich59 plików kodu/testów/kontraktu potwierdzone bez zmian przed close.
Pełne wyniki i ograniczenia: `../../quality/TASK-1159_VERIFICATION.md`. Publiczne GET
oddzielają current/frozen, panel pozostaje lekki, advanced korzysta z istniejących
kohort, a opt-in „Geometria zdjęć” używa tego samego edytora. Composed disposable PG
potwierdził geometry_saved→real reader→9/9 bez measurement/quality holdout. V2 i HTML
nie wykonują inferencji; istnieją tylko2 rzeczywiste strict T1 inputy462205 w galerii
150plansz/101foto. Pozostałe diagnostyki unavailable. Browser visual review niewykonany
z powodu file URL policy, bez obejścia. Izolowane strict typy i oba pełne buildy PASS;
standardowego workspace Admin PASS nie deklarujemy. Punkt A197GT/134foto/full0,
bez treningu, operator DB, migracji/usług/aktywacji. T6 pozostaje odrębny.

DoD i plan T5 rozliczone punkt po punkcie: funkcjonalność/read-model, brzegowe
stany, zwarty UX, trwały owner/CAS/retry i cold DB roundtrip, spójny kontrakt,
strict diagnosticv1/v2 oraz HTML, scoped test/lint/type/build, docs/map i audyt PASS.
Brak migracji schematu w T5. Odbiór na fizycznym Androidzie i browser visual review
nie były wykonywane; DOM/interakcje oraz pełne mirror buildy stanowią dowód lokalny.
T6 odbiera actual observation_sink i partial-A production handler, zakres artefaktów,
akceptację end-to-end i zastane ograniczenia T4, bez ponawiania zielonych kontroli.
