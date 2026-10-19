---
title: Zapisany koszt spinu Mumii 10 kredytów
status: done
last_updated: 2026-10-19
---

# TASK-1065 — Zapisany koszt spinu Mumii

## Status

`done`

## Goal

Najnowsze opublikowane reguły Mumii mają zapisany koszt 10 kredytów,
zgodny z kalkulatorem i bazą tabeli wypłat.

## Context

TASK-1063 poprawił efektywny koszt kalkulatora, ale nie zmienił konfiguracji
w bazie. Operator nadal widzi 100 w regułach. 2026-10-19 operator jawnie
zlecił zmianę kosztu, scalenie wszystkich poprawek oraz build i restart
samego Reviewera z zachowaniem istniejącego tunelu.

## Dependencies / entry conditions

TASK-1063 jest w main; TASK-1064 oczekuje na scalenie na bieżącej gałęzi.
Odczyt bazy: opublikowana v2 ma koszt 100; istnieje draft v3 z kosztem 100.
Przed zmianą porównać pełne linie, symbole i wypłaty draftu ze źródłem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`, tymczasowy profil Mumii.
- `ai_docs/architecture/API_CONTRACT.md`, kalkulator.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-565--tymczasowa-baza-wypłat-i-stawki-mumii`
- `ai_docs/tasks/completed/1064-mumie-share-stake-profile.md`

## Scope

Jedna transakcja przez RulesService: ustawienie kosztu draftu na 10 i publikacja,
jeżeli poza kosztem konfiguracja jest identyczna z v2. Zachowanie dawnych wersji.
Odczyt z nowego procesu i weryfikacja świeżości supergier po publikacji.
Pliki: ten task, ADMIN_APP, API_CONTRACT i dokumenty zamknięcia zadania.

## Out of scope

Zmiana kwot wypłat, migracja schematu, edycja historycznych wyników,
restart API, Admina, workerów lub tunelu. Brak nowego kontraktu API i kodu domeny.
Scalenie i wdrożenie istniejących poprawek to osobno autoryzowana operacja
operatorska po zamknięciu tej korekty konfiguracji.

## Acceptance criteria

- [x] Najnowsze opublikowane reguły i konfiguracja odczytana z nowego procesu mają koszt 10.
- [x] Linie, symbole i wszystkie kwoty wypłat zachowane; historyczna v2 nadal ma koszt 100.
- [x] Generacja supergier po publikacji jest świeża, kalkulator nadal uwzględnia darmowe spiny.
- [x] Dokumentacja oraz docs:check są aktualne; brak niezwiązanych zmian w commicie.

## Technical notes

Nie modyfikować opublikowanej v2. Wykorzystać draft v3 tylko po potwierdzeniu
identyczności jego konfiguracji. Publikacja normalnie unieważnia generację
supergier; zaczekać na istniejący worker, bez ręcznej zmiany liczników.
Lista 1/2/5/10/20 zł nadal pozostaje tymczasowo w kodzie zgodnie z D-565.

## Verification

Nowy proces aplikacyjny: odczyt reguł, porównanie konfiguracji i kalkulator
dla sekwencji 3488 oraz 2500 spinów. Oczekiwane: wypłaty 18980,
koszty 23000 i bilans -4020 kredytów. Komendy z timeoutem 120 s.
`npm run docs:check` przed commitem. Weryfikacja wdrożenia po scaleniu:
nowy BUILD_ID, odpowiedź publicznego originu i zachowana tożsamość tunelu.

## Risks / open questions

Brak otwartych decyzji. Przy różnicy draftu zatrzymać jego publikację i zachować
zmiany operatora. Nie publikować reguł z cudzymi zmianami przy okazji korekty kosztu.

## Outcome

Commit: v1.7.439 / `b971999eb6d2efc49136ff76864b83accd1cee20`.

### Changed

- Przez RulesService zmieniono draft v3 `4482fb16-a910-4dfa-b594-d2dbd1cf9aed`
  z kosztu 100 na 10 i opublikowano. Przed zapisem porównano wszystkie linie,
  symbole i wypłaty z v2: identyczne. V2 zachowana bez zmian.
- Nie zmieniono kodu, schematu, API ani kwot wypłat. Korekta danych jest trwała.

### Verification results

- Nowy proces po commicie transakcji: najnowsze opublikowane reguły mają
  koszt 10; kalkulator także 10. Zakres od 3488, 2500 spinów: 200 darmowych,
  wypłaty 18980, koszty 23000, bilans -4020 kredytów. PASS.
- Istniejący worker zakończył normalny job publikacji
  `be64e338-9441-4cf4-8a9d-0a4987fb4bfb`; input i generacja są równe 29001.
  Nie restartowano workera, API, Admina ani tunelu.
- Porównano kryteria punkt po punkcie. docs:check PASS; brak zmian modułów
  lub publicznych symboli wymagających regeneracji mapy kodu.
- Lokalny dowód konfiguracji: ignorowane artefakty
  `artifacts/mumie-payout-explanation-20261019/persisted-spin-cost-receipt.json`
  i `verify_persisted_spin_cost.py`. Brak audytu wymaganego przez plan.

### Not completed

Scalenie gałęzi wraz z TASK-1064, build i restart Reviewera będą wykonane
w kolejnym kroku operatorskim, już jawnie zleconym przez użytkownika.
Ten commit dokumentuje korektę konfiguracji, nie potwierdza wdrożenia builda.

### Documentation updates

ADMIN_APP, API_CONTRACT i dopisek do D-565 rozróżniają nową opublikowaną v3
z kosztem 10 od dawnych niezmiennych wersji. Zamknięcie przez task-close.

### Recommended next task

Po zamknięciu korekty: autoryzowane scalenie, push i wdrożenie Reviewera,
zachowując istniejący proces cloudflared i jego publicOrigin.
