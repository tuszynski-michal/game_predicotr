---
title: Lokalny selektor Windows — pełny audyt ponowny (Claude), runda 2
status: review
last_updated: 2026-10-12
---

# Audyt pełnego selektora Windows (TASK-0975–0983, ZIP 0.1.2) — Claude, runda 2

Werdykt: PASS
Audytor: Claude Fable 5.1 (`claude-fable-5-1`), sesja Claude Code, domyślny poziom rozumowania
Wykonawca: Codex (`gpt-6.1-sol`, poziomy medium/high według tabel modeli planów)
Zakres: `bb883b5902cb0934b9732d1bc24361d01085051d` (v1.7.316) … `150359c8` (v1.7.331, HEAD); kod paczki `c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f` (v1.7.329); data 2026-10-12
Runda: 2 (odpowiedź na raport REVISE `OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md`)

Przegląd kodu bez zmian w źródłach; dodatkowo wykonano wskazane kontrole na
odizolowanych fixture'ach. Audytor nie zmienił żadnego pliku źródłowego, testu,
zależności, taska, wcześniejszego raportu ani paczki. Jedynym plikiem wynikowym
jest ten raport; logi pomocnicze i sondy leżą poza repozytorium (katalog
scratch sesji), a fixture'y sond powstały w ignorowanym `apps/selector-desktop/.tmp/`
i zostały usunięte po zakończeniu.

## Streszczenie

Zbadano całą implementację `apps/selector-desktop` od v1.7.316 do v1.7.331:
granicę renderer/native, trwałość projektu, blokady, worker kontroli Windows,
start od folderu zdjęć, historię, przejęcie starych sesji, skrypty wydania i
finalną paczkę 0.1.2. Kod jest bezpiecznie odgrodzony, trwałość i własność
plików są udowodnione testami oraz własnymi sondami, a wszystkie ustalenia
P1/P2 poprzedniego raportu mają poprawki albo jawnie przyjętą granicę zakresu.
Główne pozostałe ryzyka to wygoda startu po usunięciu zapisanego projektu
(stary wpis historii blokuje źródło bez czytelnego komunikatu), liniowy wzrost
kosztu każdej operacji z wielkością inwentarza (przy 15 000 zdjęć ekstrapolacja
daje około 1 s na klawisz) oraz brak blokady auto-repeat dla Enter/Tab/Ctrl+Z.
Żadne ustalenie nie dotyczy utraty, nadpisania ani ujawnienia danych
użytkownika. PASS oznacza brak otwartych P0/P1; nie zastępuje fizycznego
odbioru TASK-0979 na komputerze odbiorcy.

## Tożsamość sprawdzonej rewizji i paczki

- Worktree `D:\game_predicotr\worktrees\offline-photo-selector`, gałąź
  `codex/offline-photo-selector`, `git status` czysty przed i po audycie.
- Historia v1.7.317–v1.7.331 ciągła od v1.7.316 (`bb883b59`); commity
  v1.7.324–v1.7.330 zawierają identyfikatory TASK-0980–0983.
- Różnica `21d8c023` (v1.7.330) → `150359c8` (v1.7.331, HEAD): wyłącznie
  dokumentacja (`ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/quality/OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_HANDOFF.md`, nowy
  brief). Kod jest identyczny z paczką: rewizja kodu = `c4181f7d` (v1.7.329);
  v1.7.330 i v1.7.331 to dokumentacja.
- Finalny ZIP `apps/selector-desktop/out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip`:
  149 402 003 B, SHA-256 `9426704949dd8ab7d16f9d9743e2254257805a8ed1cc5dce38eecd2c37442e27`
  (własny `Get-FileHash`), identyczny z kopią w `out/make/zip/win32/x64` i z
  `.sha256`/`.release.json`.
- `resources\app.asar` wyjęty własnym skryptem z ZIP-a: 348 833 B, SHA-256
  `0e2c2bf2894bd519ceea96e957e564dbe02f54d0963f3d381085396815c323c0`, zgodny z
  `.release.json`. Zawartość: 7 wpisów (`dist/build-info.json`, `dist/main.cjs`,
  `dist/preload.cjs`, `dist/renderer/app.css`, `dist/renderer/app.js`,
  `dist/renderer/index.html`, `package.json`). Brak `src/`, `node_modules`,
  plików `.ts` i `packages/`. `build-info.json`: `sourceCommit c4181f7d…`,
  `dirty=false`, `applicationSourceDirty=false`, `builtAt 2026-10-12T12:13:30.073Z`.
  `main.cjs` nie zawiera literałów `http(s)://`; `require` obejmuje tylko
  `electron` i moduły `node:`.
- ZIP ma 75 wpisów; żaden nie pasuje do `node_modules|\.ts$|/src/|packages/`.
- Historyczny ZIP aktualizacji `pilot-0.1.0-abe8e645` ma SHA-256
  `2dcfe275cd7af44519c126272ad7df0e3354faed74366663ad7126480da21bea` (zgodny
  z briefem). ZIP `pilot-0.1.2-9ade6a85` pozostaje historyczny i nie był używany.
