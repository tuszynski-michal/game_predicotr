---
title: TASK-0632 — automaticPageProposal w liście korekt geometrii strony
status: done
last_updated: 2026-09-24
---

# TASK-0632 — `automaticPageProposal` w liście korekt geometrii strony

## Status

`done`

## Goal

Endpoint `review-sources` dołącza opcjonalne, walidowane pole
`automaticPageProposal` (kopia `lateralRegistrationCandidate.analysisQuads`)
dla źródeł `review_required` bez istniejącej geometrii, tak aby edytor
korekty mógł w kolejnym tasku (T2) wystartować od tej propozycji zamiast od
pustego szablonu.

## Context

Staging `0935f4ba-63b4-4e32-a64e-521be4ef28f9` ma 33 strony
`review_required`, z czego 33/33 ma w manifeście preflightu
`lateralRegistrationCandidate` z 9 `analysisQuads` trafiającymi dobrze pełne
plansze (przycięte plansze wychodzą poza kadr, co jest oczekiwane i celowo
obsłużone w T2 jako `pending_partial`). Dziś `list_browser_page_geometry_review_sources`
(`services/api/src/game_predictor_api/api/image_imports.py`) ignoruje ten
kandydat całkowicie — operator widzi pusty, wyśrodkowany szablon 9 plansz i
musi ustawiać wszystko ręcznie, mimo że dobra propozycja już istnieje w
manifeście. Pełny kontekst i uzasadnienie decyzji: plan „wstępna geometria z
automatycznej propozycji dla przyciętych stron" (sesja 2026-09-24,
zarchiwizowany w tej rozmowie, patrz też D-439 po ukończeniu T1).

To jest T1 z 3-taskowego planu (T1 → T2 → T3). T2 (edytor wypełnia siatkę
propozycją) i T3 (przesuwanie całej planszy) to osobne zadania, każde wymaga
osobnego polecenia użytkownika.

