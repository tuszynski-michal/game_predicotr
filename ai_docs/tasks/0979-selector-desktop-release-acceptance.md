---
title: Pilotaż i odbiór wydania
status: blocked
last_updated: 2026-10-12
---

# TASK-0979 — Pilotaż i odbiór wydania

## Status

`blocked`

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
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md

## Scope

- Powtarzalny Forge ZIP, version i SHA-256, instrukcja instalacji bez instalatora i aktualizacji.
- Backup/restore projektu, source relink, logs i instrukcja niesynchronizowanego katalogu projektu.
- Pilotaż bez podpisu, sprawdzenie faktycznej drogi otrzymania paczki, ograniczenia ochrony Windows.
- Odbiór offline, restart Windows, aktualizacja EXE bez modyfikacji projektu, zdjęcia w zwykłym wyniku.
- Raport akceptacji rozdzielający kontrole agentowe od dowodów użytkownika.

## Out of scope

Podpis/certyfikat, sklep, auto-update, integracja Proton Drive, push/merge i automatyczny dostęp do komputera odbiorcy.

## Acceptance criteria

- [x] ZIP i suma kontrolna są gotowe, instrukcja pozwala rozpakować cały folder i uruchomić program.
- [ ] Czysty Windows 11 x64 bez Node/Python i bez hosta pozwala zakończyć nową partię.
- [ ] Rzeczywisty reboot i aktualizacja zachowują projekt; source relink nie resetuje decyzji.
- [ ] Wyłącznie gotowy folder wybrane jest przekazywany ręcznie, projekt nie jest synchronizowany.
- [x] Blokada Windows wstrzymuje odbiór; dokumentacja nie zaleca wyłączenia ochrony.
- [x] Outcome nie twierdzi PASS dla drugiego komputera bez dowodu operatora.

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
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/manual-image-selection-core
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run typecheck --workspace @game-predictor/manual-image-selection-core
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/reviewer
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run code-map:check
```

Powyższe skrypty istnieją w repo. W nowym worktree wymagają dostępnych
zależności oraz interpreterów; przygotowanie środowiska nie uprawnia do
restartu usług ani migracji. TASK-0975 dodał test/lint/typecheck/build/package/make aplikacji desktopowej.
Dla bieżącego taska należy zapisać sprawdzone komendy i wyniki w Outcome. Skrypty desktopu istnieją po0975; ich wynik dla bieżącego taska wymaga osobnego wykonania.
Testy Reviewera sprawdzają zgodność kontraktu; nie zastępują odbioru Electrona.
Po zmianie modułów/symboli zregenerować mapę, potem sprawdzić code-map:check.

## Risks / open questions

Drugi komputer i reboot są zależnością operatora. Nie kończ taska jako done, gdy pozostają kryteria fizycznego odbioru; zapisz gotową paczkę i blocker.

## Outcome

### Current acceptance target — 2026-10-12

Zapis raportu rundy2 i statusu odbioru: v1.7.332 /
`c7b9d52ea09b22b4a5f174d4ce8212a242a43eca`. Operator następnie uruchomił
pełną finalizację0984–0987; nowy przedmiot odbioru0.1.3 zostanie wskazany
po wykonaniu tych tasków. Fizyczny odbiór pozostaje na końcu.

Bieżący przedmiot odbioru to ZIP0.1.2:
`apps/selector-desktop/out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip`.
Source commit v1.7.329 /`c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f`;
149402003 bajtów, SHA-256
`9426704949dd8ab7d16f9d9743e2254257805a8ed1cc5dce38eecd2c37442e27`.
Pełne metadane i otwarte kryteria fizycznego odbioru są w rejestrze acceptance.
Poniższe dane0.1.0 pozostają historycznymi dowodami, nie paczką do nowego odbioru.

Brief audytu zapisano w commicie v1.7.331 /
`150359c863275ad2e427bf041a6758d049a5f768`; raport obejmuje tę rewizję
dokumentacji i kod paczki v1.7.329.
Operator przekazał niezależny raport Claude rundy2: PASS bez P0/P1;
140/140 testów i sumy finalnego ZIP-a/app.asar potwierdzone. Cztery warianty
smoke PASS za pierwszym razem; start oraz aktualizacja0.1.0→0.1.2 FAIL
za pierwszym razem, PASS po powtórce, bez wyjaśnionej przyczyny (P2-E).
Otwarte P2-A–P2-E oraz P3-A–P3-E pozostają w raporcie. Nie uznajemy ich za
naprawione ani nowych ryzyk za zaakceptowane przez operatora.
Task nadal blocked: brak fizycznego odbioru na komputerze odbiorcy.

### Changed

Część implementacyjna jest gotowa: polecenie release tworzy świeży Forge ZIP,
odrzuca stary/pusty artefakt, zapisuje streaming SHA-256, sibling .sha256 i
.release.json. Metadane zawierają wersję, bajty, sourceCommit, dirty,
applicationSourceDirty, czas oraz SHA-256 app.asar; dane buildu są też w paczce.
Smoke weryfikuje sumy i uruchamia EXE z rozpakowanego ZIP-a. Instrukcja i rejestr
odbioru oddzielają kontrole agentowe od odbioru operatora.

Commit przygotowania wydania: v1.7.321 / `60449f54d6b4cd08c041b86c294cc498b11efba4`.
Task pozostaje blocked wyłącznie na fizycznym odbiorze.

Sprawdzona historyczna paczka0979 (bez migracji0978) zachowana w
`apps/selector-desktop/out/releases/task-0979/Selektor zdjec-win32-x64-0.1.0.zip`.
Wersja0.1.0,149393535 bajtów, SHA-256
`0e21b78a2fbaa79f57a9ad6504c5a071b678f933d0e624b7bb2d09adbcc0b108`;
app.asar `f060d083ea9abea651d493dfdc8208ab2ef70d5d1b3263f635bfe3def3942964`.
Source commit `0121ce8f1bd3604977e1c60872da43a4110326d7`, dirty=true,
applicationSourceDirty=true: build nastąpił przed commitem skryptów0979.
Nie obiecujemy identycznych bajtów ZIP kolejnego buildu. Nie mylić tego
historycznego dowodu z końcową paczką poniżej.

Końcowa paczka wszystkich pięciu tasków:
`apps/selector-desktop/out/releases/pilot-0.1.0-abe8e645/Selektor zdjec-win32-x64-0.1.0.zip`.
Wersja0.1.0,149397136 bajtów, SHA-256
`2dcfe275cd7af44519c126272ad7df0e3354faed74366663ad7126480da21bea`.
app.asar SHA-256
`e2c60792e7affd24f473da939996f1ef2a511cd9c7d384fbdcef63b0526d1bab`.
Source commit `abe8e645ad9afe0444a4cf4ddd4c521b3ea7ff17` (v1.7.322),
dirty=true wyłącznie od dokumentacji, applicationSourceDirty=false.
BuiltAt2026-10-11T22:43:28.319Z, releasedAt2026-10-11T22:43:54.088Z.
Sąsiadujące .sha256/.release.json i ZIP zachowano bajtowo; sumy kopii zgodne
z artefaktami make. Release oraz pełny/source-relink/legacy smoke EXE
rozpakowanego z tego samego ZIP-a PASS, każdy krok z limitem do120 s.
Wersja0.1.0 pozostaje pierwszym nieprzekazanym pilotem. Nie jest podpisana.


### Verification results

Testy release2/2 PASS: SHA, stary/pusty ZIP, provenance i granice cleanup.
Lint/typecheck/format PASS. Release make PASS w około35 s (wewnętrzny limit110 s,
zewnętrzny120 s). Pełny smoke:release PASS (limit120 s) z ZIP: nowa partia offline,
skróty, nowy proces, odtworzenie decyzji/widoku, backup/restore, jawny relink
wyniku oraz przeniesienie folderu programu. Osobny smoke:release:shortcuts PASS
(outer120 s, test60 s): przeniesione źródło, reopen/recovery, natywny relink,
ten sam projectId, zaakceptowany JPEG i zakres10. SHA zachowanej kopii zgodne.

Pierwszy przebieg smoke timeoutował przy dynamicznym import w kontekście
main; naprawiono harness odczytem wbudowanego fs, bez zmiany runtimeUI.
Przed retry sprawdzono brak własnego EXE/orphanów i uprzątnięto własne fixture
po walidacji ścieżki. Pomocniczy test zamknięcia przed firstWindow również
nie był pełnym PASS i nie jest dowodem odbioru. Finalne dwa smoke PASS.

Mapy zregenerowane; docs:check PASS (542 decyzje/odnośniki,44 aktywne taski,
10 done), code-map:check PASS, ruff check/format generatora PASS.
Poprzednich50 testów projektu ani rdzenia/Reviewera nie powtarzano bez zmian.

Końcowy build po commicie0978: release, smoke:release,
smoke:release:shortcuts oraz smoke-legacy na EXE z tego samego ZIP-a PASS.
Legacy smoke sprawdził preview/anulowanie, token, import i nowy proces;
oryginały nietknięte. Scoped status kodu/skryptów/locków pozostał pusty.

### Not completed

Operator musi przedstawić dowody: rzeczywisty drugi komputer Windows11 x64
bez Node/Python, faktyczny kanał otrzymania ZIP-a, wynik ochrony Windows,
selekcja offline, restart Windows i aktualizacja do innej wersji programu.
Agent sprawdził relokację kopii tej samej wersji, nie fizyczną aktualizację.
Nie wykonano rzeczywistego przekazania wyników ani końcowego audytu operatora.
Wydanie jest bez podpisu; blokada ochrony wstrzymuje odbiór. Nie wyłączano jej.

### Documentation updates

Root README, ai_docs README, guide, TRACEABILITY, mapy, raport odbioru i
CURRENT_STATE opisują kod i gotową paczkę, a nie zaliczony fizyczny pilotaż.
Task pozostaje aktywny w ai_docs/tasks ze statusem blocked.

### Recommended next task

TASK-0978 jest uruchomiony: brak fizycznego odbioru0979 nie blokuje jego kodu.
Po pięciu częściach implementacyjnych audyt i fizyczny odbiór wykonuje operator.
