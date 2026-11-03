# TASK-1139 — Ograniczony preflight Mumie A2

Odczyt 2026-11-03: transakcja READ ONLY, timeout zapytań 15 s, zakres jednej gry, limit 5001 źródeł. Brak zapisów do bazy, restartów, treningu i zastosowania modelu.

| Ochrona | Zdjęcia | Zdjęcia zatwierdzone | Plansze zatwierdzone |
|---|---:|---:|---:|
| Rzeczywiście użyte TRAIN | 60 | 60 | 77 |
| Rzeczywiście użyte VALIDATION | 13 | 13 | 17 |
| Rzeczywiście użyte REGRESSION | 13 | 13 | 21 |
| Trwałe bufory | 40 | 3 | 3 |
| Wyłącznie nieużyte rezerwacje v1 | 662 | 44 | 78 |

Łącznie 788 zdjęć, 133 zatwierdzone zdjęcia i 196 plansz. Nie znaleziono recording_occurrences dla ich tożsamości. Wzrost REGRESSION o jedną planszę na zdjęciu wcześniej kontrolnym pozostaje kontrolą. Różnica względem dawnego 117/89 nie oznacza 79 przykładów TRAIN.

Ograniczona analiza pozycji wszystkich źródeł wskazuje potencjalnie 38 zdjęć/69 plansz z nieużytych rezerwacji oddalonych o ponad dziesięć zdjęć od każdej rzeczywiście użytej kontroli. Pozostałe 6 zdjęć/9 plansz leży zbyt blisko. Wynik wymaga końcowej weryfikacji atestów, tożsamości, etykiet i ograniczonej rezerwy nowym solverem; nie jest deklaracją użytego zbioru ani wyniku jakości.

Surowy lokalny odczyt: `artifacts/task1139-preflight.json`; skrypt: `artifacts/task1139-preflight.py`.

Końcowa symulacja nowej domeny na metadanych operatora (bez instalacji capability
0172) potwierdziła TRAIN 98 zdjęć/146 plansz: 60/77 wcześniej użytych i 38/69 nowych.
VALIDATION 13/17, REGRESSION 13/21; bufory 53 zdjęcia, w tym 9 opisanych/12 plansz.
Zidentyfikowano 102 zdjęcia z aktualnym grid_issue. Brak bezpiecznej rezerwy przyszłych
kontroli (0/0); nie blokuje to istniejących wystarczających kontroli. Wejścia rejestru
v2 zasymulowano z odczytanych rekordów v1 przy sprawdzonym braku recording_occurrences.
Pełny wynik: `GRID_CORRECTION_GROWTH_SIMULATION_20261103.json`.
