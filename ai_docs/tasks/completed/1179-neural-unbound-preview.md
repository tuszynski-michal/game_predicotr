---
title: Filtrowanie nieprzypisanych zdjęć i aktywacja modelu 777 a2
status: done
last_updated: 2026-11-10
---

# TASK-1179 — Nieprzypisane zdjęcia importu 777 a2

## Status

`done`

## Goal

Przycisk przypisywania plansz pokazuje wyłącznie nieprzypisane zdjęcia;
zgodny model symboli 777 a2 jest aktywny i raport dopuszcza ręczny start importu.

## Context

Operator zgłosił staging `be8b7266-1bce-44ca-a6c0-f008a4e242f8` (2201 zdjęć).
Preflight `11ca95db-c294-4bdb-b37d-65be18a46856` jest ukończony. Jedno zdjęcie
`seq_10657-10665.jpg` nie ma przypisania slotów (9 plansz). Przycisk otwiera
wszystkie propozycje, a import blokuje osobno `SYMBOL_MODEL_ACTIVATION_REQUIRED`.
Operator jawnie zlecił poprawkę i aktywację właściwego modelu 2026-11-10.

## Dependencies / entry conditions

- Zgoda dotyczy aktywacji istniejącego, zgodnego kandydata dla 777 a2;
  nie obejmuje treningu, startu importu, restartu usług, merge ani push.
- Wybór: iteracja 5 `9afa868a-70f8-42df-9f15-f2833cd98c10`, candidate_ready,
  preview canActivate=true, brak obecnej aktywacji. Test 99,401198% / 167,
  regression 100% / 151; bramka bez odrzuceń. Nowszy własny kandydat gry.
- Założenie: filtr korzysta z istniejących kodów powodu, nie z liczby propozycji.

## Recommended execution

Bieżąca sesja Codex; mała poprawka istniejącego UI bez osobnego planu,
delegowania, zmiany API ani dodatkowego audytu wymaganego przez plan.
Sprzeczny preview aktywacji lub niedopuszczony kandydat zatrzymuje aktywację.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — zdjęcia V3 bez przypisania plansz.
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md` — model gry i aktywacja.
- `ai_docs/architecture/API_CONTRACT.md` — browserowy raport i kolejka geometrii.
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md` — aktywacja i snapshot importu.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `.agents/skills/task-close/SKILL.md`

## Scope

- Opcjonalny filtr edytora po powodach NEURAL_GRID_SLOT_BINDING_REQUIRED
  i NEURAL_GRID_SOURCE_TIME_LIMIT; zapisane korekty nie wracają do kolejki.
- Przycisk ostrzeżenia uruchamia filtr; osobna akcja przywraca pełny podgląd.
- Domyślne zachowanie pozostałych konsumentów i globalne liczniki bez zmian.
- Preview i jawnie zlecona aktywacja iteracji 5 dla właściwej gry.
- Nowy proces potwierdza aktywację i odczytuje aktualny raport stagingu.

## Out of scope

- Zmiana reguł slotów, geometrii lub dopuszczania importu; usuwanie zdjęcia.
- Import, trening, reinferencja, migracje, restart usług i scalanie.

## Acceptance criteria

- [x] Przycisk ostrzeżenia pokazuje tylko nieskorygowane źródła z dwóch powodów braku przypisania.
- [x] Pełny podgląd pozostaje dostępny i nie dziedziczy filtra po ponownym otwarciu.
- [x] Filtrowany podgląd nie zmienia globalnego licznika wszystkich propozycji.
- [x] Regresja domyślnego podglądu oraz test interakcji przechodzą.
- [x] Iteracja 5 aktywna; nowy raport ma symbolModelReady=true i gotowy manifest geometrii.
- [x] Import operatora nie został uruchomiony; pominięcie jednego źródła nadal wymaga jego potwierdzenia.

## Technical notes

Filtr jest opcją PageGeometryCorrectionPanel, domyślnie false. Rodzic wiąże
tryb z konkretnym jobem preflightu. Zmiana trybu resetuje instancję edytora;
zapisane drafty pozostają przypisane do źródła. Filtr nie zastępuje backendowej
walidacji ani nie ukrywa globalnych liczników. Aktywacja używa istniejącego
preview, checksumy manifestu i standardowych nagłówków potwierdzenia API.

## Expected files

- `apps/admin/src/features/imports/image-folder-import-panel.tsx` — akcja i zakres podglądu.
- `apps/admin/src/features/imports/page-geometry-correction-panel.tsx` — opcjonalny filtr.
- `apps/admin/test-interactions/neural-import-readiness.test.mjs` — interakcja i regresje.
- `apps/admin/test/image-folder-import-panel-contract.test.mjs` — nowy zakres podglądu i ochrona licznika.
- `ai_docs/requirements/IMAGE_INGESTION.md` — doprecyzowanie podglądu.
- Mapa kodu, ten task i dokumentacja stanu aktualizowana przez task-close.

## Test cases

- Trzy propozycje, jedno źródło bez slotów → po kliknięciu widoczne tylko ono.
- Osobno oba powody; zapisane źródło nie wraca. Przełączenie na pełny podgląd → wszystkie niezapisane.
- Zamknięcie i otwarcie pełnego podglądu oraz odtworzenie po remount → domyślny pełny zakres.
- Brak wywołań startu importu podczas otwierania i przełączania podglądu.

