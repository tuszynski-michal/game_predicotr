---
title: Lokalny selektor Windows — audyt implementacji pięciu tasków (Claude)
status: review
last_updated: 2026-10-12
---

# Audyt implementacji lokalnego selektora Windows (TASK-0975–0979)

Audytor: Claude Fable 5.1 (sesja Claude Code, tylko odczyt kodu i testy na
własnych fixture'ach). Przedmiot: gałąź `codex/offline-photo-selector`,
commity v1.7.317–v1.7.323 (`e91b365c`…`d21f9f3e`), baza v1.7.316 `bb883b59`.
Audyt obejmuje kod, testy, paczkę i dokumentację. Nie obejmuje fizycznego
odbioru na drugim komputerze (TASK-0979 pozostaje `blocked`).

## Werdykt

**REVISE.** Kod jest poprawny funkcjonalnie, bezpiecznie odgrodzony i dobrze
przetestowany (109/109 testów PASS, lint/typecheck/docs/code-map PASS, paczka
zgodna z rejestrem). Przed przekazaniem pilotażu odbiorcy należy rozstrzygnąć
jeden problem wydajnościowy P1 (opóźnienie 1,7–2,6 s na każdą strzałkę,
akceptację, pominięcie i cofnięcie) oraz cztery P2 (brak wyjścia z utraty
blokady, brak drogi naprawy po usunięciu pliku wynikowego, odstępstwo od
semantyki Reviewera dla zakresów pominiętych, koszt otwarcia projektu).
Żadne ustalenie nie dotyczy utraty lub nadpisania danych użytkownika.

## Metoda i dowody

Wykonano w worktree `D:\game_predicotr\worktrees\offline-photo-selector`:

| Kontrola | Wynik |
|---|---|
| `node --experimental-strip-types --test test/*.test.mjs` (6 plików) | 109 testów, 109 PASS, 0 FAIL, 202 s |
| `npm run lint` / `npm run typecheck` (workspace) | PASS / PASS |
| `npm run docs:check` / `npm run code-map:check` | OK (542/542/542; 43 aktywne, 10 done) / aktualna |
| `git diff bb883b59..HEAD --check`, `git status` | czysto |
| SHA-256 `Selektor zdjec-win32-x64-0.1.0.zip` | `2dcfe275…21bea`, 149 397 136 B — zgodne z `.sha256` i rejestrem |
| SHA-256 `resources\app.asar` wyjęty z ZIP | `e2c60792…1bab` — zgodne z `.release.json` |
| Zawartość app.asar | 9 wpisów: `dist/` (main, preload, renderer, build-info) i `package.json`; brak `src/`, `node_modules`, plików `.ts` |
| `dist/build-info.json` w paczce | `sourceCommit abe8e645`, `dirty=true`, `applicationSourceDirty=false` — zgodne z rejestrem |
| Zakres zmian poza `apps/selector-desktop` | tylko `package.json`, `package-lock.json`, `.prettierignore`, `scripts/generate_code_map.py`, dokumentacja; Admin/Reviewer/API/OpenAPI/Alembic nietknięte |

Pomiary własne (Windows 11, PowerShell 5.1, dysk C:, fixture 300 i 3000 plików
JPEG po 2 KB, `ProjectStore` z prawdziwymi kontrolami natywnymi, skrypt poza
repozytorium):

| Operacja | 300 plików | 3000 plików |
|---|---|---|
| `create` | 5,6 s | 8,9 s |
| `navigate` (strzałka) | 1,70 s | 1,90 s |
| `accept` (Enter/F) | 2,40 s | 2,56 s |
| `skip` (Tab) / `undo` | 1,70 s / 1,71 s | 1,87 s / 1,91 s |
| `open` projektu + `close` | 2,9 s | 6,1 s |
| `SourceRegistry.register` | 1,0 s | 4,1 s |
| `openImage` (jeden JPEG do podglądu) | 0,64 s | 0,67 s |
| `selector-project-v1.json` | 42 KB | 388 KB |

Pojedyncze uruchomienie `powershell.exe -EncodedCommand` (DriveInfo albo
`Get-CimInstance Win32_Process`) trwało na tej maszynie 0,3–1,0 s.

Sondy błędów (własne fixture, skrypt poza repozytorium):

- A. usunięcie `selector-project.lock` przy otwartym projekcie → `close()`
  rzuca `LOCK_LOST` za każdym razem;
- B. usunięcie zaakceptowanego `seq_1-9.jpg` → `undo` → `OUTPUT_MISSING_FILE`;
  `skip` nadal przechodzi; `resume` → `OUTPUT_MISSING_FILE` i `issue`
  ustawione; `previewRestart` → `PROJECT_FROZEN`;
- C. pozostawiony `selector-project-lock-recovery.lock` → `open` kończy się
  z `issue = FOREIGN_CONTENT`, `resume` to samo.

## Ustalenia

### P1-1 — Koszt każdej interakcji: 1,7–2,6 s przez uruchamianie PowerShell w każdej transakcji

Dowód: tabela pomiarów wyżej. Źródła kosztu w kodzie:

- `project-store.ts` `applyJournal()` wywołuje przy **każdej** operacji
  `assertLocalStorage(outputRoot, true)` (proces PowerShell `DriveInfo`,
  `local-storage.ts:110-120`) oraz `outputFiles()` → `SecureFiles.verifyRoot()`
  → `assertWindowsReparse([root], true)` (drugi proces PowerShell z
  `Get-ChildItem -Recurse` po katalogu wyniku, `secure-files.ts:115-120`).
- `accept` dokłada trzeci proces: `sourceChecksum()` →
  `safeExistingPath(sourceRoot, imagePath)` z domyślnym
  `windowsAttributes = true` (`project-store.ts:482-484`).
- `SourceRegistry.openImage()` (`source-registry.ts:104-108`) wywołuje
  `safeExistingPath(..., true)` dwa razy na każde odczytywane zdjęcie, czyli
  dwa procesy PowerShell na JPEG. Komentarz w `path-security.ts:37` („never one
  process per JPEG”) opisuje tylko indeksowanie, nie odczyt. Przy skoku 20 okno
  ±3 ładuje do 7 nowych zdjęć, czyli do 14 procesów.
- Nawigacja strzałką jest pełną transakcją dziennika: dziennik zawiera stan
  `before` i `after` z całym inwentarzem (przy 15 000 zdjęć ≈ 2 × 1,9 MB),
  zapisywany trzy razy z `fsync`, plus stan, kopia i manifest. Każda operacja
  (także `navigate`) dopisuje trwały wpis w `receipts`, który nigdy nie jest
  usuwany; projekt rośnie liniowo z liczbą naciśnięć strzałek.

Skutek: Reviewer zapisywał kursor w IndexedDB bez zauważalnego opóźnienia;
desktop daje ~2 s na strzałkę i ~2,5 s na akceptację na tej maszynie.
Dla partii tysięcy zdjęć to zmiana jakości pracy, a limit 15 000 zdjęć jest
deklarowany bez pomiaru (co handoff sam zaznacza). Na komputerze odbiorcy czas
startu PowerShell może być inny, ale rząd wielkości (sekundy na klawisz) jest
strukturalny.

Rekomendacja (bez zmiany gwarancji trwałości): (1) wynik `DriveInfo` i skan
reparse katalogu wyniku/projektu buforować per korzeń na czas sesji albo
odświeżać co N sekund, nie w każdej transakcji; (2) dla odczytu zdjęć używać
`safeExistingPath(..., false)` — kontrola leksykalna, `lstat` przodków
i `realpath` pozostają, a skan atrybutów jest już wykonany dla całego korzenia
przy rejestracji; (3) w dzienniku przechowywać inwentarz raz (lub tylko
`after` + różnicę) i przycinać `receipts` do ostatnich K operacji albo tylko
do `accept/skip/undo/restart`; (4) rozważyć lekki, atomowy zapis kursora bez
pełnej transakcji dla `navigate` (decyzja operatora, bo plan czyni projekt
źródłem kursora). Po zmianie powtórzyć pomiar i zapisać go w rejestrze.

### P2-1 — Po utracie blokady projektu okna nie da się zamknąć

Dowód: sonda A. `main.ts:80-95`: handler `close` zawsze wywołuje
`event.preventDefault()`, a przy błędzie `controller.close()` pokazuje
`showErrorBox` i nic więcej. `ProjectStore.close()` (`project-store.ts:1048`)
wywołuje `lock.release()` → `assertOwned()` → `LOCK_LOST`, a `closed` nigdy
nie przechodzi na `true`; `closeInternal()` w kontrolerze nie zeruje `store`.
Każda kolejna próba zamknięcia kończy się tym samym komunikatem; jedyne
wyjście to Menedżer zadań. Dotyczy także katalogu projektu, który stał się
nieczytelny. Nic nie jest w locie, więc utrata danych nie grozi, ale komunikat
„Spróbuj zamknąć ponownie” jest nieprawdziwy. Rekomendacja: przy `LOCK_LOST`
(i `PROJECT_CLOSED`) zalogować zdarzenie, oznaczyć sklep jako zamknięty bez
próby `unlink` i pozwolić zamknąć okno, albo dać przycisk „Zamknij mimo to”.

### P2-2 — Usunięty lub przeniesiony plik `seq_*.jpg` trwale zamraża projekt bez drogi naprawy

Dowód: sonda B. `verifyOutput()` (`project-store.ts:439-449`) traktuje brak
zarządzanego pliku jako `OUTPUT_MISSING_FILE`, chyba że wymienia go bieżący
dziennik. Przy `undo` kontrola przed `prepare` nie ma dziennika, więc cofnięcie
jest blokowane; po ponownym otwarciu `resumeInternal()` hashuje wszystko i
zamraża projekt, a `previewRestart()` wymaga braku `issue`. Nie ma polecenia
„odtwórz brakujący plik” mimo że projekt zna ścieżkę źródłową i sumę SHA-256
(można skopiować ponownie z zweryfikowanego źródła tak jak przy recovery).
Instrukcja operatora opisuje tylko plik obcy lub zmieniony, nie brak pliku.
Rekomendacja: albo akcja „Odtwórz brakujące pliki wynikowe ze źródła”
(weryfikacja SHA jak w `copyJpeg`), albo przynajmniej procedura w instrukcji
(przywrócenie z kopii, bez ręcznej edycji manifestu).

### P2-3 — Odstępstwo od Reviewera: zakres pominięty (Tab) nie może być później wybrany

Dowód: `project-store.ts:812-820` odrzuca `accept`/`skip` kodem
`RANGE_CONFLICT`, gdy nowy zakres pokrywa się z **jakąkolwiek** wcześniejszą
decyzją, także `skipped`. Reviewer (`remote-selection-store.ts:652-700`,
`appendLocalWorkspaceDecision`) sprawdza tylko
`nextRangeStart === decision.rangeStart`; nie ma reguły nakładania, a kolizję
plików blokuje dopiero `writeOperatorLocalSelection` dla zakresu
zaakceptowanego. W Reviewerze użytkownik po „Zmień zakres” może więc wrócić do
pominiętego zakresu i przypisać mu zdjęcie; w desktopie musi cofać decyzje aż
do tego miejsca. Test „overlapping ranges … enforce domain rules” utrwala
tę ostrzejszą regułę. Plan i D-545 nakazują semantykę Reviewera i nie
wprowadzają reguły nakładania. Potrzebna decyzja operatora: albo zrównać
(blokować tylko kolizję z zakresem **zaakceptowanym**), albo zapisać ostrzejszą
regułę w wymaganiach i instrukcji.

### P2-4 — Otwarcie i wznowienie projektu skaluje się z rozmiarem wyniku i dwoma pełnymi skanami źródła

Dowód: tabela pomiarów (`open` 2,9 s → 6,1 s przy 300 → 3000 plików,
`register` 1,0 s → 4,1 s). `ProjectStore.open()` → `resumeInternal()` →
`checkSource()` → `inventoryFor()` (pełny skan + `lstat` każdego pliku +
rekurencyjny skan reparse), a potem kontroler w `replaceStore()` →
`refreshSource()` → `registry.register()` wykonuje ten sam skan drugi raz.
Dodatkowo `resumeInternal()` bez dziennika i `previewRestart()` wołają
`verifyOutput(state, state)` z `hashNames = 'all'`, czyli liczą SHA-256
**każdego** zaakceptowanego JPEG-a przy każdym otwarciu. Dla sesji z 1500
zaakceptowanymi zdjęciami po 4–8 MB to 6–12 GB hashowania na otwarcie (dziesiątki
sekund na SSD, minuty na HDD), bez paska postępu. Rekomendacja: jeden skan źródła
na otwarcie (przekazać inwentarz z `checkSource` do kontrolera), hashowanie
wyniku ograniczyć do metadanych (`size`, `mtime`, `ino`) z pełnym hashem tylko
przy niezgodności, albo wykonywać je w tle z komunikatem.

### P3-1 — Pozostawiony `selector-project-lock-recovery.lock` blokuje projekt na stałe

Dowód: sonda C. Nazwa nie jest na liście `validateProjectContents()`
(`project-store.ts:336-347`), więc po awarii procesu w oknie przejmowania
blokady (`project-lock.ts:139-167`) projekt otwiera się z
`FOREIGN_CONTENT`, a instrukcja zabrania ręcznego usuwania plików blokad.
Okno jest krótkie, ale produkt wprost nie obiecuje odporności na zanik
zasilania, więc scenariusz jest realny. Rekomendacja: dopuścić tę nazwę w
walidacji i usuwać ją tym samym mechanizmem tożsamości procesu co blokadę
główną.

### P3-2 — Zapis cache widoku bez debounce przy przewijaniu

`image-viewer.tsx:113-120` wywołuje `changeView` na każdym zdarzeniu `scroll`,
a `ViewPreferencesStore.save()` wykonuje `replace` (temp + `fsync` + `rename`)
kolejkowo dla każdego zdarzenia. `App.tsx:59` czeka na `pendingView` przed
każdą operacją, więc zaległość przewijania opóźnia następną akceptację.
Rekomendacja: debounce 200–300 ms i zapis ostatniej wartości.

### P3-3 — Dysk wymienny odrzucany kodem `NETWORK_STORAGE`

`local-storage.ts:116-120`: `DriveType !== 3` daje kod `NETWORK_STORAGE`
i komunikat o „dysku stałym”. Pendrive/dysk USB wymienny (typ 2) dostaje
mylący kod; plan mówi o „lokalnym dysku”. Decyzja operatora: dopuścić typ 2
albo zmienić kod i komunikat na `REMOVABLE_STORAGE`.

### P3-4 — Nieużywany kanał IPC `pickSource` kasuje aktywne źródło

`main.ts:234-243` wystawia `selector:pick-source`, którego `App.tsx` nie
używa. `SourceRegistry.register()` (`source-registry.ts:78`) wykonuje
`this.sources.clear()`, więc wywołanie tego kanału przy otwartym projekcie
unieważniłoby wszystkie adresy `selector-photo://` bieżącego projektu.
Martwa powierzchnia; usunąć kanał albo blokować go przy otwartym projekcie.

### P3-5 — Drobne

- Komunikat `Zapisano trwale.` pojawia się także po samej nawigacji
  strzałką (`App.tsx:113`); mylące dla użytkownika.
- Komunikaty commitów nie zawierają identyfikatorów tasków
  (`v1.7.318 - Add portable …`), podczas gdy konwencja gałęzi to
  `vX.Y.N - TASK-NNNN …`; mapowanie jest tylko w handoffie.
- `esbuild@0.25.12` przypięty w nowym workspace obok istniejącego
  `esbuild@0.28.x` w drzewie — podwójna kopia narzędzia.
- Handoff i instrukcja mówią o „retry po utracie odpowiedzi”; renderer
  generuje nowy `operationId` przy każdym wywołaniu (`App.tsx:105`), więc
  idempotencja receiptów działa tylko na poziomie `ProjectStore` i w testach.
  Nie jest to błąd (strażnicy `STALE_CURSOR`/`IMAGE_ALREADY_ACCEPTED`
  zapobiegają podwójnej decyzji), ale opis zawyża zakres mechanizmu.
- `desktop.ini`/`Thumbs.db` w katalogu wyniku lub w starym wyniku Reviewera
  dają `FOREIGN_CONTENT`/`LEGACY_OUTPUT_CONFLICT` zgodnie z planem
  (fail-closed); warto wymienić te nazwy wprost w instrukcji, bo Windows
  potrafi je utworzyć bez udziału użytkownika.

## Sprawdzone pozytywnie

- **Granice renderer/native.** `validateSender` wymaga dokładnego adresu
  `selector://app/index.html`, głównej ramki i własnego okna; liczba
  argumentów jest walidowana; polecenia przyjmują wyłącznie `imageId`/token
  UUID, nigdy ścieżki (`project-controller.ts:349-422`). CSP
  `default-src 'none'`, `sandbox`, `contextIsolation`, blokada nawigacji,
  nowych okien, webview, uprawnień i wszystkich żądań poza dwoma własnymi
  schematami. Protokół zdjęć strumieniuje tylko zarejestrowane identyfikatory
  i ponownie sprawdza tożsamość pliku po otwarciu.
- **Ścieżki.** `containedPath` odrzuca `..`, `.`, puste segmenty, `\`, `:`
  i `\0`; `assertNoLinks` sprawdza każdego przodka; `safeExistingPath`
  porównuje `realpath`; skan atrybutów `ReparsePoint` przez PowerShell ze
  stdin JSON (bez interpolacji). Testy obejmują junction w korzeniu, potomku
  i podmianę po indeksowaniu.
- **Trwałość.** Fazy `prepared → jpeg_written → committed`, zapis
  temp + `fsync` + `rename` w tym samym katalogu, kopia zapasowa po manifeście,
  dziennik kasowany na końcu; blokada projektu z `ownerId/host/pid/
  processIdentity`, przejęcie wyłącznie po potwierdzeniu śmierci procesu tego
  hosta, bez heartbeatu; przejściowa dzierżawa wyniku. Testy wstrzykują awarię
  w każdej fazie i zabijają prawdziwy proces; recovery i powtórka tego samego
  `operationId` dają jeden wynik.
- **Semantyka Reviewera.** Enter/F przesuwa o jeden z clampem, Tab pomija bez
  zmiany zdjęcia, A/Ctrl+Z cofa, strzałki nawigują, `rangeForStart`
  i `isManualSelectionRangeTerminal` z rdzenia; `resolveManualSelectionShortcut`
  chroni pola formularzy. Zgodne z `remote-manual-selection-workspace.tsx:437-600`
  (z wyjątkiem P2-3).
- **Przejęcie starej sesji.** `inspectLegacy` jest tylko do odczytu, wymaga
  fingerprintu źródła, `fileCount`, jawnej konfiguracji, dokładnego zestawu
  plików wyniku i zgodnych SHA źródło/wynik, ponawia kontrolę po hashowaniu;
  reguła kursora dla malejącego bez `natural_v2` jest identyczna z
  `resumeOperatorLocalBatch` (`operator-local-selection-output.ts:364-375`).
  Nowy projekt i wynik muszą być puste i rozłączne ze starym wynikiem; dziennik
  v2 `importCopies` ma testy ENOSPC w każdej fazie i utraty procesu.
- **Paczka.** ZIP i `app.asar` zgodne z rejestrem, bez źródeł i `node_modules`;
  `build-info.json` osadzony; smoke'i używają `mkdtemp` w `.tmp` i izolowanego
  `--user-data-dir`, sprzątają tylko własny katalog (`removeOwnedTemp`).
- **Proces.** Osobny commit na task, numeracja v1.7.317–323 ciągła od
  v1.7.316, D-545 w obu logach decyzji, CURRENT_STATE i archiwum zaktualizowane,
  taski 0975–0978 w `completed/`, 0979 aktywny jako `blocked` z pustą tabelą
  dowodów operatora, mapa kodu zregenerowana, `docs:check` zielony.

## Wymagane działania przed odbiorem pilotażu

1. Rozstrzygnąć P1-1 (akceptacja opóźnień albo poprawka buforowania kontroli
   natywnych i odchudzenia dziennika) i powtórzyć pomiar.
2. Poprawić P2-1 (zamykanie po `LOCK_LOST`) — mała zmiana w `main.ts`
   i `ProjectStore.close()`.
3. Zdecydować o P2-2 (akcja odtworzenia brakującego pliku albo procedura
   w instrukcji) i P2-3 (zrównanie z Reviewerem albo zapis reguły w wymaganiach).
4. P2-4 i P3 według uznania operatora; P3-1 i P3-4 są tanie.
5. Fizyczny odbiór TASK-0979 pozostaje bramką operatora; ten audyt go nie
   zastępuje.