- Root: `package.json` dodaje `allowScripts.esbuild@0.25.12` i skrypty
  `selector:*`; lockfile dodaje jeden `hasInstallScript` (esbuild 0.25.12).
  Brak `.npmrc`, `ELECTRON_MIRROR` i `ignore-scripts`. Electron jest pobierany
  przez Forge przy pakowaniu (`@electron/get`), nie przez skrypt instalacyjny.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-A] `apps/selector-desktop/src/native/project-controller.ts:363-385`,
  `apps/selector-desktop/src/project/recent-projects.ts:51-65`,
  `apps/selector-desktop/src/filesystem/secure-files.ts:115-120` — po usunięciu
  przez użytkownika folderów `<źródło> selekcja` i `<źródło> wybrane` stary
  wpis historii (`sourceRoot` zgodny) nadal jest jedynym kandydatem w `begin()`.
  `ProjectStore.open` → `ProjectLock.acquire` → `verifyRoot` → `lstat` rzuca
  surowy `ENOENT` (nie `SelectorError`), który `main.ts:233-246` mapuje na
  `IO_ERROR` „Operacja lokalna nie powiodła się. Sprawdź dostęp do katalogu i
  logi.”. Potwierdzone sondą A: `begin-after-delete → ENOENT`, po odtworzeniu
  pustego folderu `PROJECT_NOT_FOUND`; wpis cache pozostaje (`list()` nigdy nie
  usuwa wpisów, `remember()` filtruje tylko po `projectId`). Skutek: dla tego
  źródła nie da się już rozpocząć nowej partii z interfejsu (`create` wymaga
  `sourceToken` z `begin()`, a `customLocations` jest odrzucane przy tokenie,
  `project-controller.ts:78-86`); instrukcja (`OFFLINE_PHOTO_SELECTOR_OPERATOR.md:96-98`)
  odsyła do historii lub `Otwórz projekt`, które tu nie pomagają. Jedyne
  obejścia to zmiana nazwy folderu źródła albo ręczne usunięcie
  `selector-recent-projects-v1.json` z userData — oba nieopisane. Ten sam
  mechanizm (sonda G) sprawia, że przy dwóch wpisach cache dla tego samego
  `projectRoot` zwycięża starszy (`candidates.set` nadpisuje po tym samym
  kluczu w kolejności listy), więc nawet po ręcznym `Otwórz projekt` kolejny
  `begin()` nadal daje `SOURCE_PROJECT_CONFLICT`. Zasada „brak folderu nigdy
  nie resetuje” jest zachowana; problem dotyczy wyłącznie diagnostyki i braku
  drogi wyjścia. Proponowana poprawka: w `begin()` opakować brak folderu
  kandydata w `SelectorError` (np. `PROJECT_FOLDER_MISSING` z pełną ścieżką),
  pomijać/usuwać wpisy historii, których `projectRoot` nie istnieje (po jawnym
  komunikacie, bez automatycznego tworzenia nowego projektu), w `remember()`
  usuwać wcześniejsze wpisy o tym samym `projectRoot`, a w instrukcji opisać,
  jak rozpocząć nową partię po celowym usunięciu projektu.
- [P2-B] `apps/selector-desktop/src/project/project-store.ts:838-849`, `:681-721`,
  `:1021`, `apps/selector-desktop/src/project/types.ts:96-107` — koszt każdej
  operacji (także strzałki) rośnie liniowo z inwentarzem i historią: dziennik
  zawiera `before` i `after` z pełnym inwentarzem, jest zapisywany trzy razy z
  `fsync`, a stan i kopia zapasowa są zapisywane w całości; `receipts` rosną
  bez ograniczenia (sonda I: 12 operacji → 12 receiptów). Własny pomiar
  (fixture 2 KB/plik, dysk D:, ciepły worker) daje navigate 0,11–0,13 s przy
  300 plikach i 0,25–0,33 s przy 3000, accept 0,15–0,18 s → 0,29–0,34 s; wzrost
  jest liniowy (~95 ms + ~0,058 ms/plik), więc dla deklarowanej granicy
  15 000 JPEG ekstrapolacja daje około 1 s na strzałkę i 1,0–1,1 s na akceptację
  (bez uwzględnienia rosnących receiptów). To nie jest pomiar 15 000 (brief go
  wyklucza). D-545 (runda poprawek) i instrukcja (`OFFLINE_PHOTO_SELECTOR_OPERATOR.md:207-210`)
  jawnie zachowują format; granica jest więc przyjęta, ale dla partii bliskich
  15 000 zdjęć cel użytkowy P1-1 nadal nie jest w pełni osiągnięty. Proponowane
  działania do decyzji operatora: (a) wpisać w instrukcji orientacyjną wielkość
  partii, przy której praca jest płynna (np. do kilku tysięcy zdjęć, z
  podaniem pomiaru), albo (b) w kolejnej rundzie odchudzić dziennik (zapis
  `before` tylko jako identyfikator rewizji, inwentarz raz) i ograniczyć
  retencję receiptów do decyzji, z zachowaniem recovery.
- [P2-C] `apps/selector-desktop/src/renderer/App.tsx:166-202`,
  `packages/manual-image-selection-core/src/index.ts:211-258` — rdzeń ignoruje
  `repeat` tylko dla `f` i `a`; `Enter`, `Tab` i `Ctrl+Z` są mapowane bez tej
  kontroli, a `run()` (`App.tsx:53-71`) odrzuca zdarzenia tylko w trakcie
  trwającej transakcji. Przytrzymany Enter wykonuje więc kolejną akceptację po
  każdym zakończonym zapisie (0,15–0,35 s), przytrzymany Tab pomija kolejne
  zakresy, a przytrzymany Ctrl+Z cofa kolejne decyzje i usuwa własne pliki
  wynikowe. Nie dubluje to tej samej decyzji (strażnicy `STALE_CURSOR`,
  `IMAGE_ALREADY_ACCEPTED`), lecz tworzy niezamierzone kolejne decyzje. Smoke
  sprawdza wyłącznie `f` z `repeat: true` (`scripts/smoke-packaged.mjs:161-167`).
  Reviewer używa tej samej funkcji rdzenia, więc jest to parytet, nie regres;
  mimo to na desktopie, gdzie decyzja usuwa/kopiuje pliki, proponuję w
  handlerze `App.tsx:175-183` ignorować `event.repeat` dla akcji `accept`,
  `skip` i `undo` (bez zmiany rdzenia i Reviewera) oraz dodać test.
