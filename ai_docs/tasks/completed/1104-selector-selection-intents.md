---
title: Płynna nawigacja i niezawodne F
status: done
last_updated: 2026-10-29
---

# TASK-1104 — Płynna nawigacja i niezawodne F

## Status

`done`

## Goal

Każde osobne F jest rozliczone, a widoczny kursor reaguje niezależnie od zapisu native.

## Context

App dotychczas odrzucał F podczas busy/decode i czekał ze zmianą zdjęcia na zapis.

## Dependencies / entry conditions

Plan rev. 3 i koszt 3–5 h dla całego planu zaakceptowane 2026-10-29.
Numery 1104–1107 wolne we wszystkich lokalnych gałęziach; HEAD v1.7.495.
Operator pominął audyty Claude dla wszystkich tasków. Brak blokujących pytań.

## Recommended execution

`gpt-6.1-sol` / `high`. Ryzyko przypisania JPEG-a do złego zakresu i asynchronicznego recovery.
Eskalacja przy sprzeczności reguł celu F lub formatu. Audyt pominięty decyzją operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md`
- [D-545](../../process/decisions/DECISION_LOG_2026.md#d-545--lokalny-selektor-zdjęć-windows-dla-odbiorcy)
- [D-546](../../process/decisions/DECISION_LOG_2026.md#d-546--finalizacja-i-zgodny-kompaktowy-zapis-selektora-windows)
- [D-547](../../process/decisions/DECISION_LOG_2026.md#d-547--selektor-windows-bez-limitu-zdjęć-i-wydanie-100)
- [D-574](../../process/decisions/DECISION_LOG_2026.md#d-574--przypięty-wybór-i-optymistyczna-nawigacja-selektora)

## Scope

Maszyna intencji, adapter App, handshake main/preload, jawne błędy/timeout/retry oraz testy jednostkowe i Electron.
Pełne reguły i scenariusze: zaakceptowany plan sekcje produktu 1–10 i TASK-1104 poniżej.

## Out of scope

TASK-1105–1107, zmiany trwałego zapisu/SHA, oryginały, usługi, ochrona Windows i merge/push.

## Acceptance criteria

- [x] Każde F: jeden trwały wybór, oczekiwanie albo jawne odrzucenie; jeden operationId po retry.
- [x] Najwyżej jeden writer, jeden niewysłany cel i jeden przypięty accept; licznik/zakres dopiero po commicie.
- [x] Podgląd reaguje przed opóźnioną odpowiedzią; stale odpowiedzi nie cofają celu.
- [x] Timeout/anulowanie/decode failure i recovery zachowują właściwe imageId/range.
- [x] Close utrwala ogon, nie zwalnia locka przed zgodnym handshake; timeout nie wymusza wyjścia.
- [x] Testy zmienionego pionu, lint/typecheck/build/smoke, mapa i docs:check przechodzą.

## Technical notes

Założenie: kontrolowane opóźnienia wyłącznie w fixture/testowym procesie Electron.
Brak zmian plików operatora. Plan rozstrzyga reguły F i nawigacji; nie zmieniamy trwałego formatu.

## Expected files

Istniejące: apps/selector-desktop/src/{renderer/App.tsx,renderer/image-viewer.tsx,contracts.ts,main.ts,preload.ts,native/desktop-lifecycle.ts}; renderer-contracts i smoke-shortcuts.
Nowe: renderer/selection-intents.ts, test/selection-intents.test.mjs, scripts/smoke-fluency.mjs.
Dokumentacja: plan, wymagania/architektura, D-574, CURRENT_STATE i mapy kodu.

## Test cases

strzałka→F przed odpowiedzią, F przed decode, szybkie zmiany
  kierunku/skoku, stale odpowiedzi, przytrzymanie F, podwójne F, klik/Enter,
  uszkodzony JPEG, timeout oczekiwania, zmiana projektu i zakresu, anulowanie
  przed/po dispatch, błąd oraz utrata odpowiedzi, jeden operationId po retry,
  crash po commicie przed odpowiedzią i wznowienie w nowym procesie, zamknięcie
  z niewysłanym celem i oczekującym F. Poprzedni zaakceptowany JPEG nigdy nie
  jest ponownie wybrany dla następnego zakresu.

## Verification

Z katalogu repo, każde polecenie pod kontrolą timeout 120 s (python subprocess.run albo własny runner smoke):
`node --experimental-strip-types --test test/selection-intents.test.mjs test/renderer-contracts.test.mjs` z apps/selector-desktop;
`npm run lint --workspace @game-predictor/selector-desktop`, `npm run typecheck --workspace @game-predictor/selector-desktop`,
`npm run selector:build`, smoke fluency i shortcuts na lokalnym Electronie;
`npm run docs:check`, `npm run code-map:check`.

## Risks / open questions

Zimny JPEG nadal wymaga decode. Brak gwarancji czasu native na dysku odbiorcy. Brak blokujących pytań.

## Outcome

Commit: v1.7.496 / `b280ae39a7661fb91eef2b672763ce6e71ef7007`.

### Changed

- SelectionIntents rozdziela widoczny kursor i committed workspace, łączy niewysłane cele raz na klatkę, serializuje native oraz przypina F/Enter/click do projektu, źródła, JPEG-a, zakresu i operationId.
- Wybór czeka na commit nawigacji i decode. Timeout 10 s/anulowanie/błąd JPEG-a rozliczają wyłącznie niewysłany wybór. Kolejne F i repeat nie tworzą następnej decyzji.
- Utrata odpowiedzi wykonuje snapshot i najwyżej jedno identyczne retry. Błąd snapshot pozostaje obsłużony i blokuje mutacje. Znana odpowiedź o błędzie natywnym pozwala na dotychczasowe recovery lub bezpieczne close; nieznany wynik pozostaje zablokowany.
- Typowany handshake shutdown weryfikuje nadawcę, token i projectId. Renderer wstrzymuje wejście, kończy wysłane operacje i ostatni cel; timeout nie zamyka okna ani nie zwalnia locka. Spóźnione potwierdzenie nie kończy nowej próby.
- Stary JPEG nie jest pokazywany pod nowym celem przed decode. Native head2/journal3/ledgery, manifest v2, fsync i SHA bez zmian.

### Verification results

- `node --experimental-strip-types --test apps/selector-desktop/test/selection-intents.test.mjs apps/selector-desktop/test/renderer-contracts.test.mjs`: PASS 20/20 (14 nowych, 6 istniejących).
- Prettier zmienionych plików: PASS; lint i typecheck workspace: PASS; `npm run selector:build`: PASS. Każde polecenie z timeout 120 s.
- `node scripts/smoke-fluency.mjs --local` w apps/selector-desktop: PASS na Electron 42.11.12/Windows x64. Prawdziwe IPC z testową barierą odpowiedzi: podgląd przed odpowiedzią, przypięte F i jeden accept, anulowanie przed decode, Enter, identyczny retry po utracie odpowiedzi.
- Ten smoke zabija wyłącznie własne drzewo procesu po commicie/przed odpowiedzią, otwiera nowy proces i potwierdza trzy decyzje, zakresy 1–9/10–18/19–27, SHA trzech różnych JPEG-ów i manifest. Niewysłane F odmawia close; timeout 10 s zachowuje okno/projekt/lock, retry zamyka po utrwaleniu końcowego kursora i usuwa własny lock.
- `node scripts/smoke-shortcuts.mjs --local`: PASS (malejąca numeracja, skok20 a przesunięcie o jeden po F, krótki zakres19–20, uszkodzony JPEG, zaufany IPC oraz relink po nowym procesie).
- Runtime Electron początkowo brakował; kontrolowane pobranie zadeklarowanej zależności po eskalacji zakończyło się sukcesem. Smoke wymagał eskalacji uruchomienia procesu. Nie testowano starego asar zamiast nowego dist.
- Pierwsze smoke ujawniły wyłącznie błędy oczekiwań testu (pusty suffix bariery decode oraz zakresy po9 zamiast10); poprawione. Nie osłabiono kontraktu aplikacji.
- Mapa kodu zregenerowana; `npm run docs:check` i `npm run code-map:check`: PASS przed zamknięciem; docs ponownie sprawdzane po zamknięciu.
- Audyty Claude pominięte jawną decyzją operatora 2026-10-29 dla całego planu; nie ma niezależnego werdyktu PASS.

### Not completed

- IPC delta, cache pojedynczego DOM podglądu, pomiar p95 i finalny ZIP należą do TASK-1105–1107. Brak deklaracji PASS tych zakresów.
- Fizyczny restart Windows i komputer odbiorcy nie były sprawdzane; pozostają pending do TASK-1107/odbioru operatora.
- Bez API/Admin/Reviewer, migracji, restartów usług, danych operatora, zmian ochrony, merge i push. Dwa wcześniejsze usunięte artefakty oraz cudzy worktree nietknięte.

### Documentation updates

- Plan rev.3 accepted z zakresem/kosztem i rezygnacją z audytów; wymagania, architektura i D-574; CURRENT_STATE i mapy kodu.
- Wszystkie kryteria taska i właściwe punkty Definition of Done porównane: funkcjonalność, błędy/trwałość, kod/kontrakt desktop, UX Windows, testy i dokumentacja spełnione. Android/HTTP/API/baza nie dotyczą desktopowego taska.

### Recommended next task

- TASK-1105 — Mała aktualizacja workspace przez IPC; zaakceptowany zakres całego planu pozwala kontynuować po commicie i zapisaniu hasha.
