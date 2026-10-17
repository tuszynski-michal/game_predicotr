# Audyt TASK-1032 — Odchudzenie `AGENTS.md`: procedury do skilli

Werdykt: PASS
Audytor: gpt-6.1-sol / medium (według briefu)
Wykonawca: claude-opus-5-5 / high
Zakres: HEAD...454554fa60a0448e64fd864ea21f8e9d3e26639c oraz zmiany niezacommitowane TASK-1032, data 2026-10-16
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono skrócenie `AGENTS.md`, przeniesienie procedur do skilli, mapę reguł oraz wymuszanie budżetu i dodane testy. Nie stwierdzono otwartych P0 ani P1. Plik ma 13 942 B, oba lustra skilli są identyczne bajtowo, a dotychczasowe nagłówki zachowano. Wyniki testów i `docs:check` oceniono na podstawie deklaracji wykonawcy; nie uruchamiano ich ponownie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| `AGENTS.md` ≤ 14 000 B; budżet wymuszony | spełnione | Odczyt bajtów: 13 942 B; `scripts/check_startup_read_budget.py:167`; test granicy 14 000/14 001 B w `services/worker/tests/test_check_startup_read_budget_script.py:104`. |
| `docs:check` PASS | niezweryfikowane | PASS zadeklarowano w `ai_docs/tasks/1032-agents-md-slimming.md:344`. Statycznie potwierdzono włączenie kontroli budżetu do `docs:check`. |
| Każda dotychczasowa reguła ma wskazane miejsce w `Outcome` | spełnione | `ai_docs/tasks/1032-agents-md-slimming.md:147`; tabela zawiera 174 kolejno ponumerowane reguły. Porównano diff z treścią docelowych sekcji i skilli. |
| Brak martwych odwołań do usuniętych nagłówków | spełnione | Porównanie nagłówków `HEAD:AGENTS.md` z bieżącym plikiem: brak usuniętych nagłówków. Wskazane skille istnieją. |
| Review Codex PASS albo jawna rezygnacja operatora | spełnione | Niniejszy raport: PASS. |

## Listy zamknięte i otwarte

Zamknięte: Brak; runda 1.

Otwarte: Brak.

## Proponowane testy

Brak. Dodane testy obejmują przekroczenie budżetu, wartość graniczną i normalizację CRLF do LF.

## Zakres przeglądu i ograniczenia

Przeczytano brief, zadanie i plan, dokumenty startowe, `CLAUDE.md`, zmienione skille, skrypt budżetu i jego testy. Porównano zmiany z wersją `HEAD`, sprawdzono zgodność kopii skilli oraz zachowanie nagłówków. `git diff --check` zakończył się bez błędów.

Przegląd objął również test budżetu pominięty w pathspecach briefu, ale należący do zakresu TASK-1032. Nie uruchamiano testów, formatterów, lintowania, kontroli typów ani `docs:check`. Deklarowane wyniki tych kontroli pozostają dowodami wykonawcy.