- [P2-D] `apps/selector-desktop/src/project/project-store.ts:235-245`, `:342-348`,
  `:375-378`, `apps/selector-desktop/src/native/project-controller.ts:355-362` —
  komunikaty fail-closed startu są poprawne w skutku, ale mylące: obcy folder
  `<źródło> selekcja` z cudzymi plikami daje `PROJECT_NOT_FOUND` „Nie znaleziono
  projektu.” (sonda B; folder istnieje, a `ProjectStore.open` tworzy w nim i
  usuwa plik `selector-project.lock`, czyli pisze w nieswoim katalogu);
  niezgodny `projectId` tego samego źródła daje `SOURCE_PROJECT_CONFLICT`
  „Znaleziony projekt należy do innego źródła.” (sonda G); obcy folder
  `<źródło> wybrane` daje `FOREIGN_CONTENT` „Nowy projekt wymaga pustego
  katalogu projektu i wyniku.” bez wskazania, który z dwóch folderów jest
  zajęty, a pusty `<źródło> selekcja` został już utworzony i pozostaje (sonda C).
  Użytkownik wybierający tylko folder zdjęć nie wie, co usunąć ani przenieść.
  Proponowana poprawka: osobne kody/komunikaty z pełną ścieżką (np.
  `PROJECT_FOLDER_FOREIGN`, `OUTPUT_FOLDER_NOT_EMPTY`), sprawdzenie obu
  folderów przed `ensureDirectory` oraz brak tworzenia pliku blokady, dopóki
  katalog nie zawiera `selector-project-v1.json`/`.backup`/dziennika.
- [P2-E] `apps/selector-desktop/scripts/smoke-start.mjs:132-135`,
  `apps/selector-desktop/scripts/smoke-update.mjs:82-90`, `:203-209` — dowody
  smoke wykonawcy odtwarzają się, ale nie są odporne: w pierwszym przebiegu
  audytu `smoke:release:start` zakończył się błędem
  `page.waitForFunction: Target page, context or browser has been closed` przy
  pierwszym ponownym uruchomieniu EXE, a `smoke-update` błędem
  `Update state did not settle` (20 s) po kliknięciu „Następne” w paczce 0.1.0;
  powtórka obu na bezczynnej maszynie dała PASS. Przyczyny nie ustalono, bo
  harness sprząta `user-data` razem z logami. Przypuszczenie (nie dowód): zimny
  start PowerShell/WMI przy pierwszym `Get-CimInstance Win32_Process` na tej
  maszynie; w paczce 0.1.2 ta sama kontrola ma limit 10 s
  (`apps/selector-desktop/src/native/windows-check-worker.ts:150-153`), po którym
  pierwsze otwarcie projektu u odbiorcy kończy się `LOCK_OWNER_UNKNOWN`
  „Nie można potwierdzić tożsamości procesu.”. Proponowana poprawka: przy
  błędzie smoke zachowywać `user-data/logs/selector.log`, a dla
  `processIdentity` dodać jedno ponowienie lub dłuższy limit z zapisem czasu
  w logu. Do czasu wyjaśnienia traktować sześć PASS wykonawcy jako
  odtwarzalne, lecz wrażliwe na stan maszyny.

### P3 (mniejsze, do odnotowania)

- [P3-A] `apps/selector-desktop/src/project/project-store.ts:1110-1124` —
  `close()` toleruje tylko `LOCK_LOST`; plik blokady nadpisany obcą treścią
  (`parseOwner` → `LOCK_OWNER_UNKNOWN`, `project-lock.ts:41-67`) sprawia, że
  „Zamknij projekt” powtarzalnie kończy się błędem, a store pozostaje otwarty
  (sonda F). Zamknięcie okna działa, bo `main.ts:92-105` loguje błąd i zamyka
  mimo to. Propozycja: traktować `LOCK_OWNER_UNKNOWN` jak `LOCK_LOST` (bez
  `unlink`, z diagnostyką).
- [P3-B] `apps/selector-desktop/src/main.ts:115-120` — drugie uruchomienie EXE
  w trakcie zamykania pierwszego (flush widoku, zwolnienie blokady,
  zatrzymanie workera do 2 s) kończy się cichym `app.quit()`; handler
  `second-instance` nie ma już okna do pokazania. Użytkownik widzi tylko brak
  reakcji na dwuklik. Propozycja: krótki komunikat albo ponowienie po
  zakończeniu poprzedniego procesu.
- [P3-C] Dokumentacja nieaktualna względem stanu: wiersz indeksu D-545
  (`ai_docs/process/DECISION_LOG.md:37`) nadal mówi „0978 odroczony”, choć
  pełny wpis i taski potwierdzają wykonanie; `ai_docs/tasks/0979-selector-desktop-release-acceptance.md`
  (`last_updated 2026-10-11`, linie 64, 127-148) wskazuje paczkę 0.1.0 jako
  przedmiot odbioru, gdy rejestr i instrukcja wskazują 0.1.2; plan
  `OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md` nie odnotowuje rund 0980–0983.
