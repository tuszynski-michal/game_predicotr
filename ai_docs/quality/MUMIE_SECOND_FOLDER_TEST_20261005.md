---
title: Mumie — porównanie modeli na drugim folderze
status: completed
last_updated: 2026-10-05
---

# Mumie — porównanie modeli na drugim folderze

## Wynik

Przetestowano 200 zdjęć z 2052 w folderze
`C:\Users\tuszy\Documents\mumie wybrane\481537- 500000 cut`.
Oba modele nadal dają bardzo podobne siatki, lecz znaleziono konkretny wspólny
błąd: na zdjęciu zawierającym pięć plansz oba tworzą szóstą na pustym tle.
Obecny model nie rozwiązuje tego przypadku. Brak dowodu jego przewagi.

| Diagnostyka drugiego folderu | Iteracja 2 | Iteracja 3 |
|---|---:|---:|
| Przetworzone zdjęcia folderu | 200 | 200 |
| Zdjęcia z 9 wykrytymi planszami | 199 | 199 |
| Zdjęcia z 6 wykrytymi planszami | 1 | 1 |
| Nieprawidłowe struktury siatek | 0 | 0 |
| Pola, których crop wychodzi poza źródło | 2 | 3 |

Zgodność liczby plansz z nazwą pliku wynosi 199/200 dla obu modeli, ale
**nie jest accuracy**. Ostatni plik ma błędną metadaną zakresu dziewięciu
plansz; wizualnie zawiera tylko pięć. Strukturalnie poprawna siatka również
może znajdować się w pustym miejscu. Nie policzono accuracy 200 zdjęć bez
niezależnych referencji wszystkich plansz i granic.

## Dobór i integralność

2052 JPEG-i, zero dokładnych kopii SHA i zero SHA znanych kompletnych źródeł.
Wybrano deterministycznie 200 równomiernie po liczbowym zakresie:
`seq_481537-481545.jpg` do `seq_499996-500004.jpg`. Nie użyto nazwy pliku do
generowania geometrii ani przypisania końcowych `sequence_number`.
Inny folder i odległy numer nie dowodzą niezależnego filmu. Ujęcia nadal
przedstawiają zbliżone warunki: ten sam układ ekranu, perspektywę i zasłonięcia.

Użyto istniejącego adaptera `scripts/test_mumie_folder.py`, istniejącego ONNX
engine, CPU z czterema wątkami i tych samych eksportów iteracji 2 i 3.
Nie zmieniono kodu aplikacji, progów ani modeli. Kontrolne 11 zatwierdzonych
zdjęć z poprzedniego testu jest osobną częścią manifestu. Łącznie 422 wyniki:
200 zdjęć nowego folderu + 11 kontrolnych, dwukrotnie dla obu modeli.

