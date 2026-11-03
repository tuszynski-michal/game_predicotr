# Raport audytu — TASK-1130 / C1, Runda 1

**Metadane**
- Zadanie: TASK-1130 / C1 (source replacement repair, v3), branch `codex/777a2-readability-replacement`, baza `24f5d740`, audytowane niezacommitowane pliki C1.
- Wykonawca: gpt-6.1-sol/high. Audytor: **claude-opus-5-5 / medium** (model rzeczywisty: claude-opus-5-5).
- Runda: **1**.
- Tryb: przegląd statyczny. Nie zmieniłem żadnych plików, nie uruchamiałem testów, komend ani usług. Zużyłem 22 z 24 wywołań Read/Glob/Grep.
- Ograniczenie formy: nie odczytałem `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`, żeby zmieścić się w budżecie. Sekcje odtworzyłem według zleconej struktury.

Werdykt: PASS

Nie znalazłem P0 ani P1. Są 2 istotne ustalenia P2 i kilka P3. Żadne z nich nie blokuje commitu.

---

## Ustalenia

### P0 / P1
Brak.

### P2-1 — Bramka podglądu (dekodowanie + 300 ms) może przepuścić poprzedni obraz po zmianie wpisu lub duplikatu
- Kod: `apps/admin/src/features/manual-image-selection/replacement-repair-workspace.tsx:82-95` oraz `apps/admin/src/features/manual-image-selection/manual-image-viewer.tsx:86-102` i `:112-131`.
- `cacheScope` to `digest:sourceIdentity`. Nie zmienia się, gdy operator przełącza `entryId` albo wybiera inny duplikat. `currentImageIndex` jest zawsze `0`.
- Przy takiej zmianie `visibleImageUrl` spada na stary `imageUrl`, bo `imageUrlIndex === 0`. `sourceImageSize` pozostaje rozmiarem poprzedniego obrazu, bo `sourceUrl` nadal pasuje.
- Efekt bramki uruchamia się ponownie (zmienił się `source`) i od razu startuje 300 ms na starym obrazie.
- **Skutek:** jeśli `getFile()` lub ładowanie nowego pliku trwa ponad 300 ms (wolny dysk, pliki-zaślepki OneDrive na Windows), przycisk „Przygotuj wybrane zdjęcie” staje się aktywny. Podgląd pokazuje wtedy poprzednie zdjęcie z etykietą nowego pliku.
- Najbardziej dotyczy to ręcznego wyboru duplikatu, czyli dokładnie sytuacji, w której operator decyduje na podstawie podglądu. Kryterium 3 („decode+300ms gate”) jest spełnione tylko przy szybkim I/O.
- Rekomendacja: dodać `source.fileName` lub `entryId` do `cacheScope`. Alternatywnie warunkować `ready` tym, że załadowany URL należy do klucza bieżącego `source`.

### P2-2 — Plik `*.crswap` po awarii przeglądarki blokuje odzyskanie zapisu z błędem „obcy plik”
- Kod: `apps/admin/src/features/manual-image-selection/replacement-repair-storage.ts:140-143` (inwentarz odrzuca każdą nazwę spoza journalu), `:403-412` (`createWritable` przy JPEG) i `:44-58` (`jsonWrite`). Komunikat w `replacement-repair-workspace.tsx:306-311` każe „wybrać ponownie ten sam plik”.
- Chromium zapisuje przez plik tymczasowy `<nazwa>.crswap` w tym samym katalogu. Po zabiciu lub awarii przeglądarki w trakcie zapisu ten plik zostaje.
- Następna inspekcja kończy się wtedy błędem `REPLACEMENT_FOREIGN_FILE:seq_x-y.jpg.crswap`. Operator widzi „Katalog wyniku zawiera obcy plik” zamiast obiecanej ścieżki wznowienia.
- Zatrzymanie (fail-closed) jest bezpieczne, bo nic nie jest adoptowane. Ścieżka odzyskania z kryterium 4 („missing pending JPEG czeka na tę samą source”) w realnym Chrome wymaga jednak ręcznego usunięcia pliku tymczasowego. Testy na prawdziwym FS w Node (`apps/admin/test/fixtures/replacement-disk-directory.mjs`) tego nie odwzorowują.
- Rekomendacja:
  - albo pomijać w inwentarzu wyłącznie `<nazwa_z_journalu|manifest|handoff>.crswap`, bez adopcji i bez czytania;
  - albo dodać osobny kod błędu z instrukcją, który plik tymczasowy usunąć;
  - fizyczny test w D1 powinien to objąć.

