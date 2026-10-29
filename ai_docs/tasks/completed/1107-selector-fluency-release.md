---
title: Dowody płynności, diagnostyka i sprawdzona paczka
status: done
last_updated: 2026-10-29
---

# TASK-1107 — Dowody płynności, diagnostyka i sprawdzona paczka

## Status

`done`

## Goal

Udokumentować płynność i brak zgubionych wyborów w rzeczywistym Electronie oraz dostarczyć sprawdzony ZIP Windows 1.0.4.

## Dependencies / entry conditions

TASK-1104–1106 done; HEAD b17e0e2e, v1.7.501. Operator zatwierdził cały plan, koszt 3–5 h, testy i ZIP, bez merge/push. Audyty Claude pominięte decyzją operatora. Historia wydań i package.json kończą się na 1.0.3.

## Recommended execution

`gpt-6.1-sol`, `medium`; odbiór, diagnostyka i istniejący proces wydania. Przekroczenie celu p95 wymaga analizy śladu i decyzji operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md`
- `ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`
- `ai_docs/quality/SELECTOR_OUTPUT_FOLDER_1_0_3_20261023.md`
- `ai_docs/tasks/completed/1105-selector-workspace-updates.md` — znany baseline native-checks.
- `ai_docs/tasks/completed/1106-selector-preview-cache.md` — metody smoke/race.

## Scope

Ograniczone agregaty diagnostyczne bez danych zdjęć; minimum 30 nawigacji i 10 wyborów na małej partii kopii istniejących JPEG. Czasy wejście–paint/decode/IPC/native/confirmation, żądania i payload. Flaga release smoke --fluency, aktualizacja operatora, komplet testów selektora w grupach i wydanie Windows z SHA/metadata/asar.

## Out of scope

Usługi, zmiany oryginałów, formatów trwałych i ochrony Windows, naprawa workerów native, merge/push. Dwa wcześniejsze usunięcia artefaktów i obcy worktree pozostają poza commitem.

## Acceptance criteria

- [x] Bounded agregaty; brak logu na każdy klawisz, ścieżek i wpływu diagnostyki na operację.
- [x] Minimum 30 nawigacji i 10 wyborów, pełne próbki i kontekst maszyny; lokalny warm p95 ≤50 ms.
- [x] Cache hit przed odpowiedzią IPC opóźnioną o 500 ms; zero zgubionych F i błędnych imageId/range.
- [x] Nowy proces potwierdza JPEG/SHA/manifest/liczniki; crash, recovery, obie numeracje, skoki i granica 500000.
- [x] Pełny zestaw selektora w grupach ≤120 s concurrency=1, lint/typecheck/build i finalny rozpakowany ZIP ze smoke.
- [x] ZIP, SHA i release metadata zachowane w artifacts/selector-releases/1.0.4; stare wydania zachowane.
- [x] Dokumentacja i DoD rozliczone; fizyczny reboot i odbiór na komputerze odbiorcy pending.

## Technical notes

Bezpieczne założenie: lokalne kopie niewielkiej partii istniejących JPEG są wyłącznie fixture odbiorczym, nie pomiarem sprzętu odbiorcy. Zimny cache aplikacji nie oznacza zimnego cache systemu operacyjnego. Agregacja ma stałe limity; zapis po serii/na żądanie lub close, bez fsync na klawisz. Brak pytań blokujących przed pomiarem. Trzy timeouty native-checks były potwierdzone na poprzednim HEAD; nie zmieniamy kryteriów testów.

## Expected files

Rozszerzenie konieczne po odbiorze workflow: `SelectionIntents.apply` zachowuje gotowość tej samej bitmapy po range/undo tylko przy zgodnym project/source/image i braku decode error. Nowy cel nadal wymaga decode. Rodzic potwierdził poprawkę w zakresie odbioru. Pierwszy kandydat ZIP z b4251886 zachowany osobno; nie jest wydaniem finalnym.

Istniejące: native/diagnostic-log.ts, src/main.ts, scripts/smoke-fluency.mjs, scripts/smoke-release.mjs, package.json i package-lock.json, instrukcja operatora, mapa i stan. Proponowane: ograniczony moduł agregatów/test, skrypt odbiorczego pomiaru i raport jakości.

## Test cases

Plan TASK-1107: warm/cold, opóźnienie500 ms, 30/10, finalny ZIP, strzałki/F/Enter, kierunki i skoki1/20, granica500000, zły JPEG, konflikt, utrata odpowiedzi, nowy proces i upgrade1.0.3.

## Verification

Każde polecenie przez scripts/run-bounded.mjs; testy concurrency=1, grupy ≤120 s. Lint/typecheck/build ≤120 s, make ≤300 s po uprzedzeniu, każdy smoke ZIP ≤120 s. Wyniki dopisywane po wykonaniu.

## Risks / open questions

Brak fizycznego reboot Windows i dostępu do komputera odbiorcy. Nie ma gwarancji wydajności innego dysku/ochrony/CPU.

## Outcome

Commit: v1.7.504 (hash dopisuje kolejny commit).

### Changed

- Agregaty diagnostyczne: trzy stałe metryki, ostatnie 256 próbek na metrykę i liczność serii. Zapis przy close/openLogs, whitelista liczb, bez ścieżek/ID zdjęć, bez per-key append/fsync. Błąd zapisu agregatu nie zmienia wyniku operacji.
- Odbiorczy harness mierzy wejście–paint, cold decode, confirmation, rzeczywisty snapshot IPC, native execute, żądania i JSON. Używa 12 kopii czterech istniejących JPEG 720×1280, nie zmienia oryginałów. Zachowuje wszystkie próbki i nieudane próby.
- Finalny ZIP smoke ma jawne flagi --fluency i --measurement. Wersja aplikacji 1.0.4, z historii wydań kończącej się na 1.0.3. Make ma uzgodniony limit 280 s w wrapperze wydania, cały release 300 s.
- Workflow wykrył regresję: range/undo na tym samym obrazie zerowało gotowość bez kolejnego decode. SelectionIntents zachowuje ready wyłącznie przy tym samym project/source/image i bez decode error; zmiana celu nadal czeka na właściwy callback. Testy range→F/undo→F i innego celu dodane.
- Checkpointy kodu: v1.7.502 / b4251886095bda7c1d9cec783942414e19ea9dd5; poprawiony runtime v1.7.503 / 6681d53456cfd27d83b0ac56fe50d00638003f43. Zadanie pozostawało in_progress do finalnych smoke. Pierwszy kandydat zachowany osobno, nie jest paczką do przekazania.

### Verification results

- Pełne pięć grup z --test-concurrency=1, każda z limitem 120 s: UI/foundation 52/52 (12,3 s), native 21/21 (5,1 s), project/start 72/72 (45,0 s), archive/compact 97/97 (93,4 s), legacy/diagnostics 64/64 (17,0 s). Razem 306/306. Nowy dodatkowy test whitelisty: celowane agregaty 2/2. Trzy znane testy timeoutów 150/200 ms tym razem PASS bez zmian; wcześniejszy baseline nie jest deklarowany jako naprawiony.
- Po naprawie gotowości: intents/cache/renderer/workspace 37/37 PASS, w tym range→F, undo→F, inny target i blokowanie obcego kontekstu. Łącznie 309 unikalnych testów; całych grup nie powtarzano bez potrzeby. Dodatkowy krótki runner 2/2 został omyłkowo uruchomiony podczas oczekiwania na persistence; pełne grupy nie nakładały się. Odstępstwo jawnie zapisane w raporcie.
- Formatowanie, lint i typecheck PASS. Build/make/verifier PASS w nowym procesie; finalny release ok. 24 s, limit 300 s. Mapa regenerowana, docs/mapa sprawdzane przy zamknięciu.
- Finalny rozpakowany ZIP: workflow, fluency, measurement, shortcuts oraz pełny release smoke PASS. Weryfikacja SHA, metadata i app.asar/ścisłej zawartości przed każdym wariantem. Crash przed odpowiedzią, ponowienie identycznego operationId, błędny JPEG, konflikty, zamykanie i recovery zachowują dane. Zoom/scroll/fullscreen, obie numeracje, skoki 1/20 i granica 500000 PASS.
- Rzeczywista aktualizacja ZIP 1.0.3→1.0.4 PASS: kopia projektu, kursor, decyzje/JPEG/SHA, jawny relink wyniku i kolejne decyzje po nowym procesie; oryginalne fixture i historyczna paczka bez zmian.
- Finalne pomiary: warm 30, mediana 22,1 ms / p95 25,5 ms / max 27,7 ms; cold 4, p95 40,5 ms; cold decode 4, p95 31,4 ms; confirmation 10, p95 216,6 ms; snapshot IPC 30, p95 1,0 ms; native 46, p95 213,5 ms; JSON koperty p95 904 B / max 984 B. Warm p95 ≤50 ms PASS. Rendering opportunity jest konserwatywnym proxy paint, nie pomiarem fotonów monitora.
- Cache hit przed odpowiedzią opóźnioną o 500 ms PASS. Dziesięć osobnych F/Enter: 10/10 poprawnych JPEG/range, manifest i licznik po nowym procesie. Zero nowych żądań aktywnych cache hitów; 15 żądań prefetch granicy okna jawnie odrębne.
- Finalny ZIP `artifacts/selector-releases/1.0.4/Selektor zdjec-win32-x64-1.0.4.zip`: 149420406 B, SHA-256 `7e2d3f32515a72e6eb55b92bbdd9a4dc405bbe337b4e67ebf3381bd902b2c1b6`. app.asar `71c7916a82abea15e9f85d4f020b3223c38f0c143dcb81c6aff66c8da57eae6c`. Obok suma i metadata; applicationSourceDirty=false, globalne dirty=true z cudzych zmian poza aplikacją. Runtime z 6681d534. Stary kandydat i ZIP 1.0.3 zachowane.
- Dowody: `ai_docs/quality/SELECTOR_FLUENCY_1_0_4_20261029.md`, `artifacts/selector-fluency-20261029/measurement-final2-zip.json` i logi w tym katalogu. Nieudane próby harnessów zachowane: dynamic import w evaluate, synchronizacja bootstrapu, opaque ID między procesami, oczekiwanie starego skip i kontrola SelectionIntents zamiast main aria-busy. Asercji danych nie osłabiano.

### Not completed

- Audyt Claude pominięty decyzją operatora; bez niezależnego werdyktu PASS.
- Fizyczny restart Windows i odbiór na komputerze zgłaszającego pending. Wynik małej partii na opisanym Ryzen/NVMe/Defender nie prognozuje innego sprzętu ani dużego zbioru. Nie nagrywano ETL i nie zmieniano ochrony.
- Bez API/Admin/usług, oryginałów, migracji, merge/push lub dystrybucji. Cudze dwa usunięcia i obcy worktree zachowane poza commitami.

### Documentation updates

Instrukcja operatora 1.0.4 i opcjonalny Defender recording z lokalnie sprawdzonym -Seconds, architektura agregatów/gotowości, raport jakości, plan, mapa i CURRENT_STATE. Brak nowej decyzji produktowej, kontraktu HTTP lub migracji.

### Definition of Done / plan

| Obszar | Rozliczenie |
|---|---|
| Funkcjonalność | Wszystkie siedem kryteriów taska spełnione; F, range/undo, race, crash/recovery i close sprawdzone. Wartości sekwencji zachowują domenę. |
| Kod | Ograniczone agregaty, jeden runtime preview, brak obejść sesyjnych; nowy proces i finalny ZIP sprawdzone. Regresja naprawiona u przyczyny. |
| Dane | Format/SHA/lease/fsync bez osłabienia, wyłącznie kopie fixture; schemat bazy i migracje N/A. |
| Kontrakt | Bez HTTP/OpenAPI; typowany IPC i fallback sprawdzone. Nie zmieniono formatu projektu. |
| Testy/narzędzia | Pełne grupy oraz świeży zmieniony pion, format/lint/typecheck/build, finalne smoke i SHA/asar; komendy ograniczone czasowo. Odstępstwo dodatkowego runnera jawne. |
| UX | Istniejące stany oczekiwania/błędu, repeat i duplikaty sprawdzone; dotyk/Android N/A dla aplikacji Windows. |
| Dokumentacja | Outcome, raport, instrukcja, plan, mapa i okno procesu aktualizowane; zamknięcie skryptem task-close. |
| Raport/odbiór | Artefakt, wyniki i ryzyka podane. Reboot/odbiorca pending; audyt pominięty, merge/push bez zgody nie wykonane. |

### Recommended next task

Odbiór operatora i fizycznego komputera odbiorcy. Scalenie/push dopiero po osobnej wyraźnej zgodzie na wynik i integrację.
