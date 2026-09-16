---
title: TASK-0483 — Stabilna weryfikacja symboli i ochrona nieczytelnych cropów
status: done
last_updated: 2026-09-06
---

# TASK-0483 — Stabilna weryfikacja symboli i ochrona nieczytelnych cropów

## Goal

Usunąć pełne przeładowanie strony po poprawnej decyzji w `Weryfikacji symboli`
oraz zapewnić, że crop raz oznaczony jako `unreadable` pozostaje jawnie
oznaczony i wykluczony z treningu także po późniejszym przypisaniu etykiety.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`

## Scope

- lokalne ukrycie poprawnie zapisanych kart bez ponownego pobierania strony;
- pozostawienie kart po konflikcie lub częściowym błędzie;
- zachowanie `quality_issue=unreadable` przy zwykłym zatwierdzeniu i zmianie
  symbolu dla tych samych pikseli;
- widoczny badge i delikatna szara warstwa na nieczytelnym cropie w pełnym
  widoku planszy;
- odczytowy audyt historii nieczytelnych cropów gry `777 v0.2`, bez zmiany
  danych.

## Out of scope

- automatyczne cofanie lub masowa zmiana danych gry;
- zmiana cropa, geometrii albo modelu symboli;
- zmiana API, OpenAPI lub schematu PostgreSQL.

## Invariants

- nieczytelność jest właściwością bieżących pikseli, nie przypisanej etykiety;
- zwykła zmiana etykiety nie może zakwalifikować nieczytelnego cropa do
  treningu;
- pełny sukces ukrywa wyłącznie dokładne checksum-bound targety operacji;
- częściowy wynik nie ukrywa targetów bez indywidualnego potwierdzenia;
- dane gry nie są mutowane bez osobnego preview i potwierdzenia użytkownika.

## Acceptance criteria

- pojedyncza poprawna decyzja usuwa kartę bez requestu bieżącej strony;
- pełna poprawna operacja masowa usuwa swoje widoczne targety bez refill;
- konflikt lub błąd nie usuwa karty;
- approve/reassign zachowuje `unreadable` i crop pozostaje poza treningiem;
- pełny widok planszy oznacza taki crop tekstem i warstwą wizualną;
- audyt `777 v0.2` rozróżnia bieżące cropy chronione i te, które utraciły
  ochronę.

## Outcome

Udane decyzje pojedyncze i masowe chowają teraz tylko swoje targety przez
`hiddenCellIds`; nie przełączają strony w loading i nie zwiększają rewizji
ponownego pobrania. Niezależne liczniki nadal odświeżają się według nowej
rewizji katalogu. Konflikty i wyniki częściowe pozostają widoczne.

Domena zachowuje `quality_issue=unreadable` przy `approve` i `reassign`, więc
zmiana logicznego symbolu nie kwalifikuje tych samych pikseli do treningu. Widok
planszy otrzymał tekstowy badge `Nieczytelny` oraz delikatną szarą warstwę nad
cropem.

Odczytowy audyt gry `777 v0.2` (`9ed937db…`) znalazł 45 bieżących cropów na 18
planszach, które miały `unreadable` dla tej samej checksummy. Wszystkie 45 nadal
ma tę ochronę; zero utraciło status, zero spełnia bieżący kształt warunków
treningowych. Nie wykonano żadnej mutacji danych.

Weryfikacja: 47 skoncentrowanych testów API/domeny/storage, 20 testów Admina,
Ruff i izolowany mypy dla zmienionego modułu, pełny lint i typecheck Admina
oraz produkcyjny build — zielone. Standardowy mypy API nadal raportuje 48
wcześniejszych błędów w zależnościach i 20 niezwiązanych plikach; zmieniony
moduł nie ma własnego błędu po odizolowaniu importów.
