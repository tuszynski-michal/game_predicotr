---
title: TASK-0740 — T1 — odczytowa ocena biblioteki wzorców symboli
status: done
last_updated: 2026-09-29
---

# TASK-0740 — T1 — odczytowa ocena biblioteki wzorców symboli

## Status

`done`

## Goal

Narzędzie tylko do odczytu mierzy dla ośmiu symboli gry `777`, jak często
propozycja z biblioteki zweryfikowanych komórek zgadza się z decyzją operatora,
i pokazuje propozycje dla próbki oczekujących komórek z pasma pewności 60–80%.

## Context

Aktywny model myli się systematycznie na nagraniach innych niż treningowe.
Próba z 2026-09-29 wykazała 95,6% zgodności biblioteki przy 14,9% modelu na
tej samej próbie. Plan: `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`.

## Dependencies / entry conditions

- Fakt: lokalna baza `game_predictor` działa, zarządzane oryginały są w
  `artifacts/data/originals`, aktywna iteracja modelu ma checkpoint w
  `artifacts/data/models`.
- Fakt: worktree nie ma własnego `.venv`; komendy używają interpretera
  głównego checkoutu z `PYTHONPATH` wskazującym źródła worktree.
- Założenie: import (`import_job_id`) jest przybliżeniem nagrania. Nie jest to
  dowód niezależności nagrań.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo: poziomu nie da się ustawić
z sesji). Model sesji zmienił się w trakcie z `claude-fable-5-1`; plan
odnotowuje zmianę. Prototyp powstał w tej sesji. Niezależny review
`claude-opus-5-5`, `high`, osobny agent. Eskalacja: rozbieżność pomiaru z próbą większa niż 3 punkty
procentowe wymaga analizy przed dalszą pracą.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-464)
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`

## Scope

- Czysty moduł opisów, głosowania i reguły pewności.
- Skrypt odczytowy: budowa biblioteki, ocena z wyłączeniem importu, próbka
  oczekujących komórek dla każdego z ośmiu symboli, raport JSON i arkusze PNG.
- Raport jakości w `ai_docs/quality/`.

## Out of scope

- Zapis do bazy, migracje, API, UI, trening, zmiana aktywnego modelu.
- Inne gry i inne pasma pewności niż wskazane parametrem.

## Acceptance criteria

- [x] Sesja bazy jest tylko do odczytu (`REPEATABLE READ`, `READ ONLY`,
  wyłącznie SELECT); ten sam odcisk stanu komórek we wszystkich
  uruchomieniach. Pierwotne sformułowanie „przed i po” w jednej transakcji
  niczego nie dowodziło i zastąpiono je porównaniem między uruchomieniami.
- [x] Pomiar z wyłączeniem importu dla wszystkich ośmiu symboli: zgodność,
  macierz pomyłek, pokrycie i zgodność reguły R7, wynik per pasmo predykcji.
- [x] Wycinek o sumie pikseli innej niż zapisana jest wykluczony i policzony
  (test; w danych na żywo 0 takich wycinków).
- [x] Komórka bez 7 dostępnych wzorców daje `do_przeglądu`.
- [x] Powtórne uruchomienie na tym samym stanie daje identyczny raport.
- [x] Testy jednostkowe modułu, Ruff i mypy dla zmienionych plików.
- [x] Niezależny audyt bez otwartych P0–P2; osobny commit, Outcome,
  CURRENT_STATE.

## Technical notes

- Dobór wzorców i tożsamość wycinka: reguły R3–R5 planu.
- Odtworzenie wycinka: `CanonicalSourceLoader.load`, potem
  `source_direct_warp_rgb` na `paddedSourceQuad` i kontrola
  `rgb_pixel_checksum_sha256` względem `rendered_pixel_checksum_sha256`.
- Opis B wymaga checkpointu aktywnej iteracji (`bestState`) i `torch` CPU.
  Brak checkpointu zatrzymuje narzędzie błędem, bez cichego przejścia na sam
  opis A.
- Głosowanie: 7 najbliższych według podobieństwa kosinusowego; zwycięzca
  według sumy podobieństw; remis rozstrzyga niższy indeks klasy.
- Komenda ma budżet czasu i pamięć podręczną wycinków w katalogu wyników;
  przerwane uruchomienie wznawia się bez ponownego dekodowania.
- Próbka oczekujących: deterministyczna kolejność `md5(id)`, równomiernie po
  importach.

## Expected files

- Nowe (proponowane):
  `services/worker/src/game_predictor_worker/symbols/reference_library.py`
  (`shape_descriptor`, `hue_descriptor`, `gray_world`, `vote`, `decide`),
  `services/worker/tests/test_symbol_reference_library.py`,
  `scripts/evaluate_symbol_reference_library.py`,
  `ai_docs/quality/SYMBOL_REFERENCE_LIBRARY_STAGE_A.md`.
- Istniejące, tylko używane:
  `services/worker/src/game_predictor_worker/images/normalization.py::CanonicalSourceLoader`,
  `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py::source_direct_warp_rgb`,
  `services/worker/src/game_predictor_worker/images/symbol_model_benchmark.py::SpatialSymbolCnn`.

## Test cases

- 7 zgodnych wzorców w A i B → pewna propozycja tego symbolu.
- 6 z 7 zgodnych → `do_przeglądu`.
- A i B wskazują różne symbole → `do_przeglądu`.
- Mniej niż 7 dostępnych wzorców po wyłączeniu importu → `do_przeglądu`.
- Opis kształtu jest niezmienny względem zmiany barwy przy zachowanej jasności.
- Wejście o złym kształcie lub typie → błąd, nie wynik.

## Verification

Z katalogu worktree, PowerShell:

```powershell
$env:PYTHONPATH = "services\worker\src;services\api\src"
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe'
$p = Start-Process -FilePath $py -ArgumentList @('-m','pytest','services/worker/tests/test_symbol_reference_library.py','-q','-p','no:cacheprovider','--basetemp','C:\Users\tuszy\AppData\Local\Temp\srl-pt') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Testy są planowane do chwili wpisania wyników w Outcome.

