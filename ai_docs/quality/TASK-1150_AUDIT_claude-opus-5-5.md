---
title: Audyt TASK-1150
status: active
last_updated: 2026-11-03
---

# Audyt TASK-1150 — Atomowy zapis postępu przy krótkiej blokadzie pliku Windows

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...a3064372d3f33fcc6b0d3f708696d617051839aa oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem zmianę w `write_json_atomic` (`grid_training_child.py`), nowy moduł testów, task i raport weryfikacji. Porównałem je z zakresem, kryteriami akceptacji i listą Out of scope. Sprawdziłem też konsumentów writera, czyli nadzorcę w handlerze, Watchdog i zapisy dziecka.

Zmiana jest minimalna i zgodna ze specyfikacją. Funkcja ponawia wyłącznie `os.replace`, ten sam kompletny i zsynchronizowany przez fsync tempplik, tylko dla jawnych `winerror` 5, 32 i 33. Robi najwyżej 7 prób z opóźnieniami 10/20/40/80/160/160 ms. Pierwotny błąd jest propagowany bez opakowania, a `finally` sprząta wyłącznie własny tempplik. Destination nie jest usuwany ani nadpisywany w miejscu.

Główne ryzyko resztkowe to mała możliwość niestabilności testu rzeczywistego uchwytu Windows (P2-1). Pozostały też otwarte kroki procesu przed commitem: mapa kodu i docs:check.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/tests/test_grid_training_atomic_json.py:200` — Funkcja `release_reader` zamyka uchwyt bezwarunkowo przy każdym wywołaniu `sleep`. Załóżmy, że po zamknięciu uchwytu pojawi się druga przejściowa odmowa `os.replace`, na przykład gdy antywirus skanuje świeży tempplik bez FILE_SHARE_DELETE. Wtedy `CloseHandle` zostanie wywołane drugi raz na już zamkniętym uchwycie. Asercja padnie z mylącym komunikatem. W skrajnym przypadku zamknięty zostanie niepowiązany uchwyt procesu, który dostał ten sam numer. Kod produkcyjny jest poprawny, a problem dotyczy tylko stabilności testu. Proponowana poprawka: w `release_reader` zamykać uchwyt tylko gdy `not released`. Asercje `len(failures) == 1` i `delays == [0.01]` z linii 209 można zostawić jako jawny sygnał nieoczekiwanej drugiej odmowy. Można też świadomie zaakceptować ryzyko jako niskie.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zwykły zapis nadal atomowy, jedna próba bez oczekiwania | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_child.py:98-101`: `break` po pierwszym sukcesie. Test `services/worker/tests/test_grid_training_atomic_json.py:22` sprawdza kolejność fsync→replace i brak `sleep`. |
| Przejściowa jawna blokada Windows ponawiana w ścisłym limicie na tym samym temppliku | spełnione | `grid_training_child.py:44` (stała opóźnień, suma 0,47 s) oraz `grid_training_child.py:105-109`. Test `test_grid_training_atomic_json.py:56` dla kodów 5, 32 i 33 sprawdza jeden tempplik, jeden fsync i opóźnienia `[0.01, 0.02]`. |
| Trwała blokada kończy się błędem, zostawia poprzedni destination i sprząta tempplik; inne błędy nie są maskowane | spełnione | `grid_training_child.py:105-111`. Test `test_grid_training_atomic_json.py:93` sprawdza 7 prób, ten sam obiekt błędu, stare bajty i usunięcie tylko własnego temppliku. Test `test_grid_training_atomic_json.py:132` sprawdza same errno EACCES oraz kody 2, 80 i 87: jedna próba, zero `sleep`. |
| Test rzeczywistego uchwytu Windows bez FILE_SHARE_DELETE; testy deterministyczne liczby prób, opóźnień i braku zmiany budżetu/protokołu | spełnione | `test_grid_training_atomic_json.py:156-215` wywołuje CreateFileW z prawem GENERIC_READ i współdzieleniem READ\|WRITE, a uchwyt jest zamykany w `finally`. Log `artifacts/task1150-unit.log`: „12 passed in 1.29s”. Log `artifacts/task1150-consumers-short-path.log`: „34 passed, 1 deselected in 21.62s”. Linia serializacji `grid_training_child.py:95` jest bez zmian. Patrz też P2-1. |
| Scoped testy, lint/mypy, docs/map i audyt Opus rozliczone przed osobnym commitem/task-close | niespełnione (otwarte zgodnie z taskiem) | Testy, ruff, mypy i format mają PASS według logów `task1150-unit.log`, `task1150-lint.log`, `task1150-types.log` i `task1150-format.log`. Hashe SHA-256 obu plików są zgodne z `artifacts/task1150-frozen-sha256.txt`. Nie wykonano jeszcze regeneracji mapy (`scripts/generate_code_map.py`, wymaganej przez AGENTS.md dla nowego modułu testów), `docs:check`, commitu ani task-close. Task oznacza to jako „Not completed” po stronie prowadzącego. Ten raport rozlicza audyt Opus. |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1.

## Proponowane testy

- W `services/worker/tests/test_grid_training_atomic_json.py` można dodać opcjonalny test bajtowy. Sprawdzałby, że zapisany plik jest identyczny z `json.dumps(value, indent=2, sort_keys=True).encode("utf-8")`. Potwierdziłoby to brak zmiany formatu protokołu na poziomie bajtów, nie tylko semantyki JSON. Komenda: `.venv/Scripts/python.exe -m pytest -q --basetemp=.t/<nowy-id> services/worker/tests/test_grid_training_atomic_json.py`.
- Przed commitem prowadzący powinien wykonać `scripts/generate_code_map.py` oraz `npm run docs:check`.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief audytu;
- `services/worker/src/game_predictor_worker/images/grid_training_child.py`, linie 1–130 i 195–300 (writer, `ChildControl.write_progress`, Watchdog);
- `_read_json` w `grid_training_handler.py`, który czyta przez `read_text`, czyli bez FILE_SHARE_DELETE, co potwierdza mechanizm awarii;
- wyniki grep wszystkich wywołań `write_json_atomic` w `services/`;
- nowy moduł testów;
- fragment AGENTS.md o mapie kodu i audycie.

Sprawdziłem też:
- że diff `CODE_MAP*.md` zawiera tylko zmianę końców linii i nic dla TASK-1150;
- że pliki TASK-1149 nie należą do zakresu tej zmiany;
- końcówki logów wykonawcy;
- zgodność hashy SHA-256 obu plików z zamrożoną listą.

Ponowienie dotyczy wszystkich konsumentów writera: spec i allowance w handlerze oraz result, parity i bundle w dziecku. W Watchdog dodaje najwyżej 0,47 s pod blokadą. Nie zmienia to formatu, budżetu ani protokołu i jest zgodne z zamiarem taska.

Nie uruchamiałem testów, lint ani mypy. Wyniki pochodzą z logów wykonawcy. Nie czytałem lokalnego trace `diagnostic-1.log` ani `result-1.json`. Nie da się statycznie potwierdzić, że rzeczywista odmowa w przebiegu 7a1b3835 była krótką blokadą współdzielenia, a nie trwałym ACL. Task słusznie tego nie obiecuje.
