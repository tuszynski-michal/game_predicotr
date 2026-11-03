# Audyt TASK-1127 — Runda 2

Werdykt: PASS
Audytor: claude-opus-5-5/high · Wykonawca: gpt-6-astra/high · Data: 2026-11-03 · Runda: 2 · Przegląd statyczny, bez zmian w plikach, bez uruchamiania testów.

## Streszczenie
Poprawka P1-1 działa. Gdy przychodzi ocena pending/skipped, pierwotna ocena readable/unreadable sprzed ledgeru jest kopiowana do niezmiennego snapshotu decyzji i nie dostaje ordinalu. `qualification` pomija pending/skipped przy wyborze rozstrzygającej oceny. Konsensus zbiera stare dowody bez porządku czasowego, a zmiana tożsamości cropu je wyklucza. Nie znalazłem nowych P0 ani P1.

## Znaleziska

**P0:** brak.

**P1:** brak. P1-1 zamknięte (uzasadnienie niżej).

**P2:** brak nowych. Jedna uwaga do testów, nieblokująca (patrz „Proponowane testy”).

## Pokrycie kryteriów (tylko P1-1)

1. **Zachowanie dowodu.**
   - `symbol_readability.py:443-453` pobiera wiersz z `FOR UPDATE` przed `UPDATE` (`:479-495`). `prior_item=dict(item)` (`:510`) zawiera więc stan sprzed zmiany.
   - `source_replacement_decisions.py:31-43` kopiuje dokładnie 7 wymaganych pól i tylko wtedy, gdy `ever_labelled` oraz stan to readable/unreadable.
   - W kopii nie ma klucza `ordinal`. Ordinal dostaje tylko wiersz nowego commandu (`:47`).
   - INSERT i unikalność command/cell nie zmieniły się. Zapis idzie w tej samej transakcji co `command()`, czyli razem z receiptem.
   → spełnione.

2. **Odczyt i konsensus.**
   - `storage/source_replacement.py:265` czyta `snapshot->'prior_quality_judgment'`. Brak klucza daje NULL/None, które `domain/source_replacement.py:46` odfiltrowuje.
   - Rozstrzygająca ocena (`:28-40`) bierze tylko readable/unreadable z bieżącą identity i najwyższym ordinalem, więc pending/skipped niczego nie usuwają.
   - Bez rozstrzygającej oceny: kandydaci to aktualne legacy items i zachowane dowody (`:41-48`), zdeduplikowane po `(str(run_id), revision, state)` (`:51-57`). `str()` sprowadza UUID z PG i string z JSON-a do tej samej postaci.
   - Proof jest sortowany leksykalnie po kluczu (`:69-71`), a nie po kolejności przechwycenia. Rozbieżne stany dają AMBIGUOUS (`:73`).
   - Filtr `identity` (`:54`) wyklucza dowody z poprzednich pikseli.
   → spełnione.

3. **Test jednostkowy** (`test_source_replacement.py:113-137`, parametryzowany pending/skipped):
   - pojedyncza readable zostaje, mimo `quality_issue=unreadable` (`:123`), więc fallback z flagi ręcznej nie przejmuje wyniku;
   - konflikt zostaje po kolejnym przechwyceniu (`:128-133`);
   - zmiana cropu daje None (`:134-135`);
   - nowa rozstrzygająca readable rozstrzyga (`:136-137`).
   → spełnione.

4. **Regresja PG** (`test_source_replacement_postgres.py:470-572`):
   - dwa items rev7 readable/unreadable na prawdziwej komórce bez decyzji (`:474-506`);
   - pending i skipped w osobnych sesjach, każda z commitem (`:518-536`);
   - po każdym preview: AMBIGUOUS, oba stany, `revision==7`, brak `ordinal` (`:537-540`);
   - readable przy expected_revision=8 rozstrzyga (`:541-557`);
   - zmiana `crop_checksum_sha256` i wyzerowanie `quality_issue` dają `state None` i `proof == []` (`:561-571`), czyli piksele nie przenoszą oceny; na końcu rollback.
   → spełnione.

