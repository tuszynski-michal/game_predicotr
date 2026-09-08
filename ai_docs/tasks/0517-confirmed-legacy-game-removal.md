---
title: TASK-0517 — Confirmed legacy game removal
status: in_progress
last_updated: 2026-09-09
---

# TASK-0517 — Zatwierdzone usunięcie starej gry

## Status

`in_progress`

## Goal

Wdrożyć przygotowanie schematu, wygenerować aktualny preview i — wyłącznie po
osobnym dokładnym potwierdzeniu — wznowieniowo usunąć dane `777 v0.1`, zachowując
zweryfikowane archiwum czatowe i wszystkie dane `new-siedem`.

## Context

TASK-0516 dostarczył niezależnie zatwierdzany mechanizm porcji. Użytkownik
polecił przejść dalej, co autoryzuje ocenę i wdrożenie przygotowawczych migracji,
ale nie zastępuje dokładnego potwierdzenia finalnego preview destrukcyjnego.

## Dependencies / entry conditions

- Migracje 0103/0104 są zastosowane, a usunięcie bazodanowe ma terminalny
  receipt `database_done`.
- Archiwum 414705 układów zgodne read-only z PostgreSQL.
- Brak aktywnych jobów i oczekujących locków przy inspekcji 2026-09-08.
- Około 48 GiB wolnego na C; szacunek nowych indeksów 4,2 GB, wymagany bufor
  co najmniej 10 GB. Warunki trzeba ponownie sprawdzić po migracji.

## Recommended execution

`gpt-5.6-sol medium`; niezależny review `gpt-6-astra high` przed destrukcją.
Przerwać przy utracie zapasu, drift schema/archive, aktywnym jobie, nieznanej
własności albo błędzie migracji; nie omijać fence i receipt.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/RESUMABLE_LEGACY_DELETION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/quality/TASK_0516_RESUMABLE_DELETION_REVIEW.md`

## Scope

- Dodać fail-fast timeout do DDL 0103 i zweryfikować migrację.
- Zastosować 0103/0104 w nadzorowanym oknie; indeksy concurrent mogą być
  bezpiecznie wznowione.
- Wykonać read-only preview i przekazać dokładny SHA oraz zakres operatorowi.
- Po osobnym dokładnym potwierdzeniu uruchamiać ograniczone invokacje aż do
  `database_done`, monitorując miejsce, joby, drift i ochronę `new-siedem`.
- W osobnym etapie 0517 wykonać reference-aware GC wyłącznie zasobów starej gry;
  nie usuwać archiwum ani katalogu operatora.

## Out of scope

Partycje game_data_v2, migracja `new-siedem`, `VACUUM FULL`, kompaktowanie VHDX,
usunięcie archiwum czatowego i jakakolwiek zmiana `Documents/777`.

## Acceptance criteria

- [x] Migracje kończą się na 0104 i brak invalid indeksów.
- [x] Aktualny preview jest ready, zgodny z archiwum i bez aktywnych jobów.
- [x] Usunięcie nie rozpoczyna się bez exact SHA i potwierdzenia operatora.
- [x] Po zatwierdzeniu receipt dochodzi do database_done bez duplikacji liczników.
- [x] `new-siedem`, współdzielone executions i archiwum pozostają zgodne.
- [ ] GC usuwa tylko osierocone managed assets starej gry po ponownej walidacji.

## Test cases / verification

Focused 0516 tests i migration smoke przed wdrożeniem. Po wdrożeniu: current head,
invalid indexes, disk free, active jobs, read-only preview. Po destrukcji: receipt,
brak legacy identity, obecność protected identity, archive checksum/search smoke,
brak obcych referencji i raport odzyskanego miejsca.

## Outcome

In progress. Bazowa część operacji została zakończona:

- receipt: `database_done`, 81 etapów, 10549 zatwierdzonych porcji;
- usunięto rekord gry i jej dane domenowe, w tym 580105 plansz oraz 8701575
  obserwacji komórek;
- `new-siedem` pozostaje obecne, nie ma aktywnych jobów starej gry;
- archiwum 414705 układów zachowuje SHA-256
  `0e1d18a6f9ffe22860c6956f8f5761909df45021465643817c8cbf2426314c5e`.

Reference-aware GC pozostaje częściowo wykonany. Read-only preview wskazuje 9599508
plików o rozmiarze 104,888 GiB, po ochronie 80640 żywych ścieżek i manifestów.
Preview SHA-256:
`c4cce437b5f84df95f0ea07e6b68d4f8dffe2696e495c82badeb92946d2b2b2b`.
Szczegóły mają SHA-256
`e9a672233c1136e1929402c0d584a92b1ea44ea849ceea045563e33b33db1d0e`.
Receipt zatrzymał się po 15700 rekordach: usunięto 2258144 pliki o łącznym
rozmiarze 21271550497 bajtów (19,811 GiB). Pozostałe zasoby są odłączone w
`artifacts/data.detached-20260908-legacy-reset`, a aktywny `artifacts/data` jest
pusty. Fizyczne wznowienie wymaga nowego osobnego dokładnego potwierdzenia i
ponownego sprawdzenia aktywnych jobów oraz referencji bezpośrednio przed
wykonaniem.
Wznawialny executor jest zaimplementowany i przetestowany: weryfikuje oba SHA,
blokuje zapisy do tabel przechowujących ścieżki, odświeża żywe referencje,
sprawdza fingerprint każdego kandydata, przenosi go atomowo do kwarantanny i
utrwala kursor po usunięciu. Executor mapuje teraz logiczne ścieżki preview do
jawnie wskazanego `data.detached-*`, wymaga pustego aktywnego `data`, trwale
wiąże katalog z receiptem i rozlicza przerwany zapis `.tmp` względem faktycznej
lokalizacji źródła/kwarantanny. Siedemnaście testów skupionych, Ruff i kontrola
formatu przechodzą. Wznowienia nie uruchomiono po zatrzymaniu przez operatora,
ponieważ wymaga ono ponowionej dokładnej zgody dla tego preview.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0517 | `gpt-5.6-sol` | `medium` | Nadzorowane wykonanie gotowego mechanizmu z jawnie przypiętymi bramkami i receipt. | `gpt-6-astra high` przed destrukcją |
