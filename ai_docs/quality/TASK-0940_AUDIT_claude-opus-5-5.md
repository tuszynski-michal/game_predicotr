---
title: TASK-0940 — audyt niezależny (claude-opus-5-5 / high)
status: accepted
last_updated: 2026-10-09
---

# TASK-0940 — audyt: zielona bramka `npm run quality`

Audytor: niezależny subagent claude-opus-5-5 / high, świeży kontekst, tylko
odczyt (zamiennik audytu gpt-6.1-sol do czasu dostępności CLI, D-535).
Wykonawca: claude-sonnet-5-5 / high. Zakres: zmiany niezacommitowane względem
v1.7.272 (680dcec9) w worktree `mumie-super-game`, około 170 plików.

## Przebieg

- Runda 1: REVISE. [P0] skip korpusu w `test_whole_layout_symbol_review.py`
  ukrywał deterministyczny błąd `SYMBOL_DATASET_CALIBRATION_CHAIN_DRIFT`
  (dowody w `ai_docs/quality/*.json` przypinały sumę CRLF manifestu, który od
  TASK-0812 jest LF); [P1] drugi test tej samej pary; [P2] rozszerzenie
  zamrożonego manifestu v2 działało wstecz na migracje 0131/0134/0142;
  [P2] guard korpusu pomijał asercje niezależne od korpusu w teście
  pipeline; [P2] brak pokrycia ścieżki 409 guard-rebind po HTTP; [P2]
  nieprecyzyjne cytowania reguł; [P2] drobne zmiany runtime w skryptach
  nienazwane w Outcome. Klasyfikacja każdej zmienionej asercji: żadna nie
  została osłabiona bez poprawnego odwołania do reguły; przepięcia sum
  (deskryptor v19, `lateral_partial_contract`) przeliczone i uznane za
  legalne korekty bazowe.
- Runda 2 (po poprawkach): 7/7 uwag zamkniętych, jedna nowa [P1]:
  przepięcie sum dowodów nie doszło do punktu stałego (10 referencji ze
  stanem pośrednim). Odstępstwo wykonawcy (`POST_V5_SHARED` zamiast
  `SHARED` w manifeście v5) zaakceptowane, bo migracje wstawiają wyłącznie
  `SHARED`.
- Domknięcie: wykonawca powtórzył przepięcie pozycyjnie względem HEAD do
  punktu stałego (5 iteracji, 19 wartości), dodał
  `scripts/check_quality_evidence_digests.py` (0 niezgodności), tabelę
  `ai_docs/quality/evidence-digest-references.json` dla pól `*Sha256` bez
  ścieżki i test `services/worker/tests/test_quality_evidence_digests.py`.
  Lead zweryfikował niezależnie: checker 0 niezgodności, nowy test PASS.

## Werdykt końcowy

PASS po domknięciu P1 (weryfikacja leada narzędziem kontrolnym).

## Testy (wykonawca po ostatniej rundzie, audytor w rundzie 2)

- `npm run format:check`, `lint`, `typecheck` (mypy 836 plików),
  `openapi:check`, `snapshot:validate`, `fixture:validate`: exit 0.
- JS: admin 679, reviewer 237, vision-lab 62, admin-api-client 102,
  board-search-ui 80, manual-image-selection-core 110, shared-ts 46,
  vision-lab-api-client 15 — wszystkie PASS.
- API pytest z PostgreSQL: 2725 PASS, 13 skipped, 0 fail (45 min);
  po przepięciu sum bez PG: 2464 PASS, 275 skipped.
- Worker pytest (python głównego venv): 2781 PASS, 43 skipped, 0 fail.
- Jedyny znany wyjątek: `test_another_root_cannot_admit_same_manifest`
  pada tylko przy junction `.venv` w worktree (środowisko).

## Odłożone (jawnie)

- 3 testy historycznych migracji 0133–0136 wycofane skipem z powodem;
  ponowne włączenie wymaga harnessu budującego stan tych rewizji.
- 25 testów korpusów M5 pomijanych, gdy korpus nie istnieje lokalnie.
- Opcjonalnie `disable_existing_loggers=False` w `alembic/env.py` zamiast
  `conftest.py`.

Przegląd statyczny, bez zmian plików przez audytora.
