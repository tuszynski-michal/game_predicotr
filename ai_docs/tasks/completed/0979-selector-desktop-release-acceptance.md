---
title: Pilotaż i odbiór wydania
status: done
last_updated: 2026-10-13
---

# TASK-0979 — Pilotaż i odbiór wydania

## Status

`done`

## Goal

Dostarczyć wersjonowaną paczkę Windows i uzyskać udokumentowany odbiór pełnego przepływu u odbiorcy.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

TASK-0977 zakończony. TASK-0978 nie jest zależnością. Końcowy audyt operatora po całym zakresie. Pierwotny warunek fizycznych dowodów zamknięcia został zastąpiony jawnym zatwierdzeniem operatora 2026-10-13 (D-547); nie deklarujemy tych testów jako wykonanych.

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
- [x] Zaakceptowane decyzją operatora D-547, bez fizycznego dowodu PASS: czysty Windows 11 x64 bez Node/Python i bez hosta pozwala zakończyć nową partię.
- [x] Zaakceptowane decyzją operatora D-547, bez fizycznego dowodu PASS: rzeczywisty reboot i aktualizacja zachowują projekt; source relink nie resetuje decyzji.
- [x] Zaakceptowane decyzją operatora D-547; bez dowodu rzeczywistego przekazania: wyłącznie gotowy folder wybrane jest przekazywany ręcznie, projekt nie jest synchronizowany.
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

Operator 2026-10-13 polecił: „zmerguj zmiany do głównej gałęzi i zatwierdź odbiór -wygeneruj wersje 1. a cały worktree usuń”. Odbiór zamknięto na podstawie tej jawnej decyzji. Nie przedstawiono osobnych dowodów fizycznego drugiego komputera, rebootu Windows ani wyniku ochrony na komputerze odbiorcy; nie oznaczamy tych kontroli jako PASS. Decyzja operatora zwalnia je jako bramkę zamknięcia TASK-0979, nie zastępuje dowodów testowych. Niezależny końcowy audyt nowych zmian nie został wykonany; nie przypisujemy wydaniu 1.0.0 historycznego PASS Claude.

## Outcome

### Zamknięcie wydania 1.0.0 — 2026-10-13

Pierwsze dwa pełne smoke ZIP1.0.0 FAIL przy oczekiwaniu na scroll120/100 po wznowieniu. Bounded diagnostyka wykazała trwającą natywną animację po obsłudze okien; ustawiona testowo pozycja zmieniała się jeszcze przed zamknięciem, a aplikacja odtwarzała bieżący widok. Hipotezy CSS/fokusu i próba strażnika odtwarzania layoutu nie usunęły zjawiska; zmiany runtime wycofano. Poprawka harnessu v1.7.346 / d117adb092bb83ea9ab54393bf08d37f50b8122c czeka na 250ms bez zmiany przewijania (limit5s), następnie ustawia120/100, sprawdza trwały stan i po nowym procesie nadal wymaga dokładnie120/100. Pełny packaged oraz finalZIP smoke PASS. Nie osłabiono asercji ani nie zmieniono kodu aplikacji. Logi nieudanych prób i diagnostyka zachowane. Jest to obserwacja natywnego przewijania w automatyzacji; nie przypisujemy definitywnej przyczyny do konkretnego mechanizmu Chromium.

Wydanie **1.0.0**, kod v1.7.345 / `7808f0caab808717e9a6eda284c963df838e47f0`. Paczka zachowana poza worktree:
`D:/game_predicotr/artifacts/selector-releases/1.0.0/Selektor zdjec-win32-x64-1.0.0.zip`.
ZIP 149411351 B, SHA-256 `67311421f7b2810a0c6df519c8dc33243f2234766d94a37d59aa0fee1d069efb`;
app.asar SHA-256 `fb9e57f90e0b4922134e806322896617c6fb4f9d8e1c033d2ed009bb91c198ac`.
Obie flagi dirty=false. Metadane .release.json i suma .sha256 są obok ZIP-a.
Przygotowanie wersji: v1.7.345 / `7808f0caab808717e9a6eda284c963df838e47f0`. Scalenie poprawki głównego checkoutu: v1.7.344 / 95a05d9eafd0d9f512332635e8ff9d5fcdf2eca8.

