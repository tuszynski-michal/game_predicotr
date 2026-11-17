# Częściowe poprawki i modele Mumie a2 — 17.11.2026

## Wykorzystanie poprawek

Skrypt operatorski wymuszał `screen+grid`, który wymaga kompletnych dziewięciu
plansz. Istniejący tryb `grid-only` wykorzystuje częściowe korekty punktów.

| Materiał | TRAIN zdjęcia/plansze | VALIDATION zdjęcia/plansze | REGRESSION zdjęcia/plansze |
| --- | ---: | ---: | ---: |
| Zakończony trening całego zdjęcia | 10/90 | 5/45 | 13/21 |
| Nowy podgląd punktów siatki | 503/647 | 19/60 | 13/21 |

Rzeczywiste preview wykonano przy wymuszonym PostgreSQL READ ONLY: `canStart=true`,
brak blokad, 493 częściowo poprawione zdjęcia TRAIN. Pula kwalifikowanych etykiet
ma 561 zdjęć/758 plansz. To kwalifikacja do przyszłego treningu, nie nowy trening.

W dawnym splicie 25 631 zdjęć populacji miało 428 przypisań TRAIN; reprezentantów
TRAIN było 379: 10 pełnych, 367 częściowych z 424 kwalifikowanymi planszami oraz
2 bez kwalifikowanych plansz (`pendingCorrection=true`, pusta lista etykiet).
Pozostałe 49 przypisań to niereprezentatywne kopie. Bilans jest dokładny:
428 = 49 + 367 + 2 + 10; 379 = 367 + 2 + 10. Screen wykorzystał wszystkie 10
pełnych reprezentantów. Szczegółowe powody odrzucenia pojedynczych etykiet nie
są zapisane w manifeście; kategorie pominięć wyprowadzono z jego flag. Osobny
licznik flag bufora dotyczy populacji i nie jest składnikiem bilansu TRAIN. Przypisania,
reprezentanci, kwalifikowane etykiety i faktyczne użycie są różnymi licznikami.
Nowe preview ponownie sprawdza dowody i podział; dwóch splitów nie sumujemy.

## Wspólne porównanie modeli

Kohorta `19a52a6c-99ea-56ba-b713-c918338db415`, SHA manifestu
`d2c9c9c552fcaf3ff89c5acb6803ab9f6061ad67c962b487bddd4a35d4f22620`.
Osiem wcześniejszych modeli tej samej rodziny i kandydat dostały te same pięć
pełnych zdjęć VALIDATION A. Regułę rankingu zamrożono przed inferencją: poprawne
całe zdjęcia, poprawne plansze, mniejszy błąd geometrii, ID przy dokładnym remisie.
REGRESSION nie wybierała modelu; potwierdzała zamrożony wybór.

| Wersja | Poprawne zdjęcia A | Poprawne plansze A | Błąd geometrii A |
| --- | ---: | ---: | ---: |
| `9992a316` — najlepszy starszy według A | 5/5 | 45/45 | 0,003362654 |
| `3ed60010` | 4/5 | 44/45 | 0,002091415 |
| `bf327cfa` | 4/5 | 44/45 | 0,003415389 |
| `1be01f29` | 4/5 | 44/45 | 0,003468128 |
| `0ce39122` | 4/5 | 44/45 | 0,004044328 |
| `abe39bce` | 4/5 | 44/45 | 0,004146745 |
| `01767a49` — bezpośrednia baza | 4/5 | 44/45 | 0,004801590 |
| `158a740f` | 4/5 | 44/45 | 0,006072648 |
| `0b37cba4` — nowy kandydat | 5/5 | 45/45 | 0,003329561 |

Starszy zwycięzca to `9992a316-1b08-554e-aa3d-ec05addffb89`, eksport przebiegu
`42012366` z 8 listopada. Mniejszy błąd `3ed60010` nie rekompensuje utraty całej
poprawnej planszy i zdjęcia według ustalonej wcześniej kolejności.

| Kontrola | Starszy poprawne plansze | Nowy poprawne plansze | Starszy w granicy pól | Nowy w granicy pól |
| --- | ---: | ---: | ---: | ---: |
| VALIDATION A | 45/45 | 45/45 | 43/45 | 42/45 |
| REGRESSION | 21/21 | 21/21 | 17/21 | 18/21 |

