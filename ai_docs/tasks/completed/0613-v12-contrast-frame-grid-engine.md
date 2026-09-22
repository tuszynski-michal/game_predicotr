---
title: V1.2 contrast-frame geometry engine
status: done
---

# TASK-0613 — Testowy silnik V1.2 kontrastowej ramki i siatki

## Status

`done`

## Goal

Udostępnić jawny, testowy wariant V1.2, który rejestruje dziewięć plansz po
lokalnym kontraście ramki, uczy per gra niezależnych marginesów siatki symboli
wyłącznie z ręcznie potwierdzonych par geometrii i nie wymaga czerwonego koloru.

## Context

T01 potwierdził, że klasyczny detektor czerwieni nie znajduje sam czterech
stron Mumii, a dotychczasowa ręczna korekta ma tylko jeden quad. V1.2 wymaga
dwóch jawnych ról: `boardFrameQuad` dla zewnętrznej planszy i
`symbolGridQuad` dla układu symboli. Stary pojedynczy `finalQuad` nie może
zostać niejawnie uznany za obie role.

## Dependencies / entry conditions

- TASK-0612 jest ukończony: raport jakości i cztery źródła Mumii są dostępne.
- Istnieje wersjonowana ręczna korekta strony i checksum-bound preflight.
- Przyjęte założenie implementacyjne: techniczny wariant nazywa się
  `contrast_frame_grid_v1_2`, jest opt-in i pozostawia domyślny V1.1 bez
  zmiany. Jego profil składa się z niezmiennych par ręcznych quadów bieżącej
  gry; pojedynczy pełny obraz (9 par) jest minimalnym materiałem profilu.

## Recommended execution

gpt-5.6-terra / xhigh. Zadanie zmienia wersjonowany kontrakt ręcznej geometrii,
preflightu i UI, dlatego wymaga osobnego review gpt-6-astra / medium po
własnym audycie. Krytyczny konflikt zgodności historycznych jobów lub wymóg
modyfikacji V1.1 blokuje task.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/V1_2_MUMIE_GEOMETRY_DIAGNOSIS.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Dodać wersjonowany wariant `contrast_frame_grid_v1_2`, dostępny wyłącznie
  jako jawny wybór nowego preflightu; default pozostaje V1.1.
- Zmienić override strony addytywnie: opcjonalne, kompletne pary
  `boardFrameQuads` i `symbolGridQuads`; gdy para istnieje, `finalQuads` musi
  być zgodne z `symbolGridQuads` dla kompatybilnego downstreamu.
- Zapisać i snapshotować per-game profil V1.2 tylko z ręcznie zapisanych,
  kompletnych par. Profil zachowuje obie geometrie, identyfikatory/revisions,
  źródłowe checksumy oraz własną checksumę; worker wyprowadza cztery odporne
  marginesy dopiero z przypiętego snapshotu.
- W workerze użyć rejestracji do manualnych kotwic tej samej gry, następnie
  lokalnego dopasowania czterech krawędzi z kontrastu jasności/barwy i
  niezależnego wyznaczenia siatki symboli. Nie ma wywołania maski czerwieni,
  miary red coverage ani klasycznego red detectora na ścieżce V1.2.
- Gdy brakuje profilu, kontrast jest niejednoznaczny, obrysy nie tworzą
  spójnej siatki 3 × 3 lub wynik siatki jest niebezpieczny, zwrócić
  `review_required`, bez automatycznego cropa i bez aktualizacji profilu.
- Dodać do Admina wybór V1.2 i dwie edytowalne warstwy korekty: ramkę planszy
  oraz siatkę symboli. Zapis obu jest świadomym potwierdzeniem; istniejąca
  korekta pojedynczego quada nadal działa dla V1.0/V1.1.
- Przypiąć wariant, wersję kontrastu i profil do joba/manifestu, tak aby retry
  oraz resume odtwarzały ten sam wynik. Zachować obsługę ostatniej strony
  500 000 przez istniejący wariant przepływu.

## Out of scope

- Zmiana algorytmu, domyślnego wyboru, snapshotów lub wyników V1.1.
- Jakiekolwiek zmiany kodu, danych, migracji, testów albo porządkowania V2.0
  i V2.1.
- Aktywacja produkcyjna, automatyczny import po niepewnej geometrii oraz
  dostrajanie modelu pod konkretne Mumie.

## Acceptance criteria

- [x] V1.2 jest dostępnym testowym wyborem, a brak wyboru nadal przypina V1.1.
- [x] Nowa ścieżka V1.2 nie odwołuje się do detekcji ani pokrycia czerwieni.
- [x] Ręczny zapis dwóch geometrii jest walidowany, checksummowany,
      przechowywany addytywnie i izolowany po `game_id`.
- [x] V1.2 używa tylko pełnych, ręcznie potwierdzonych par jako kotwic/profilu;
      stary pojedynczy quad nie jest materiałem uczącym.
- [x] Słaby lub sprzeczny wynik nie tworzy automatycznej geometrii importowej.
- [x] Preflight/retry przypinają wariant i profil; historyczne joby pozostają
      czytelne.
- [x] UI umożliwia niezależne zatwierdzenie obrysu i siatki bez pogorszenia
      korekty V1.1.

## Technical notes

`VerifiedPageRegistrar.initialize` może dostarczyć homografię do ręcznej
kotwicy bez uruchomienia jego kontroli czerwieni. V1.2 tworzy odrębny adapter,
który na tej projekcji analizuje lokalny gradient RGB/Lab po obu stronach
każdej przewidywanej krawędzi. Każda krawędź może przesunąć się tylko w
ograniczonym pasie wokół projekcji. Kandydat przechodzi jedynie przy stabilnym
maksimum kontrastu, dodatnim wymiarze i kompletnym uporządkowanym układzie 3 ×
3; w przeciwnym razie zostaje `review_required`.