**Uwaga o renumeracji:** oryginalny plan proponował `TASK-0624`/`TASK-0625`/
`TASK-0626` i `D-433`. W repo te numery są już zajęte przez ukończone,
niepowiązane taski (`0624-symbol-review-page-skip.md`,
`0625-partial-visibility-domain-renderer.md`,
`0626-partial-visibility-pipeline-review.md`) i decyzję („Lekki skok stron w
Weryfikacji symboli..."). To drobna różnica techniczna (PLAN_STANDARD.md) —
ten task używa `TASK-0632` (pierwszy wolny numer), a docelowy wpis
`DECISION_LOG.md` użyje `D-439` (pierwszy wolny po `D-438`). T2 i T3 z tego
samego planu, gdy zostaną zlecone, powinny użyć `TASK-0633`/`TASK-0634`.

## Dependencies / entry conditions

- Brak zależności od innych niedokończonych tasków. Kod `lateral_candidate_from_entry`
  (`services/worker/src/game_predictor_worker/images/lateral_partial_artifact.py:104`)
  pokazuje zweryfikowany kształt `lateralRegistrationCandidate` i dozwolone
  wartości `recoveryKind`, ale nie jest reużywany bezpośrednio (inny kontrakt:
  ten kod waliduje pełny import, nie pomoc edytora).
- Worker, manifest i `geometry_origin` nie zmieniają się w tym tasku.

## Recommended execution

`claude-sonnet-5`, reasoning `high`. Zmiana kontraktu API w pełnym pionie
(FastAPI, OpenAPI, klient); logika walidacji jest prosta, ale wymaga
dyscypliny w generowaniu klienta. Eskalacja: jeśli `npm run openapi:check`
wykaże zmianę poza nowym polem, zatrzymać się i zgłosić rozbieżność zamiast
naprawiać niezwiązany dryf. Dodatkowy review nie jest wymagany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md` (sekcja `review-sources`, ok. l. 3156–3205)
- `ai_docs/requirements/IMAGE_INGESTION.md` (ok. l. 100–115)

## Scope

- `services/api/src/game_predictor_api/schemas/image_imports.py`: nowy
  `AutomaticPageGeometryProposalPayload` i pole `automatic_page_proposal` na
  `BrowserPageGeometryReviewSourceResponse`.
- `services/api/src/game_predictor_api/api/image_imports.py`: helper
  wypełniający to pole wyłącznie dla `geometry_origin == "manual_template"`,
  z pełną walidacją read-only (żaden błąd walidacji nie wyjątkuje ani nie
  blokuje listy — po prostu `None`).
- `packages/admin-api-client`: `npm run openapi:generate` (tylko
  wygenerowane pliki), test klienta.
- Dokumentacja: `API_CONTRACT.md`, `IMAGE_INGESTION.md` (jedno zdanie każdy),
  `DECISION_LOG.md` (`D-439`), `CURRENT_STATE.md`.

## Out of scope

- Worker, manifest, `page_geometry_registration.py`, `page_geometry_preflight.py`.
- Edytor Admin (`page-geometry-correction-panel.tsx`) — to T2.
- Przesuwanie całej planszy — to T3.
- `geometry_origin`, `review_required_source_count`, blokada importu,
  `automatic_partial_proposals`.
- Ręczna edycja wygenerowanych typów klienta.

## Acceptance criteria

- [ ] `BrowserPageGeometryReviewSourceResponse` ma opcjonalne pole
      `automaticPageProposal` (JSON), pomijane gdy `None`.
- [ ] Pole obecne wyłącznie dla `geometry_origin == "manual_template"` i
      wyłącznie gdy `lateralRegistrationCandidate` przechodzi pełną walidację
      opisaną w Technical notes.
- [ ] Istniejące testy `test_image_imports_api.py` (w tym l. ~1858, ~2296)
      przechodzą bez zmiany asercji.
- [ ] Nowe testy pokrywają: happy path (propozycja obecna, punkt poza
      kadrem), brak `analysisQuads`, niezgodną liczbę quadów, punkt
      zmiennoprzecinkowy, punkt poza dozwolonym zakresem, nieznany
      `recoveryKind`, brak wymiarów obrazu, istniejący override (propozycja
      ma być pominięta).
- [ ] `npm run openapi:generate` + `npm run openapi:check` przechodzą, diff
      zawiera wyłącznie nowe pole/typ.
- [ ] `mypy --strict` i `ruff` czyste dla zmienionych plików.

## Technical notes

**Aktualne zachowanie:** `list_browser_page_geometry_review_sources`
(`api/image_imports.py:1229`) buduje `BrowserPageGeometryReviewSourceResponse`
z `raw` (wpis manifestu) i nigdy nie czyta `raw["lateralRegistrationCandidate"]`.

**Wymagane zachowanie:**

1. Schemat (`schemas/image_imports.py`), wzorem `AutomaticPartialGeometryProposalPayload`
   i `exclude_if` na `automatic_partial_proposals` (l. 511–513):

   ```python
   class AutomaticPageGeometryProposalPayload(ApiModel):
       origin: Literal[
           "lateral_source_support", "frame_support_review", "standalone_frame_lines"
       ]
       quads: list[list[ManualSourceGeometryPoint]] = Field(min_length=1, max_length=9)
       review_slots: list[Annotated[StrictInt, Field(ge=0, le=8)]] = Field(
           default_factory=list, max_length=9
       )
   ```

   Uwaga: pole `origin` w tym payloadzie odpowiada `recoveryKind` z surowego
   manifestu (worker nazywa to inaczej niż API — patrz `lateral_partial_artifact.py:177`
   `recovery_kind = raw.get("recoveryKind", "lateral_source_support")`).
   `automatic_page_proposal: AutomaticPageGeometryProposalPayload | None = Field(default=None, exclude_if=lambda value: value is None)`
   na `BrowserPageGeometryReviewSourceResponse`.

2. Helper w `api/image_imports.py`, wywoływany tylko gdy
   `geometry_origin == "manual_template"` (czyli: brak override'u i brak
   `raw_quads` — patrz istniejąca zmienna `geometry_origin` w handlerze,
   l. 1326–1332):

   ```python
   def _automatic_page_proposal(
       raw: Mapping[str, object], *, expected_board_count: int
   ) -> AutomaticPageGeometryProposalPayload | None:
   ```

   Reguły — każda porażka zwraca `None`, bez wyjątku:
   - `raw["lateralRegistrationCandidate"]` musi być `Mapping` z
     `origin == "automatic_search_proposal"`;
   - `recoveryKind` (brak → `"lateral_source_support"`) musi być jedną z
     trzech dozwolonych wartości;
   - `raw["activeBoardSlots"] == list(range(expected_board_count))` i
     `len(analysisQuads) == expected_board_count`;
   - `raw["imageWidth"]`/`raw["imageHeight"]` to `int >= 1` (brak → `None`);
   - każdy quad ma dokładnie 4 punkty `{"x": int, "y": int}` (`bool` nie
     jest dozwolony — sprawdzić `type(...) is int`), każdy punkt w
     `[-W, 2*W) × [-H, 2*H)` (te same granice co walidacja zapisu
     `pending_partial` w `PageGeometryOverrideService._parse_and_validate`);
   - `reviewRequiredSlots` (brak → `[]`) to lista unikalnych int w zakresie
     slotów.

   Wywołanie w handlerze — dodać parametr do konstruktora `BrowserPageGeometryReviewSourceResponse`
   (koło l. 1393, obok `automatic_partial_proposals`):

   ```python
   automatic_page_proposal=(
       _automatic_page_proposal(raw, expected_board_count=_expected_board_count_from_relative_path(source_relative_path))
       if geometry_origin == "manual_template"
       else None
   ),
   ```

3. `npm run openapi:generate` regeneruje klienta. Wrapper
   `listBrowserPageGeometryReviewSources` w
   `packages/admin-api-client/src/index.ts` nie zmienia sygnatury (pole jest
   częścią istniejącego response type).

**Przykład wejście → wynik:**

- Wpis `review_required`, brak override'u, `analysisQuads` z 9 quadami, jeden
  quad ma `x = -27` (mieści się w `[-1080, 2160)` dla `imageWidth=1080`) →
  `automaticPageProposal` obecne, quady identyczne z surowymi (bez
  przycinania — przycinanie do bezpiecznego zakresu to zadanie T2 w admin).
- To samo, ale `activeBoardSlots == [0,1,2,3,4,5,6,7]` (8 zamiast 9) →
  `None`.
- Wpis z istniejącym `manual_override` → `geometry_origin != "manual_template"`
  → helper w ogóle nie jest wywoływany, pole zawsze `None`.

**Przypadki brzegowe:** brak `lateralRegistrationCandidate` (typowe dla
większości `review_required` bez polityki lateral) → `None`, lista działa
jak dziś. Punkt zmiennoprzecinkowy lub `bool` → `None`. Nieznany
`recoveryKind` → `None`. Te reguły nie zmieniają `review_required_source_count`
ani blokady importu `IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED`.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/schemas/image_imports.py`,
  `services/api/src/game_predictor_api/api/image_imports.py`,
  `services/api/tests/test_image_imports_api.py`,
  `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`.
- Nowe (wygenerowane, bez ręcznej edycji): `packages/admin-api-client/openapi/*`,
  `packages/admin-api-client/src/generated/*`.

## Test cases

- Happy path: 9 `analysisQuads`, jeden `x < 0`, `recoveryKind` domyślny →
  pole obecne, quady identyczne, `geometryOrigin == "manual_template"`.
- Brak `analysisQuads` → pole nieobecne w JSON.
- 8 quadów przy 9 oczekiwanych → `None`.
- Punkt `x` typu `float` → `None`.
- Punkt `x >= 2*imageWidth` → `None`.
- Nieznany `recoveryKind` → `None`.
- Brak `imageWidth`/`imageHeight` w `raw` → `None`.
- Istniejący override (`geometry_origin == "manual_override"`) → pole zawsze
  `None`, nawet z prawidłowym kandydatem.
- Regresja: istniejące testy l. ~1858 i ~2296 (manifest z
  `lateralRegistrationCandidate` zawierającym tylko `{"version": ...}`, bez
  `analysisQuads`) przechodzą bez zmiany asercji — helper zwraca `None`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_imports_api.py -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/api/image_imports.py services/api/src/game_predictor_api/schemas/image_imports.py services/api/tests/test_image_imports_api.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/api/image_imports.py services/api/src/game_predictor_api/schemas/image_imports.py
npm run openapi:generate
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
```

Timeout 120 s na komendę.

## Risks / open questions

- Jakość propozycji dla przyciętych plansz zależy od homografii kandydata —
  poza zakresem tego tasku (tylko przekazanie danych, nie ocena jakości).
- Nazwa pola `origin` w nowym payloadzie może być myląca względem
  `raw["origin"] == "automatic_search_proposal"` (to inny `origin`, na
  poziomie `lateralRegistrationCandidate`, nie kandydata propozycji). Nazwa
  pochodzi z zaakceptowanego planu; jeśli wykonawca T2 uzna to za mylące,
  zgłosić, nie zmieniać cicho.

## Outcome

### Changed

- `services/api/src/game_predictor_api/schemas/image_imports.py`: nowy
  `AutomaticPageGeometryProposalPayload` (`origin`, `quads`, `review_slots`)
  i pole `automatic_page_proposal` na
  `BrowserPageGeometryReviewSourceResponse` (`exclude_if` gdy `None`).
- `services/api/src/game_predictor_api/api/image_imports.py`: helper
  `_automatic_page_proposal` (walidacja best-effort, zwraca `None` przy
  każdym niespełnionym ogniwie) wywoływany w
  `list_browser_page_geometry_review_sources` wyłącznie dla
  `geometry_origin == "manual_template"`.
- `services/api/tests/test_image_imports_api.py`: 7 nowych testów (happy
  path z planszą poza kadrem; 5 wariantów odrzucenia — brak
  `analysisQuads`, zła liczba plansz, punkt float, punkt poza zakresem,
  nieznany `recoveryKind`; brak wymiarów obrazu; pierwszeństwo istniejącego
  override'u).
- `packages/admin-api-client/openapi/openapi.json`,
  `packages/admin-api-client/src/generated/{index.ts,types.gen.ts}`:
  wygenerowane przez `npm run openapi:generate` (diff czysto addytywny —
  nowy typ + jedno pole; `sdk.gen.ts` bez zmian).
- `packages/admin-api-client/test/client.test.mjs`: nowy test przelotu pola
  przez wrapper `listBrowserPageGeometryReviewSources`.
- `ai_docs/architecture/API_CONTRACT.md`, `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/DECISION_LOG.md` (D-439), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- `pytest services/api/tests/test_image_imports_api.py -q` → 51/51 passed.
- `ruff check` (oba zmienione pliki `src/`) → czysto.
- `mypy` (oba zmienione pliki `src/`) → 79 błędów, identyczne co do liczby i
  treści na czystym `git stash` do `v0.10.402` (potwierdzone bezpośrednim
  porównaniem) — wszystkie to przedsesyjne `import-not-found` dla modułów
  `game_predictor_worker.*` niezwiązane z tą zmianą; zero nowych błędów.
- `npm run openapi:generate` + `npm run openapi:check` → zielone, diff
  wyłącznie nowy typ i pole.
- `npm run test --workspace @game-predictor/admin-api-client` → 61/61
  passed, w tym oba testy dryfu generowanego klienta.

### Not completed

- Nic w zakresie tego taska. T2 (edytor Admin startuje od propozycji) i T3
  (przesuwanie całej planszy) to osobne, jeszcze niezlecone taski.

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md`: nowy akapit o `automaticPageProposal`
  za akapitem `geometryOrigin=manual_template` (ok. l. 3197+).
- `ai_docs/requirements/IMAGE_INGESTION.md`: zdanie łączące istniejący opis
  „roboczy szablon” z nazwą pola API (ok. l. 108–115).
- `ai_docs/process/DECISION_LOG.md`: nowy wpis **D-439** (renumeracja z
  planowanego D-433, który był już zajęty).
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0632 na szczycie.

### Recommended next task

- T2 (prefill edytora Admin propozycją, oznaczanie przyciętych plansz jako
  `pending_partial`) — wymaga osobnego polecenia użytkownika, proponowany
  numer `TASK-0633` (nie `TASK-0625`, patrz renumeracja w sekcji Context).
