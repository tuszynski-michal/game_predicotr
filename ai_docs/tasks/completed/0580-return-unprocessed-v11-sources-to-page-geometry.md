---
title: Return unprocessed v1.1 sources to normal page geometry
status: done
---

# TASK-0580 — Przywrócenie nieprzetworzonych źródeł v1.1 do ręcznej geometrii strony

## Status

`in_progress`

## Goal

Każde źródło v1.1 ze statusem `review_required`, dla którego nie powstały
plansze ani symbole, jest dostępne w zwykłej kolejce „Ręczna korekta zdjęć
geometrii”, razem z możliwością podmiany JPEG-a przed zapisem geometrii.

## Context

Ukończony preflight `4c611361-a011-4d48-9a1e-e2983215885a` dla stagingu
`45163 - 70371 cut` ma 2801 źródeł: 2761 `registered` i 40
`review_required`. Wszystkie 40 mają `lateralRegistrationCandidate`, ale nie
mają quadów, outputów plansz ani outputów symboli. Endpoint listy ukrywa je
wyłącznie przez wariant v1.1, dlatego panel pokazuje zero pozycji mimo
nieprzetworzonej geometrii.

## Dependencies / entry conditions

- Staging i jego manifest są niezmienne; zmiana nie przelicza ani nie zapisuje
  JPEG-ów, jobów, manifestów, cropów, plansz lub symboli.
- Istniejący `PageGeometryCorrectionPanel` obsługuje już źródło
  `review_required` z `geometryOrigin=manual_template` oraz opcjonalną
  propozycję automatyczną.
- Decyzja użytkownika: te pozycje mają wrócić do normalnej ręcznej geometrii,
  nie do odrębnego widoku selektywnej korekty plansz.

## Recommended execution

`gpt-5.6-sol`, reasoning `high`. Zmiana dotyka bramki API i uprawnień do
podmiany checksum-bound źródła, więc wymaga regresji API oraz sprawdzenia na
istniejącym lokalnym manifeście. Eskalacja do `gpt-6-astra`, reasoning `high`,
jest wymagana tylko, gdy testy ujawnią konflikt z trwałą proweniencją manifestu
albo importem rozpoczętym dla tego samego stagingu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Zwracać każde `review_required` z manifestu `review-sources` niezależnie od
  obecności `lateralRegistrationCandidate`; propozycja pozostaje opcjonalną
  informacją w tej samej odpowiedzi.
- Traktować takie źródło jak każdą inną niepotwierdzoną pozycję kolejki:
  pełna ręczna geometria, wykluczenie albo checksum-bound podmiana JPEG-a są
  dozwolone do czasu zapisu geometrii lub startu importu.
- Utrzymać ochronę przed podmianą źródła już ręcznie zatwierdzonego,
  wykluczonego, nienależącego do stagingu albo użytego przez rozpoczęty import.
- Uzupełnić wymagania, kontrakt API, decyzję architektoniczną, stan projektu i
  testy regresji.

## Out of scope

- Zmiana algorytmu v1.1, jego snapshotu, automatycznej propozycji lub
  ponowne uruchamianie preflightu.
- Zmiana niezmiennego manifestu, statusów 2761 zarejestrowanych źródeł,
  istniejących danych gry albo wygenerowanych cropów/plansz/symboli.
- Nowy widok UI, nowy endpoint albo migracja bazy.

## Acceptance criteria

- [ ] Dla ukończonego preflightu v1.1 źródło `review_required` z
  `lateralRegistrationCandidate` zwraca się w `review-sources` jako zwykłe
  `review_required` i `manual_template`.
- [ ] To samo źródło można podmienić przez istniejący checksum-bound endpoint,
  jeśli nie ma ręcznego override'u, wykluczenia ani importu.
- [ ] Dotychczasowe blokady podmiany po akceptacji geometrii i po starcie
  importu pozostają fail-closed.
- [ ] Lokalny odczyt raportu `45163 - 70371 cut` po zmianie pokazuje dokładnie
  40 pozycji normalnej ręcznej geometrii, bez tworzenia joba i bez mutacji
  manifestu.
- [ ] Kontrakt i testy regresji opisują ten routing.

## Technical notes

Obecna bramka w
`create_image_import_router.list_browser_page_geometry_review_sources` pomija
`review_required`, jeżeli przypięty snapshot jest v1.1, manifest ma
`lateralRegistrationCandidate`, a nie istnieje bieżący override. Jest to
filtr prezentacji, a nie status manifestu: wpis nadal jest nierozstrzygnięty i
nie ma finalnych quadów. Usunąć filtr oraz analogiczną, dodatkową blokadę w
`replace_unconfirmed_browser_page_geometry_source`; zachować wspólną walidację
`review_required`, provenance, override'ów, wykluczeń i istniejącego importu.