- [P3-D] `ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md:151-164` — instrukcja
  dla `OUTPUT_MISSING_FILE` każe szukać „kopii zapasowej” pliku `seq_*`, a nie
  mówi, że bajtowo identyczna kopia zawsze istnieje w źródle pod ścieżką
  `decisions[].imagePath` z manifestu (program i tak sprawdza SHA-256 przy
  wznowieniu). Nie jest to automatyczny repair (poza zakresem), tylko
  brakujące zdanie w procedurze.
- [P3-E] `apps/selector-desktop/test/release.test.mjs` sprawdza wyłącznie
  funkcje pomocnicze (`hashFile`, `requireFreshArchive`, `gitBuildInfo`); nie ma
  automatycznego testu zawartości `app.asar` (brak `src/`, `node_modules`) ani
  spójności `build-info.json` z `.release.json`. Ten audyt sprawdził to ręcznie.

## Pokrycie kryteriów audytu

| Obszar / kryterium | Status | Dowód |
|---|---|---|
| Start: tylko folder zdjęć, foldery `… selekcja` i `… wybrane` obok źródła, pełne ścieżki w formularzu | spełnione | `project-controller.ts:339-395`, `App.tsx:340-446`; `start-resume.test.mjs:156`; smoke start PASS (powtórka); sonda H |
| Nazwa gry jako etykieta (nie ścieżka, nie gameId), walidacja 1–80 znaków | spełnione | `contracts.ts:106-118`, `state-codec.ts:73-78`, `project-controller.ts:133-141`; `start-resume.test.mjs:156,258` |
| Ponowny wybór źródła wznawia projekt bez konfiguracji, w obu kierunkach, po nowym procesie | spełnione | `start-resume.test.mjs:156` (ascending/descending), smoke start PASS; sonda timing `reopenBeginMs` |
| Wznowienie bez cache, stary projekt bez gameName, otwarcie ręczne, relink + restart | spełnione | `start-resume.test.mjs:156,233,375`; smoke shortcuts/start (relink) PASS; `project-controller.ts:463-486` |
| Cache nie jest dowodem własności; tożsamość pod lockiem przed recovery | spełnione | `project-store.ts:304-362` (lock → identity → `resumeInternal`), `start-resume.test.mjs:27,293,332` |
| Niejednoznaczne/obce/uszkodzone foldery nie resetują ani nie nadpisują | spełnione z zastrzeżeniem | fail-closed potwierdzone sondami A–C, E, G; komunikaty i brak wyjścia: P2-A, P2-D |
| Anulowanie pickera, podwójne `create`, opaque `sourceToken` | spełnione | sonda H (`cancelled-begin null`, ten sam `projectId`, `STALE_SOURCE_TOKEN`); `start-resume.test.mjs:258`; `project-controller.ts:397-419` |
| Etykiety, kolejność działań, stany oczekiwania/błędu, klawiatura | spełnione z zastrzeżeniem | `App.tsx:285-481,478-480` (status „Weryfikacja…”), `resolveManualSelectionShortcut` chroni pola; auto-repeat: P2-C |
| Kierunek numeracji nie odwraca naturalnej listy; oba kierunki po restarcie | spełnione | `source-registry.ts:74-82` (naturalCompare), `project.test.mjs:295`, `start-resume.test.mjs:156`; smoke shortcuts (malejący) PASS |
| Zakres z `rangeForStart`, bez dowolnych 1–9 | spełnione | `project-store.ts:865-868,950-955`, `state-codec.ts:93-99,149-167`; `project.test.mjs:375` (zakres 2 plansz tylko na granicy) |
| Enter/F +1, Tab bez zmiany zdjęcia, skoki, zmiana zakresu, undo, granica, otwarcie po undo | spełnione | `project-store.ts:853-971`, `App.tsx:147-199`; `project.test.mjs:295,359,375`; smoke full PASS |
| Pominięty zakres można wypełnić; kolizja z accepted i powtórne źródło blokują | spełnione | `project-store.ts:869-898`; sonda I (`refill-skipped`, `RANGE_CONFLICT`, `IMAGE_ALREADY_ACCEPTED`); `project.test.mjs:87` |
| Repeat/podwójny submit/oczekujący zapis nie dublują decyzji; licznik po trwałym zapisie | spełnione z zastrzeżeniem | `App.tsx:53-71,97-130` (busy guard, snapshot po zapisie), `project.test.mjs:210,359`; smoke full (double click, `f` repeat); auto-repeat Enter/Tab/Ctrl+Z: P2-C |
| Zoom 100–3000, fullscreen, scroll obu osi, podgląd ±3, debounce i flush widoku | spełnione | `view-preferences.ts:14-35,76-120`, `image-viewer.tsx:42-103`, `project-controller.ts:224-230`; `renderer-contracts.test.mjs:48,69`; smoke ux/full PASS |
| Projekt źródłem prawdy, manifest operator-local v2 pod nazwą `manual-image-selection-output-v1.json`, bez `items` | spełnione | `operator-local.ts:3-47`; `project.test.mjs:295` (`items` nieobecne) |
| Oryginalne bajty JPEG `seq_<start>-<end>.jpg`, źródło tylko do odczytu, undo/restart usuwają tylko własne pliki | spełnione | `project-store.ts:577-642,677-678`, `secure-files.ts:253-263`; `project.test.mjs:295,563,739`; smoke full/legacy (oryginały niezmienione) |
| Intent przed zmianą JPEG, fazy dziennika, backup, temp/sync/replace, awarie każdej fazy, utrata odpowiedzi, retry tego samego `operationId` | spełnione | `project-store.ts:515-524,643-740,800-1059`; `project.test.mjs:451` (17 faz), `:499,:652,:693,:1048` (prawdziwy proces); sonda I (`replay-same-op`, `OPERATION_ID_CONFLICT`) |
| Recovery przed mutacją; ENOSPC, rename failure, uszkodzony stan, niezgodny manifest, brak folderu, zła suma | spełnione | `project-store.ts:741-770,823-835`; `project.test.mjs:499,528,591,621,652,879,912`; `legacy-recovery.test.mjs:48-281` |
| Lock atomowy; brak takeover po heartbeat; host, PID, tożsamość procesu; druga instancja; output lease | spełnione | `project-lock.ts:75-169`, `project-store.ts:661-662,726-738`; `project.test.mjs:765,806,847,974,1048`; `native-checks.test.mjs:162` |
| LOCK_LOST blokuje zapis, pozwala zamknąć, nie usuwa obcej blokady; brak folderu nie resetuje | spełnione | `project-store.ts:1110-1124`, `main.ts:82-111`; `project.test.mjs:163`, `native-checks.test.mjs:237`; smoke ux PASS (obcy lock bajtowo identyczny) |
| Brak własnego JPEG: diagnostyka i opisana droga przywrócenia; bez auto-repair; obce pliki chronione | spełnione (granica zakresu) | `project-store.ts:485-512`, `App.tsx:505-507`; `project.test.mjs:126`; instrukcja 151-170; P3-D |
| Sandbox, contextIsolation, brak nodeIntegration, CSP, blokada sieci/nawigacji/okien, walidacja nadawcy IPC | spełnione | `main.ts:52-76,154-164,212-249`, `contracts.ts:175-185`; `foundation.test.mjs:51`; smoke full (`fetch` i `window.open` zablokowane) |
| Opaque ID obrazu, strumieniowanie bez base64, traversal/ADS/junction/katalogi nadrzędne/zmiana między sprawdzeniem a użyciem | spełnione | `contracts.ts:186-199`, `path-security.ts:6-95`, `source-registry.ts:144-174`, `secure-files.ts:137-200`; `foundation.test.mjs:34,65,98,121`; `project.test.mjs:955`; `native-checks.test.mjs:162` |
| Worker: świeże kontrole, typowane JSONL, limity, timeout, awaria, zamknięcie, brak nowych procesów na krok | spełnione | `windows-check-worker.ts:17-68,124-157,305-337`; `native-checks.test.mjs:50-266`; sonda timing `workerSpawns=1` dla 12 operacji |
| Open: jeden zweryfikowany skan; pełne SHA i koszt stanu/historii jako jawna granica | spełnione (granica zakresu) | `project-store.ts:148-152,394-416`, `project-controller.ts:142-173`; `native-checks.test.mjs:237`; instrukcja 143-144, 207-210; ocena kosztu: P2-B |
| Debounce widoku nie gubi ostatniego widoku i nie wstrzymuje decyzji | spełnione | `view-preferences.ts:76-96` (ostatnia wartość), `App.tsx:82-96` (bez oczekiwania przed `execute`); smoke ux (burst 50 → 1 zapis, flush przy zamknięciu) |
| Przejęcie v1/v2: tożsamość źródła i sumy, preview, jawne utworzenie, oryginał niezmieniony, odmowy | spełnione | `legacy-preview.ts:63-269`, `project-controller.ts:237-338`; `legacy-contract.test.mjs:14-325`; smoke legacy PASS |
| Journal v2 wieloplikowy, recovery journal v1, generacja, anulowanie/token, nowy proces | spełnione | `state-codec.ts:206-256`, `project-store.ts:171-303,673-676`; `legacy-recovery.test.mjs:48,94,144,180,207,281` |
| Aktualizacja ZIP 0.1.0 → 0.1.2 na własnej kopii: decyzje, relativePath, kierunek, sumy | spełnione | smoke-update PASS (powtórka): `projectId`, kursor `photo3.jpg`, `nextRangeStart 19→28`, SHA `seq_1-9.jpg`, oryginały bez zmian |
| SHA ZIP i app.asar, build-info, sourceCommit, dirty, zawartość asar, brak źródeł/zależności runtime | spełnione | sekcja „Tożsamość…”; `forge.config.cjs:1-10`; `release.mjs`, `release-support.mjs:13-40` |
| Root workspace/lockfile: Electron, install scripts, brak globalnego wyłączenia i mirror | spełnione | `package.json:14-17`, diff lockfile (jeden `hasInstallScript` dla esbuild 0.25.12), brak `.npmrc` |
| Brak uploadu/linków/synchronizacji/Proton; brak zmian Admina/Reviewera/API/OpenAPI/bazy | spełnione | `git diff --stat bb883b59..21d8c023`: poza `apps/selector-desktop` tylko root `package.json`, `package-lock.json`, `.prettierignore`, `scripts/generate_code_map.py` i `ai_docs/`; `main.cjs` bez URL |
| TASK-0979: fizyczny odbiór (drugi komputer, kanał dostarczenia, reboot, ochrona Windows, aktualizacja u odbiorcy) | niezweryfikowane | osobna bramka operatora; lokalny smoke i sondy tego nie dowodzą (`OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md:90-106`) |
| Wydajność dla 15 000 JPEG | niezweryfikowane | brief wyklucza benchmark; dostępna tylko ekstrapolacja z 300/3000 (P2-B) |

