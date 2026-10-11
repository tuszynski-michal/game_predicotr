---
title: Pilotaż i odbiór wydania
status: todo
last_updated: 2026-10-11
---

# TASK-0979 — Pilotaż i odbiór wydania

## Status

`todo`

## Goal

Dostarczyć wersjonowaną paczkę Windows i uzyskać udokumentowany odbiór pełnego przepływu u odbiorcy.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

TASK-0977 zakończony. TASK-0978 nie jest zależnością. Końcowy audyt operatora po całym zakresie. Operator udostępnia drugi komputer i dowody rzeczywistego odbioru.

## Recommended execution

`gpt-6.1-sol / medium`. Operator wykona końcowy audyt całego zakresu; zalecany model
`claude-sonnet-5-5 / medium`. CLI audytora nie jest bramką implementacji.
Konfiguracja odpowiada tabeli planu. Eskaluj, gdy zmiana wymaga innego modelu
własności danych, nowych reguł domeny lub niezgodnego formatu. Nie zmieniaj
modelu/reasoning niejawnie. Wyjątek operatora: bez audytu przed każdym commitem; końcowy przegląd po pięciu taskach.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md — TASK-0979
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md — obowiązująca sekcja operator-local
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Powtarzalny Forge ZIP, version i SHA-256, instrukcja instalacji bez instalatora i aktualizacji.
- Backup/restore projektu, source relink, logs i instrukcja niesynchronizowanego katalogu projektu.
- Pilotaż bez podpisu, sprawdzenie faktycznej drogi otrzymania paczki, ograniczenia ochrony Windows.
- Odbiór offline, restart Windows, aktualizacja EXE bez modyfikacji projektu, zdjęcia w zwykłym wyniku.
- Raport akceptacji rozdzielający kontrole agentowe od dowodów użytkownika.

## Out of scope

Podpis/certyfikat, sklep, auto-update, integracja Proton Drive, push/merge i automatyczny dostęp do komputera odbiorcy.

## Acceptance criteria

- [ ] ZIP i suma kontrolna są gotowe, instrukcja pozwala rozpakować cały folder i uruchomić program.
- [ ] Czysty Windows 11 x64 bez Node/Python i bez hosta pozwala zakończyć nową partię.
- [ ] Rzeczywisty reboot i aktualizacja zachowują projekt; source relink nie resetuje decyzji.
- [ ] Wyłącznie gotowy folder wybrane jest przekazywany ręcznie, projekt nie jest synchronizowany.
- [ ] Blokada Windows wstrzymuje odbiór; dokumentacja nie zaleca wyłączenia ochrony.
- [ ] Outcome nie twierdzi PASS dla drugiego komputera bez dowodu operatora.

## Technical notes

Smoke test na komputerze agenta nie zastępuje tej bramki. Podpis nie gwarantuje braku ostrzeżeń, a niepodpisany ZIP nie musi być zawsze blokowany. Pakowanie może wymagać znanego builda dłuższego niż 120 s; poinformuj przed nim o czasie i ustaw timeout. Nie wykonuj usług, publikacji albo operacji danych poza planem.

## Expected files

- Nowe, proponowane: ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md, ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md.
- Nowe konfiguracje release apps/selector-desktop, artefakty ZIP/SHA-256 w ignorowanym katalogu.
- Dokumentacja CURRENT_STATE, task Outcome, README i TRACEABILITY.

## Test cases

- Paczka dostarczona przez faktyczny kanał użytkownika → rozpakowanie i uruchomienie.
- Selekcja offline z wyłączonym hostem, restart Windows, update programu, reopen projektu.
- Przeniesienie source i jawny relink, backup/restore na kopii, odczyt wynikowych JPEG-ów.
- Version/checksum każdej paczki; brak dostępu sieciowego aplikacji.

## Verification

Z katalogu worktree selektora. Każda skończona komenda ma timeout do 120 s;
znany dłuższy build tylko po uprzedniej informacji i osobnym limicie.

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run test --workspace @game-predictor/reviewer
npm run docs:check
npm run code-map:check
```

Powyższe skrypty istnieją w repo. W nowym worktree wymagają dostępnych
zależności oraz interpreterów; przygotowanie środowiska nie uprawnia do
restartu usług ani migracji. TASK-0975 ma dodać test/lint/typecheck/build/
package/make aplikacji desktopowej, a następnie zapisać sprawdzone komendy
i wyniki w Outcome. Te skrypty są teraz proponowane, nie wykonane.
Testy Reviewera sprawdzają zgodność kontraktu; nie zastępują odbioru Electrona.
Po zmianie modułów/symboli zregenerować mapę, potem sprawdzić code-map:check.

## Risks / open questions

Drugi komputer i reboot są zależnością operatora. Nie kończ taska jako done, gdy pozostają kryteria fizycznego odbioru; zapisz gotową paczkę i blocker.

## Outcome

### Changed

Przygotowano specyfikację taska i zaakceptowany plan. Implementacja nie została rozpoczęta.

### Verification results

Kontrole przygotowanej dokumentacji: check_decision_links.py PASS (542 odnośniki/wpisy/wiersze indeksu), check_current_state_window.py PASS (47 aktywnych tasków, 10 done). Testów implementacji nie uruchamiano.

### Not completed

Kryteria implementacyjne pozostają do wykonania. Audyt operatora jest odłożony do końca pięciu tasków.

### Documentation updates

Task, plan, D-545 i wpisy źródeł prawdy opisują zaakceptowany zamiar.

### Recommended next task

TASK-0978 po przygotowaniu paczki; fizyczny odbiór wydania i końcowy audyt operatora pozostają do potwierdzenia.
