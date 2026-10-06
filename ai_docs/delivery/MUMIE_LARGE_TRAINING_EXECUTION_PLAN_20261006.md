---
title: Mumie — większy zbiór i trwałe użycie modelu
status: accepted
last_updated: 2026-10-06
---

# Stan, cel i upoważnienie

Operator wielokrotnie zlecił samodzielne dalsze treningi, użycie wewnętrznych AI
i wykorzystanie trzech niezależnych katalogów. W ostatniej rozmowie wskazał
priorytet dokładności oraz większej porcji danych. Nie wymagamy ponownej zgody
na przygotowanie i izolowany trening. Aktywacja, operacje DB i wdrożenie
pozostają odrębnymi działaniami.

Fakt: po v1.7.218 nie uruchomiono nowego treningu. Szacunek 1–3 godzin treningu
nie oznacza działającego procesu. Ostatni RGB trenował 633.28 s na 327 wycinkach;
najlepsza była epoka 8 z 20. Zwiększamy różnorodność danych, nie liczbę powtórzeń
tych samych przykładów. Liczność 2000–3000 jest celem, nie dowodem jakości.

Cel: większy eksperymentalny zbiór, jedna oceniona wersja RGB i przygotowana
integracja umożliwiająca korzystanie z modelu przy kolejnych uploadach.
Rozpoznawanie symboli i poprawność geometrii mają odrębne kryteria odbioru.
Nie deklarujemy poprawności całego filmu na podstawie 34 kierunkowych przykładów.

## A — TASK-0871: większa seria do wizualnej oceny

Reuse aktualnego batcha trzeciego filmu, dotychczasowych quadów, słownika
i symbol_batch_labels.prepare. Najpierw sprawdzić dotychczasowe wejścia i
całe grupy zdjęć. Wykluczyć pierwszy film, źródła human26/human8, validation,
diagnostic, wszystkie dotychczas ocenione rastry i dawne AI audit.

Wybór deterministyczny: do 2000 nowych, unikalnych rastrów; równomierne przejście
przez klasy propozycji i zdjęcia, maksymalnie 80 nowych wycinków na zdjęcie.
Propozycja CNN służy wyłącznie do doboru. Nie jest etykietą. Przy braku pokrycia
ujawnić rzeczywiste liczności zamiast dopisywać próbki. Kategorie nie ujawniają
propozycji reviewerom. Pakiety mają najwyżej 100 przypadków; istniejący limit
API/referencji i dotychczasowy workflow pozostają bez zmian.

Każdy pakiet zachowuje źródło, board/field, quad, pixel/PNG SHA i zatwierdzony
słownik. Dwa niezależne review oglądają dokładne rastry i istniejące kotwice
człowieka. Przyjmujemy wyłącznie zgodne high/high readable. Nieczytelność,
rozbieżność i grid_issue wykluczają target. AI-origin nigdy nie staje się
decyzją człowieka. Ramka jest obserwacją; nie tworzymy targetów Super.

Przygotowanie i review mają ograniczone kroki z wznowieniem. Status stale
oddziela liczbę wybranych, wyrenderowanych, ocenionych i zakwalifikowanych
przypadków oraz stan CNN. Fresh-process kontrola, niezależny audyt, Outcome
i osobny commit kończą ten task. Na tym etapie nie uruchamiamy CNN.

## B — TASK-0872: większy izolowany trening RGB

Po zakończeniu A dodać jawny wersjonowany kontrakt agregacji wielu pakietów.
Nie zwiększać po cichu limitów dawnych referencji ani protokołu generation4.
Reuse SymbolTrainingInputs, durable RunManager, checkpoint/RNG, preprocessing
i obecny model RGB. Nowy protokół ma najwyżej 20 epok, 7200 s i 50000 kroków;
jedna wersja i jeden run, bez automatycznego szukania seedów lub refitów.
Budżet jest limitem, nie obietnicą czasu ani dokładności.

Przed treningiem niezależnie zweryfikować pełny zbiór, pochodzenie AI/human,
brak powtórzeń i wykluczone całe źródła. Zachować human84 do wyboru epoki
i kalibracji. Human26 i human8 pozostają po-treningowymi kontrolami.
Każda klasa ma osobne porównanie z R2 RGB i V4 RGB; regresja blokuje przyjęcie.
Export CPU ONNX musi odtwarzać rzeczywisty model. Czas pozostały podawać dopiero
po pomiarze pierwszych epok; stale kontrolować logi i zapisane checkpointy.
Brak niezależnego pomiaru populacji należy jawnie ujawnić.