Operator 2026-10-13 polecił: „zmerguj zmiany do głównej gałęzi i zatwierdź odbiór -wygeneruj wersje 1. a cały worktree usuń”. Odbiór zamknięto na podstawie tej jawnej decyzji. Nie przedstawiono osobnych dowodów fizycznego drugiego komputera, rebootu Windows ani wyniku ochrony na komputerze odbiorcy; nie oznaczamy tych kontroli jako PASS. Decyzja operatora zwalnia je jako bramkę zamknięcia TASK-0979, nie zastępuje dowodów testowych.

Testy release2/UI6, lint/typecheck, release i trzy kontrole końcowego ZIP-a (full/UX/start obu kierunków) PASS. Dowody i granice w quality/OFFLINE_PHOTO_SELECTOR_RELEASE_1_0_0_20261013.md. Word/screenshots pozostają osobnym zadaniem. Poprzednie sekcje Outcome opisują ówczesne blokady historycznych wydań, nie aktualny status.

### Historical acceptance target — 2026-10-12

Bieżący przedmiot odbioru po finalizacji 0984–0987 to ZIP **0.1.3**:
`apps/selector-desktop/out/releases/pilot-0.1.3-0b1ab330/Selektor zdjec-win32-x64-0.1.3.zip`.
Source commit v1.7.337 /`0b1ab3302df2119efb2519661e2f82b8bdf545df`;
149410942 B, dirty=false, applicationSourceDirty=false.
ZIP SHA-256 `cfb078b5f86a57cd781d99210ff699849485031a1ac173b6acb1861c1a145761`;
app.asar `23e0fa358455e6796fa01fd6951e695a6d6b9e9312730c86ec3382a8bad0e3a2`.
Pełne metadane i otwarte kryteria fizycznego odbioru są w rejestrze acceptance;
aktualne dowody lokalne w quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md.
Końcowy brief audytu: quality/OFFLINE_PHOTO_SELECTOR_FINAL_CLAUDE_AUDIT_BRIEF_20261012.md.
Nie wpisano PASS drugiego komputera, dystrybucji, reboot ani ochrony Windows.
Poniższe dane 0.1.0/0.1.2 są historyczne, nie paczką do nowego odbioru.

Zapis raportu rundy 2: v1.7.332 /`c7b9d52ea09b22b4a5f174d4ce8212a242a43eca`.
Ten audyt dotyczył poprzedniej paczki 0.1.2, nie finalizacji 0.1.3.

Brief audytu zapisano w commicie v1.7.331 /
`150359c863275ad2e427bf041a6758d049a5f768`; raport obejmuje tę rewizję
dokumentacji i kod paczki v1.7.329.
Operator przekazał niezależny raport Claude rundy2: PASS bez P0/P1;
140/140 testów i sumy finalnego ZIP-a/app.asar potwierdzone. Cztery warianty
smoke PASS za pierwszym razem; start oraz aktualizacja0.1.0→0.1.2 FAIL
za pierwszym razem, PASS po powtórce, bez wyjaśnionej przyczyny (P2-E).
Otwarte w tamtym raporcie P2-A–P2-E oraz P3-A–P3-E mają odpowiedzi w
finalizacji 0984–0987. Pierwotnego raportu nie zmieniano; nowe dowody
wykonawcy nie są niezależnym audytem Claude ani odbiorem operatora.
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
Agent sprawdził relokację oraz rzeczywiste różne ZIP-y na własnych kopiach;
nie jest to aktualizacja na komputerze odbiorcy ani fizyczny restart Windows.
Nie wykonano rzeczywistego przekazania wyników ani końcowego audytu operatora.
Wydanie jest bez podpisu; blokada ochrony wstrzymuje odbiór. Nie wyłączano jej.

### Documentation updates

Root README, ai_docs README, guide, TRACEABILITY, mapy, raport odbioru i
CURRENT_STATE opisują kod i gotową paczkę, a nie zaliczony fizyczny pilotaż.
Task pozostaje aktywny w ai_docs/tasks ze statusem blocked.

### Recommended next task

TASK-0978 i wszystkie rundy implementacyjne są wykonane. Operator przeprowadza
końcowy audyt paczki 0.1.3 oraz uzupełnia dowody fizycznego odbioru TASK-0979.
