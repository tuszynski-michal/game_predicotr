---
title: Przejęcie starej sesji
status: done
last_updated: 2026-10-11
---

# TASK-0978 — Przejęcie starej sesji

## Status

`done`

## Goal

Utworzyć projekt desktopowy z dowodowo zgodnej sesji operator-local v1/v2 bez modyfikowania oryginału.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

TASK-0979 — część implementacyjna wydania gotowa. Operator uruchomił 0978 poleceniem wykonania pięciu tasków. Końcowy audyt operatora po całym zakresie. Został dołączony do bieżącego zlecenia; brak fizycznego odbioru 0979 nie zatrzymuje implementacji 0978.

## Recommended execution

`gpt-6.1-sol / high`. Operator wykona końcowy audyt całego zakresu; zalecany model
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
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md — TASK-0978
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md — obowiązująca sekcja operator-local
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Read-only odczyt manifestów operator_local v1/v2, preview i jawne utworzenie nowego projektu.
- Walidacja tożsamości źródła, powiązań ordinal/path, JPEG-ów i checksum.
- Zachowanie numeracji, decyzji, natural_v2/legacy cursor semantics i końcowej granicy.
- Brak automatycznego złagodzenia zgodności po różnej checksumie metadanych.

## Out of scope

Zmiana oryginalnej sesji, odczyt cudzego IndexedDB, core-items manifest, import zmienionego źródła na podstawie domysłu o mtime.

## Acceptance criteria

- [x] Zgodny komplet source/output odtwarza ten sam postęp; oryginał jest nietknięty.
- [x] Nieznany format, brak checksum/dowodów, zmieniona lista i różne JPEG checksums blokują.
- [x] Manifest core-items nie jest traktowany jako operator_local.
- [x] Nie można uznać dowolnej różnicy checksummy za zmianę wyłącznie dat plików.

## Technical notes

buildRemoteSourceManifestV1 zawiera sizeBytes i lastModifiedMs. Sam historyczny output przechowuje checksum, nie kompletny porównywalny source inventory. Jeśli nie można dowieść zgodności, nie rekonstruuj utraconych informacji z aktualnego folderu jako faktów historycznych. Rozszerzenie migracji skopiowanego źródła ze zmienionymi mtime wymaga oddzielnego planu dowodów.

Dodatkowa zgodność: Reviewer używa File.type w źródłowym fingerprint,
a desktop image/jpeg. Nietypowy historyczny MIME może więc blokować przejęcie
pomimo tych samych nazw plików. Nie zmieniać fingerprint ani metadanych,
aby wymusić migrację. Brak sourceManifestChecksumSha256/fileCount lub
niejednoznaczna konfiguracja historycznego v1 nie dowodzą zgodności.

Jawne ograniczenie zgodności: v1 wymaga zapisanych firstLayout/direction.
Historyczny końcowy v1 w kierunku malejącym (zakres1–9, bez semantyki
selectionComplete v2) może mieć sprzeczny stan kontynuacji. Taki manifest
jest odrzucany, zamiast zmieniać ukrycie postęp lub regułę zakończenia.
Wynika to z zachowania semantyki i fail-closed przejęcia zgodnej sesji.
Historię z powtórną akceptacją tej samej source path również odrzucamy:
parser starego formatu ją toleruje, ale GUI Reviewera i bieżący desktop
nie pozwalają tworzyć takich decyzji. Nie rozszerzamy domeny ukrytym wyjątkiem.

Jawne założenie formatu: brak historycznego pola bieżącej generacji partii
nie pozwala odtworzyć go jako osobnego faktu. Zachowujemy selectionGeneration
każdej decyzji; nowy lokalny licznik to ich maksimum lub0 przy pustej historii.
Nie wpływa to na numerację, kursor ani pliki oryginału.

## Expected files

- Nowe, proponowane: apps/selector-desktop/src/legacy-adoption/ i test/legacy*.test.mjs.
- Istniejące tylko do odczytu: OperatorLocalOutputManifestV1/V2, resumeOperatorLocalBatch, buildRemoteSourceManifestV1.
- Dokumentacja procesu migracji i task Outcome.

