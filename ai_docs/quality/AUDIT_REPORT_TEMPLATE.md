---
title: Szablon raportu audytu krzyżowego
status: active
last_updated: 2026-10-08
---

# Szablon raportu audytu krzyżowego

Raport zapisuje się jako `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` normalną
prozą po polsku. Audytor wypełnia poniższy szablon w całości: sekcje bez
znalezisk zawierają zdanie „Brak.”, nie są pomijane. Wiersz `Werdykt:` jest
czytany maszynowo przez `scripts/audit_task.ps1`, więc musi mieć dokładnie
postać `Werdykt: PASS` albo `Werdykt: REVISE`.

Zasady werdyktu i ważności:

- `PASS` oznacza brak otwartych znalezisk P0 i P1. Znaleziska P2 mogą
  pozostać i są wtedy wymienione z propozycją poprawki lub akceptacji ryzyka.
- `REVISE` oznacza co najmniej jedno otwarte znalezisko P0 lub P1. Otwarte
  P0/P1 blokują commit taska.
- P0: błędne działanie, utrata danych, luka bezpieczeństwa albo niespełnione
  kryterium akceptacji. P1: brak wymaganego testu, naruszenie kontraktu lub
  procesu z `AGENTS.md`, rozwiązanie niejawnie sesyjne zamiast trwałego.
  P2: drobne ulepszenie lub ryzyko, które można odnotować zamiast naprawiać.
- Każde znalezisko wskazuje `ścieżka:linia` (numer po zmianie), opisuje skutek
  i podaje proponowaną poprawkę. Nie zgłaszaj uwag stylistycznych ani
  rozszerzeń zakresu.

## Szablon do skopiowania

```markdown
# Audyt TASK-NNNN — <tytuł taska>

Werdykt: PASS
Audytor: <model, reasoning>
Wykonawca: <model, reasoning>
Zakres: <base>...<HEAD sha> oraz zmiany niezacommitowane, data <RRRR-MM-DD>
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

<Dwa–cztery zdania: co zbadano, ogólna ocena, główne ryzyko.>

## Znaleziska

### P0

- [P0-1] `ścieżka:linia` — <opis, skutek, proponowana poprawka>

Brak.

### P1

- [P1-1] `ścieżka:linia` — <opis, skutek, proponowana poprawka>

### P2

- [P2-1] `ścieżka:linia` — <opis, skutek, proponowana poprawka lub akceptacja ryzyka>

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): <identyfikatory znalezisk z
poprzedniego raportu, które poprawka usunęła, z dowodem>.

Otwarte: <identyfikatory wszystkich nadal otwartych znalezisk P0–P2>.

## Proponowane testy

- <Test lub scenariusz, którego brakuje albo który zwiększyłby pewność; podaj plik i komendę.>

## Zakres przeglądu i ograniczenia

<Co faktycznie przeczytano, czego nie dało się sprawdzić statycznie, np. brak uruchomienia testów.>
```

W prawdziwym raporcie usuń przykładowe wiersze, które nie mają zastosowania
(na przykład `[P0-1]` przy „Brak.”), i zostaw jedną z form każdej sekcji.