Kryteria akceptacji tasków 0975–0978 i 0980–0983 zostały sprawdzone na podstawie
plików tasków, kodu i testów wskazanych wyżej; wszystkie zaznaczone `[x]`
mają odpowiadający dowód w kodzie i testach. Jedyne odstępstwa od deklaracji
wykonawcy to kwestie z P2-A, P2-C, P2-D i P2-E, które nie unieważniają
żadnego kryterium, lecz go uzupełniają.

## Status ustaleń poprzedniego raportu REVISE

| Ustalenie | Status | Dowód i ocena granicy |
|---|---|---|
| P1-1: 1,7–2,6 s na interakcję | zamknięte w części zmierzonej; reszta jako jawna granica (P2-B) | Worker usuwa starty procesów: w sondzie `workerSpawns=1` dla całej sesji; navigate 0,11 s (300) / 0,27 s (3000) wobec 1,70 / 1,90 s w poprzednim audycie, accept 0,16 / 0,32 s wobec 2,40 / 2,56 s, open 0,5 / 2,4 s wobec 2,9 / 6,1 s. Druga przyczyna (pełny inwentarz w dzienniku, retencja receiptów) pozostaje zgodnie z D-545 i instrukcją 207-210; przy kilku tysiącach zdjęć akceptowalna, przy 15 000 ekstrapolacja ~1 s/klawisz, co wymaga decyzji operatora. |
| P2-1: brak wyjścia po LOCK_LOST | zamknięte | `project-store.ts:1110-1124` (closeIssue, bez `unlink`), `main.ts:82-111` (zamknięcie okna zawsze); `project.test.mjs:163`, `native-checks.test.mjs:237`; smoke ux PASS: proces zamknięty, obcy lock bajtowo identyczny, ostatni scroll zapisany, `LOCK_LOST` w logu. Wariant `LOCK_OWNER_UNKNOWN` przy zamykaniu projektu: P3-A. |
| P2-2: brak seq JPEG | granica zakresu, akceptowalna | Nowe decyzje blokowane (`OUTPUT_MISSING_FILE`, `project-store.ts:485-512`), dobra/zła kopia i `resume` (`project.test.mjs:126`), komunikat w UI (`App.tsx:505-507`) i procedura w instrukcji 151-164. Brak auto-repair jest przyjętą granicą; brakuje zdania o identycznej kopii w źródle (P3-D). |
| P2-3: skipped range | zamknięte | `project-store.ts:869-880` blokuje tylko kolizję z `accepted`; sonda I: powrót do pominiętego zakresu, `RANGE_CONFLICT` dla nakładania z accepted, `IMAGE_ALREADY_ACCEPTED` dla tego samego źródła; `project.test.mjs:87`; wymagania (`requirements/MANUAL_IMAGE_SELECTION.md`, akapit rundy poprawek) i instrukcja 108-110 zaktualizowane. Reviewer (`remote-selection-store.ts:681`) nie ma reguły nakładania, więc desktop jest ostrzejszy tylko wobec zaakceptowanych zakresów, czego wymaga wymaganie. |
| P2-4: koszt open | zamknięte w części (jeden skan); pełne SHA jako jawna granica | `checkSource` → `inventoryFor` jeden raz, scan przekazany do `registerVerifiedScan` (`project-store.ts:394-416`, `project-controller.ts:142-173`), `native-checks.test.mjs:237` (stub `register` rzuca, a open działa). Pełne SHA wyniku przy open/recovery zostaje (`project-store.ts:764,791`); instrukcja 143-144 ostrzega. Koszt rośnie z rozmiarem wyniku; dla realnych partii (setki–tysiące JPEG po kilka MB) to sekundy–dziesiątki sekund na otwarcie, bez paska postępu poza komunikatem „Weryfikacja…”. Granica przyjęta w D-545. |
| P3-1: recovery guard | granica zakresu, akceptowalna | `project-lock.ts:81-85`: nieznana blokada odzyskiwania daje `LOCK_OWNER_UNKNOWN` z jawnym komunikatem (sonda E), bez takeover po heartbeat; `project.test.mjs:195`; instrukcja 168-170. Ręczne sprzątanie przez operatora pozostaje jedyną drogą. |
| P3-2: scroll | zamknięte | `view-preferences.ts:76-120` (debounce 250 ms, wspólny Promise, `flush`), `project-controller.ts:224-230`; `renderer-contracts.test.mjs:69`; smoke ux (burst 50 → jeden zapis, widok po zamknięciu i nowym procesie). |
| P3-3: USB | zamknięte (USB poza pilotażem) | `local-storage.ts:44-55`: `REMOVABLE_STORAGE` z własnym komunikatem; instrukcja 145-146. |
| P3-4: pickSource | zamknięte | kanał nieobecny w `contracts.ts:2-20` i `preload.ts`; smoke ux sprawdza `'pickSource' in window.selector === false`; anulowanie `begin()` zachowuje projekt i draft (sonda H, `start-resume.test.mjs:258`). |
| P3-5: drobne | zamknięte / przyjęte | Komunikat nawigacji „Pozycja zdjęcia zapisana.” osobno od „Wybór zapisany trwale.” (`App.tsx:119-128`); commity 0980–0983 mają identyfikatory TASK; drugi `esbuild` pozostaje decyzją planu poprawek (bez przebudowy zależności); instrukcja 207-210 poprawnie opisuje idempotencję tego samego `operationId`; `desktop.ini`/`Thumbs.db` wymienione w instrukcji 167. |

