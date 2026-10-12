---
title: Dowody poprawek selektora po audycie operatora
status: ready_for_review
last_updated: 2026-10-12
---

# Dowody poprawek selektora po audycie operatora

Raport wykonawcy, nie niezależny audyt. TASK-0980–0982 zakończone w kodzie
i lokalnych testach. Werdykt oryginalnego audytu pozostaje REVISE; operator
ponownie sprawdza poprawiony zakres przed przekazaniem pilotażu.

Źródło: [oryginalny raport](OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md),
SHA-256 `feeb4aafa04d9d3d6ffd0062614934fe5da4871b00da8bc72c7e16548a566158`.
Plik wejściowy pozostaje niezmieniony. Zakres i przyjęte ograniczenia opisuje
[zaakceptowany plan](../delivery/OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md).

## Odpowiedzi na ustalenia

| Ustalenie | Wykonanie | Dowód / pozostałe ograniczenie |
|---|---|---|
| P1: start PowerShell na każdym kroku | Jeden worker, świeże kontrole każdego żądania | Native 15/15; fixture 3 JPEG w dwóch przebiegach: NAV 67–88 ms, preview 7–15 ms, accept 92–133 ms; bez dodatkowych startów po rozgrzaniu |
| P1: rozmiar dziennika i receiptów NAV | Format i pełna retencja zachowane | Koszt rośnie z inwentarzem i historią; nowy protokół trwałości poza tą rundą; brak benchmarku 15 000 |
| P2: zamknięcie po LOCK_LOST | Close bez usuwania cudzej blokady | Regresje backendu i rzeczywisty EXE: wyjście, obcy lock bajtowo identyczny, log LOCK_LOST, ostatni scroll zapisany |
| P2: brak seq JPEG | Nowe decyzje blokowane, instrukcja odtworzenia zgodnej kopii | Missing→skip/accept→reopen→zła/dobra kopia→resume PASS; brak automatycznego repair |
| P2: pominięty zakres | Skipped nie blokuje późniejszej akceptacji | Projekt48/48: powrót do skipped, konflikt accepted i ponowny source nadal chronione |
| P2: podwójny scan open i SHA | Jeden zweryfikowany scan źródła; wszystkie SHA pozostają | Test pojedynczego scan PASS; duży wynik nadal kosztowny przy open, UI pokazuje weryfikację |
| P3: recovery guard | Fail-closed z diagnostyką | Pusta blokada nie dowodzi właściciela; bez automatycznego przejęcia |
| P3: scroll | Debounce 250 ms, wspólny pending Promise i flush | UI 4/4 i ZIP UX: burst 50 daje jeden zapis końcowy; accept, close i nowy proces zachowują właściwy widok |
| P3: nośnik wymienny | Kod REMOVABLE_STORAGE i właściwy komunikat | Brak rozszerzenia pilotażu do USB; reguły lokalnego storage zachowane |
| P3: pickSource | Martwy kanał usunięty | Kontrakt i ZIP UX PASS; anulowanie pickera projektu nie resetuje pracy |
| P3: komunikat po NAV | Oddzielny komunikat nawigacji | ZIP UX PASS; trwałe potwierdzenie wyboru tylko po accept |
| P3: commit bez TASK ID | Nowe commity mają numery0980–0982 | Stara historia bez zmian |
| Pozostałe: esbuild, retry UI, desktop.ini/Thumbs.db | Bez przebudowy zależności; instrukcja doprecyzowana | Idempotencja dotyczy tego samego operationId; obce pliki nadal blokują wynik |

## Testy tej rundy

130 unikalnych testów PASS: native 15, projekt 48, legacy 25, recovery 26,
przerwania prawdziwego procesu3, foundation 7, UI 4 i release 2. Grupy miały
rzeczywisty timeout najwyżej120s. Lint całego desktopu, typecheck, format,
package/release, docs:check/code-map:check i whitespace Git PASS.
Starsze rdzeń110 i Reviewer264 nie były ponawiane bez zmiany modułów.
Poprzednie109/109 z audytu dotyczą paczki0.1.0.

Finalny ZIP 0.1.1: full smoke, shortcuts/source-relink, legacy i UX/LOCK_LOST
PASS. Każdy wariant ponownie weryfikuje ZIP i rozpakowany app.asar przed
uruchomieniem własnej kopii EXE. Test aktualizacji rzeczywistych ZIP-ów
0.1.0→0.1.1 PASS: zachowane projectId, decyzje, currentRelativePath i SHA
seq_1-9.jpg; nowy seq_19-27.jpg przetrwał proces. Jawne przepięcie kopii
wyniku, a oryginalne fixture SHA/size/mtime pozostają identyczne.
Brak własnych osieroconych procesów.

Dwa pierwsze błędy harnessów odnotowane w Outcome: UX zakładał całkowity
scroll zamiast rzeczywistej wartości DOM przy skali Windows; update
porównywał opaque UUID między procesami. Poprawiono testy na dokładne
współrzędne oraz ordinal/relativePath/zapisany kursor. Finalne przebiegi PASS.
Nie zmieniono dla nich runtime. Poprawka update po326 znajduje się w327;
ZIP pozostaje niezmieniony z326, applicationSourceDirty=false w chwili builda.

Logi ignorowane przez Git: apps/selector-desktop/.tmp/0981-*.log oraz
0982-*.log, finalne0981-smoke-ux-final.log i0982-smoke-update-final.log.
Pełne komendy i kryteria: Outcome ukończonych tasków0980,0981,0982.
Pomiar trzech JPEG-ów potwierdza usunięcie narzutu startu procesu;
nie gwarantuje stałego czasu dla dowolnego rozmiaru zdjęć, źródła lub historii.

## Commity i paczka

| Zakres | Commit |
|---|---|
| TASK-0980 backend | v1.7.324 / a5ae96049de1fb48a216d7ebaaf895a24cc1e6e1 |
| TASK-0981 UI | v1.7.325 / 892c34f1f99bd54b0d8394919a389682a3d8891e |
| TASK-0982 źródła wydania | v1.7.326 / ede94bdcb3ad1cac5838f524b604423bec81b69f |

Finalna paczka i pełne metadata są w [rejestrze odbioru](OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md):
`apps/selector-desktop/out/releases/pilot-0.1.1-ede94bdc/Selektor zdjec-win32-x64-0.1.1.zip`,
149400221 bajtów, SHA-256
`fa1891d20f0348de2e89e4a66d5b4e849744ba148ae961c29e5997072512b023`.
app.asar SHA-256
`9c3d0c6bb46ac262106c1cf1e8c5181971045ee4ebafdf0d0bfcb957bd17adc8`.
dirty=false, applicationSourceDirty=false. Obok są .sha256 i .release.json.
Oba stare ZIP-y zachowały pierwotne sumy. Artefakty nie należą do commita Git.

## Otwarte granice odbioru

Ponowna ocena P1 i innych poprawek należy do operatora. Nie uruchamiano
samodzielnego CLI audytu i nie zastępowano Claude rodziną Codex.
Nie wykonano fizycznego odbioru TASK-0979: drugi komputer, rzeczywista
dystrybucja, restart Windows i uruchomienie bez narzędzi deweloperskich.
Niepodpisany pilot; blokada Windows wstrzymuje odbiór.
Pozostają pełne SHA przy open, rosnący stan/receipts, nieznany recovery guard,
brak USB i automatycznego odtworzenia JPEG-a. Brak uploadu/linków/synchronizacji,
zmian usług/API/Admin/Reviewera/bazy, danych operatora, push, merge i benchmarku.