### P3 (nieblokujące)
1. **Ścieżka odczytu zapisuje pliki.** `readActiveFilledGapsManifest` (`manual-selection-repair-storage.ts:212-214`) wywołuje `readReplacementFilledGaps`, a to `inspectOutputUnlocked`. Każde wywołanie bezwarunkowo nadpisuje manifest v3 i handoff (`replacement-repair-storage.ts:239-244`) i może zatwierdzić intent. Dzieje się to także z konsumenta cropu (`selected-image-crop-storage.ts:371`). Jest to bezpieczne (zapis pod lockiem, weryfikacja sha i rozmiaru), ale zbędnie zmienia mtime. Warto zapisywać tylko przy zmianie.
2. **Brak polskich etykiet** dla `REPLACEMENT_TARGET_EXISTS`, `REPLACEMENT_COMMITTED_FILE_MISSING`, `REPLACEMENT_WRITTEN_CHECKSUM_MISMATCH`, `REPLACEMENT_EMPTY_JPEG`, `REPLACEMENT_MULTIPLE_PENDING`, `REPLACEMENT_DIRECTORY_CHANGED` i `REPLACEMENT_UNVERIFIED_COMMIT` (`replacement-repair-workspace.tsx:333-362`). Użytkownik zobaczy surowy kod.
3. **Luki w walidacji journalu.** `validateReplacementRepair` nie sprawdza `typeof write.fileName === 'string'` przed `validateReplacementTarget`. Nie sprawdza też formatu UUID dla `write.id` (`replacement-repair.ts:230-247`). W obu przypadkach skończy się błędem, ale z mniej czytelnym kodem.
4. **Zawieszony intent blokuje cały katalog wyniku.** Pending intent dla wpisu A, który stał się nieaktualny w API (albo którego źródło zmieniono lub usunięto), uniemożliwia zapis B w tym samym katalogu (`replacement-repair-storage.ts:365-373`). To świadoma konsekwencja zasady „pending czeka na tę samą source”. Odnotowuję jako ograniczenie operacyjne, bez propozycji zmiany zakresu.
5. **Brak blokady między przepływami.** Lock v3 (`replacement-repair:<name>`) nie jest współdzielony z writerami v1/v2. Wyścig na jednym pustym katalogu z dwóch różnych przepływów nie jest serializowany. Później v1/v2 i tak odmawia, gdy istnieje v3 (`manual-selection-repair-storage.ts:146-152`), a v3 odmawia obcych plików. Ryzyko jest teoretyczne.

---

## Tabela pokrycia kryteriów

| # | Kryterium | Dowód (plik:linia) | Status |
|---|---|---|---|
| 1 | Typ to wyłącznie wygenerowany `SourceReplacementRequestExport` | `replacement-repair.ts:1-4,13` | ✅ |
| 1 | Kanoniczny digest: SHA-256 z kompaktowego JSON-a z posortowanymi kluczami, bez własnego `digest` | `replacement-repair.ts:49-80`, `replacement-repair-storage.ts:61-71`; backend `symbol_readability.py:27-32`, `source_replacement_retirement.py:458-464` (payload w camelCase, zgodny) | ✅ |
| 1 | `entry.digest` jako nieprzejrzysty `scopeDigest`; origin pomijany | `replacement-repair.ts:137-145,179` (zwraca tylko znane pola) | ✅ |
| 1 | Prawdziwy fixture z PG | core test `:42` | ✅ |
| 2 | Tylko dokładne zakresy, bez min/max i zaokrąglania | `replacement-repair.ts:114-135,154-163`; listing `replacement-repair-storage.ts:119-123` | ✅ |
| 2 | Bieżący wpis porównywany po id/revision/scopeDigest/phase/sourceSha/zakresie/seq, bez globalnej rewizji batcha | `replacement-repair.ts:165-187`, `replacement-repair-storage.ts:282-303`; test `:312` | ✅ |
| 2 | `getGame` z skonfigurowanego API | `replacement-repair-workspace.tsx:157-160` | ✅ |
| 3 | Źródło tylko do odczytu, listowane bez czytania bajtów; B pomijane | `replacement-repair-storage.ts:97-127`, workspace `:184-186`; test `:120` | ✅ |
| 3 | Duplikaty wymagają ręcznego wyboru | workspace `:191-198,250-267`; interakcja `:71` | ✅ |
| 3 | Wynik osobny, nie ten sam i nie zagnieżdżony | `replacement-repair-storage.ts:85-95,339-342`; test `:142,149` | ✅ |
| 3 | Jedno zdjęcie naraz, bramka decode+300 ms | workspace `:90-95,284-289` | ⚠️ P2-1 |
| 4 | v3 zawiera request i journal o wymaganym kształcie | `replacement-repair.ts:14-34` | ✅ |
| 4 | Intent trwale zapisany przed JPEG, potem zapis, hash, commit, handoff | `replacement-repair-storage.ts:391-427` | ✅ |
| 4 | Stabilne opId, utracona odpowiedź, pending czeka na tę samą source | `:344-356,365-384`; testy `:153,180,352` | ✅ (⚠️ P2-2 w realnym Chrome) |
| 4 | Obcy, zmieniony lub częściowy cel kończy się fail-closed, bez adopcji i nadpisania | `:140-181,219-223,401-402`; testy `:264,323` | ✅ |
| 4 | Wspólny WebLocks per nazwa katalogu, fallback kolejką; prywatna inspekcja bez locka | `:184-196,305-321,332,343`; testy `:391,452` | ✅ |
| 5 | `deriveReplacementFilledGaps` daje niezmieniony v1 tylko z commitów zweryfikowanych | `replacement-repair.ts:280-322` | ✅ |
| 5 | Handoff należy do repairKey/katalogu; nieaktualny podzbiór regenerowany | `replacement-repair-storage.ts:144-180`; test `:421` | ✅ |
| 5 | Readery v1/v2 odmawiają v3 | `manual-selection-repair-storage.ts:146-152`; test `:176` | ✅ |
| 6 | Staging zachowuje request A+B, ale files tylko z jawnie wybranych commitów A | `replacement-repair.ts:324-360`; core test `:191` | ✅ |
| 6 | Bez endpointu ani typu API; lokalny zapis nie zamyka luki w backendzie | `replacement-repair.ts:324`; workspace `:313-316` | ✅ |

