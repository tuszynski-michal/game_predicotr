---
title: TASK-0743 — A4 — podpowiedzi z dwóch opisów i rozmiar biblioteki wzorców
status: done
last_updated: 2026-09-29
---

# TASK-0743 — A4 — podpowiedzi z dwóch opisów i rozmiar biblioteki wzorców

## Status

`done`

## Goal

Komórka „do przeglądu” dostaje podpowiedź dwóch kandydatów z połączonych
głosów obu opisów, a pomiar pokazuje, czy większa biblioteka wzorców
(więcej wzorców na grupę) poprawia pokrycie bez utraty zgodności.

## Context

Operator wskazał trzy komórki z błędną podpowiedzią „kształt wskazuje”
(`292172c9`, `681eaba5`, `aa8e6866`). Wszystkie były „do przeglądu”, więc
żadna pewna propozycja nie była błędna. Na 38 komórkach przeglądu ze ślepej
próbki: podpowiedź z kształtu 31/38, połączona 33/38, połączona z dwoma
kandydatami 38/38, stary model 28/38. Operator zaakceptował pomiar i zmianę
podpowiedzi; stara predykcja modelu pozostaje nietknięta jako rezerwa.

## Dependencies / entry conditions

- TASK-0742 done (`v1.7.56`), D-465.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Niezależny review
`claude-opus-5-5`, `high`, osobny agent.

## Relevant docs

- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-464, D-465)
- `ai_docs/quality/SYMBOL_REFERENCE_LIBRARY_STAGE_A.md`

## Scope

- Głos zachowuje wagi klas; podpowiedź = klasy o największej sumie wag obu
  opisów (dwie pierwsze). Pewne propozycje (reguła R7) bez zmian.
- Parametr `--references-per-group` we wszystkich podkomendach; domyślna
  wartość zmieniana z 15 na 40 tylko wtedy, gdy pomiar nie obniży zgodności
  (zapowiedziane operatorowi przed pomiarem).
- `blind-rescore` raportuje trafność podpowiedzi na komórkach przeglądu:
  kształt, połączona (1 i 2 kandydatów), stary model, połączona + stary model.
- Pomiar T1 i ślepej próbki dla 15 i 40 wzorców na grupę; podgląd Arbuz
  z nową podpowiedzią.

## Out of scope

- Zapis w bazie, maskowanie zasłonięć, trening, etap B.

## Acceptance criteria

- [x] Pewne propozycje przy 15 wzorcach identyczne jak w TASK-0742.
- [x] Raport trafności podpowiedzi na komórkach przeglądu ślepej próbki.
- [x] Porównanie 15 i 40 wzorców: pokrycie i zgodność T1 oraz ślepej próbki.
- [x] Podgląd pokazuje dwóch kandydatów dla komórek przeglądu.
- [x] Testy, Ruff, mypy; niezależny audyt bez P0–P2; commit, Outcome,
  CURRENT_STATE.

## Technical notes

- Wagi klas liczone jak dotąd: suma `max(podobieństwo, 0) + 1e-6` po
  sąsiadach danej klasy.
- Podpowiedź to informacja pomocnicza; nie zmienia R7 ani bramki.
- Zmiana domyślnego rozmiaru biblioteki następuje po pomiarze, jeżeli
  zgodność T1 i ślepej próbki nie spada; stara wartość pozostaje dostępna
  parametrem.

## Test cases

- Wagi klas sumują wagi sąsiadów; dwóch kandydatów w kolejności malejącej.
- Podpowiedź przy braku wzorców jest pusta.

## Outcome

### Changed

- `Vote.class_weights` i `hint_candidates` w `symbols/reference_library.py`.
- Skrypt: `--references-per-group` (domyślnie 40, zapisywany w raportach),
  podpowiedź dwóch kandydatów w podglądzie, `reviewHints` w `blind-rescore`.
- Raport jakości (sekcja A4), D-465 (rozmiar biblioteki, podpowiedzi).

### Verification results

- 41 testów PASS; Ruff i mypy `--strict` PASS.
- Przy 15 wzorcach pewne propozycje identyczne jak w TASK-0742 (ślepa
  próbka 80,6% / 100%; podgląd: 0 różnic na 11 864 komórkach).
- 40 wzorców: T1 87,8% / 99,7%, ślepa próbka 90,3% / 100% (177 pewnych);
  podgląd: 0 zmian symbolu pewnej propozycji, 542 przegląd→pewne, 58 odwrotnie.
- Podpowiedź na komórkach przeglądu ślepej próbki: 2 kandydatów 38/38
  (15 wzorców) i 19/19 (40 wzorców); dotychczasowa z kształtu 31/38 i 15/19.
- Niezależny audyt `claude-opus-5-5`: PASS bez P0–P2; poprawiono P3
  (parametr w raportach, stały kształt raportu podpowiedzi, testy remisu i
  liczenia podpowiedzi, wpis w D-465).

### Not completed

- Zasłonięta śliwka `292172c9` nadal ma błędną podpowiedź; wymaga wzorców
  z poprawek operatora.
- Pasmo 0–60% bez ślepej oceny.

### Recommended next task

- Operator poprawia w Adminie komórki takie jak `292172c9`; ponowny podgląd
  pokaże, czy nowe wzorce pomagają. Potem decyzja o innych symbolach lub
  etapie B.
