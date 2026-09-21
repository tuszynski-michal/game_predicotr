---
title: Gotowość wspólnej geometrii shape v2 przy tworzeniu gry
status: done
task_id: TASK-0607
---

# TASK-0607 — gotowość wspólnej geometrii shape v2 przy tworzeniu gry

## Status

`done`

## Goal

Pozwolić utworzyć każdą grę, a przy jej tworzeniu i w katalogu jednoznacznie
pokazać, czy pełnostronicowa geometria z ramką jest obsługiwana wspólnym
profilem, czy wymaga doprecyzowania lub ręcznej korekty pierwszego importu.

## Context

G03 może przypiąć aktywny profil `framed_full_page_v2`, ale sama nazwa gry nie
jest dowodem zgodności strony. Użytkownik wymaga jednego tworzenia gier, bez
powielania geometrii dla Mumii, Gangu i następnych zgodnych gier. Kolor ramki i
lokalna kotwica nie są konfiguracją konieczną. Treasure bez ramki pozostaje
poza rodziną v2; system ma to komunikować jako potrzebę doprecyzowania, a nie
próbować użyć profilu z innej rodziny.

## Dependencies / entry conditions

- G03 (`v0.10.347`) przypina tylko aktywny, integralny profil
  `framed_full_page_v2` i zawsze zostawia wynik do ręcznego potwierdzenia.
- G06 tworzy trwałe profile, lecz G07 dopiero będzie je kwalifikować i
  aktywować; brak aktywnego profilu jest prawidłowym stanem startowym.
- Istniejący pion katalogu tworzy gry bez usuwania lub przepisywania danych.
- Rozstrzygnięcie zadania: wybór formatu strony jest trwałą konfiguracją gry;
  brak wyboru dla starych gier oznacza `requires_clarification`. Nie tworzy się
  konfiguracji koloru ani lokalnej kotwicy.

## Recommended execution

gpt-5.6-terra, high — pion obejmuje migrację, katalog API, wygenerowany klient
i formularz Admina, ale nie zmienia importu ani aktywacji. Niezależny audyt
gpt-6-astra, medium jest obowiązkowy po implementacji; P0/P1 zatrzymuje plan,
a P2/P3 trzeba naprawić i poddać re-audytowi przed zamknięciem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` (G04)
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `services/api/src/game_predictor_api/application/catalog.py`
- `services/api/src/game_predictor_api/api/catalog.py`
- `apps/admin/src/features/games/game-catalog.tsx`

## Scope

- Dodać przez migrację trwałą, pojedynczą konfigurację gotowości geometrii
  strony dla gry: `framed_full_page_v2` albo `requires_clarification`.
  Konfiguracja ma topologię 3 × 3 / 3 × 5 tylko dla zgodnej rodziny i nie
  zawiera koloru, kotwicy, obrazu, profilu lokalnego ani danych importu.
- Nowe tworzenie gry przyjmuje konfigurację z domyślnym
  `requires_clarification`; istniejące gry dostają taki sam bezpieczny stan
  przez odczytowy fallback, bez migracji danych użytkownika.
- Udostępnić w `GameResponse` read model gotowości: wybrany format strony,
  status, konkretny kod/polską wiadomość i — tylko dla zgodnej rodziny —
  identyfikator/numer/checksumę aktywnego profilu shared. Brak, konflikt lub
  uszkodzenie profilu nie wybiera zastępczej wersji i ma czytelny stan review.
- Rozszerzyć kontrakt API, wygenerowany klient i katalog Admina. Formularz
  tworzenia wyjaśnia, że pełna strona z ramką używa wspólnej geometrii bez
  wyboru barwy, zaś inny format wymaga doprecyzowania. Lista pokazuje stan i
  przyczynę ręcznego działania.
- Zachować możliwość utworzenia gry w obu stanach. Nie zmieniać startu importu
  ani nie promować profilu/shared propozycji do automatycznego importu.

## Out of scope

- Aktywacja, kwalifikacja, rollback i kandydatury G07.
- Modyfikacja polityki preflightu G03, automatyczny import lub pilot G05.
- Obsługa Treasure bez ramki; jej stan ma pozostać `requires_clarification`.
- Kolor ramki, lokalne kotwice, JPEG-i i dane semantyczne per gra.

## Acceptance criteria

- [ ] Każdą grę można utworzyć; wybór `framed_full_page_v2` nie wymaga koloru
  ani lokalnej kotwicy, a brak/inna rodzina daje jawne doprecyzowanie.
- [ ] API i Admin pokazują ten sam, deterministyczny status oraz konkretny
  powód: aktywny profil, brak aktywnego profilu, konflikt/uszkodzenie albo
  nieobsługiwany format strony.
- [ ] Read model profilu nie ujawnia dowodów, obrazów ani routingu gry; nie
  wybiera candidate/rejected/retired ani starszego profilu zastępczego.
- [ ] Zmiana konfiguracji gry i aktywnego profilu odświeża stan bez zmiany
  historycznych jobów lub danych importu.
- [ ] Migracja, OpenAPI/generowany klient, testy API/Admina, lint, typecheck i
  audyt Astra Medium potwierdzają pion.

## Technical notes

Tabela konfiguracji jest per-game control plane, natomiast profil pozostaje
globalnym descriptor-only control plane. Readiness nie jest zgodą na import:
`ready_for_shared_preflight` oznacza wyłącznie, że gra deklaruje rodzinę v2 i
istnieje jeden integralny aktywny profil. `manual_review_required` oznacza
zgodną rodzinę bez aktywnego profilu lub z błędem profilu; `requires_clarification`
oznacza brak deklaracji albo format poza v2. W przypadku konfliktu lub uszkodzenia
nie wolno ukryć błędu jako gotowości.

## Expected files

- Istniejące: modele/migracje Alembic katalogu, `catalog.py` domeny,
  `application/catalog.py`, endpointy i schematy katalogu.
- Istniejące: generator OpenAPI, `packages/admin-api-client`, katalog gier
  Admina oraz jego state/actions/tests.
- Istniejące: `DATA_MODEL.md`, `API_CONTRACT.md`,
  `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`, `CURRENT_STATE.md` i Decision Log.

## Test cases

- Tworzenie gry z deklaracją pełnej ramki działa bez koloru/kotwicy; bez
  aktywnego profilu zwraca `manual_review_required` z konkretnym kodem.
- Aktywny integralny profil daje `ready_for_shared_preflight` i ujawnia tylko
  immutable referencję; candidate/rejected/retired nie są gotowe.
- `requires_clarification` oraz stara gra bez konfiguracji są tworzone/odczytane
  bez błędu i pokazują jasną prośbę o doprecyzowanie.
- Konflikt/nieintegralny aktywny profil daje fail-closed status, bez wyboru
  wcześniejszej wersji; responsy i UI pozostają zgodne z OpenAPI.
- Katalog Admina pokazuje komunikat i po zapisie/odświeżeniu aktualizuje stan.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# timeout: maks. 120 s na komendę
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\api\tests\test_catalog*.py services\api\tests\test_global_geometry*.py -q --basetemp .runtime\pytest-shape-v2-g04
npm --prefix apps\admin run lint
npm --prefix apps\admin run typecheck
npm --prefix apps\admin test -- --test-name-pattern "game-catalog"
```

