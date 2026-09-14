---
title: Status etapu gotowego stagingu importu plansz
status: done
last_updated: 2026-09-14
---

# TASK-0543 — status etapu gotowego stagingu importu plansz

## Status

`done`

## Goal

Każdy staging w sekcji `Import plansz z manifestu` pokazuje przy liczbie plików,
rozmiarze i skrócie ID trwały etap pracy oraz jednoznacznie oznacza jako
`gotowy` import, który zakończył cięcie zdjęć na symbole.

## Context

Lista stagingów pokazuje dziś wyłącznie metadane folderu. Operator nie może z
niej odróżnić folderu dopiero załadowanego od stagingu z przygotowanym
preflightem, gotową siatką albo zakończonym importem symboli.

## Dependencies / entry conditions

- Gotowe stagingi mają trwały `uploadId` i checksumę manifestu.
- Panel już pobiera joby importu i preflightu geometrii dla aktywnej gry.
- Payload obu rodzajów jobów zawiera `sourceSelectionId` oraz
  `sourceManifestSha256`, więc etap można związać z dokładnym stagingiem bez
  zmiany API.

## Recommended execution

`gpt-6-astra` z poziomem `high`. Zmiana jest mała, ale wymaga poprawnego
ustalenia pierwszeństwa trwałych etapów i zabezpieczenia przed przypisaniem joba
innego manifestu. Dodatkowy review jest potrzebny dopiero przy zmianie kontraktu
API lub semantyki lifecycle jobów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Dodać czystą funkcję wyznaczającą etykietę etapu stagingu z istniejących
  jobów i aktywnego raportu.
- Pokazać etykietę bezpośrednio po tekście `staging <skrót>`.
- Rozpoznać etapy: `załadowano folder`, `przygotowano preflight`,
  `przygotowano siatkę` oraz `gotowy`.
- Zwiększyć ograniczone pobranie historii do wartości wystarczającej dla całej
  widocznej listy stagingów.
- Dodać regresje pierwszeństwa etapów i dopasowania checksummy.

## Out of scope

- Nowy endpoint lub pola OpenAPI.
- Zmiana lifecycle jobów, ich uruchamianie, retry albo dane użytkownika.
- Usuwanie zakończonych stagingów.

## Acceptance criteria

- [x] Folder bez raportu pokazuje `oczekuje na operację · załadowano folder`.
- [x] Otwarty raport albo zgodny job geometrii pokazuje co najmniej
      `oczekuje na operację · przygotowano preflight`.
- [x] Ukończony zgodny preflight z manifestem siatki pokazuje
      `oczekuje na operację · przygotowano siatkę`.
- [x] Zgodny import w stanie `waiting_for_review` albo `completed` pokazuje
      `gotowy`.
- [x] Job obcego `uploadId` albo innej checksummy nie podnosi etapu stagingu.
- [x] Stan po odświeżeniu wynika z danych API, a nie tylko z pamięci komponentu.

## Technical notes

Etapy mają rosnące pierwszeństwo: folder → preflight → siatka → gotowy. Import
jest gotowy po zakończeniu przetwarzania obrazów i utworzeniu kolejki symboli,
czyli dla `waiting_for_review`, oraz pozostaje gotowy po `completed`. Preflight
siatki jest uznany za przygotowany wyłącznie dla joba `completed` z niepustą
`geometryManifestChecksumSha256`. Dopasowanie wymaga jednocześnie ID stagingu i
checksummy jego manifestu. Sam aktywnie otwarty raport może podnieść etap do
preflightu, ale trwałe wyższe etapy po odświeżeniu wynikają z historii jobów.

## Expected files

- Istniejący: `apps/admin/src/features/imports/image-folder-import-state.ts` —
  wyznaczanie etapu.
- Istniejący: `apps/admin/src/features/imports/image-folder-import-panel.tsx` —
  render etykiety i zakres pobranej historii.
- Istniejący: `apps/admin/test/image-folder-import-state.test.mjs` — regresje
  logiki etapów.
- Istniejący: `apps/admin/test/image-folder-import-panel-contract.test.mjs` —
  kontrakt położenia informacji.
- Istniejący: `ai_docs/requirements/ADMIN_APP.md` — wymaganie prezentacji.
- Istniejący: `ai_docs/process/CURRENT_STATE.md` — wynik zadania.

## Test cases

- Brak jobów i zamknięty raport → etap załadowanego folderu.
- Aktywny raport lub rozpoczęty/nieudany zgodny job geometrii → przygotowany
  preflight.
- Ukończony job geometrii bez checksummy wyniku → nadal przygotowany preflight.
- Ukończony job geometrii z checksumą wyniku → przygotowana siatka.
- Import `waiting_for_review` i `completed` → gotowy.
- Obcy staging lub stara checksumma → brak awansu etapu.

## Verification

```powershell
npm --workspace @game-predictor/admin run test -- --test-name-pattern "staging|etap|manifest"
npm --workspace @game-predictor/admin run typecheck
npm --workspace @game-predictor/admin run lint
```

Kryterium zaliczenia: testy zmienionego pionu, typecheck i lint Admina kończą
się bez błędów, a rzeczywisty staging `c2547b09` jest rozpoznany jako `gotowy`
na podstawie joba `waiting_for_review`.

## Risks / open questions

- Historia jobów pozostaje ograniczona; limit 200 chroni endpoint przed
  nieograniczonym odczytem. Bardzo stary staging poza tym oknem może pokazać
  wcześniejszy etap do czasu otwarcia jego raportu.

## Outcome

### Changed

- Dodano checksum-bound wyznaczanie najwyższego etapu stagingu i etykietę
  bezpośrednio po `staging <skrót>`.
- Import w `waiting_for_review` albo `completed` jest oznaczany jako `gotowy`;
  wcześniejsze etapy rozróżniają folder, preflight i gotową siatkę.
- Zwiększono ograniczone odczyty jobów importu i walidacji do 200, aby status
  obejmował widoczną historię stagingów.

### Verification results

- `node --experimental-strip-types --test --test-isolation=none apps/admin/test/*.test.mjs`
  — 466/466 testów zaliczonych.
- `npm --workspace @game-predictor/admin run typecheck` — zaliczony.
- `npm --workspace @game-predictor/admin run lint` — zaliczony.
- Odczyt działającego API i wykonanie nowego selektora dla `c2547b09` zwróciły
  `2611 plików · 690.0 MB · staging c2547b09 · gotowy`.

### Not completed

- Nie zmieniano API, jobów ani danych użytkownika; nie było to potrzebne.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`

### Recommended next task

- Brak; zakres zgłoszenia jest zamknięty.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0543 | gpt-6-astra | high | Ustalenie deterministycznego pierwszeństwa trwałych etapów istniejącego workflow i test regresyjny ma umiarkowane ryzyko UI. | Nie; `gpt-6-astra` z `xhigh` tylko przy zmianie API lub lifecycle jobów. |
