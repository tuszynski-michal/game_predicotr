---
title: TASK-0157 image selection scale quality and owner acceptance
status: in_progress
release: "0.4"
last_updated: 2026-08-03
---

# TASK-0157 — Image selection scale, quality and owner acceptance

## Status

`in_progress`

## Goal

Udowodnić na goldenach oraz profilach 10 000/30 000, że selektor jest szybszy
od pełnego pipeline'u, bounded pamięciowo i nie wybiera błędnego zakresu.

## Context

Bez pomiaru nowy moduł może tylko przenieść koszt albo błędy do innego miejsca.
Jest to końcowa bramka wersji 0.4 przed rozpoczęciem pracy na dużych danych
wersji 0.5 i TASK-0076.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_07_0_EXECUTION_PLAN.md`
- `ai_docs/tasks/0156-image-selection-job-resume-and-observability.md`

## Scope

- utworzyć niezależne adnotacje zakresów, grup i poprawnych reprezentantów,
- objąć różne kąty, blur, refleks, zasłonięcie, clipping, późniejsze duplikaty,
  skoki numeracji i stronę końcową,
- zmierzyć precision grupowania, auto-selection precision, manual rate i
  coverage,
- zmierzyć upload, skan, OCR count, throughput, peak RSS i rozmiar storage,
- uruchomić profile 10 000 oraz 30 000 z twardym timeoutem i cleanupem fixture,
- porównać liczbę wejść oraz estymowany koszt z pełnym pipeline'em,
- przeprowadzić ręczny odbiór workspace'u, modala, outputu i handoffu,
- zapisać raport i decyzję `ready | optimize | reject`.

## Out of scope

- pełne przetworzenie 500 000 layoutów,
- tuning symbol classifier,
- zmiana kolejki lub dodanie chmury bez dowodu benchmarku,
- obniżenie fail-closed quality gate w celu poprawy samego czasu.

## Acceptance criteria

- [x] Golden ma zero fałszywych scaleń dwóch różnych zakresów.
- [x] Każdy auto-selected reprezentant ma poprawny zakres i kompletną widoczną
      stronę według niezależnej adnotacji.
- [x] Niepewne przypadki trafiają do manual review zamiast auto-selection.
- [x] Profil 10 000 kończy się w ≤15 minut, a 30 000 w ≤45 minut na komputerze
      właściciela.
- [x] Peak RSS i storage są zmierzone oraz mieszczą się w zaakceptowanym
      budżecie raportu.
- [x] Liczba kosztownych OCR/weryfikacji skaluje się z grupami × top-k, nie N.
- [x] Restart/cancel profile nie pozostawia procesu ani częściowego manifestu.
- [ ] Właściciel potwierdza nawigację, single-file fallback, Enter, strzałki,
      nazwy outputu i jawny handoff.
- [x] Raport końcowy jawnie zezwala lub blokuje użycie przed TASK-0076.

## Technical notes

Duży fixture ma powstawać w ignorowanym katalogu i może używać kontrolowanych
kopii/hardlinków, ale raport musi oddzielić koszt I/O fixture od właściwego
dekodowania i selekcji. Każda komenda ma jawny timeout; profil 30k może dostać
limit dłuższy niż 120 sekund dopiero po uprzednim komunikacie.

## Expected files

- `scripts/run_image_selection_benchmark.py`
- `scripts/run_image_selection_benchmark.ps1`
- `ai_docs/quality/image-selection-*.json`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile smoke -TimeoutSeconds 120
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 10000 -TimeoutSeconds 1200
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 30000 -TimeoutSeconds 3600
```

## Risks / open questions

- Budżet jest provisionalny do pierwszego pomiaru na komputerze właściciela;
  może zostać zaostrzony, ale nie rozluźniony ponad proces wielogodzinny bez
  nowej decyzji produktowej.

## Outcome

Techniczna część bramki jest ukończona. Dodano niezależny kontrakt adnotacji,
benchmark używający produkcyjnego taniego skanu, wewnętrzny i zewnętrzny timeout,
atomowy raport oraz bezpieczny cleanup fixture. Profile smoke, 10 000 i 30 000
przeszły z zerem fałszywych scaleń, pełnym grouping/auto-selection precision i
niezmienionym inventory źródłowym. Profil 10k trwał 252,51 s i zużył dodatkowo
76,2 MiB peak RSS, a 30k 792,43 s i 194,0 MiB. Sparse verification zachowało
limit `grupy × top-k`.

Raport `quality/IMAGE_SELECTION_ACCEPTANCE.md` nadaje decyzję techniczną
`ready`, ale odbiór właściciela nawigacji, single-file fallbacku, Entera,
strzałek, nazw outputu i jawnego handoffu nadal oczekuje. Z tego powodu zadanie
pozostaje `in_progress`, nie jest przenoszone do `completed/`, a TASK-0076 nadal
jest zablokowany.

Przed odbiorem właściciela usunięto wykrytą lukę odświeżania Admina: aktywny run
jest odpytywany co 2 s, pojedynczy request jest anulowany po 10 s, a cała sesja
pollingu ma limit 45 minut i cleanup przy zmianie gry lub stanu terminalnego.
Klient API jawnie przekazuje `AbortSignal`; powtarzające się błędy odświeżania są
widoczne, ale nie blokują pozostałych akcji.

Cykl manualnego fallbacku został również domknięty transakcyjnie. Ostatnia
decyzja dla runu blokuje rekord joba, potwierdza brak nierozwiązanych grup i
wykonuje idempotentne `waiting_for_review -> created` z zachowaniem checkpointu
oraz liczników. Admin natychmiast odczytuje ten stan i kontynuuje polling; ręczne
`Ponów` w osobnym workspace nie jest potrzebne.

Workspace odbiorowy pokazuje teraz postęp i wyniki selektora bez konieczności
przechodzenia do `Jobów`: status i etap, `X/N`, procent, grupy, wybory
automatyczne, manualne przypadki, pominięcia, błędy, liczbę kosztownych
weryfikacji oraz oddzielne czasy uploadu i obliczeń. Identyfikatory runu, joba i
manifestu wejściowego zostały przeniesione do zwijanych szczegółów technicznych.

Pierwszy rzeczywisty przebieg 180 zdjęć ujawnił nieakceptowalny manual rate
`32/32`. Przyczyną była zmienna liczba wykrywanych czerwonych ramek, odrzucenie
OCR przed pełną weryfikacją oraz ocena ekspozycji całej ciemnej obudowy.
`fast-image-selector-v2` wprowadził stabilny fingerprint HSV ekranu, pełny
fallback OCR przestrzennej siatki etykiet i guard, który nie tworzy grupy z
jednej klatki przejściowej. Kontrolny przebieg tych samych 180 plików zakończył
się w 44,2 s: 7 poprawnych zakresów wybrano automatycznie, 4 grupy oznaczono
jako powtórzenia, a manual review wyniósł `0`. Odbiór UI nadal wymaga
powtórzenia runu przez właściciela na uruchomionych usługach.