Otwarte po tej rundzie: P2-A, P2-B, P2-C, P2-D, P2-E oraz P3-A–P3-E (żadne
nie blokuje commitu; P2-B wymaga decyzji operatora o wielkości partii lub
kolejnej rundzie).

## Faktycznie uruchomione komendy i wyniki

Wszystkie komendy uruchomiono przez `apps/selector-desktop/scripts/run-bounded.mjs`
z podanym limitem; kod 124 oznaczałby przekroczenie limitu (nie wystąpił).

| Komenda | Limit | Wynik | Czas | Uwagi |
|---|---|---|---|---|
| `git status --short`, `git log`, `git diff --name-status 21d8c023 HEAD`, `git diff --stat bb883b59 21d8c023` | 30 s | 0 | <1 s | worktree czysty; różnica po v1.7.330 tylko w dokumentacji |
| `Get-FileHash` finalnego ZIP, kopii `out/make` i ZIP 0.1.0 | 30 s | 0 | 2 s | sumy zgodne z briefem i `.release.json` |
| `npm run test --workspace apps/selector-desktop` | 120 s | 0 | 29 s | 140 testów, 140 PASS, 0 FAIL, 5 suit (foundation 7, project 48, native 15, UI 4, legacy 25, legacy-recovery 29, start-resume 10, release 2) |
| `npm run lint --workspace apps/selector-desktop` | 60 s | 0 | 3 s | bez uwag |
| `npm run typecheck --workspace apps/selector-desktop` | 60 s | 0 | 3 s | bez uwag |
| `npm run docs:check` | 60 s | 0 | 3 s | `check_decision_links: OK (542/542/542)`, `check_current_state_window: OK (43 active, 10 done)` |
| `npm run code-map:check` | 60 s | 0 | 6 s | „code map is up to date” |
| `git diff --check` | 30 s | 0 | <1 s | czysto |
| `npm run smoke:release:start` | 120 s | 1 (pierwszy przebieg) / 0 (powtórka) | 14 s / 24 s | pierwszy przebieg: `Target page, context or browser has been closed` w `waitForHistory` po relaunchu; powtórka: 4 PASS (oba kierunki, historia, relink i ponowny wybór) |
| `npm run smoke:release` (full) | 120 s | 0 | 20 s | 6 PASS, w tym `fetch`/`window.open` zablokowane, nowy proces, relink, kopia projektu, restart |
| `npm run smoke:release:shortcuts` | 120 s | 0 | 15 s | 2 PASS (malejący F, zakres 19–20, zły JPEG, opaque IPC, przeniesione źródło) |
| `npm run smoke:release:legacy` | 120 s | 0 | 14 s | 1 PASS (preview, anulowanie, token, import, oryginały bez zmian, nowy proces) |
| `npm run smoke:release:ux` | 120 s | 0 | 15 s | 2 PASS (bez `pickSource`, debounce/flush, LOCK_LOST z zachowanym obcym lockiem) |
| `node scripts/smoke-update.mjs <ZIP 0.1.0> <ZIP 0.1.2>` | 120 s | 1 (pierwszy przebieg) / 0 (powtórka) | 50 s / 38 s | pierwszy przebieg: `Update state did not settle` (20 s) po „Następne” w 0.1.0; powtórka PASS: kursor, decyzje, SHA `seq_1-9.jpg`, nowa decyzja po procesie |
| własny skrypt `inspect-asar.mjs` (wyjęcie `app.asar` z ZIP, SHA, lista wpisów, build-info) | 90 s | 0 | 4 s | wynik w sekcji „Tożsamość…” |
| własna sonda `probe-scenarios.mjs` (scenariusze A–I na `ProjectController` z atrapą dialogów) | 120 s | 0 | ~30 s | wyniki cytowane w znaleziskach; fixture w `.tmp` usunięty |
| własna sonda `probe-timing.mjs` (300 i 3000 plików po 2 KB) | 120 s | 0 | ~25 s | tabela poniżej |