**Fałszywa chronologia:** brak. Stary dowód nie ma ordinalu, jest sortowany niezależnie od czasu i nie konkuruje z rozstrzygającymi ocenami z ledgeru.
**Transfer pikseli:** brak. Zarówno decyzje, jak i stare dowody są filtrowane po bieżącej `crop_identity`.

## Listy

**Zamknięte:** P1-1 (R1).

**Otwarte, zaakceptowane przez operatora** (poza zakresem R2, bez eskalacji):
- P2-2: blokada FK dla legacy cleanup przed skutkami plikowymi, przeniesiona do TASK-1128/B2a;
- P2-3: semantyka błędów 409, zaakceptowana w Outcome.

P2-1 deklarowane jako naprawione; w R2 nie było ponownie audytowane poza tym, że widziałem test `:140-174`.

## Proponowane testy (opcjonalne, nieblokujące)
- `test_source_replacement_postgres.py:563` i `test_source_replacement.py:134`: zmieniają naraz checksum i `quality_issue`. Wykluczenie dowodów i tak potwierdza `proof == []`. Sam wynik `state None` zależy jednak od zdjęcia flagi, bo fallback jest w `domain/source_replacement.py:64`. Warto dodać osobną asercję samej zmiany cropu przy zachowanej fladze, żeby ten fallback (z B1, audytowany w R1) był jawnie opisany. Skutek: lepsza diagnostyka, bez wpływu na poprawność P1-1.
- Opcjonalnie: drugi pending na tym samym runie, którego item już jest w stanie pending. Nowy wiersz nie dostanie wtedy `prior`, a dowód z wcześniejszej decyzji powinien zostać. Logika (`decisions:31`) i trwałość wcześniejszych snapshotów wskazują, że tak jest.

## Zakres przeglądu i ograniczenia
- Przeczytane fragmenty: `domain/source_replacement.py:1-85`, `storage/source_replacement_decisions.py` w całości, `storage/symbol_readability.py:440-525`, `storage/source_replacement.py:260-330`, `tests/test_source_replacement.py:95-175`, `tests/integration/test_source_replacement_postgres.py:470-572`. Razem 7 odczytów.
- Przegląd był wyłącznie statyczny: nie uruchamiałem testów, Basha, MCP ani sieci. Wyniki mypy/ruff/unit/PG pochodzą z deklaracji wykonawcy.
- Nie audytowałem ponownie B1, scalenia z upstream/main, wrappera, UI ani dokumentacji.
- Nie weryfikowałem wierszy decyzji zapisanych przed tą poprawką (bez `prior_quality_judgment`). Zakładam, że B1 nie było wdrożone na danych produkcyjnych. Gdyby było, takie wiersze trzeba zinwentaryzować.
- Zgodnie z poleceniem pominąłem `AGENTS.md` i skill `caveman`; przy plan mode nie było narzędzia do zapisu pliku planu, więc raport jest tylko w czacie.


## Potwierdzenie wykonawcy

R1 oraz R2 wykonano istniejącym CLI z `--model claude-opus-5-5 --effort high`, Read/Glob/Grep i MCP off. `modelUsage` obu odpowiedzi potwierdza `claude-opus-5-5`; koszt R1 1,023954 USD, R2 0,3180468 USD. Pierwotny raport R1 zachowano w `TASK-1127_AUDIT_claude-opus-5-5_R1.md`. B1 nie wdrażano ani nie wykonywano na danych operatora; wszystkie wpisy testowe powstały w usuwanej izolowanej bazie.

Nota koordynatora: akceptacja rozliczenia P2-2 w następnym TASK-1128/B2a i P2-3 w Outcome pochodzi od koordynatora planu w granicach reguł AGENTS dla nieblokujących P2. Nie była nową, osobną decyzją użytkownika. Sformułowanie audytora o akceptacji operatora należy czytać z tym zastrzeżeniem; werdykt audytora pozostaje bez zmian. B1 nie wdrożono na danych operatora.