Nie zmieniać `review_reason` ani schematu odpowiedzi. Dzięki temu istniejący
panel dostaje tę samą pozycję jako `manual_template`, pokazuje kompletną
geometrię strony i może zachować opis propozycji automatycznej. Nie ma
duplikowania pozycji ani przejścia do równoległego workflowu.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/image_imports.py` —
  lista źródeł korekty i bramka podmiany.
- Istniejące: `services/api/tests/test_image_imports_api.py` — regresje listy
  i podmiany źródła v1.1.
- Istniejące: `ai_docs/requirements/IMAGE_INGESTION.md` — zachowanie v1.1.
- Istniejące: `ai_docs/architecture/API_CONTRACT.md` — semantyka
  `review-sources` i podmiany.
- Istniejące: `ai_docs/process/DECISION_LOG.md` — decyzja o trasowaniu
  nierozstrzygniętego źródła.
- Istniejące: `ai_docs/process/CURRENT_STATE.md` — wynik TASK-0580.
- Istniejące: ten task — `Outcome` i status.

## Test cases

- Manifest v1.1: ręczny override, jedno zwykłe `review_required` z kandydatem
  i jedno zarejestrowane źródło → lista zawiera override oraz kandydat w
  deterministycznej kolejności; kandydat ma `review_required` i
  `manual_template`.
- Niepotwierdzone źródło v1.1 z kandydatem → istniejąca podmiana tworzy
  rewizję stagingu i zachowuje idempotentny replay.
- Źródło z override'em albo staging z importem → podmiana nadal zwraca
  `IMAGE_REPLACEMENT_NOT_ALLOWED`.
- Lokalny raport rzeczywistego stagingu → 40 pozycji, 0 nowych jobów i brak
  zmiany checksumy manifestu.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; każdy krok z timeoutem do 120 s
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_imports_api.py -k "geometry_review_listing or page_source_replacement" -q --basetemp .test-tmp\codex-0580-geometry-review
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/api/image_imports.py services/api/tests/test_image_imports_api.py
.\.venv\Scripts\python.exe -m mypy services/api/src services/worker/src
npm --prefix apps/admin run typecheck
```

Po testach odczytać istniejący endpoint lokalnego stagingu i potwierdzić 40
źródeł oraz tę samą checksumę manifestu. Nie wywoływać endpointu zapisu.

## Risks / open questions

- Zmiana zastępuje część D-397 dotyczącą odseparowania kandydatów v1.1 od
  pełnej korekty. D-401 musi jawnie zachować selektywne ponowne użycie
  zarejestrowanych źródeł i brak automatycznych cropów.
- Zmiana ujawni również przyszłe, analogiczne źródła v1.1. Jest to zamierzone:
  nierozstrzygnięte źródło bez materializacji nie może zniknąć z jedynej
  kolejki, która może je zatwierdzić.

## Outcome

### Zmiana

- `review-sources` zwraca teraz także `review_required` z roboczym
  `lateralRegistrationCandidate` v1.1 jako `geometryOrigin=manual_template`.
  Nie zmienia manifestu, nie uruchamia ponownie preflightu ani nie tworzy
  plansz lub symboli.
- Podmiana JPEG-a dla takiego nierozstrzygniętego źródła wraca do istniejącego,
  checksum-bound workflowu. Nadal jest blokowana po ręcznym override, wykluczeniu
  albo rozpoczęciu importu.
- Regresje obejmują widoczność w zwykłej kolejce ręcznej geometrii oraz podmianę
  nierozstrzygniętego źródła z kandydatem v1.1.

### Weryfikacja

- `pytest services/api/tests/test_image_imports_api.py -k "geometry_review_listing or page_source_replacement" -q`: 6 passed.
- `ruff check` i `ruff format --check` dla zmienionych plików: passed.
- `mypy services/api/src services/worker/src`: passed.
- `npm --prefix apps/admin run typecheck`: passed.
- Odczyt lokalnego stagingu `45163 - 70371 cut` potwierdził bez zmiany jego
  joba ani manifestu: 40 z 40 źródeł jest zwracanych do ręcznej geometrii jako
  `review_required` i `manual_template`.

### Poza zakresem

- Statyczny test admina
  `page-geometry-correction-panel-contract.test.mjs` pozostaje czerwony przez
  wcześniej niezgodne oczekiwanie wobec niezmienianego komponentu
  `PageGeometryCorrectionPanel`; nie jest to regresja tego taska. Typecheck
  admina przeszedł poprawnie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0580 | `gpt-5.6-sol` | `high` | Wąska, lecz ważna zmiana bramki API i checksum-bound podmiany, wymagająca regresji oraz odczytu istniejącego manifestu. | Nie; `gpt-6-astra high` tylko przy konflikcie z proweniencją manifestu lub rozpoczętym importem. |
