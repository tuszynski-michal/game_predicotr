---
title: Jawne możliwości modelu i kwalifikacja gry
status: done
last_updated: 2026-11-03
---

# TASK-1156 — Jawne możliwości modelu i kwalifikacja gry

## Status

`done`

## Goal

Nowe operacje sprawdzają planszę 5 kolumn × 3 wiersze i stronę 3 × 3 przed inferencją oraz dopuszczają automat wyłącznie z przypiętą oceną konkretnej gry.

## Context

T2 zaakceptowanego planu pełnych plansz. T1 zakończony `887d8a3b`; operator zlecił T0–T6, koszt i audyty. Nowa gra otrzymuje propozycje bez odziedziczonej kwalifikacji. `expectedLayoutCount` pozostaje limitem numerów gry.

## Dependencies / entry conditions

T0 i T1 done. Koordynator uruchomił T2. Trzy zmiany metadata record-hash T1 (CURRENT_STATE, archive Q4 i completed1155) są znane i należą do następnego commita.

## Recommended execution

`gpt-6.1-sol` / `high`; niezależny review `claude-opus-5-5` / `high` uruchamia koordynator. Sprzeczność domeny albo niedostępna konfiguracja blokuje zależną implementację.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md` — T2
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-584--wersjonowana-bezpieczna-akceptacja-siatek`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-585--jawne-możliwości-i-przypięta-kwalifikacja-gry-w-nowych-operacjach-sieci`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów`

## Scope

- Jawny adapter odwróconych nazw catalogue-v1 bez zmiany immutable SHA.
- Zamknięty wersjonowany top-level operation pin; acceptance-v3 nad crop-v2 i nowa polityka preflight.
- Exact evaluation/model/game/SHA i currentness; brak raportu/historyczna publikowalność daje unqualified, nadal propozycje.
- Kontrola przed runnerem, workerem i API write; retry nie aktualizuje pinu.

## Out of scope

Kalibracja T4 i jej magazyny, inne głowice/topologie, trening/inferencja operatora, migracje operatora, usługi, aktywacja, main/merge/push.

## Acceptance criteria

- [x] Układ 3×5 i strona 3×3 sprawdzane przed inferencją; nieobsługiwany układ blokuje runner, zachowuje źródło.
- [x] Zgodna nowa gra bez exact PASS tej gry otrzymuje wyłącznie propozycje.
- [x] Nowe v3 przypina raport lub unqualified; restart i retry nie podnoszą kwalifikacji.
- [x] API recheckuje przypięty dowód przed automatic write; currentness nie jest zastępowane innym raportem.
- [x] Historyczne v1/v2 snapshoty, propozycje, hashe i decyzje bez zmian; nieznane/brakujące nowe piny blokowane.
- [x] Scoped testy, lint/format i docs/code-map PASS; scoped typy bez nowych błędów wobec jawnego baseline, niezależny Opus R2 PASS przed commitem. Standardowy Admin tsc ma opisany blocker worktree.

## Technical notes

Projekt roboczy: `artifacts/task1156-preflight/TASK-1156_DRAFT.md`. Bezpieczne założenie: strona 3×3 oznacza pojemność, nie dziewięć wymaganych obecnych plansz. Nowy top-level pin nie zmienia snapshotów v1/v2. Historical eligibility nie jest oceną konkretnej gry. Współdzielony reader wykorzystuje istniejącą walidację raportu i currentness D-559. Brak/stale dowodu blokuje automat; awaria DB nie staje się sukcesem. API recheck działa w transakcji zapisu. Dokładne dowody zostają zamrożone, bez lookup najnowszego default/assignment przy retry.

## Expected files

Nowe proponowane domenowe capabilities/operation pin i storage qualification reader; istniejące `application/jobs.py`, resolver, reinference prepare, acceptance, worker preflight/production/reinference i API automatic writers. Wymagania/architektura, decyzja, mapa kodu i testy tego pionu. Pola prezentacji API T5; zmiana typed API wymaga pełnego pionu w tym tasku.

## Test cases

Adapter zachowuje SHA; unsupported układ nie wywołuje runnera; per-game PASS/missing/foreign/stale; unqualified pozostaje po nowej publikacji; forged/missing pin; FIT_OUTLIERS nadal blokuje; legacy bytes/decisions; replay prepare; API nie ufa workerowi; korekty ręczne zachowane.

## Verification

