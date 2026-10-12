---
title: Lokalny selektor Windows — finalizacja i dowody pilota0.1.3
status: in_progress
last_updated: 2026-10-12
---

# Finalizacja selektora Windows — dowody wykonawcy

Zakres: TASK-0984–0987, D-546 i pełna runda zatwierdzona przez operatora.
Ten raport zapisuje wykonane kontrole. Nie jest końcowym audytem Claude ani
odbiórką na komputerze odbiorcy. TASK-0979 pozostaje osobną bramką fizyczną.

## Ukończone etapy i źródła

- TASK-0984: v1.7.334 /c52518a8ece7c79f88b31224d4d90a84f0779b4c; bezpieczna historia/foldery, repeat decyzji i zamykanie/relaunch.151 testów oraz actualfull/UX smoke PASS.
- TASK-0985: v1.7.335 /d82fbcb576ef138b8b6049102212b85f97d0a803; head2/journal3, mirrored immutable inventory/baseline, append-only receipts bez retencji.233 testy PASS. Wewnętrzny review Codex REVISE2P1 → jedna runda poprawek → ograniczony PASS. [Raport](TASK-0985_ENGINEERING_REVIEW_CODEX.md) zachowuje pierwotne znaleziska i rozróżnia przegląd od testów oraz Claude.
- TASK-0986: v1.7.336 /c43434c28d49597407072f9636c7c07d1c3622b8; ograniczony timeout retry, bezpieczne telemetry, failure logs i exactarchive provenance.53 focused testy PASS, actualstart obu kierunków PASS. Pierwsze błędy harnessu i ich poprawki są w Outcome, nie są ukryte.

## Kontrole kodu przed finalnym release

Z worktree `D:\game_predicotr\worktrees\offline-photo-selector`, Node24.21.0.
Każda komenda skończona ma jawny limit w run-bounded.mjs.

| Komenda | Limit | Wynik |
|---|---|---|
| npm run test --workspace @game-predictor/selector-desktop |120 s|262/262 PASS,110,837 s;0 skip; pełny runtime po0986 |
| npm run test --workspace @game-predictor/manual-image-selection-core |60 s|110/110 PASS,2,132 s |
| node --experimental-strip-types --test apps/reviewer/test/operator-local-selection-output.test.mjs |60 s|16/16 PASS,0,160 s; bez uruchamiania Reviewera |
| desktop lint/typecheck/Prettier |60/60/30 s|PASS0986; końcowa kontrola nowych skryptów po pomiarze |

Najbardziej istotne przypadki: każda faza upgrade/ledger/head, rzeczywisty
exit i nowy proces, ENOSPC/rename/partial suffix, dwa uszkodzone mirrory,
obcy lock/plik, dokładny stary receipt po undo/restart, migracja legacy1/2,
relink źródła/wyniku podczas pending operacji i pending upgrade, oba
kierunki/naturalny kursor oraz brak decyzji z auto-repeat.

## Diagnostyka sprawdzona na rzeczywistym EXE

TASK-0986 celowo przerwał smoke-start po uruchomieniu testowego EXE.
Oczekiwany exit1 zachował `artifacts/selector-smoke-diagnostics/smoke-start-fiYX0L`:
selector.log64B z application-start oraz failure.json z kontrolowaną
przyczyną, timeout close i wymuszonym zakończeniem tylko własnego PID.
Fixture nie istnieje po capture; liczba procesów Selektor-zdjec wyniosła0.
Nie jest to PASS pozytywnego scenariusza; to dowód ścieżki błędu. Dodatni
smoke-start po poprawce finalizera przeszedł osobno. Gdy capture nie działa,
regresja potwierdza pozostawienie własnej fixture. Logi nie zawierają obrazów;
reason ma limit1500 znaków i redaguje dane obrazów/base64/buffer.

## Pozostałe kroki TASK-0987

Kontrolowany pomiar15000, SHA/provenance finalnego ZIP0.1.3, wszystkie finalne
smoke i oba rzeczywiste update zostaną zapisane po wykonaniu. Nie oznaczono
ich jako PASS na podstawie planu. Nie uruchomiono usług operatora ani nie
zmieniono jego danych, API, Admina, Reviewera, OpenAPI lub bazy.