## Otwarte
- P2-1: bramka podglądu po przełączeniu wpisu lub duplikatu.
- P2-2: pozostałości `*.crswap` po awarii blokują wznowienie z mylącym komunikatem.
- P3-1 do P3-5: opcjonalne.

## Zamknięte (zweryfikowane w tej rundzie)
- Zgodność digestu TS z Pythonem: klucze w camelCase, `sort_keys`, kompaktowe separatory, ASCII i bezpieczne liczby całkowite.
- Kolejność zapisu: intent, JPEG, sprawdzenie sumy kontrolnej, commit, handoff.
- Brak adopcji i nadpisania obcego celu: `TARGET_EXISTS` i inwentarz.
- Prywatna inspekcja bez locka zapobiega zakleszczeniu w writerze.
- v1/v2 odmawia v3, w tym w `writeRepairManifest` przez `readRepairManifest`.
- Origin z pliku jest pomijany. Postęp innego wpisu nie unieważnia pozostałych.

## Proponowane testy
1. Interakcja: przełączenie `entryId` lub duplikatu przy opóźnionym `getFile()` (ponad 300 ms). Przycisk musi pozostać nieaktywny do zdekodowania nowego obrazu.
2. Storage: pozostały `seq_x-y.jpg.crswap` przy pending intent. Oczekiwane zachowanie zgodne z wybraną poprawką P2-2 (pominięcie albo dedykowany kod), bez adopcji.
3. Storage: `readActiveFilledGapsManifest` na v3 bez zmian nie zmienia bajtów ani mtime manifestu (jeśli wdrożone zostanie P3-1).
4. Walidacja: journal z `fileName` niebędącym stringiem lub `id` niebędącym UUID daje `REPLACEMENT_INVALID_JOURNAL`.

## Ograniczenia
- Przegląd statyczny i selektywny. Z budżetu 22 z 24 wywołań nie czytałem pełnych testów, `package.json` ani locka, `manual-selection-repair-workspace.tsx:60-72,1230-1260`, dokumentów planu i decyzji D580 ani szablonu raportu.
- Wyniki testów, tsc, ESLint i Prettier przyjmuję z deklaracji wykonawcy, bez weryfikacji.
- Zachowanie FSA w realnym Chromium (`.crswap`, uprawnienia, WebLocks między kartami) i fizyczny picker na Windows są poza tym audytem (D1/operator).
- Nie oceniam zakresu C2 i go nie rozszerzam.

**Oświadczenie:** audyt wykonałem wyłącznie statycznie (Read/Grep), bez modyfikacji plików i bez uruchamiania testów, komend ani usług.


## Rozliczenie koordynatora po R1 (nie jest ponownym audytem)

R1 został zachowany. Kontekst konsumenta cropu (permission=read) potwierdził funkcjonalny błąd kompatybilności odczytu handoffu: bezwarunkowe createWritable w readerze odmawiało poprawnemu katalogowi v3. Koordynator sklasyfikował ten kontekst jako P1-COMPAT mimo wstępnej uwagi P3-1 audytora. W jednej rundzie poprawek reader otrzymał read-only verify+derive persisted committed bez promowania intent; recovery jest wyłącznie jawne readwrite. Test readonly handle sprawdza brak createWritable, niezmienione bajty/mtime i pominięcie intent. Wymagany celowany R2 Opus5.5/medium przed commitem, bez ponownego pełnego audytu.

P2-1: cacheScope obejmuje entryId/source.fileName; test przełączenia duplicate przy opóźnieniu >400ms i decode+300ms PASS. P2-2: znany .crswap otrzymuje osobny failclosed kod i polską instrukcję, bez usuwania/adopcji; fizyczny Chromium smoke w D1. Brakujące komunikaty dostały polskie etykiety i polski fallback. Pozostałe uwagi: journal używa stabilnego nonempty operationId generowanego crypto.randomUUID; pending blokuje ogon celowo, a v1/v2 i v3 nie powinny równocześnie inicjalizować jednego pustego outputu. Bez rozszerzania starego workflow.
