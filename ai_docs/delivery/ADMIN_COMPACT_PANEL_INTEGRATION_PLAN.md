---
title: Integracja kompaktowego panelu z główną gałęzią
status: accepted
last_updated: 2026-10-09
---

# Integracja kompaktowego panelu — TASK-0945

## Cel i autoryzacja

Operator polecił „Połącz to z głównym branchem” po zamknięciu TASK-0940–0943.
Integracja obejmuje wcześniejszy zaakceptowany zakres panelu i jego przewidziane
styki z Mumiami. Nie jest zgodą na migrację bazy operatora, push ani cykl usług.
Zachowujemy ograniczenie kosztu: jedna runda Claude, jedna ograniczona runda
poprawek, testy istniejących pionów bez benchmarków i powtarzania audytów panelu.

## Sprawdzony stan

- Main `v1.1-vision-lab-hybrid-geometry`: fc3d188/v1.7.287.
- Panel `codex/admin-compact-panel`:433d8bfe/v1.7.278, kod/audyty zamknięte.
- Main zawiera superGameState, koszt per pozycja, manifestv6, nowy proces dokumentacji
  i poprawkę ręcznej geometrii0944. Panel wnosi małe kafelki/modale i bound-preview delete.
- Obie migracje0152 mają rodzica0151. D-536 koliduje: main używa go dla serii,
  panel dla kompaktowego UI. Historyczne taski0940 są różne i mają różne nazwy plików.
- Main ma niezapisane dokumenty/package-lock i v7-output. Nie usuwać/stashować.
  Patch/status/hash zapisane w ignorowanych artifacts/integration; panel nie zmienia locka.

## TASK-0945 — Spójne scalenie i weryfikacja

Przygotować merge w istniejącym worktree na `codex/admin-compact-integration`
od aktualnego main, z panelu jako drugim rodzicem. Zachować nowy format
CURRENT_STATE/DECISION_LOG, importując tylko nowe decyzje i wpisy panelu.
Decyzja panelu otrzymuje wolny D-538; raporty historyczne zachowują oryginał
z jawnym mapowaniem starego numeru. Nie renumerować historycznych commitów/tasków.

Dodać pustą migrację `0153_merge_compact_super_games` z oboma rodzicami0152
i guard wskazujący tę pojedynczą głowę. Nie zmieniać opublikowanych rodziców
ani kolejności domenowej. Na izolowanej bazie sprawdzić upgrade obu gałęzi.

Wspólne komponenty mają zachować compact i supergame marker/provisional.
Wkład, saldo i „na maszynie” używają kosztu per pozycja również dla pinów
kompaktowych i zamrożonego wyniku. Nie zmieniać dawnych digestów777.
Backend pozostaje źródłem OpenAPI; wygenerować cały klient z połączonego kodu.

Po testach i audycie bez P0/P1 utworzyć merge commit v1.7.288, zapis hashów
w następnym commicie dokumentacyjnym. Dopiero wtedy fast-forward main,
sprawdzając jego świeży tip oraz niezmienność niezapisanych plików operatora.
Jeśli main zmienił się równolegle, najpierw uwzględnić nowy tip, nie resetować.

## Weryfikacja i ryzyka

Task posiada konkretne testy migracji, pinów supergry/compact i istniejące suite.
Najpierw focused Python/TS, lint/types, potem PG, docs/maps/OpenAPI i buildy.
Wszystkie skończone komendy mają timeout120s (audyt480s); dłuższe buildy wymagają
uprzedniej informacji. Produkcyjna migracja/backfill/backup/live ingress są poza integracją.
Otwarte pytania produktowe: brak; zmiany są pogodzeniem już zaakceptowanych kontraktów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0945 | gpt-6.1-sol | high | Integracja migracji, wspólnego kontraktu i kwot pinów bez regresji dwóch gałęzi. | claude-opus-5-5 / high, ograniczony do zmian integracyjnych. |
