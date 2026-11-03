# Audyt TASK-1130 / C1 — celowany R2

Werdykt: PASS
Audytor: claude-opus-5-5 / medium (potwierdzone actual modelUsage).
Wykonawca: gpt-6.1-sol / high.
Runda: 2.

**Werdykt: PASS.** Poprawka P1-COMPAT zamyka problem i nie psuje recovery ani handoff. P2-1, P2-2 i P3-2 też są zamknięte. Nowych P0/P1/P2 nie znalazłem, zostały tylko dwie drobne uwagi P3.

## Ustalenia zamknięte

**P1-COMPAT: zamknięte, oba kierunki działają.**

*Czytanie z uprawnieniem read-only niczego nie zapisuje ani nie promuje:*
- `readReplacementFilledGaps` (`apps/admin/src/features/manual-image-selection/replacement-repair-storage.ts:242-262`) działa pod tym samym lockiem nazwy wyniku (`serialize`, `:245`).
- Najpierw `readReplacementRepair` (`:73-83`) sprawdza schemat v3, `selectedDirectoryName` i skrót żądania (`:61-71`, `:79`).
- Potem `assertOutputInventory` (`:129-184`) sprawdza inwentarz katalogu i własność handoffu. Robi to wyłącznie przez `entries()`, `fileOrNull` i `text()`, czyli bez zapisu.
- SHA i rozmiar weryfikuje tylko dla wpisów `committed` (`:251-252`). `file!` jest bezpieczne, bo brak pliku `committed` rzuca błąd (`:270-271`).
- Zwraca czyste `deriveReplacementFilledGaps` (`packages/manual-image-selection-core/src/replacement-repair.ts:280-322`). Ta funkcja pomija `intent` (`:291`) i wymaga zweryfikowanego pliku (`:292-300`).
- Ta ścieżka nie wywołuje `inspectOutputUnlocked`, `jsonWrite`, `commitReplacementWrite` ani `verifyJpeg`.
- Wspólny reader (`manual-selection-repair-storage.ts:209-218`) przy obecnym pliku v3 od razu zwraca wynik readera v3. Nie przechodzi do ścieżki legacy.

*Ścieżka zapisu nadal działa jak przed zmianą:*
- `inspectReplacementOutput` i `inspectOutputUnlocked` (`:187-240`) korzystają ze wspólnego `verifyReplacementFile` (`:264-280`).
- Gdy `intent` ma już JPEG, wywołują `verifyJpeg` i `commitReplacementWrite` (`:223-230`), a potem zapisują manifest i handoff (`:233-238`).
- Writer (`:340-446`) zachowuje pełną sekwencję:
  - inspect pod lockiem (`:360`),
  - paragon `committed` po utraconej odpowiedzi (`:364-372`),
  - autoryzacja przez API przed nowym JPEG (`:374`),
  - wznowienie oczekującego wpisu z tym samym id, SHA i rozmiarem (`:382-391`),
  - utrwalenie `intent` (`:415`),
  - brak adopcji pliku docelowego (`:418-419`),
  - sprawdzenie po zapisie (`:430-436`),
  - commit (`:437-442`),
  - ponowny inspect (`:444`).

*Testy:*
- `apps/admin/test/replacement-repair.test.mjs:559-595`: przy read-only `writes === 0`, bajty i mtime manifestu bez zmian, brakujący handoff nie powstaje, a `intent` z istniejącym JPEG zostaje `intent` i daje 0 wpisów.
- Fixture (`apps/admin/test/fixtures/replacement-disk-directory.mjs:30-49`): tryb read-only blokuje zarówno `create`, jak i `createWritable`, a licznik zapisów rośnie przed blokadą.
- Recovery po stronie zapisu pokrywa istniejący test `:185`.

