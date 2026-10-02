---
title: TASK-0814 — druga runda przeglądu etykiet: ponowna ocena plansz złych z oceną „lekko nacięta”
status: done
last_updated: 2026-10-02
---

# TASK-0814 — druga runda przeglądu etykiet

## Status

`done`

## Goal

Narzędzie `label_review` pozwala operatorowi ponownie ocenić wyłącznie
plansze oznaczone w pierwszej rundzie jako „zła” (opcjonalnie także „nie da
się ocenić”) z trzecią oceną „lekko nacięta”, a raport podaje dwa odsetki
błędów per poziom: ścisły i luźny.

## Context

Operator przeglądał 600 plansz (TASK-0801), przez pierwsze ok. 226 pozycji
oznaczając lekko nacięte symbole jako złe; poprosił 2026-10-02 o ponowne
pokazanie złych. Dla gry Mumie planowane są „super symbole” wymagające
dokładniejszego cięcia, dlatego potrzebne są oba odsetki.

## Dependencies / entry conditions

- TASK-0801 w repo; katalog przeglądu
  `production-geometry-snapshots\label-review-seed801` z historią pierwszej
  rundy (`history.jsonl` jest źródłem prawdy). Serwer przeglądu działa na
  `127.0.0.1:8103` i operator może jeszcze oceniać — nie zatrzymuj go i nie
  zmieniaj jego plików.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Rozszerzenie istniejącego małego
narzędzia. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/tasks/completed/0801-production-geometry-training-snapshot.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md`

## Scope

- Runda druga jako osobny magazyn decyzji w tym samym katalogu przeglądu
  (osobne pliki historii i decyzji; pliki pierwszej rundy tylko do odczytu).
- Wybór pozycji rundy drugiej: migawka decyzji pierwszej rundy w chwili
  przygotowania (parametr: tylko „zła” albo „zła” i „nie da się ocenić”),
  zapisana w pliku rundy, żeby późniejsze zmiany pierwszej rundy jej nie
  zmieniały.
- Oceny rundy drugiej: „dobra”, „lekko nacięta”, „zła”, „nie da się
  ocenić”; klawisze i opis reguły na stronie (dobra: linie w przerwach albo
  minimalnie zahaczają o brzeg; lekko nacięta: symbol w pełni rozpoznawalny,
  ale linia wyraźnie go nacina; zła: przesunięcie/przechył, część
  sąsiedniego symbolu w komórce, zła liczba kolumn lub rzędów, nie ta
  plansza).
- Raport łączony: dla pozycji z rundą drugą obowiązuje jej ocena, dla
  pozostałych ocena pierwszej rundy. Odsetek luźny = zła / oceniane;
  odsetek ścisły = (zła + lekko nacięta) / oceniane; „nie da się ocenić”
  poza mianownikiem; przedziały Wilsona 95% per poziom; liczba pozycji
  pierwszej rundy bez oceny.
- Uruchomienie rundy drugiej na osobnym porcie (domyślnie 8104), tylko
  `127.0.0.1`.
- Testy, wpis w przewodniku.

## Out of scope

- Zmiana próbki, zmiana decyzji pierwszej rundy, zmiany snapshotów.

## Acceptance criteria

- [x] Runda druga nie modyfikuje plików pierwszej rundy (test).
- [x] Zestaw pozycji rundy drugiej jest zamrożony przy przygotowaniu i
      odtwarzalny; ponowne przygotowanie bez `--force` nie nadpisuje
      istniejącej rundy.
- [x] Cztery oceny, cofanie i wznowienie działają jak w pierwszej rundzie.
- [x] Raport łączony z odsetkiem ścisłym i luźnym per poziom.
- [x] Pierwsza runda i jej serwer działają bez zmian (testy TASK-0801
      zielone).
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Kod rundy pierwszej w `vision_lab/label_review.py`. Serwer pierwszej rundy
uruchomiono z głównego checkoutu ze starszym kodem — zmiany w worktree nie
wpływają na działający proces. Nie przygotowuj rundy drugiej na
rzeczywistym katalogu, dopóki operator nie skończy pierwszej; przetestuj na
kopii katalogu w katalogu tymczasowym (bez kopiowania wycinków, jeśli da
się wskazać je ścieżką).

## Expected files

- Istniejące: `vision_lab/label_review.py`,
  `services/worker/tests/test_vision_lab_label_review.py`,
  `ai_docs/guides/VISION_LAB_LOCAL.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "label_review or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services
```

## Outcome

### Changed

- `vision_lab/label_review.py`: runda druga w osobnych plikach katalogu przeglądu
  (`round2.json`, `round2-history.jsonl`, `round2-decisions.json`,
  `round2-summary.json`); `read_first_round` (tylko odczyt `history.jsonl`, ignoruje
  niedokończoną ostatnią linię), `prepare_round2`, `verify_round2`, `Round2Store`,
  `create_round2_app`, `PAGE_ROUND2` (wyprowadzona ze strony pierwszej rundy, z regułą
  i czterema ocenami), `summarize_combined`; polecenia `round2-prepare` (`--include
  bad|bad-unreadable`, `--force`), `round2-serve` (domyślnie port 8104), `round2-report`.
  Kod pierwszej rundy bez zmian.
- `services/worker/tests/test_vision_lab_label_review.py`: 6 nowych testów.
- `ai_docs/guides/VISION_LAB_LOCAL.md`: sekcja rundy drugiej.

### Verification results

- `pytest services/worker/tests -k "label_review or no_production_storage_imports"`:
  14 passed (7 testów TASK-0801 bez zmian + 6 nowych + test importów).
- `ruff check` i `ruff format --check` na zmienionych plikach: czysto; `mypy --strict`
  na `label_review.py`: bez błędów. `ruff check services` zgłasza jeden wcześniej
  istniejący E501 w `test_page_geometry_preflight.py` (poza zakresem).
- Przebieg na kopii małych plików rzeczywistego katalogu (kopia `crops/` w katalogu
  tymczasowym): `round2-prepare --include bad-unreadable` zamroził 10 pozycji (stan
  pierwszej rundy: rewizja 617), ponowne przygotowanie bez `--force` dało
  `LABEL_REVIEW_ROUND2_EXISTS`, `round2-report` wypisał raport łączony, serwer
  rundy drugiej na porcie 8115 odpowiedział poprawnie i został zatrzymany.

### Not completed

- Kryterium „Osobny commit, `Outcome`, `CURRENT_STATE.md`” — commit i `CURRENT_STATE.md`
  należą do orkiestratora.
- Runda druga nie została przygotowana na rzeczywistym katalogu (zgodnie z zakazem).

### Documentation updates

- `ai_docs/guides/VISION_LAB_LOCAL.md`.

### Recommended next task

- Po przygotowaniu i ocenie rundy drugiej: decyzja operatora o progu odsetka ścisłego
  i luźnego dla S/B oraz o dokładniejszym cięciu dla „super symboli” gry Mumie.