Miara granicy pól używa istniejącego progu przesunięcia węzłów 10% rozmiaru pola
(`grid-cell-cut-v1`). Suma ról: oba modele mają 66 poprawnych plansz i 60 w granicy
pól. Błąd REG wynosi 0,006198241 dla starszego i 0,006030654 dla nowego, około 2,7%
mniej. Poprawa poprzedniego raportu wobec słabszej bazy `01767a49` (44 -> 45 oraz
17 -> 21) nie oznaczała takiej przewagi nad najlepszym starszym modelem.

Wniosek: nowy model dorównuje starszemu liczbą poprawnych plansz na tych kontrolach
i ma nieco mniejszy średni błąd. Nie wykazano przyrostu liczby poprawnych plansz
ani łącznej liczby plansz w granicy pól względem starszego.

## Dowody i ograniczenia

Produkcja: `GridCohortSnapshot`, adapter zdjęć kontrolnych, ONNX assessment,
`grid-correction-metrics-v1`. SHA szczegółów i identyczność źródeł/grup/wejść
sprawdzono przed inferencją. Etykiety są związane SHA całego manifestu.
Metryki kandydata i bezpośredniej bazy dokładnie odtworzyły poprzedni raport.

Artefakty: `artifacts/TASK-1240-comparison/` — wejście, pomiary per model/rola,
wybór sprzed REG, porównanie, oryginalne źródło wykonanej wersji i receipt SHA.
Lejek v3 ma osobny receipt z SHA manifestu i pełnego źródła przeliczenia oraz
kopią tego źródła. Oryginalnych wyników v1/v2 nie nadpisano.
Preview: `artifacts/TASK-1240-grid-only-preview.json`. Późniejsze zawężenie typu
zdjęć i rozdzielenie nazw liczników nie zmieniły inferencji ani wyników; wykonane
źródło i oryginalne artefakty pozostały zachowane.

Pomiar dotyczy 18 znanych zdjęć. REG ma 13 częściowych zdjęć i ocenia tylko
oznaczone cele. Niezależność sesji i brak ekspozycji starszych modeli na te zdjęcia
nie są dowiedzione. Ranking na pięciu zdjęciach ma ograniczoną zdolność uogólnienia.
To porównanie diagnostyczne, nie nowy certyfikat aktywacji. Nie strojono wag,
progów, augmentacji ani receptur. Nie było nowego treningu ani aktywacji.

## Naprawa uruchamiania

`Start-GridCorrectionLearning.ps1` domyślnie wybiera `grid-only`; `screen+grid`
wymaga jawnego wyboru. Zapisane polecenie nie zmienia trybu ani klucza: konflikt
zatrzymuje skrypt przed POST. Stary przebieg wymaga jego zapisanego trybu, a osobny
przyszły przebieg — nieużywanego `-CommandFile`. Plik `.game.json` wiąże polecenie
z grą, kluczem i SHA bajtów. Konflikt kończy operację przed żądaniem API. Starszy
domyślny plik wiąże nazwa zawierająca GameId. Istniejący niestandardowy plik bez
metadanych nie jest wysyłany automatycznie.

Skrypt wymaga API trwałego przygotowania TASK-1230 i sprawdza je przez OpenAPI
przed POST. Instalacja bez funkcji dostaje błąd bez startu treningu. W działającym
checkoutcie funkcja już istnieje; jej odrębne niezacommitowane zmiany nie należą
do tego taska. Kontrakt API i zasady danych pozostają bez zmian.

Testy uruchamiają rzeczywisty PowerShell z atrapą API, bez realnych jobów.
Regresje datasetu sprawdzają zachowanie częściowych punktów i wag oraz ochronę
detektora. Końcowe wyniki jakości i audytu są w Outcome TASK-1240.

Claude: runda 2 PASS, 0 P0/P1; 24 celowane testy PASS. Dwa zaakceptowane drobne
ryzyka operatorskie: używać wyłącznie absolutnej ścieżki `-CommandFile`; przerwanie
zapisu niestandardowego polecenia przed zapisem `.game.json` blokuje automatyczne
ponowienie bez POST i wymaga odzyskania metadanych. Zachować polecenie i klucz.