## C — TASK-0873: kandydat integracji

Po PASS B prześledzić istniejący release manifest i ścieżkę rozpoznawania.
Przygotować zgodne mapowanie zatwierdzonych symboli Mumii, preprocessing,
kalibrację, eksport i test importu bez automatycznej aktywacji modelu.
Zachować działanie 777 oraz dotychczasowych modeli. Nowy upload ma wykonywać
inferencję; poprawki zbierają się do późniejszego zbiorczego treningu.

Przed kodowaniem tego taska doprecyzować aktualne punkty integracji i odbioru
w samym tasku. Jeśli konieczna będzie zmiana API, zakomunikować ją operatorowi
i wykonać jeden spójny pion z OpenAPI, klientem i testem żądania. Nie tworzyć
równoległego endpointu bez potrzeby. Operacyjny import/DB/aktywacja/wdrożenie
wymagają konkretnego preview; przygotowanie kodu i testów odbywa się wcześniej.

## Odbiór, ryzyka i granice

| Wymaganie | Task | Dowód |
|---|---|---|
| Większy, różnorodny zbiór | 0871 | Rzeczywiste liczności, dokładne rastry, dwa review, pochodzenie i wykluczenia |
| Dłuższy trening oceniany wynikami | 0872 | Checkpointy, per-class gates, CPU ONNX parity, fresh resume |
| Widoczny efekt przy uploadzie | 0873 | Zgodny kandydat integracji, mapowanie i test przepływu bez aktywacji |
| Poprawki bez treningu na każdym uploadzie | 0873 | Regresja istniejącego workflow i zapisane instrukcje użycia |

AI consensus może być błędny. Dane z tego samego filmu nie zastępują nowego
niezależnego testu. Wybrany zbiór może nie osiągnąć celu 2000–3000; to wymaga
ujawnienia, nie osłabienia bramek. Poprawność cięcia siatki wymaga odrębnego
pomiaru i nie wynika z wyników klasyfikatora. Brak dokładnego terminu wdrożenia
przed sprawdzeniem integracji. Bez DB, migracji, usuwania, Super targets,
automatycznego push, merge, aktywacji ani wdrożenia.

## Wynik wykonania A i B — 2026-10-06

TASK-0871 zakończony: 2000 dokładnych rastrów, dwa niezależne review,
1726 zaakceptowanych ocen AI. Commit v1.7.219.

TASK-0872 zakończył jeden izolowany run RGB: 20 epok / 1360 kroków,
631.21 s pierwszej próby; 695.96 s łącznie z odtworzeniem eksportu w nowym
procesie. Odbiór implementacji, trwałości, CPU ONNX i rzeczywistego wznowienia
przeszedł. Kandydat V5 jest odrzucony: human34=29/34 wobec R2 RGB34/34;
10/18 bramek klas nie przechodzi. Wynik i niezmienne dowody zachowano w
ai_docs/quality/MUMIE_LARGE_RGB_EXPERIMENT_20261006.md.

Etap C pozostaje niewykonany: warunek przyjęcia kandydata w B nie został
spełniony. Nie uruchamiamy refitu ani innego seeda w tym protokole. Następny
osobno opisany eksperyment powinien kontrolować udział ocen człowieka i AI
oraz ekspozycję zdjęć, zanim zażądamy kolejnych oznaczeń lub wydłużymy trening.
Jest to kierunek dalszej pracy, bez zmiany bramek tego planu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0871 — większa seria i ocena wizualna | gpt-6.1-sol | high | Dobór źródeł i dokładnych rastrów musi zachować niezależne testy oraz pochodzenie oznaczeń. | Dwa wizualne review gpt-6.1-sol/high; niezależny audyt gpt-6.1-sol/high, zgodnie z wcześniejszą zgodą na wewnętrzne AI |
| TASK-0872 — nowy protokół i większy RGB | gpt-6.1-sol | high | Jawne limity, wielopakietowy manifest oraz trwałe checkpointy nie mogą osłabić dawnych kontraktów. | Niezależny audyt kodu, danych i actual inference: gpt-6.1-sol/high |
| TASK-0873 — kandydat integracji | gpt-6.1-sol | high | Mapowanie klas i release muszą zachować istniejące rozpoznawanie oraz nie aktywować modelu automatycznie. | Niezależny audyt kontraktu i regresji: gpt-6.1-sol/high |