**P2-1: zamknięte.**
- `cacheScope` składa się z digestu, `sourceIdentity`, `entryId` i `fileName` (`replacement-repair-workspace.tsx:88`).
- W renderze po zmianie źródła klucz cache jest już nowy. Przez jeden render widać jeszcze stary URL, bo `imageUrlIndex` jeszcze się nie zmienił (`manual-image-viewer.tsx:86-91`). Uruchomiony wtedy timer jest jednak kasowany w cleanupie efektu (`replacement-repair-workspace.tsx:90-95`), gdy microtask zeruje URL (`manual-image-viewer.tsx:126-129`). Dzieje się to dużo wcześniej niż po 300 ms.
- `sourceImageSize` jest powiązane z `sourceUrl` (`:99-102`).
- Test `replacement-repair-workspace.test.mjs:130-226` sprawdza: po 400 ms przy wolnym `getFile` przycisk zapisu jest wyłączony, po samym udostępnieniu URL nadal wyłączony, a po zdarzeniu load i 350 ms włączony.

**P2-2: zamknięte.**
- `REPLACEMENT_TEMPORARY_WRITE_REMAINS` dotyczy tylko pliku `<nazwa>.crswap`, którego `<nazwa>` jest na liście oczekiwanych plików (journal albo manifest/handoff) (`replacement-repair-storage.ts:141-143`). Każdy inny nieznany plik daje `FOREIGN_FILE` (`:144`).
- Sprawdzenie inwentarza poprzedza każdy zapis w inspect (`:208` przed `:233`). Plik `.crswap` nie jest usuwany ani adoptowany.
- Test `:537-557` sprawdza, że bajty `.crswap` zostają takie same i że nie powstaje `seq_1-9.jpg`.
- Polski komunikat jest zgodny z wymaganiem (`replacement-repair-workspace.tsx:348-349`).

**P3-2: zamknięte.** Typowe błędy mają polskie etykiety (`:333-373`). Pozostałe kody `REPLACEMENT_*` dostają ogólny komunikat z kodem w nawiasie (`:374-379`).

## Uwagi otwarte (P3, nie blokują commitu)

1. **P3-a: luka w teście.** Test P2-1 nie sprawdza, że przycisk jest jeszcze wyłączony zaraz po zdarzeniu load, przed upływem 300 ms. `loadVisibleImage` od razu czeka 350 ms (`:202`). Kod gate jest poprawny, ale timera nie sprawdza bezpośrednio żaden assert.
2. **P3-b: przypadek brzegowy.** Jeśli zapis pierwszego manifestu przerwie się w Chrome, zanim powstał `replacement-repair` (zostaje sam `<manifest>.crswap`, a manifestu nie ma), lista oczekiwanych plików jest pusta. Wynikiem jest wtedy `FOREIGN_FILE`, a nie `TEMPORARY_WRITE_REMAINS` (`:133-139`). Nadal działa to bezpiecznie (fail-closed) i jest zgodne z zasadą „tylko nazwa przypięta do własnych plików”. Jedyny skutek to mniej zrozumiały komunikat.

## Zakres i ograniczenia
- Tylko statyczne Read i Grep: 11 ograniczonych odczytów (po ≤150 linii) i 3 Grep.
- Przeczytane fragmenty:
  - `replacement-repair-storage.ts` 30-104, 110-329, 330-447,
  - `manual-selection-repair-storage.ts` 200-249,
  - core 200-329,
  - workspace 55-114 i 320-381,
  - viewer 47-146,
  - testy 537-595 i 130-226,
  - fixture 1-68.
- Nie czytałem crop consumera (`selected-image-crop-storage.ts:366-395`) ani raportu R1. Uprawnienie read opieram na opisie koordynatora i na fixture read-only.
- Nie uruchamiałem testów. Wyniki 60/60, FS 17/17 i core 14/14 przyjmuję od koordynatora.
- Fizycznego smoke testu w Chrome dla `.crswap` (D1) nie da się sprawdzić statycznie.
- Nie audytowałem ponownie całego C1.

## Oświadczenie
Nic nie zmieniłem: żadnych edycji, testów, usług, delegowania ani MCP.


## Rozliczenie wykonawcy po R2

P3-a: dodano bezpośredni assert disabled po load przed upływem 300 ms; istniejący test delayed duplicate ponownie PASS. P3-b pozostaje zaakceptowanym ograniczeniem: bez własnego manifestu narzędzie nie uznaje .crswap za owned, zachowuje plik i odmawia ogólnym komunikatem obcego katalogu. Bez kolejnych zmian protokołu i bez R3.