Po każdej partii smoke sprawdzono `Get-Process Selektor-zdjec`: brak
osieroconych procesów. Testów wykonawcy nie opisuję jako własnych; liczby
140/140 i wyniki smoke pochodzą z własnych uruchomień.

Pomiar własny (Windows 11, dysk D:, fixture 2 KB/plik, prawdziwe kontrole
natywne, jeden worker):

| Operacja | 300 plików | 3000 plików | Poprzedni audyt (300 / 3000) |
|---|---|---|---|
| `create` | 0,79 s | 3,18 s | 5,6 / 8,9 s |
| `navigate` (6 prób) | 0,105–0,128 s | 0,249–0,328 s | 1,70 / 1,90 s |
| `accept` (3 próby) | 0,148–0,177 s | 0,294–0,335 s | 2,40 / 2,56 s |
| `skip` | 0,100 s | 0,235 s | 1,70 / 1,87 s |
| `undo` (skipped / accepted) | 0,115 / 0,121 s | 0,262 / 0,267 s | 1,71 / 1,91 s |
| `begin()` istniejącego projektu (open) | 0,53 s | 2,44 s | 2,9 / 6,1 s (open+close) |
| `selector-project-v1.json` | 43 KB | 394 KB | 42 / 388 KB |
| starty PowerShell w sesji | 1 | 1 | wiele na operację |

Mały fixture nie dowodzi wydajności dla 15 000 JPEG ani dla dużych plików;
benchmarku nie uruchamiano.

## Potrzebne poprawki, brakujące testy i ograniczenia odbioru

Poprawki (kolejność według wpływu na użytkownika):

1. P2-A: obsługa brakującego folderu projektu z historii (jawny kod i
   ścieżka, pomijanie/usuwanie martwych wpisów, preferencja najnowszego
   wpisu dla tego samego `projectRoot`) oraz opis w instrukcji, jak zacząć
   nową partię po celowym usunięciu projektu.
2. P2-C: ignorowanie `event.repeat` dla accept/skip/undo w rendererze
   desktopu.
3. P2-D: precyzyjne komunikaty dla obcych folderów `… selekcja`/`… wybrane`,
   bez tworzenia pustego folderu projektu i pliku blokady w nieswoim katalogu.
