---
title: TASK-0366 — numery sekwencji częściowej strony z nazwy pliku
status: done
last_updated: 2026-09-01
---

# TASK-0366 — numery sekwencji częściowej strony z nazwy pliku

## Cel

Usunąć regresję, przez którą kompletna końcowa strona krótsza niż dziewięć
plansz zachowywała puste numery mimo poświadczonej nazwy
`seq_<start>-<end>.jpg`.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Zakres

- zachować dotychczasowe mapowanie pozycji dla pełnej strony dziewięciu plansz;
- uznać stronę 1–8 za kompletną, gdy liczba i pozycje detekcji dokładnie
  odpowiadają poświadczonemu zakresowi;
- pozostawić niekompletną geometrię bez numeru, bez przesuwania pozycji;
- naprawić pięć istniejących rekordów `seq_499996-500000.jpg` po sprawdzeniu
  braku konfliktu właściciela i rekordu kanonicznego.

## Definition of Done

- [x] `seq_499996-500000.jpg` mapuje pozycje `0–4` na `499996–500000`.
- [x] Niepełna geometria strony nadal wymaga korekty.
- [x] Testy produkcyjnego workflowu i Ruff przechodzą.
- [x] Pięć istniejących rekordów ma zgodne numery planszy, review i snapshotu.

## Outcome

Przyczyną był warunek `expected_count == 9` w ścieżce geometrii v20. Parser
nazwy działał poprawnie, ale adapter odrzucał poświadczony zakres strony
pięcioplanszowej. Warunek rozdzielono na kompletną zadeklarowaną stronę 1–9
oraz kompatybilną ścieżkę sparse wyłącznie dla strony dziewięcioplanszowej.

Kontrolowana korekta bazy przypisała rekordom pozycje `499996–500000` po
uzyskaniu blokad zakresu oraz potwierdzeniu braku konfliktów. Aktywny import nie
został zatrzymany ani zduplikowany. Ponowne przygotowanie projekcji musi zostać
zakolejkowane po zakończeniu transakcji aktywnego importu.
