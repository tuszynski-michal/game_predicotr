---
title: Mumie — sprawdzenie modeli na niezależnej partii zdjęć
status: accepted
last_updated: 2026-10-05
---

# Sprawdzenie większej partii Mumii

Operator zlecił dalszą samodzielną pracę i poprawianie wykrytych błędów do
chwili rzeczywistej potrzeby jego interakcji. Nie wymaga kolejnej zgody na
odczyt wcześniej wskazanego folderu ani rutynowe testy i poprawki.

## Stan, cel i reguły

TASK-0855 dostarczył dwa zamrożone modele RGB/gray, oba 83/84 na małej
walidacji. Aktualne 339 etykiet i wszystkie magazyny pozostają bez zmian.
Folder `C:\Users\tuszy\Documents\mumie wybrane\481537- 500000 cut`
ma 2052 zdjęcia z innego nagrania niż pierwszy wskazany folder. Wybieramy
600 równomiernie po deduplikacji i wykluczeniu pełnych komponentów użytych
do uczenia/walidacji oraz źródeł chronionych. To rozpoznawanie nowych zdjęć,
bez referencji pozwalających wyliczyć accuracy. Nie dobieramy temperatur,
wag ani modelu na tej partii. Super pozostaje osobnym nieoznaczonym atrybutem.

## TASK-0856 — trwała inferencja i przegląd

Proponowane moduły `vision_lab/symbol_batch.py` i `symbol_batch_review.py`
wykorzystują istniejące `SymbolTrainingAdapter.validate`, checksummed JSON,
create-only `publish_file`, blokadę `exclusive_bounded`, ONNX geometrii,
`lattice_cell_quads` i `crop_cell`. Słownik klas i eksporty są odczytywane
z zakończonych, weryfikowanych RunState. Manifest przypina SHA źródeł,
geometrii, obu eksportów, historii treningu i porównania TASK-0855.

Przed pikselami sprawdzamy pełny graf D-498 i chronione źródła. Całe komponenty
development/validation są wykluczone, nie tylko 13 oznaczonych zdjęć.
Powtórzony bajtowy SHA w folderze nie tworzy drugiej próbki. Każde zdjęcie
jest dekodowane osobno i ma niezmienny wynik wraz z SHA wizualizacji.
Blokada i ponowna kontrola wiązań zapobiegają równoległym writerom.
Wznowienie sprawdza opublikowane wyniki; nie liczy ich ponownie. Zmiana
źródła, modelu lub niezgodny artefakt zatrzymuje proces jawnym błędem.

Sieć nie może narysować więcej plansz niż wynika z nazwy pliku i końca
operatorowego folderu. Inspekcja ujawniła `seq_499996-500004.jpg` w folderze
kończącym się na500000; na zdjęciu są rzeczywiście5 plansz. Ograniczamy ten
zakres do końca folderu, jawnie oznaczając konflikt nazwy. Nie zmieniamy pliku
operatora ani nie przypisujemy finalnej sekwencji. Przy nadmiarze
zachowujemy najwyżej N kandydatów o najwyższym score, następnie istniejący
reading_order. Nadmiar/brak jest zapisanym problemem zdjęcia, bez zgadywania
ostatecznych numerów sekwencji. Nie tworzymy brakujących plansz. Nieprawidłowa
geometria i pola poza zdjęciem wymagają review; pozaobrazowe pola nie otrzymują
fikcyjnych pikseli ani przewidywanego symbolu.

Każdy dostępny crop ma identyczny renderer RGB96, resize64/normalize-half
z torchvision, gray3 po normalizacji. CPU ONNX dostaje batch do 135 pól.
Zamrożona temperatura RGB1.05/gray1.25, fuzja RGB0.3/gray0.7 i próg0.9
są odczytywane z porównania, bez lokalnego strojenia. Zgodność modeli nie
zatwierdza symbolu ani siatki. Wyniki zawierają obie klasy, pewność, powody
review i jednoznaczny numer zdjęcia/planszy/pola.

Przegląd pokazuje pełne zdjęcie z siatkami, cropy i propozycje. Lista ograniczona
do przypadków niepewnych oraz rozłożonej po źródłach kontroli każdej klasy
zapobiega tysiącom kafelków. Pozostałe zdjęcia są dostępne przez indeks.
Kontrola przez agenta jest analizą, nie zapisem zatwierdzeń człowieka.
Jeżeli model ma rzeczywiste błędy, usuwamy przyczyny techniczne; braku nowych
etykiet nie maskujemy samopotwierdzaniem przewidywań. Dopiero konieczne
oznaczenie niezależnego zestawu przez człowieka jest granicą pracy.

## Odbiór, testy i ograniczenia

Testy planowane: count5 zamiast6, brak plansz, częściowe pola, deterministyczna
kolejność, preprocessing równy treningowi, disagreement/prog0.9, chronione
komponenty, drift, create-only i wznowienie po utracie odpowiedzi. Kontrola
format/lint/typecheck oraz regresje dotychczasowych modeli. Realne 600 zdjęć,
podsumowanie liczności bez fikcyjnego accuracy, kontrola wizualna problemów,
restart w nowym procesie i niezmienione oryginalne SHA. Osobny commit.

Każda skończona porcja ma timeout120s i limit25 zdjęć. Trwały postęp per zdjęcie
pozwala kontynuować po przerwaniu. Pamięć obejmuje jeden obraz i do135 cropów;
galeria zapisuje jeden atlas zamiast135 plików. Brak DB, automatycznej zmiany
etykiet, treningu na przewidywaniach, aktywacji, push, merge i wdrożenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0856 — trwała inferencja i przegląd 600 zdjęć | gpt-6.1-sol | high | Ochrona komponentów, zgodność preprocessingu, wznowienie i ocena rzeczywistych przypadków. | Odrębny samodzielny przegląd, testy integralności i wizualny odbiór; bez delegowania |