4. P2-B: decyzja operatora: zapis orientacyjnej wielkości partii w instrukcji
   albo runda odchudzania dziennika/receiptów.
5. P2-E: zachowanie logów `user-data` przy błędzie smoke; ponowienie lub
   dłuższy limit `processIdentity` z zapisem czasu.
6. P3-A–P3-E według uznania operatora (małe zmiany kodu i dokumentacji).

Proponowane testy (plik i komenda):

- `apps/selector-desktop/test/start-resume.test.mjs`: `begin()` z jedynym
  wpisem historii wskazującym usunięty folder projektu (oczekiwany
  `SelectorError` z kodem i ścieżką, bez tworzenia projektu); dwa wpisy
  historii dla tego samego `projectRoot` (najnowszy wygrywa); obcy folder
  `… wybrane` przy nowym projekcie (brak pozostawionego pustego `… selekcja`).
  Komenda: `node --experimental-strip-types --test test/start-resume.test.mjs`.
- `apps/selector-desktop/test/renderer-contracts.test.mjs` lub nowy test
  rendererowy: `Enter`/`Tab`/`Ctrl+Z` z `repeat: true` nie wywołują
  `execute`. Komenda: `npm run test:ui --workspace @game-predictor/selector-desktop`.
- `apps/selector-desktop/test/project.test.mjs`: `OUTPUT_MISSING_FILE` przy
  `undo` (obecny test używa `skip`), `close()` przy `LOCK_OWNER_UNKNOWN`,
  prawdziwy drugi żywy proces trzymający blokadę (tryb `hold` w
  `project-worker.mjs` istnieje, ale żaden test go nie używa).
- `apps/selector-desktop/test/release.test.mjs`: test zawartości `app.asar`
  i zgodności `build-info.json` z `.release.json` dla istniejącego ZIP-a
  (pomijany, gdy paczki brak).
- Smoke: zachowanie `selector.log` z `user-data` przy błędzie, aby
  pierwszy nieudany przebieg był diagnozowalny.

Ograniczenia odbioru (poza tym audytem, zgodne z zaakceptowanym zakresem):

- Fizyczny odbiór TASK-0979: rzeczywisty komputer odbiorcy, kanał
  dostarczenia ZIP, brak narzędzi deweloperskich, restart Windows,
  aktualizacja u odbiorcy, reakcja ochrony Windows na niepodpisaną paczkę.
  Lokalny smoke i restart procesu tego nie dowodzą; blokada Windows
  wstrzymuje odbiór bez wyłączania ochrony.
- Brak obietnic: odporność na zanik zasilania/uszkodzenie dysku (brak
  fsync katalogu na Windows, `secure-files.ts:205-215`), blokady między
  komputerami przez synchronizację, obsługa USB, automatyczne odtworzenie
  JPEG-a, stały czas dla 15 000 zdjęć. Granice te są spójne z D-545 i opisane
  w instrukcji (`OFFLINE_PHOTO_SELECTOR_OPERATOR.md:145-146,164,194-211`).

Czy kod może przejść do pilotażu: tak, w zakresie lokalnym. Brak otwartych
P0/P1; trwałość, własność plików i granice bezpieczeństwa są potwierdzone.
Przed przekazaniem paczki odbiorcy zalecam rozstrzygnięcie P2-A (bo jest to
pierwszy scenariusz, na który natknie się użytkownik po pomyłce) i decyzję w
sprawie P2-B dla planowanej wielkości partii; pozostałe P2 mogą trafić do
następnej rundy. Fizyczny odbiór TASK-0979 pozostaje osobną bramką operatora.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: `AGENTS.md`, `ai_docs/README.md`, sekcje selektora w
`CURRENT_STATE.md` (ograniczenia, plan, TASK-0979, 10 ostatnich done), D-545
w obu logach decyzji, sekcje D-545 wymagań i architektury, trzy plany,
instrukcję operatora, rejestr odbioru, handoff, dowody poprawek i startu,
poprzedni raport REVISE, brief, taski 0975–0983 (przez wyciąg kryteriów
subagenta z cytatami `plik:linia`), całość `apps/selector-desktop/src`
(wszystkie 23 moduły), skrypty build/release/smoke, konfigurację Forge,
tsconfig, eslint, manifest workspace'u, diff root `package.json`/lockfile oraz
mapę pokrycia 140 testów (subagent, weryfikacja wybranych testów własnymi
sondami). Porównano reguły z `packages/manual-image-selection-core/src/index.ts`
(`rangeForStart`, `nextManualRangeStart`, `isManualSelectionRangeTerminal`,
`resolveManualSelectionShortcut`, `naturalCompare`) i z Reviewerem
(`remote-selection-store.ts:652-700`, `remote-manual-selection-workspace.tsx:432,549-550`).

Nie wykonano: benchmarku 15 000 zdjęć ani dużych plików (ekstrapolacja
liniowa z 300/3000 jest przypuszczeniem), testu zimnego startu WMI (wymagałby
zmiany stanu systemu), odbioru na drugim komputerze, testu z prawdziwymi
zdjęciami operatora. Nie uruchamiano usług API/Admin/Reviewera/workera, nie
instalowano zależności, nie przebudowywano paczki, nie wykonywano commitów,
push ani merge. Pierwsze niepowodzenia dwóch smoke nie zostały wyjaśnione
(P2-E); powtórki dały PASS. Subagenci (Claude Sonnet) pracowali wyłącznie w
trybie odczytu; ich wyciągi zostały zweryfikowane punktowo przez audytora w
kodzie i testach.