Worker normalizuje każdą zatwierdzoną parę względem wyprostowanej ramki i
wyznacza cztery marginesy `left/top/right/bottom` jako mediany. Są one
wskazówką do ograniczonego, rozszerzonego obszaru analizy siatki, nigdy cropem
samym w sobie. Estymator symboli oraz jego kontrola, że linie nie przecinają
symboli, pozostają ostatnią bramką. Wynik preflightu serializuje zewnętrzne
`boardFrameQuads`, wyznaczone `symbolGridQuads`, dowody kontrastu i checksumę
profilu; kompatybilne `quads` pozostają obrysem wejściowym dla istniejącej
ścieżki V1.1/V1.0 downstreamu.

Automatyczne kotwice nie są promowane w V1.2. Zmiana, usunięcie albo
niezgodność checksumy dowolnej ręcznej pary z przypiętego profilu powoduje
utworzenie nowego preflightu, nigdy ciche użycie innego profilu.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/lateral_partial_contract.py`
  — wariant i capability.
- Nowe: `services/worker/src/game_predictor_worker/images/contrast_frame_grid_v12.py`
  — niezależna rejestracja V1.2 i profil marginesów.
- Istniejące: `services/worker/src/game_predictor_worker/images/page_geometry_preflight.py`
  — routing V1.2, snapshot i manifest.
- Istniejące: domena, serwis, repozytorium oraz model override strony w API;
  nowa migracja Alembic po 0117.
- Istniejące: schematy/API jobów i importów oraz wygenerowany klient OpenAPI.
- Istniejące: `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`
  i wybór silnika w imporcie.
- Nowe/skoncentrowane: testy API, workera i Admina dla V1.2.

## Test cases

- Ręczna para 9 ramka→siatka → profil tej samej gry z czterema marginesami;
  pojedynczy legacy quad → brak profilu V1.2.
- Dwie gry z różnymi parami → snapshot jednej nie zawiera drugiej.
- Kontrastowe ramki czerwone, niebieskie i ciemne/jaśniejsze → V1.2 mierzy
  krawędzie bez pola lub funkcji red coverage.
- Niepewny kontrast, niekompletne 3 × 3, niebezpieczny wynik siatki →
  `review_required`, bez `registered` i bez profilu.
- V1.2 retry/resume → identyczny wariant/profil/checksum; zmiana pary → nowy
  snapshot.
- V1.1/historyczny job → niezmieniony payload i rezultat.
- Edytor V1.2 zapisuje obie warstwy; edytor V1.1 nadal wysyła wyłącznie
  `finalQuads`.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
.venv\Scripts\python.exe -m pytest services/api/tests/test_page_geometry_overrides.py services/api/tests/test_browser_image_imports.py services/worker/tests/test_contrast_frame_grid_v12.py services/worker/tests/test_page_geometry_preflight.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/page_geometry_overrides.py services/api/src/game_predictor_api/application/page_geometry_overrides.py services/api/src/game_predictor_api/storage/page_geometry_override_repository.py services/worker/src/game_predictor_worker/images/contrast_frame_grid_v12.py services/worker/src/game_predictor_worker/images/page_geometry_preflight.py
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin -- --file src/features/imports/page-geometry-correction-panel.tsx --file src/features/imports/image-folder-import-panel.tsx
git diff --check
```

## Risks / open questions

- Pierwsze pełne przykłady Mumii mogą wymagać ręcznego zatwierdzenia obu
  warstw. To jest oczekiwany koszt startowy, nie automatyczny backfill danych.
- Odbiór dokładności wizualnej nie należy do T02; T03 przygotuje nakładki do
  oceny operatora.

## Outcome

### Implementacja

- Dodano migrację `0118`, addytywny zapis par `boardFrameQuads` /
  `symbolGridQuads`, walidację zawierania i checksummowany snapshot profilu
  per `game_id`.
- Dodano `contrast_frame_grid_v12.py`: manualne kotwice tej samej gry,
  docisk czterech granic po kontraście RGB, medianę czterech marginesów po
  homografii i bezpieczny estymator siatki symboli.
- API, manifest schema 4 i Admin przypinają profil do preflightu. Panel ma
  dwie warstwy do potwierdzenia. Import/reprocess V1.2 są zablokowane do
  odbioru wizualnego; V1.1 nie jest modyfikowany.

### Weryfikacja

- Końcowy zestaw skoncentrowany: 19 testów Python oraz 5 testów
  interakcyjnych i 15 testów kontraktowych/szkicu Admina.
- Przeszły: targeted Ruff, `compileall`, OpenAPI generate/check, typecheck,
  Prettier i ESLint zmienionych plików (pozostaje tylko istniejące ostrzeżenie
  `<img>` w panelu importu).
- Własny audyt naprawił odwrócone przekształcenie perspektywy podczas docisku
  kontrastu oraz regresję, w której para V1.2 mogła zmienić payload V1.1.
  Audyt Astra Medium usunął błąd konwersji wyniku estymatora, obsługę
  konkurujących granic, niepełny podgląd automatycznych warstw i możliwość
  potwierdzenia jedynie proponowanej ramki.

### Ograniczenia

- T02 nie jest odbiorem wizualnym Mumii; V1.2 celowo nie wykonuje importu.
- Pierwszy pełny kadr Mumii wymaga ręcznego potwierdzenia obu warstw, zanim
  może zostać kotwicą dla kolejnych zdjęć.