Artefakty:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-folder-test-20261005\second-481537-500000`.
Wyniki create-only są związane z SHA manifestu, źródeł, modeli i obrazów.
Pierwszego testu nie nadpisano. Katalog wyników jest ignorowany przez Git.

| Element | SHA-256 |
|---|---|
| Manifest payload | `16bd985c89a4d974c0b040e5068141a646b54e798555254653e1694f92871c5c` |
| Inwentarz folderu | `761eb419f85a35a2d790a6321cff37bc845aaab376422995816bb7cc8d57d6c2` |
| Anotacje, rewizja 591 | `06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43` |
| Summary payload | `7a2ff65d5234eb4b01789a4bd2d50b781b1388df0b34e46b41c8e3832e7703c0` |
| Bundle iteracji 2 | `d1b0beec1f905bf4564ef856ea13de061a9b725e24e780e8247e9176bd77f157` |
| Bundle iteracji 3 | `024dc1f0d5bc46515cb4173e04c474ea864d730b4d48abd6f418bacfa9b43566` |

## Różnice między modelami

Porównano wyłącznie predykcje obu modeli na tych samych zdjęciach. Plansze
dopasowano istniejącymi `hungarian` i `quad_iou`, maksymalizując IoU narożników
z minimum 0,5. Następnie policzono odległość euklidesową odpowiadających sobie
węzłów we współrzędnych oryginalnego obrazu. Żaden model nie jest referencją.

43128 porównań węzłów: mediana 0,327794 px, P95 0,794990 px, maksimum
28,947359 px. Największa różnica dotyczy zdjęcia z fałszywą szóstą planszą.
Mała mediana i P95 wyjaśniają wizualną zbieżność; nie dowodzą poprawności.
Szczegóły: `comparison-diagnostics.json` z bindingiem manifestu i top 10 różnic.

## Przypadki do dalszej pracy

### `seq_499996-500004.jpg` — fałszywa plansza

Bezpośredni odczyt źródła pokazuje pięć plansz o widocznych numerach
499996–500000. Oba modele zwracają sześć. Szósta siatka leży na niebieskim
pustym tle po prawej stronie drugiego rzędu, przy strzałce interfejsu.
Arkusz cropów iteracji 3 pokazuje 15 pól tła zamiast symboli tej planszy.
Oba modele znajdują pięć rzeczywistych plansz, ale tworzą dodatkową.
Jest to obserwacja wizualna agenta, nie zapis anotacji ani akceptacja operatora.

Nazwa `seq_499996-500004` sugeruje dziewięć pozycji, lecz obraz kończy dane
na 500000. Metadanej nie poprawiano i nie tworzono brakujących sekwencji.
W przyszłej referencji należy rozdzielić rzeczywiste plansze od pustych miejsc;
nie dostarczać fałszywej siatki jako targetu uczenia.

### `seq_485704-485712.jpg` — ucięty kadr

Zdjęcie źródłowe obcina górną krawędź pierwszej planszy. Render nie może
odzyskać brakujących pikseli: iteracja 2 ma dwa, iteracja 3 trzy niemożliwe
cropy. W arkuszu iteracji 3 brakuje trzech górnych pól pierwszej planszy.
Nie jest to dowód, że symbol istnieje poza obrazem ani zwykła klasa symbolu.
Wymaga osobnej oceny niepełnej geometrii i nieczytelnych pól.

Te dwa przypadki są wskazane przez bieżące diagnostyki; lista nie dowodzi,
że pozostałe 198 zdjęć jest bezbłędne. Ręka i nakładki gry zasłaniają niektóre
pola również na zdjęciach niewyróżnionych przez liczność lub granice cropów.

## Odbiór wizualny i kontrola poprzednich 11

Obejrzano 20 równomiernie wybranych par nakładek, pięć par o największych
różnicach i oba przypadki diagnostyczne. Pełne źródła obu przypadków oraz
arkusze cropów iteracji 3 również obejrzano. W pozostałych oglądanych
miniaturach nie zauważono oczywistych przesunięć całych wierszy/kolumn.
Nie wykonano ręcznego audytu każdego pola z 200 zdjęć.

Kontrolne 11: oba modele 11/11 zdjęć i 99/99 plansz według D-483, identyczne
metryki jak w TASK-0845. Image-macro: iteracja 2 0,001239334759; iteracja 3
0,000001539849. Audyt potwierdza 99 `proposal_unchanged` z iteracji 3,
przyjętych przez operatora. To kontrola odtworzenia poprzedniego pomiaru,
nie nowy niezależny dowód jakości drugiego folderu. Nie zmieniono zatwierdzeń.

## Podgląd i weryfikacja

Podgląd operatora: `case-review.html`, lokalnie
`http://127.0.0.1:8108/second-481537-500000/case-review.html`.
Używa istniejącego serwera localhost PID 41152; nie uruchomiono drugiej usługi.
Opisuje dwa przypadki i jawnie oddziela kontrolne 11. Startuje filtrem dwóch
przypadków; można wybrać cały folder albo kontrolę. Pokazuje modele obok siebie
i rozwijane cropy. W przeglądarce potwierdzono nawigację 1/2–2/2, 200 zdjęć,
11 kontrolnych i wycinki. Obejrzano render fałszywej planszy obu modeli.
Pliki galerii działają także lokalnie z katalogiem assets; serwer nie ma autostartu.

7 istniejących testów adaptera PASS. Nie zmieniano kodu adaptera, API ani
aplikacji, więc nie uruchamiano ich szerszych buildów lub dodatkowego typechecku.
Wykonano 12 ograniczonych kroków inferencji, maksymalnie 40 zdjęć na proces,
timeout 120 s. Nowe procesy odzyskały po 211 wyników: pending=0, bez inferencji.
Ponowne finish/audit/verify potwierdziły identyczny raport i integralność 422
wyników, źródeł, modeli oraz wszystkich obrazów wyjściowych. Nie było timeoutów.
Nie sprawdzano restartu komputera.

## Odbiór planu i następny zakres

Wszystkie kryteria TASK-0846 zostały spełnione: manifest drugiego folderu,
komplet 200 wyników obu modeli, ograniczony przegląd, uczciwe diagnostyki,
osobna kontrola 11, restart procesów, podgląd i dokumentacja. Brak accuracy
nie jest maskowany procentem zgodności z nazwami. Ograniczenia pozostają jawne.

Do dalszego uczenia najbardziej przydadzą się referencje niepełnych ekranów,
pustych miejsc i zasłoniętych/uciętych pól oraz rzeczywiste poprawki granic.
Przed treningiem trzeba uzyskać aktualne zatwierdzenia i sprawdzić obsługę
nieobecności w istniejącym protokole. Nie zamieniano predykcji w etykiety.

Nie wykonano treningu, aktywacji, DB, migracji, importu produkcyjnego,
V3-D/TASK-0805, rozpoznawania symboli ani złotej ramki Super. Nie wykonano
push ani merge. Równoległe zmiany głównego checkoutu i zastane pliki klienta
pozostały poza zakresem.

Commit zadania: `v1.7.190`; pełny hash zostanie zapisany po commicie w Outcome
i CURRENT_STATE.