## Verification

Z katalogu repozytorium; każda komenda z timeoutem 120 s:

```powershell
node node_modules/tsx/dist/cli.mjs --tsconfig apps/admin/tsconfig.json --test apps/admin/test-interactions/neural-import-readiness.test.mjs
node --experimental-strip-types --test apps/admin/test/page-geometry-correction-panel-contract.test.mjs apps/admin/test/image-folder-import-state.test.mjs
npm exec --workspace @game-predictor/admin -- eslint src/features/imports/image-folder-import-panel.tsx src/features/imports/page-geometry-correction-panel.tsx
npm run typecheck --workspace @game-predictor/admin
.venv/Scripts/python.exe scripts/generate_code_map.py
npm run docs:check
git diff --check
```

Test interakcji uruchomić z konfiguracją tsx z package.json (tsx --tsconfig
apps/admin/tsconfig.json --test). Build Admina tylko jako kontrola artefaktu;
nie restartować działającej usługi bez zgody.

## Risks / open questions

- Aktywacja wpływa na nowe importy i nie zmienia snapshotów historycznych jobów.
- Produkcyjny Admin może wymagać osobnego builda/restartu; brak zgody w tym zadaniu.

## Outcome

Commit: v1.7.594 (hash dopisuje kolejny commit).

### Changed

- „Przypisz plansze ręcznie” otwiera wyłącznie niezapisane zdjęcia o powodach
  NEURAL_GRID_SLOT_BINDING_REQUIRED lub NEURAL_GRID_SOURCE_TIME_LIMIT.
- Opcja wspólnego edytora jest domyślnie wyłączona. Filtr jest związany z jobem;
  pełny podgląd wraca po osobnej akcji lub zamknięciu i ponownym otwarciu.
  Zmiana trybu resetuje instancję; filtrowana lista nie nadpisuje globalnego licznika.
- Aktywowano własnego kandydata 777 a2, iteracja5 `9afa868a-70f8-42df-9f15-f2833cd98c10`;
  manifest `962769e1cd1b239049e755701ebc7ec8858ecb71b032adf9847bc0e1ed7c87fb`.
  Preview zezwalał na aktywację, brak poprzedniej aktywacji; gate bez odrzuceń.
- Zdarzenie aktywacji1: `0a80edd0-119c-4961-ba28-28d0d305d338`,
  czas `2026-11-10T14:22:38.098127Z`, idempotency key
  `a3964052-d9bc-58a2-9ce3-16b1c2657415`. Aktor: Codex na jawne polecenie operatora.

### Verification results

- `node node_modules/tsx/dist/cli.mjs --tsconfig apps/admin/tsconfig.json --test`
  z `neural-import-readiness.test.mjs` i `neural-source-binding.test.mjs`: 22/22 PASS.
  Nowy test osobno obejmuje oba powody, zapisane źródło, pełny podgląd,
  zamknięcie/otwarcie, zachowanie globalnego licznika i brak startu jobów.
- `node --experimental-strip-types --test` dla `page-geometry-correction-panel-contract`,
  `image-folder-import-state`, `image-folder-import-panel-contract` i
  `neural-import-preflight`: 57/57 PASS. Dwa istniejące wzorce source-contract
  uaktualniono do nowego zakresu podglądu i warunkowego callbacka;
  nie usunięto kontroli potwierdzenia pominięcia.
- Prettier --check: PASS. ESLint zmienionych 4 plików: 0 błędów,
  4 zastane ostrzeżenia (img i nieużywane symbole poza zmienionymi fragmentami).
- `npm run typecheck --workspace @game-predictor/admin`: PASS.
- Regeneracja mapy kodu: wykonana, wynik identyczny z HEAD.
- Nowy proces odczytał zapisaną aktywację. Nowy raport stagingu:
  symbolModelReady=true, symbolModelBlockerCode=null, geometryPreflightArtifactReady=true,
  geometryEngineVariantEnabled=true, neuralUnboundSourceCount=1, liczba plansz=9,
  existingImportJob=null. Fingerprint inferencji symboli:
  `60f14be94287cbade532616227d643ce2974c916b10c670830aa3765cfe98cfb`.
- Admin działa jako `next dev` na3000, nie wymaga builda ani restartu dla tej poprawki.
- `git diff --check`: PASS. `npm run docs:check`: PASS — linki, okno stanu,
  11/11 budżetów (odczyt startowy43 104 B) i 2 pary kopii skilli.
- Brak osobnego planu wymagającego audytu; dodatkowy audyt nie jest wymagany.

### Not completed

- Nie uruchomiono importu, reinferencji, treningu ani restartu usług.
- Bez fizycznego testu Androida i pełnego builda aplikacji. UI zweryfikowano
  testami interakcji w JSDOM, bez odczytu niezwiązanych okien użytkownika.
- Bez merge i push; poprawka na `codex/777a2-import-binding-filter`.

### Documentation updates

- Doprecyzowano filtr w IMAGE_INGESTION.md; task, aktualny stan i archiwum
  zamykane standardowym task-close. API i model danych nie zmieniły się.

### Recommended next task

- Odbiór operatora: odświeżyć stronę i raport stagingu; poprawić wskazane źródło
  albo potwierdzić pominięcie jednego zdjęcia i samodzielnie rozpocząć import.
- Integracja poprawki po akceptacji wyniku i zgodzie na merge/push.
