---
title: TASK-0742 — A3 — odczytowy podgląd propozycji dla predykcji Arbuz
status: done
last_updated: 2026-09-29
---

# TASK-0742 — A3 — odczytowy podgląd propozycji dla predykcji Arbuz

## Status

`done`

## Goal

Operator widzi w lokalnym widoku, na jakie symbole biblioteka wzorców
(polityka `no-bulk-approve-v2`) zmieniłaby wszystkie oczekujące komórki z
predykcją Arbuz poniżej 60% oraz 60–80%, bez żadnej zmiany w bazie.

## Context

Etap A przeszedł bramkę (TASK-0741). Operator nie zlecił etapu B; chce
najpierw zobaczyć kierunek zmian na pełnej grupie. D-465 wyłącza z wzorców
zatwierdzenia masowe.

## Dependencies / entry conditions

- TASK-0740 i TASK-0741 done; D-465 accepted.
- Fakt 2026-09-29: oczekujące komórki Arbuz bez flagi jakości i z pełną
  widocznością: 3 295 poniżej 60%, 8 569 w 60–80%, z 8 742 zdjęć.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Niezależny review
`claude-opus-5-5`, `high`, osobny agent. Eskalacja: ponowna ślepa ocena z
polityką v2 poniżej bramki etapu A wstrzymuje przekazanie podglądu jako
rekomendacji.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-464, D-465)
- `ai_docs/quality/SYMBOL_REFERENCE_LIBRARY_STAGE_A.md`

## Scope

- Polityka wzorców `no-bulk-approve-v2` (D-465) jako parametr wszystkich
  podkomend, domyślna.
- Podkomenda `blind-rescore`: ta sama zamrożona próbka ślepej oceny,
  propozycje z polityką v2, porównanie z ocenami operatora (oryginalnymi i
  poprawionymi).
- Podkomenda `preview`: wszystkie oczekujące komórki wskazanych predykcji w
  zakresie pewności, propozycje, zestawienie „z czego na co” per pasmo,
  lokalna strona z miniaturami (limit na grupę) i pełny plik JSON.

## Out of scope

- Zapis propozycji, zmiana etykiet, API, UI Admina, trening (etapy B i C).

## Acceptance criteria

- [x] Tylko odczyt bazy; pliki w katalogu wyników oraz we wskazanej, współdzielonej
  pamięci podręcznej wycinków wzorców (`--library-cache`).
- [x] Polityka v2 wyklucza komórki, których ostatnie zdarzenie decyzji jest
  masowym `approve`; `reassign` pozostaje.
- [x] Ponowna ocena ślepej próbki z polityką v2 raportowana obok v1.
- [x] Podgląd obejmuje wszystkie wskazane komórki (albo jawnie liczy
  wykluczone), pasma `<60%` i `60–80%`, zestawienie przejść i miniatury.
- [x] Wznawialne renderowanie w limicie czasu jednego polecenia.
- [x] Testy, Ruff, mypy; niezależny audyt bez P0–P2; commit, Outcome,
  CURRENT_STATE.

## Technical notes

- Ostatnie zdarzenie decyzji: `image_symbol_review_events` po
  `(game_id, cell_review_id, created_at)` (istniejący indeks), akcje
  `approve` i `reassign`, masowe = `operation_id IS NOT NULL`.
- Wycinki podglądu bez kontekstu (pamięć); kontekst renderowany tylko dla
  miniatur.
- Pasma: krawędzie z parametru, domyślnie 0,6.

## Expected files

- Istniejące: `scripts/evaluate_symbol_reference_library.py`.
- Nowe: `scripts/symbol_reference_preview.html`, testy w
  `services/worker/tests/test_evaluate_symbol_reference_library_script.py`.

## Test cases

- Grupowanie przejść i wybór miniatur deterministyczny, z limitem.
- Renderowanie bez kontekstu zapisuje i wczytuje pamięć podręczną.
- Ponowna ocena odrzuca próbkę, której komórki lub sumy pikseli różnią się
  od zamrożenia.

## Verification

Komendy i wyniki zapisuje raport jakości po uruchomieniu.

## Risks / open questions

- Po wyłączeniu zatwierdzeń masowych biblioteka ma mniej wzorców zgodnych z
  predykcją modelu; pokrycie może spaść.

## Outcome

### Changed

- `scripts/evaluate_symbol_reference_library.py`: parametr
  `--reference-policy` (`all-human-v1`, domyślnie `no-bulk-approve-v2`
  według D-465) we wszystkich podkomendach liczących propozycje;
  podkomendy `blind-rescore` (ponowna ocena zamrożonej próbki, przypięta do
  gry i checkpointu, bez komórek próbki w bibliotece) i `preview` (jeden
  przewidziany symbol, pasma pewności, zestawienie przejść, lokalny widok,
  wznawialne renderowanie z pamięcią podręczną wierszy).
- `symbols/reference_library.py`: `vote_batch` (wsadowe głosowanie o tych
  samych sąsiadach co `vote`), wspólne `_vote_from_neighbours`.
- `scripts/symbol_reference_preview.html`: widok offline.
- D-465 w `DECISION_LOG.md`, plan (A3), raport jakości (sekcja A3).

### Verification results

- 36 testów PASS; Ruff check/format i mypy `--strict` PASS.
- `all-human-v1` odtwarza wyniki T1 bez zmian (pokrycie 80,5%, zgodność
  99,5%); `no-bulk-approve-v2`: 2 508 wzorców, 79,1% / 99,5%.
- Ślepa próbka z polityką v2: oceny oryginalne 80,5% / 99,4%, poprawione
  80,6% / 100%; bramka PASS; zmienione propozycje 6 z 200.
- Podgląd Arbuz poniżej 80%: 11 864 komórek; 0–60%: 77,1% bez zmiany,
  15,0% do przeglądu; 60–80%: 61,0% bez zmiany, 14,0% do przeglądu,
  największe przejścia do Wiśni (766) i Pomarańczy (588). `preview.json`
  SHA `0ed25966…16e9` powtarzalny; wznowienie z limitem 30 s sprawdzone.
- Niezależny audyt `claude-opus-5-5`: pierwszy przebieg FAIL (4 × P2),
  po poprawkach PASS bez P0–P2. Poprawiono także P3: atomowy zapis i
  odporność pamięci podręcznej wierszy, wersja biblioteki w jej kluczu.

### Not completed

- Pasmo 0–60% nie ma ślepej oceny; jego wyniki są niepotwierdzone.
- Pozostałe P3: `blind-rescore` sprawdza grę i model po renderowaniu
  biblioteki; wznowienie podglądu nadal liczy deskryptory biblioteki.

### Documentation updates

- D-465, plan, raport jakości, CURRENT_STATE.

### Recommended next task

- Decyzja operatora po obejrzeniu podglądu: kolejne symbole w podglądzie,
  ślepa ocena pasma 0–60% albo uruchomienie etapu B.
