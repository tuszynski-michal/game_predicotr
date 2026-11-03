---
title: Historia audytów planu uczenia geometrii z korekt
status: active
last_updated: 2026-11-02
---

# Historia audytów planu — zapis ustaleń z czatu

To skrócony zapis wyników dwóch rzeczywistych audytów Claude Code, nie nowy
audyt ani pełna transkrypcja. Pełne raporty CLI były zwrócone w czacie.
Audytor: `claude-opus-5-5/high`. Obydwa przeglądy wyłącznie do odczytu,
bez testów, treningu, zmian danych ani delegowania. Operator jawnie zgodził
się na przekazanie planu i niezbędnych fragmentów repozytorium do Anthropic.

## Runda 1

Werdykt: **REVISE**, 4 P1 i 5 P2.

- P1: nowa ocena niezgodna z dotychczasową polityką raportu i publikacji.
- P1: kontrola w workerze wymaga pełnych zdjęć mimo planowanego partial.
- P1: słabe kryterium poprawy na zbiorze wyboru checkpointu; brak definicji
  nowej metryki i dostatecznej liczby plansz kontrolnych.
- P1: losowy podział zdjęć nie chroni sąsiednich klatek.
- P2: porównanie z rzeczywistym przypisaniem gry; ponowne użycie rejestru
  D-554; deterministyczny przydział i freeze; readiness workera/bazy/budżetu;
  obowiązkowa tabela audytów i zapis planu.

Audytor zaznaczył brak pełnego odczytu ADMIN_APP, architecture/VISION_LAB,
readerów dowodów i freeze oraz UI. Uwagi o nich były oparte na planie.

## Runda 2

Werdykt: **REVISE**, 2 P1 i 4 P2.

- P1-A: partial controls trzeba dopuścić w obu rolach przez cały pion:
  capture.used, minima, manifest/freeze, GridBoardDataset, CohortPhotos,
  trainer oraz evaluator. Sam adapter VALIDATION nie wystarcza.
- P1-B: „wiarygodna kolejność” wymaga wskazania źródła i weryfikacji.
  UUID/ordinal/created_at nie są chronologią. Bufor liczy wszystkie zdjęcia.
- P2: określić legacy scope, gry wymagające poprawy i jawne zawężanie zakresu.
- P2: nazwać metrykę wyboru checkpointu i regułę remisów.
- P2: utrwalać bufory i respektować je w kolejnych iteracjach.
- P2: na pełnych zdjęciach zachować false/duplicate detection guards oraz
  określić dopasowanie przewidywań do etykiet.

Audytor przeczytał m.in. reader capture, commands/ordinals, domenę oceny,
publikację, worker i datasety. Nie odczytał całego UI, freeze ani pełnych
wpisów D-548–D-560. Werdykt dotyczył planu, nie implementacji.

## Stan po przyjęciu planu do implementacji

Operator zlecił całość rewizji uwzględniającej powyższe uwagi.
[Zapisany plan](../delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md)
przypisuje taski TASK-1120–1123 i obowiązkowe audyty implementacji przed
commitem. Nie ma nowego PASS planu. Preflight danych jest pierwszą bramką
i może zatrzymać implementację, jeśli dane nie spełniają przyjętych zasad.
