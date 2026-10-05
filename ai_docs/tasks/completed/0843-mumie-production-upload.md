---
title: TASK-0843 — Mumie, wgranie do głównej aplikacji
status: done
last_updated: 2026-10-04
---

# TASK-0843 — Mumie, wgranie do głównej aplikacji

## Status

`done` — wgranie źródeł i preflight; plansze wymagają przeglądu geometrii.

## Goal

Utworzyć grę Mumie z profilem siatek Mumii i wgrać 225 źródłowych JPEG-ów przez
istniejące API bez duplikowania, zmiany sekwencji i zatwierdzania propozycji.

## Context

W labie import jest kompletny, ale główna aplikacja ma wyłącznie 777.
Operator polecił niezależnie dokończyć wgrywanie. Mechanika Super i wypłaty
mogą poczekać; nie blokują osobnej gry, źródeł oraz przeglądu geometrii.

## Dependencies / entry conditions

TASK-0842 zakończony. API 8000 i worker działają na migracji 0140; profil Mumii
jest wdrożony. Źródła mają jawne zakresy `seq_*`; brak potrzeby zgadywania pozycji.
Zgoda operatora obejmuje addytywny import danych, bez kasowania i migracji.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, według planu wznowienia. Konflikt gry, source SHA,
manifestu lub fingerprintu blokuje zależny zapis; bez obniżania bramek.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — import i wirtualne geometrie
- `ai_docs/process/DECISION_LOG.md` — D-484, D-489, D-490

## Scope

Gra draft `mumie` / „Mumie”, `grid_profile_mumie_v1`, upload znanego folderu,
preflight i dostępny import wirtualnych komórek, trwałe wznowienie i raport.

## Out of scope

Symbole jako etykiety, payouty, obliczanie targetu, aktywacja nowego modelu,
shadow, migracje, usuwanie danych i ręczne zatwierdzanie sieci za operatora.

## Acceptance criteria

- [x] Gra Mumie odrębna od 777; poprawny profil i zapis odczytany z nowego procesu.
- [x] 225/225 plików w checksum-bound stagingu, jawne zakresy sekwencji zachowane.
- [x] Preflight/import rozliczony; 225 źródeł wymagających decyzji jawnie zgłoszone.
- [x] Identyczne wznowienie odzyskuje staging/job; nie duplikuje danych.
- [x] Raport, Outcome, CURRENT_STATE i osobny commit.

## Technical notes

Użyć istniejącego katalogu i workflow browser-selections; `X-Admin-Intent`.
Obecny historyczny `run_v20_layout_import.py` przypina usunięty `verified_v19`:
nie wykonywać go. Nowy pomocnik przypina obsługiwane wirtualne przetwarzanie
i istniejące fingerprinty preflightu. Nie zmienia API ani generowanych klientów.
Nie tworzy słownika z automatycznych predykcji i nie kopiuje etykiet 777.

## Expected files

- Nowe: `scripts/run_mumie_image_import.py`, test requestów i raport jakości.
- Istniejące: CURRENT_STATE i guide (komenda wznowienia).
- Poza Git: trwały raport uploadu, gameId, uploadId, jobId i checksummy.

## Test cases

Nieprawidłowy profil istniejącej gry daje błąd; zmieniony zbiór plików nie
wznawia starego stagingu; payload używa wirtualnego trybu; retry odzyskuje job.

## Verification

Testy i Ruff, każdy krok do 120 s; krótki odczyt API z nowego procesu;
ograniczony polling istniejących jobów. Proces tła zapisuje PID i deadline;
nie uruchamiać drugiej kopii przy nieustalonym stanie pierwszej.

## Risks / open questions

Preflight może wymagać korekt. Bez zweryfikowanego symbolu lub reguł nie ma
poprawnego payoutu; brak ten nie może zostać zamaskowany pozornym wynikiem.

## Outcome

Gra draft `fea55cc1-ebf4-4cee-b3ab-a520017ed1be` z profilem Mumii. Upload
225/225 JPEG-ów, 61 768 538 bajtów, 13,62 s, sfinalizowany staging
`becad72f-200d-4ba1-8d35-464b19d8f299`. Geometry job
`3e0151c8-b9ff-4da1-b96d-72af4cb01912` completed: 225 review, 0 failed.
Preflight 2025 nowych pozycji i `IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED`.
Nie uruchomiono importu plansz, nie obchodzono wymaganych zatwierdzeń.

Wznowienie uploadu i advance w nowych procesach zachowało staging/job bez
duplikowania. CLI zapisuje stan na dysku, wiąże wejście SHA, propaguje query
`gameId` i blokuje ponowienie nieznanego wyniku tworzenia stagingu. Brak kontekstu
gry w pierwszej próbie preflightu usunięto w CLI i objęto testem requestów.

5 testów PASS (0,80 s), Ruff check i format dwóch plików PASS, Mypy strict
nowego CLI PASS (`--follow-imports skip`, 1 moduł). Pierwsza szersza próba Mypy
z błędnie zawężonym MYPYPATH wyłącznie do workera miała brak importów API
i timeout 120 s; runner zakończył drzewo procesów. Poprawiono ścieżki API/worker
i wykonano kontrolę zakresu CLI. Nie zmieniano kodu zależności ani ich testów.

Raport `ai_docs/quality/MUMIE_PRODUCTION_UPLOAD_20261004.md` i guide zawierają
stan, checksumy i wznowienie. TASK-0830 nie włącza inferencji w głównym imporcie;
V3-D nadal wymaga wyraźnego polecenia. Bez nowych migracji, usuwania danych,
aktywacji modelu, etykietowania symboli, payoutów i shadow. DoD oraz plan
rozliczone punkt po punkcie: źródła wgrane, dalsza materializacja jawnie zablokowana.

Commit: `v1.7.188` / `476bdc268e366720337299fb843666ec865fd9be`
(hash dopisany po commicie).

Commity 187–188 scalone fast-forward do brancha integracyjnego na podstawie
wcześniejszej zgody. Zachowano zastane zmiany, nie wykonano push ani migracji.
