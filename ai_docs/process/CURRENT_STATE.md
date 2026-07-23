---
title: Current project state
status: active
last_updated: 2026-07-24
---

# Current State

## Phase

`M1 zaplanowany i podzielony — oczekiwanie na start M1.1`

## Completed

- właściciel odpowiedział na Q-001–Q-014 i doprecyzował Q-018,
- zaakceptowano decyzje D-001–D-012,
- ustalono całkowicie offline mobile od M1,
- ustalono skalę do około 500 000 layoutów na grę i 12–15 gier,
- ustalono ciągłą, cykliczną sekwencję i procedurę duplikatu bez confirmation chain,
- ustalono wyłącznie wzorce `PAYLINE`, joker, sumowanie i longest match,
- ustalono spin 0, koszt każdego kolejnego spinu i kumulację wszystkich payoutów,
- Target obejmuje `layout_count - 1` spinów i pokazuje dodatnie lokalne maksima,
- zaakceptowano precomputing payoutów, SQLite w APK i lokalny proces wydania,
- przeanalizowano trzy przykładowe zdjęcia i zaakceptowano wymienny stos prototypu,
- zsynchronizowano wymagania, architekturę, model danych, kontrakty, roadmapę i testy,
- podzielono M1 na sześć podetapów z osobnymi bramkami jakości,
- ustalono wersjonowaną aktywację snapshotu po aktualizacji APK,
- finalne APK M1 nie deklaruje uprawnienia Android `INTERNET`,
- usunięto artefakty instalacyjne pakietu dokumentacji, a materiały historyczne
  przeniesiono do `ai_docs/archive/` i `ai_docs/tasks/completed/`.

## In progress

Brak prac implementacyjnych. Plan wykonania M1 jest gotowy. Repozytorium
oczekuje na polecenie rozpoczęcia M1.1.

## Open but not blocking M1

- Q-015–Q-017: reprezentatywny zbiór zdjęć, stabilność ekranu i etykiety treningowe,
- Q-019: jeden czy wielu administratorów,
- Q-020: zakres dozwolonej analizy aplikacji referencyjnej,
- finalne modele OCR/ML po benchmarku,
- ostateczna nazwa sekcji `Result` albo `Target`,
- semantyka kilku rozłącznych zwycięskich ciągów na jednej payline dla plansz szerszych niż 5 kolumn.

Żaden z tych punktów nie zmienia zakresu planszy 3 × 5 ani mock danych M1.

## M1 execution structure

Obowiązuje
`delivery/MILESTONE_01_EXECUTION_PLAN.md`:

1. M1.1 — fundament i offline SQLite spike,
2. M1.2 — kontrakty oraz algorytmy,
3. M1.3 — generator, snapshot i repozytorium,
4. M1.4 — UI matching,
5. M1.5 — Target i tabela,
6. M1.6 — release APK i testy urządzeń.

Każdy podetap musi przejść własną bramkę przed rozpoczęciem następnego.

## Next recommended task

Po wyraźnym poleceniu właściciela utworzyć wyłącznie zadanie:

```text
TASK-0002 — Monorepo and offline SQLite spike
```

Zakres obejmuje tylko M1.1: strukturę monorepo, standardy jakości, minimalną
aplikację Android i odczyt małego wersjonowanego SQLite bez sieci. Nie obejmuje
jeszcze payout, pełnego generatora, planszy, matching ani Target.

## Do not start yet

- żadnej implementacji ani inicjalizacji frameworków bez następnego polecenia,
- panelu admina przed zdefiniowaniem osobnego zadania M2,
- masowego przetwarzania zdjęć,
- finalnego wyboru OCR/ML,
- Celery/Redis, mikroserwisów i chmury,
- synchronizacji danych mobilnych,
- publicznego deploymentu lub publikacji w Google Play.

## Handoff notes

Dokumentacja opisuje zaakceptowany model produktu i architektury. M1 nie ma
pytania produktowego blokującego start. Decyzje o package managerze, Python
toolingu, `applicationId` i dokładnej komendzie Android build zostaną podjęte w
M1.1 na podstawie kompatybilnych stabilnych wersji i zapisane w Decision Log.

Benchmark 500 000 layoutów pozostaje bramką M3 przed uznaniem rozwiązania
SQLite/TypeScript za wystarczające dla docelowej skali.
