---
title: TASK-0342 — Elastyczna geometria strony i wysyłanie partii
status: done
last_updated: 2026-08-30
---

# TASK-0342 — Elastyczna geometria strony i wysyłanie partii

## Goal

Pozwolić poprawiać dziewięć rozdzielonych ramek na zakrzywionym ekranie oraz
zapisać serię ręcznych korekt przed jednym ponownym preflightem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- prowadzone wskazanie narożników LT, PT, PD, LD z walidacją kolejności;
- 36 niezależnych punktów krawędzi zachowujących odstępy dziewięciu ramek;
- dokładny reset do geometrii wczytanej dla źródła;
- zapis wielu override'ów bez preflightu po każdym zdjęciu;
- jedna jawna akcja wysłania zapisanej partii;
- ponowna edycja istniejących ręcznych override'ów;
- lokalny dostęp do odroczonej kolejki niepełnej geometrii.

## Out of scope

- zmiana progów czerwonej ramki albo ORB/RANSAC;
- automatyczne zaakceptowanie starej geometrii bez kontroli człowieka;
- rozszerzenie uprawnień zdalnego Reviewera;
- usuwanie historycznych rewizji geometrii.

## Outcome

- Admin generuje dziewięć row-major quadów z rozdzielonej siatki krawędzi 6 ×
  6, pozwala dowolnie dopasować jej punkty oraz wyjątkowo poprawić jeden quad.
- Sekwencja kliknięć narożników jest jawna i fail-fast dla skrzyżowanego
  obrysu. `Reset` przywraca wczytane narożniki i quady.
- `Zapisz i przejdź dalej` utrwala append-only override, a `Wyślij zapisane do
  weryfikacji` dopiero potem uruchamia wspólny preflight.
- API listy źródeł zwraca bieżące ręczne quady, rewizję i informację o zmianie
  względem snapshotu. Dzięki temu wszystkie 13 zapisanych stron nowej gry można
  ponownie skorygować; stary import z czterema kotwicami nie jest źródłem
  aktualnego licznika.
- Testy domeny siatki, kontraktu UI, lokalnego Reviewera, API i generowanego
  klienta przechodzą. Szczegóły komend znajdują się w raporcie commita.

## Known limitation

Stare override'y zapisane jako stykająca się siatka muszą zostać raz poprawione
przez operatora. System nie zgaduje nowych krawędzi ani nie obniża twardej
bramki czerwonej ramki.
