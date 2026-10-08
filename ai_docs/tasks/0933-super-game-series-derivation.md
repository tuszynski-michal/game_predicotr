# TASK-0933 — Wyprowadzanie serii supergry i API serii

## Status

`todo`

## Goal

Dla gry z rodzajem `wild_super_spins` system wyprowadza z pociętych plansz
serie supergry (trigger, długość z retriggerami, status, weryfikacja
triggera) do tabeli `super_game_series`, odświeża je po korektach symboli i
udostępnia API listy, plansz serii i zapisu super symbolu.

## Context

Super symbol jest widoczny tylko na zdjęciach, więc operator definiuje go
ręcznie; system musi najpierw wskazać, gdzie zaczyna się i kończy seria.
Plan: etap S-B, sekcja „Supergra jako stan sekwencji”.

## Dependencies / entry conditions

- TASK-0931 (role, rejestr rodzajów) i TASK-0932 (ewaluator) zacommitowane.
- Fakt: tabele gry są partycjonowane `LIST (game_id)` z RLS
  (`ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`); nowa tabela musi być
  sklasyfikowana w bramce własności.
- Decyzja operatora: do progu liczą się komórki z przypisanym symbolem
  (predykcja albo człowiek); plansza musi być pocięta.

## Recommended execution

claude-opus-5-5 / high. Tabela partycjonowana, wyprowadzanie z przypadkami
brzegowymi, durable job, API pionem. Eskalacja do claude-fable-5-1 / high
przy problemach z RLS lub wydajnością przejścia po 500 000 pozycji. Audyt:
gpt-6-astra / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Migracja: `super_game_series` (partycja per gra): `id`, `game_id`,
  `trigger_sequence_number`, `start_sequence_number`, `length`,
  `retrigger_sequence_numbers integer[]` (numery do 500 000; test z numerem
  > 32 767), `completeness` (`complete|incomplete`), `run_verification`
  (`verified|unverified`, obejmuje trigger i wszystkie retriggery),
  `super_symbol_id` FK symbols null, `defined_by`, `defined_at`, `revision`,
  `generation_id`, `updated_at`; unikalność `(game_id, trigger_sequence_number)`;
  tabela robocza generacji i tabela audytu zmian super symbolu.
- Use case `derive_super_game_series(game_id)`: strumieniowe przejście po
  pozycjach `1…expected_layout_count` (partie, bez ładowania wszystkich
  plansz do pamięci); reguły z rejestru rodzaju; stan `base/super` i licznik
  pozostałych spinów; brak planszy = pusta, spin zużyty; seria wychodząca
  poza ostatnią znaną planszę → `completeness = incomplete`.
- Generacja i podmiana: job zapisuje serie do tabeli roboczej z nowym
  `generation_id`; po przejściu całej sekwencji podmienia zawartość gry w
  **jednej transakcji** (usuń serie nieobecne w generacji z audytem; wstaw
  nowe; dla istniejącej tożsamości `(game_id, trigger)` zaktualizuj przedział,
  `completeness`, `run_verification`, zachowując `super_symbol_id`, `revision`
  i `defined_*`). Przedłużenie przez nowy retrigger **nie** kasuje symbolu.
  Restart joba kasuje tabelę roboczą tej generacji i zaczyna od nowa; żaden
  stan pośredni nie jest widoczny w API.
- Źródło wejścia: komórki z przypisanym symbolem (decyzja człowieka albo
  predykcja, także plansze `pending`) z projekcji weryfikacji komórek, nie
  z kanonicznej projekcji `accepted/corrected`; plansza liczy się tylko po
  pocięciu siatką (komplet komórek z geometrią). Zbiór wejścia = te komórki
  + katalog ról symboli + `super_game_kind` + aktywna wersja reguł.
- Wersja wejścia (zamiast maksimum rewizji/`updated_at`, które nie wykrywa
  każdej zmiany ani usunięcia): tabela `super_game_derivation_state`
  (`game_id` PK, `input_version bigint`, `current_generation_id`,
  `input_version_of_generation`, `updated_at`; nieaktualność **nie jest
  osobną kolumną**, lecz wynika zawsze z porównania
  `input_version != input_version_of_generation`, więc jest widoczna od
  pierwszej zmiany wejścia, także przed startem joba i w trakcie jego
  pracy). Każdy zapis
  zmieniający zbiór wejścia (zapis/usunięcie predykcji, korekta symbolu,
  korekta i unieważnienie siatki, import plansz, zmiana roli symbolu,
  zmiana rodzaju gry, publikacja reguł) inkrementuje `input_version` **w tej
  samej transakcji** co zapis; lista punktów zapisu jest wyliczona w kodzie
  i pokryta testem. Job odczytuje `input_version` na starcie; transakcja
  publikacji blokuje wiersz stanu (`FOR UPDATE`) i porównuje wersję
  atomowo z podmianą.
- Kandydat nieaktualny: jeżeli wersja się zmieniła, generacja robocza jest
  **odrzucana** (nie podmienia obowiązujących serii), a job kolejkuje
  dokładnie jeden ponowny przebieg (deduplikacja na grę). Do zakończenia
  przeliczenia API serwuje ostatnią opublikowaną generację, a każda
  odpowiedź kalkulacji i wyszukiwania niesie na **poziomie odpowiedzi**
  pole `superGameState: { fresh: boolean, inputVersion,
  generationInputVersion }` wyliczone z porównania wersji, niezależnie od
  tego, czy dana plansza ma `superGame`; konsumenci (TASK-0935, TASK-0936)
  pokazują ostrzeżenie i liczą wszystkie plansze gry jako `provisional`,
  gdy `fresh = false` (nowy trigger mógł powstać tam, gdzie poprzednia
  generacja miała tryb bazowy). CAS zapisu symbolu sprawdza `revision` i tożsamość serii;
  zapis w stanie `stale` jest dozwolony i przenosi się po tożsamości.