Bezpośredni pytest zmienionego pionu, scoped ruff/format/mypy, izolowany PostgreSQL harness, docs:check, code-map:check. Każda skończona komenda z timeout ≤120 s. Wyniki i jawne ograniczenia baseline: `ai_docs/quality/TASK-1156_VERIFICATION.md`. Niezależny Opus R1 i focused R2 PASS, uruchomione przez koordynatora.

## Risks / open questions

Historyczny model bez jawnego raportu gry nie ma automatu dla nowych operacji. T2 PASS nie dowodzi silniejszej kalibracji T4. Brak blokujących pytań produktowych.

## Outcome

Commit: v1.7.560 (hash dopisuje kolejny commit).

### Changed

- Jawny adapter catalogue-v1 i strict operation pin bez zmiany snapshotów/historycznych SHA.
- Preflight-v14, acceptance-v3 nad crop-v2, exact per-game report albo frozen unqualified.
- Worker/API guards przed inferencją i automatic write; stable-input cold retry nie pobiera nowej kwalifikacji.
- Wczesny zapis geometrii nowego joba v3 jest zawsze `needs_review`, także przy workerowym `ready`/`manual_v1`; tylko autorytatywny finalizer może promować qualified wynik. Poprawka własnego P1 potwierdzonego przez koordynatora przed zakończonym R1.
- Po R1: exact repo lookup pod admission lock bez okna historii, fail-closed ambiguity, blokada modelowego human stamp oraz testy actual report mismatch/concurrency/workflow. Ręczne akceptacje pozostają serwerowe.
- OpenAPI/generowany klient oraz parser Admin wspierają nowe polityki. Bez nowego endpointu i nowych tabel.

### Verification results

Wyniki, komendy i ograniczenia: `ai_docs/quality/TASK-1156_VERIFICATION.md`.

### Not completed

R1 i focused R2 Opus5.5/high PASS; raport `ai_docs/quality/TASK-1156_AUDIT_claude-opus-5-5.md`, pierwotny R1 zachowany osobno. Jedna runda poprawek zamknęła pięć uwag R1 i obie luki P1 koordynatora. Brak otwartych P0/P1. Bez dalszej zmiany zachowania po R2.

Pozostają cztery nieblokujące P2 z R2 (nie naprawiono ich w tym tasku):

- P2-1: dwa joby o identycznej stabilnej tożsamości i identycznym pinie także dają `NEURAL_GRID_OPERATION_IDENTITY_AMBIGUOUS`. Możliwe po zastąpieniu FAILED/CANCELLED preflightu nową bazą. Ogranicza ponowienia (fail-closed), nie podnosi kwalifikacji i nie dopuszcza automatu.
- P2-2: strict v3 blokuje human stamp także wtedy, gdy availability metadata odzwierciedla ludzką decyzję z zaufanego `geometry_guard_resolution_manifest`. Taka plansza może wymagać ponownego prawdziwego manual approval i do tego czasu pozostawać `geometry_incomplete`. Dotychczasowe ręczne API approval zachowuje swój workflow; T5 powinno wyjaśnić ten przypadek.
- P2-3: exact JSONB lookup ma PG coverage ścieżki VALIDATE, ale nie IMPORT. Import/reprocess cold retry sprawdzono unitowo; brak dowodu PG tej gałęzi SQL.
- P2-4: test współbieżności nie potwierdza oczekiwania drugiego backendu przez `pg_locks`; skrajny przeplot może nie odtworzyć rywalizacji o blokadę. Kod używa transakcyjnego advisory lock, ale ten szczegół coverage pozostaje ograniczony.

Standardowy Admin tsc pozostaje z blockerem starego klienta przez junction; izolowany strict worktree typecheck PASS. Scoped mypy ma 0 nowych błędów wobec pięciu znanych UUID|None oraz wcześniejszego Row/tuple. Nie wykonano wdrożenia, treningu, aktywacji, operator DB writes, migracji ani restartów.

### Documentation updates

D-585, wymagania/architektura VISION_LAB, CURRENT_STATE i generowana mapa kodu.

### Recommended next task

Punkt kontrolny A: 197 aktualnych GT / 134 zdjęcia, pełnych zdjęć 9/9: 0; dane nie kwalifikują modelu. T3–T6 czekają na ponowną decyzję kosztową operatora po prawie czterech godzinach etapu A (dalsze szacowane 4–6 h). Pytanie zadał koordynator; bez tej odpowiedzi nie rozpoczynać T3. Rzeczywisty trening wymaga osobnej zgody i trwałego limitu.
