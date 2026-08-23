---
title: Remote manual image selection feasibility and implementation plan
status: done
last_updated: 2026-08-23
---

# TASK-0272 — Analiza zdalnej ręcznej selekcji zdjęć

## Status

`done`

## Goal

Udokumentować wykonalną, bezpieczną i możliwą do etapowego wdrożenia architekturę zdalnej ręcznej selekcji zdjęć, bez implementowania funkcji produkcyjnej.

## Context

Obecny moduł działa wyłącznie lokalnie w przeglądarce operatora i zapisuje pliki przez File System Access API. Wymagany jest wariant, w którym host udostępnia ograniczony czasowo link, zdalny operator przegląda własne zdjęcia bez masowego uploadu, a wyłącznie zaakceptowane JPEG-i i decyzje trafiają niezawodnie do katalogu hosta.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/tasks/completed/0246-manual-local-image-selection.md`
- `ai_docs/tasks/completed/0261-game-independent-manual-image-selection.md`
- `ai_docs/tasks/completed/0113-remote-reviewer-threat-model-session-hardening.md`
- `ai_docs/tasks/completed/0115-secure-ingress-runbook-remote-end-to-end-acceptance.md`
- `ai_docs/tasks/completed/0249-board-cell-geometry-review-queue-and-shared-reviewer.md`

## Scope

- Zrekonstruowanie faktycznego lokalnego przepływu, kontraktów JSON, trwałości i ograniczeń przeglądarki.
- Analiza istniejącego Reviewera, sesji, tunelu, routingu, autoryzacji, API, bazy, workerów i logowania pod kątem bezpiecznego reuse.
- Porównanie maksymalnie trzech realnych architektur i wybór rekomendowanego MVP.
- Projekt mapowania katalogów, stanu kanonicznego, outboxu, idempotencji, kolejek, uploadu, wznowienia, bezpieczeństwa i finalizacji.
- Opis wszystkich wymaganych scenariuszy błędów, invariantów, benchmarku, rollout i rollback.
- Utworzenie dokumentu technicznego oraz breakdownu małych, zależnych tasków implementacyjnych z doborem modeli i checkpointów.
- Przedstawienie propozycji P-XXX i R-XXX do osobnej akceptacji.

## Out of scope

- Implementacja produkcyjnego linku, endpointów, migracji, UI, uploadu lub zmian eksportu.
- Uruchamianie tunelu, otwieranie portów, przesyłanie rzeczywistych zdjęć i masowe benchmarki.
- Modyfikowanie produkcyjnych JSON-ów, `AGENTS.md` albo niezwiązanych modułów.

## Acceptance criteria

- [x] Dokument zawiera wszystkie 33 wymagane sekcje techniczne oraz końcowy wynik w kolejności 1–28 określonej przez właściciela.
- [x] Ważne ustalenia mają status i dowód w konkretnym pliku, klasie lub funkcji.
- [x] Porównano maksymalnie trzy realne warianty i wskazano jeden rekomendowany.
- [x] Jednoznacznie opisano źródło prawdy, mapowanie katalogów, maszyny stanów, trzy kolejki, idempotencję i finalizację.
- [x] Każdy z 26 scenariuszy awarii ma zachowanie, źródło prawdy, komunikat, retry i ochronę danych.
- [x] Plan testów obejmuje skalę od małego katalogu do 8–15 tys. zdjęć lub operacji, bez wykonywania masowego testu.
- [x] Breakdown zawiera osobno weryfikowalne taski, zależności, testy, DoD, rollback, ryzyko, model i reasoning.
- [x] Propozycje P-XXX i R-XXX pozostają wyłącznie do akceptacji; `AGENTS.md` nie jest zmieniony.
- [x] Nie zmieniono kodu produkcyjnego ani danych użytkownika.

## Technical notes

- Dotychczasowy lokalny moduł musi pozostać działającym fallbackiem.
- Istniejący Reviewer i Quick Tunnel mogą być współdzieloną infrastrukturą dopiero po potwierdzeniu izolacji scope'u; nie wolno automatycznie rozszerzyć obecnej autoryzacji.
- Twierdzenia zależne od aktualnego wsparcia API przeglądarek wymagają sprawdzenia w aktualnych źródłach platformy webowej.

## Expected files

- `ai_docs/tasks/0272-remote-manual-image-selection-analysis.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run format:check
git diff --check
git status --short
```

## Risks / open questions

- Czy deklarowane 15 000 oznacza unikalne finalne pliki czy wszystkie operacje wyboru i cofania.
- Czy trwałe wznowienie bez ponownego wskazania folderu ma być wymagane również poza przeglądarkami Chromium.
- Jaki mechanizm host-local ma bezpiecznie powiązać wskazany katalog bazowy z procesem API po restarcie.

## Outcome

Analiza została ukończona bez implementacji funkcji produkcyjnej.

### Changed

- Dodano propozycję architektury z rekonstrukcją obecnego modułu, trzema
  wariantami, rekomendacją, kontraktami, modelami stanów i awarii.
- Rozpisano 19 małych tasków implementacyjnych oraz propozycje P-001–P-003 i
  R-001–R-005.

### Verification results

- Celowany Prettier dla czterech zmienionych dokumentów — zaliczony.
- Pełny `npm run format:check` przerwano po 120 s; przed przerwaniem raportował
  wcześniejsze ostrzeżenia w plikach poza TASK-0272.
- `git diff --check` — zaliczony dla śledzonych zmian.
- Kontrola 19/19 wymaganych pól tasków i 26/26 scenariuszy awarii.

### Not completed

- Nie implementowano endpointów, migracji, UI, tunelu ani transferu zdjęć.
- Nie wykonano masowego benchmarku ani testu publicznego ingressu.

### Documentation updates

- Dodano `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`.
- Zaktualizowano indeks i `CURRENT_STATE.md`; decyzje pozostają `PROPOSED`.

### Recommended next task

- Po decyzji właściciela: TASK 1 — browser capability i filesystem feasibility
  spike. Nie rozpoczynać TASK 2 przed jego checkpointem.