- Wyzwalanie: durable job lane `general` po: zakończeniu importu (nowe
  plansze), zapisie predykcji symboli, korekcie symboli, korekcie siatki,
  zmianie roli symbolu lub rodzaju gry, publikacji wersji reguł; z
  deduplikacją na grę; ręcznie z API.
- API: `GET /api/v1/games/{gameId}/super-game-series?status&verification&cursor`,
  `POST …/super-game-series/derive`, `GET …/super-game-series/{seriesId}/boards`
  (plansze `trigger…start+length-1` w formacie widoku wyszukiwania plansz,
  z `missing: true` dla brakujących), `PUT …/super-game-series/{seriesId}/super-symbol`
  (`symbolId | null`, `expectedRevision`; konflikt → 409). OpenAPI, klient,
  wrappery, request testy.

## Out of scope

- UI (TASK-0934, TASK-0935), wypłaty serii (TASK-0936).
- Gry z rodzajem `none` (zero serii, job kończy się natychmiast).

## Acceptance criteria

- [ ] Łańcuch: trigger na 100, retrigger na 105 → seria 101–120; trigger na
      110 w serii nie otwiera nowej.
- [ ] Brak planszy 103 → seria bez zmian długości; plansza oznaczona `missing`.
- [ ] Ostatnia znana plansza 108 przy serii 101–110 → `incomplete`.
- [ ] Trigger albo retrigger z komórką bez decyzji człowieka → `unverified`.
- [ ] Ponowne wyprowadzenie bez zmian plansz nie zmienia `revision` ani
      `super_symbol_id`; nowy retrigger przedłuża serię i zachowuje symbol;
      utrata triggera usuwa serię z wpisem audytu; pochłonięcie triggera przez
      wcześniejszą serię usuwa późniejszą, wcześniejsza zachowuje swój symbol.
- [ ] Retrigger o numerze 40 000 zapisuje się i odczytuje poprawnie.
- [ ] Restart joba w połowie: API nie pokazuje stanu pośredniego; po
      ponownym przebiegu wynik identyczny z przebiegiem bez restartu.
- [ ] Korekta symbolu w trakcie joba: kandydat odrzucony, obowiązujące serie
      bez zmian, `superGameState.fresh = false`, dokładnie jeden ponowny
      przebieg, wynik uwzględnia korektę; po nim `fresh = true`.
- [ ] Nowy trigger zapisany przed startem joba: odpowiedź wyszukiwania dla
      tej pozycji nie ma jeszcze `superGame`, ale `superGameState.fresh =
      false`; w trakcie pracy joba nadal `false`; po publikacji `true` i
      `superGame.kind = trigger`.
- [ ] Każdy punkt zapisu z listy wejścia inkrementuje `input_version` w tej
      samej transakcji (test parametryczny po liście); usunięcie predykcji
      też.
- [ ] Zmiana rekordu o niskiej rewizji przy innym rekordzie o wyższej
      (scenariusz 100 / 1→2) jest wykrywana.
- [ ] `PUT super-symbol` z nieaktualnym `expectedRevision` → 409, bez zapisu.
- [ ] Bramka własności tabel V2 klasyfikuje nową tabelę.

## Technical notes

- Źródło prawdy komórek: wyłącznie kontrakt z sekcji Scope (projekcja
  weryfikacji komórek z przypisanym symbolem, także plansze `pending`,
  pocięte siatką); kanoniczna projekcja `accepted/corrected`
  (`image_sequence_canonical.py`) **nie** jest źródłem wyprowadzania.
- Sekwencja startuje w trybie bazowym na pozycji 1; zawinięcie `N → 1` nie
  przenosi serii (plan, Z-1 poprzedniej rewizji).
- Granice transakcji: tabela robocza zapisywana partiami (osobne
  transakcje), podmiana w jednej transakcji końcowej razem z porównaniem
  `input_version` pod blokadą wiersza stanu; rozmiar partii i pomiar
  pamięci w Outcome.

## Expected files

- Nowe: migracja `015x_super_game_series.py`,
  `services/api/src/game_predictor_api/domain/super_game_series.py`,
  `application/super_game_series.py`, `storage/super_game_series_repository.py`,
  `api/super_game_series.py`, `schemas/super_game_series.py`,
  handler joba w `services/worker`.
- Istniejące: rejestr jobów, bramka własności V2, `DATA_MODEL.md`,
  `API_CONTRACT.md`, `packages/admin-api-client` (generowany).

## Test cases

- Jak w kryteriach; dodatkowo test PG (opcjonalny, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`)
  na 2 000 pozycji z 30 seriami: czas i pamięć w granicach partii.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "super_game" -q
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "super_game" -q
npm run openapi:generate; npm run openapi:check
npm run python:lint; npm run python:typecheck
```

## Risks / open questions

- Fałszywe triggery z predykcji Mumia↔Sarkofag; pole `trigger_verification`
  i ponowne wyprowadzanie po korektach ograniczają skutki.
- Wydajność na 500 000 pozycji: wymagany pomiar w Outcome.
- Super symbolem może być tylko zwykły symbol (nie Wild, nie uruchamiający);
  walidacja w `PUT super-symbol`.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
