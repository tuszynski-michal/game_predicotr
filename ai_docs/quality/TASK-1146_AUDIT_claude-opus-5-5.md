# Audyt TASK-1146: zgodność kontroli startu z głową Alembic 0177

**Werdykt: PASS.** Nie ma uwag P0 ani P1.

Model: claude-opus-5-5 / high. Wykonałem 6 odczytów, czyli tyle, ile wynosił limit: 5 wskazanych plików i jeden celowany Grep.

## Co sprawdziłem

1. **Pin głowy.** `services/api/src/game_predictor_api/storage/schema_readiness.py:18` ustawia `EXPECTED_ALEMBIC_HEAD = "0177_source_replacement_purge"`. Wartość zgadza się z `revision` w `services/api/alembic/versions/0177_source_replacement_purge.py:5`. Rewizja ma `down_revision = "0176_source_replacement_closed"` (`:6`), więc łańcuch 0176→0177 jest spójny.
2. **Kontrola pozostała fail-closed.** `require_alembic_head` (`schema_readiness.py:46-51`) nadal wymaga dokładnej równości `found != EXPECTED_ALEMBIC_HEAD`. Nie ma listy dozwolonych starych rewizji ani innego obejścia. Brak tabeli i liczba wierszy różna od 1 dalej dają `None`, a więc odmowę (`:37-43`). Ani zapytania, ani obsługi błędów nie zmieniono.
3. **Test rzeczywistej głowy.** `services/api/tests/test_schema_readiness.py:15-18` czyta `ScriptDirectory` z `alembic.ini` w katalogu głównym. `ROOT = parents[3]` (`:12`) wskazuje poprawny katalog, a `script_location` w `alembic.ini:2` pasuje do lokalizacji migracji. Test porównuje całą listę `get_heads()` z jednoelementową listą `[EXPECTED]`, więc wykryje też rozgałęzienie historii. Dodatkowo jawnie przypina literał 0177.
4. **Odmowa dla innych rewizji.** Parametryzacja w `test_schema_readiness.py:54-77` zachowuje przypadki `None`, starsze rewizje i `9999_future`. Dodano 0171, 0172, 0173, 0174, 0175 i 0176, w tym poprzedni błędny pin 0174 (`:72`). Test sukcesu (`:86-92`) zostaje bez zmian.
5. **Liczba testów.** Zgadza się z deklaracją wykonawcy: 1 + 1 + 1 + 19 przypadków parametryzacji + 1 = **23**.
6. **Zakres.** Zmiana dotyczy tylko stałej, docstringu, testu i dokumentacji taska. Nie ma zmian w migracjach, API, zapytaniach do bazy ani w obsłudze błędów. Rewizji 0178 nie ma w kodzie ani w testach, co jest prawidłowe.

## Uwagi P2

Brak istotnych uwag P2. Zostały tylko drobne obserwacje, które nie blokują commitu:

- **O1 (do task-close):** `ai_docs/tasks/1146-readability-startup-schema-head.md:47-49`. Kryteria akceptacji są jeszcze odznaczone, `:80` mówi „audyt: w toku”, a `:2`/`:11` mają status `in_progress`. To normalny stan przed zamknięciem. Należy go uzupełnić w task-close razem z wersją v1.7.540 i hashem.
- **O2 (kosmetyka, opcjonalnie):** `schema_readiness.py:3-6`. Zawinięcie wiersza „API, worker and maintenance / scripts” jest nierówne. Nie sprawdziłem też, czy wzmianka o `game-data-v2-manifest-v21` jest aktualna dla 0177, bo wynik Grepa był ucięty i `v21` się w nim nie pojawił. To tylko komentarz i nie wpływa na działanie kontroli.

## Stan uwag

- **Zamknięta:** rozjazd pinu 0174 z rzeczywistą głową 0177. Pin i test są zgodne.
- **Zamknięta:** brak pokrycia odmowy dla rewizji pośrednich 0171–0176.
- **Otwarta (proces):** O1, do domknięcia w task-close i commicie.
- **Otwarta (kosmetyka):** O2, nieblokująca.
- **Niezweryfikowane w tym audycie:** nie sprawdzałem, czy API i worker rzeczywiście wywołują ten sam `require_alembic_head`, bo nie mieściło się to w limicie odczytów. Przyjmuję to jako fakt podany w briefie.

## Proponowane testy

Obecny zestaw wystarcza dla tej poprawki. Zostają tylko kroki potwierdzające, do uruchomienia przez wykonawcę lub koordynatora:

- Ponowne uruchomienie `pytest services/api/tests/test_schema_readiness.py` tuż przed commitem.
- W trakcie zatwierdzonego wdrożenia, już poza tym taskiem: po `db:migrate` do 0177 sprawdzić start API i workera. Obie usługi powinny przejść kontrolę bez `ALEMBIC_HEAD_MISMATCH`, a przed migracją, na bazie 0171, powinny odmówić startu.

## Dowody wykonawcy

Przyjmuję je bez własnego potwierdzenia. Według wykonawcy test był FAIL przed poprawką (0177 vs 0174) i jest PASS po niej (23 testy, 2,88 s). Ruff, mypy modułu produkcyjnego, docs i mapa kodu przeszły. Trzy zastane błędy typów w testach merge są poza zakresem i opisane w Outcome. Tych testów nie uruchamiałem. Brak hasha commita przed audytem jest prawidłowy.

---

**Oświadczenie: przegląd statyczny, bez zmian w plikach.** Nie uruchamiałem testów, usług, migracji, buildów ani operacji na bazie danych.