## Risks / open questions

- Próba jest wybiórcza: operator poprawiał głównie błędy modelu.
- Pytania O1 i O2 planu nie blokują pomiaru, ale ograniczają jego interpretację.

## Outcome

### Changed

- Nowy czysty moduł
  `services/worker/src/game_predictor_worker/symbols/reference_library.py`:
  opis kształtu bez barwy, histogram barwy, korekta balansu bieli, głosowanie
  7 najbliższych wzorców i reguła pewności R7.
- Nowy skrypt odczytowy `scripts/evaluate_symbol_reference_library.py`
  (podkomenda `evaluate`): biblioteka zweryfikowanych komórek, ocena z
  wyłączeniem importu, próbka oczekujących komórek dla ośmiu symboli,
  `report.json`, `pending-proposals.json` i arkusze PNG. Wznawialny przez
  pamięć podręczną wycinków; kod wyjścia 3 oznacza niepełne renderowanie.
- Testy: `services/worker/tests/test_symbol_reference_library.py`,
  `services/worker/tests/test_evaluate_symbol_reference_library_script.py`.
- Raport: `ai_docs/quality/SYMBOL_REFERENCE_LIBRARY_STAGE_A.md`.

### Verification results

- 20 testów PASS (6,21 s); Ruff check/format i mypy `--strict` PASS dla
  czterech plików.
- Pomiar na 2 706 zweryfikowanych komórkach: głos kształtu 95,6%, pewne
  propozycje pokrywają 80,5% komórek ze zgodnością 99,5% (11 błędów).
  Aktywny model na tej wybiórczej próbie 12,7%. Rozbieżność z próbą z
  rozmowy mieści się w 3 pp (model 14,9% wtedy wyliczony z odtworzonych
  logitów, teraz z predykcji zapisanych w bazie).
- Próbka 400 oczekujących komórek z pasma 60–80%: szczegóły per symbol w
  raporcie jakości.
- `report.json` SHA `a461e260…8f8c` i `pending-proposals.json` SHA
  `26317ee6…1e71036` identyczne w sześciu uruchomieniach (cztery wykonawcy,
  dwa audytora).
- Niezależny audyt `claude-opus-5-5`: PASS bez P0–P2; poprawione P3 opisane
  w raporcie jakości.

### Not completed

- Brak ślepej oceny operatora (TASK-0741). Zgodność na oczekujących
  komórkach nie jest potwierdzona.
- Pozostawione P3: aktywny model tylko z wpisu `activate`, budżet czasu bez
  liczenia opisów, nazwa arkusza z kodu symbolu w bazie.

### Documentation updates

- Raport jakości, plan (tabela modeli po zmianie modelu sesji),
  CURRENT_STATE.

### Recommended next task

- TASK-0741: zamrożenie 200 komórek i ślepa ocena operatora.