## Test cases

- v1/v2, rosnący/malejący, legacy bez natural_v2, końcowy zakres.
- Obcy core-items, brak source fingerprint, missingseq, changedJPEG, różne mtime.
- Anulowane preview i błędny import pozostawiają oryginalne pliki identyczne.

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

Wykonanie uruchomiło późniejsze polecenie operatora dotyczące pięciu tasków. Historyczny manifest może nie zawierać wystarczających dowodów.

## Outcome

### Changed

Zaimplementowano read-only preview operator-local v1/v2, weryfikację fingerprint,
ordinal/path i dokładnego zestawu wyników oraz SHA źródłowych/wynikowych JPEG-ów.
Nowy projekt i wynik są puste i niezależne od oryginału. Seed zachowuje historię,
kursor, numerację i generacje decyzji bez powtarzania accept. Journal schema v2
z importCopies umożliwia wieloplikowy recovery; zwykły journal v1 pozostaje zgodny.
Native controller/IPC używa opaque tokena preview oraz oddzielnego SourceRegistry.
Renderer pokazuje podgląd, anulowanie i jawne potwierdzenie nowych lokalizacji.
Przy recovery także już istniejący imported JPEG wymaga ponownego SHA źródła.

Commit implementacji v1.7.322 zostanie zapisany pełnym hashem po commicie.

### Verification results

Wszystkie skończone kroki ograniczono run-bounded.mjs do120 s. Łącznie107
unikalnych testów PASS: kontrakt legacy25, recovery29, zwykły projekt43,
foundation7, UI3. test:legacy początkowo24/24 (21,725 s), dodatkowe dwa testy
new roots/historical browser2/2 (8,512 s; jeden nowy unikalny przypadek).
Legacy recovery17/17 (80,082 s), fault/rechecks12/12 (31,657 s) i wersje/realne
nowe procesy4/4 (44,427 s). Grupy zwykłego projektu17/17,12/12,14/14, następnie
wąskie replay/process-death2/2. Nie sumujemy powtórzeń jako nowych przypadków.

Lint, typecheck, Prettier, git diff --check oraz package z buildem PASS.
smoke:legacy rzeczywistego EXE PASS: preview/anulowanie, odmowa dowolnej ścieżki
zamiast tokena, import, identyczne oryginały i kontynuacja w nowym procesie.
Screenshot podglądu sprawdzono wizualnie. EPERM realpath oraz cache Electron
w sandbox rozwiązano eskalowanym wykonaniem, bez zmiany kontraktu testów.
Rdzenia/Reviewera nie zmieniano; wcześniejsze110/110 i264/264 nie są nowym
wynikiem0978. Finalny ZIP z committed runtime zostanie osobno przebudowany.
Mapę zregenerowano. docs:check PASS (542 decyzje/odnośniki/wiersze indeksu,
43 aktywne taski,10 done); code-map:check PASS. Ruff check i format generatora PASS.

### Not completed

Końcowy audyt operatora i fizyczny odbiór0979. Nie wykonano benchmarków,
operacji na zdjęciach operatora, uploadu, usług API/Admin ani migracji.
Brak dowodów, różnica MIME/mtime/fingerprint, niejednoznaczny v1, niezgodny
końcowy malejący v1 oraz powtórzona akceptacja tej samej source path blokują
import. Oryginał pozostaje dostępny w dotychczasowym narzędziu. Nie rozszerzono
zakresu o dowody dla zmienionych metadanych. Awaria procesu ma testy recovery;
nie obiecujemy gwarancji po awarii dysku lub zasilania.

### Documentation updates

Wymagania, architektura, plan, instrukcja, TRACEABILITY, README, mapy,
CURRENT_STATE i zestawienie przekazania opisują implementację oraz ograniczenia.
Task przeniesiono do completed. Generacja nowej partii to maksimum generacji
zachowanych decyzji lub0, ponieważ stary manifest nie ma osobnego pola.

### Recommended next task

Końcowy audyt operatora całych pięciu tasków i fizyczny odbiór0979. Brak push,
merge lub dalszej implementacji bez nowego zlecenia.