## Risks / open questions

- G07 nie wystawia jeszcze aktywacji, więc produkcyjny stan startowy będzie
  zwykle `manual_review_required`; to nie jest blokada tworzenia gry.
- Istniejące gry nie dostają automatycznej klasyfikacji po nazwie. Operator
  wybiera format jawnie, aby nie traktować Treasure albo nieznanej gry jako
  kompatybilnej tylko przez podobny kod.

## Outcome

Wypełnia agent po pracy.

### Changed

- Dodano trwałą konfigurację rodziny geometrii strony gry oraz migrację Alembic
  `0116`; historyczny `NULL` pozostaje bez zmian danych i jest odczytywany jako
  `requires_clarification`.
- Katalog API udostępnia deterministyczny read model gotowości oraz wyłącznie
  immutable referencję do jedynego integralnego profilu `active`. Błąd,
  konflikt albo brak profilu kończą się fail-closed stanem manual review.
- Zaktualizowano kontrakt OpenAPI, wygenerowany klient, katalog Admina oraz
  dokumentację. UI pozwala utworzyć każdą grę i jasno rozróżnia wspólną
  geometrię strony z ramką od formatu wymagającego doprecyzowania.

### Verification results

- 37 skoncentrowanych testów API przeszło; Ruff, ograniczony mypy, kontrola
  aktualności OpenAPI i klienta wygenerowanego przeszły.
- Typecheck Admina, 18 skoncentrowanych testów katalogu oraz Prettier dla
  zmienionych plików przeszły.
- Pierwszy audyt Astra Medium wykrył P2 w obsłudze błędu odczytu aktywnego
  profilu. Poprawiono go i dodano regresję; końcowy re-audyt Astra Medium nie
  wykazał P0–P3.

### Not completed

- Nie uruchomiono migracji na danych użytkownika. G07 aktywuje profile, a G05
  wykonuje pilot; oba pozostają poza zakresem G04.
- Pełna suita Admina pozostaje zablokowana przez wcześniejszy, niezależny test
  `page-geometry-correction-panel-contract.test.mjs`; skoncentrowane testy
  katalogu przeszły.

### Documentation updates

- Zaktualizowano `DATA_MODEL.md`, `API_CONTRACT.md`,
  `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`, `ADMIN_APP.md`, `CURRENT_STATE.md`
  i `DECISION_LOG.md`.

### Recommended next task

- G07 — kwalifikacja i aktywacja wiedzy shared.
