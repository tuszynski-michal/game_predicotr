# TASK-0469 — Full-layout structural detector

## Status
done
## Goal
Kolorystycznie niezależny lokalizator dziewięciu rzeczywistych obszarów plansz lub jawne odrzucenie.
## Relevant docs
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
## Dependencies
0468; zaakceptowany plan 0468–0472. Użytkownik zlecił całą pozostałą serię.
## Scope / expected files
Nowy moduł `auto-crop-v11.ts`, eksport pakietu, testy struktury i ograniczony runner development.
## DoD / tests
Pełne 3×3, brak syntetycznych plansz, maksymalnie 96 kandydatów, bounded analiza, kolor nie stanowi dowodu. Testy brakującego rzędu, niejednoznaczności i luminancji. Stary v10 bez zmian. Odbiór skuteczności dopiero 0472.
## Outcome
Nowa oddzielna ścieżka v11, bez zmiany v10. Cechy luminancji i gradientów,
9 bounded masek, integralna dylatacja, komponenty, niezależny dowód tekstury
wewnętrznej, ograniczenie 96 kandydatów/192 rzędów, spójność rozmiarów także
między rzędami (przyciski obudowy nie mogą zastępować plansz).
Testy core i typecheck OK. Development: 1/5 pełny układ na 960, reszta manual
po najwyżej dwóch analizach. To NIE jest odbiór jakości, recall jest niski.
Progi zamrożone przed holdout; brak dopasowywania do niego. Nie włączono v11.
Następny task: 0470 w ramach autoryzowanej serii.
