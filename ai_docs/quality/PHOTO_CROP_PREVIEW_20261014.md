---
title: P1 — galeria przycięcia zdjęć zatwierdzonych siatek
status: active
last_updated: 2026-10-14
---

# P1 — galeria przycięcia zdjęć zatwierdzonych siatek

## Numeracja

Bieżący task galerii to `TASK-1016`. Wcześniejszy identyfikator `TASK-1007`
z commitów v1.7.361/362 pozostaje w historii; numer zajmuje teraz przekazany
plan doszkalania V3 (rewizja 6, zakres `TASK-0993–1015`). Nie przepisano
historii commitów. Kolejne taski przycinania otrzymają numery po sprawdzeniu
aktualnych rezerwacji.

## Zlecony zakres i wynik

Operator zlecił wyłącznie P1 planu przedstawionego w rozmowie: lokalna galeria
HTML z 30–50 istniejącymi zdjęciami z różnych gier, porównaniem przed i po
przycięciu oraz rzeczywistym pomiarem rozmiaru. Oryginały i dane bazy pozostają
bez zmian. P2–P4 ani instalacja skilli nie zostały uruchomione.

Wynik zawiera **40 zdjęć / 360 siatek**: 36 zdjęć gry `7` („777 a1”) i 4 gry
`mumie` („Mumie a1”). Jeden przycięty plik obejmuje wszystkie dziewięć siatek
źródła; oryginał jest liczony raz w podsumowaniu.

Galeria: `D:/game_predicotr/artifacts/photo-crop-preview-20261014/gallery/index.html`.
Paczka lokalna: `D:/game_predicotr/artifacts/photo-crop-preview-20261014/gallery.zip`.
W katalogu galerii są kopie zdjęć, JPEG-y po przycięciu, pełne JPEG-y kontrolne,
bezstratne WebP oraz `report.csv` i `report.json`. Plik HTML działa przez
`file://`, bez serwera i zależności sieciowych; udostępnia filtr gry, sortowanie,
nakładki geometrii, powiększenie i pobieranie plików.

## Rzeczywisty pomiar

| Wariant | Bajty |
| --- | ---: |
| Oryginały, 40 unikalnych plików | 10 992 053 |
| Przycięte JPEG-y | 7 845 699 |
| Różnica względem oryginałów | 3 146 354 |
| Pełne JPEG-y zapisane tym samym sposobem | 10 993 481 |
| Przycięte WebP lossless | 21 562 010 |

Łączna redukcja JPEG wynosi **28,6239%**. Obliczenie dzieli różnicę sum bajtów
przez sumę oryginałów, nie uśrednia procentów poszczególnych zdjęć. Zakres
redukcji pojedynczego JPEG wynosi 11,9293–44,8185%; żaden JPEG próbki nie jest
większy od oryginału. Różnica względem pełnego JPEG kontrolnego wynosi
3 147 782 B. Wariant WebP ma dokładnie takie same piksele jak wycięty obszar
źródła, lecz jest większy od oryginałów o 10 569 957 B.

JPEG-y zostały ponownie zakodowane z tablicami kwantyzacji i próbkowaniem
chrominancji odczytanymi z oryginału, z optymalizacją kodowania. Nie jest to
bezstratne przycinanie JPEG i nie dowodzi zgodności istniejących renderów
komórek ani możliwości podmiany źródła w produkcji. Pełny JPEG kontrolny
oddziela wpływ kadru od wpływu nowego zapisu. Miary KB/MB są dziesiętne.

Nie zwolniono miejsca na dysku: przygotowanie galerii dodaje kopie. Oryginały
nie były zastępowane, przenoszone ani usuwane. Próbka jest celowa i nie daje
podstaw do ekstrapolacji 28,6% na całą bibliotekę.

## Kwalifikacja i geometria

Metadane odczytano w PostgreSQL w transakcji `REPEATABLE READ` z wymuszonym
`default_transaction_read_only=on`, z timeoutami połączenia, zapytań i blokad.
Odczyty były ograniczone do maksymalnie 80 kandydatów na niearchiwalną grę.
Wybrane źródła mają `geometry_complete`, kanoniczną przestrzeń współrzędnych
EXIF/RGB oraz zgodność `approved_geometry_revision = geometry_revision`
wszystkich nieodrzuconych plansz. Wykluczono oczekujące sloty korekty i
`grid_issue`; sprawdzono też oczekującą lub niezatwierdzoną geometrię innych
referencji do tych samych bajtów źródłowych. Nie wymagano zatwierdzenia symboli:
`pending_review` przy zatwierdzonej geometrii nie oznacza korekty siatki.

Gra `777a2` nie miała kandydatów z jawnym zatwierdzeniem bieżącej geometrii
wszystkich plansz; cztery źródła Mumii spełniały ten ścisły warunek. Nie
zmieniono progów kwalifikacji dla uzyskania większej różnorodności.

Kadr jest obwiednią wszystkich bieżących quadów plansz i komórek, w tym
`paddedSourceQuad`, rozszerzoną o 50 px i ograniczoną do wymiarów obrazu.
Początek zaokrąglono w dół, koniec w górę. Obraz dekodowano z orientacją EXIF;
sprawdzono wymiary, SHA-256 pliku i przypiętą checksumę kanonicznych pikseli.

## Weryfikacja

- 40 unikalnych źródeł, 360 plansz, dokładnie 40 przyciętych JPEG-ów, 40
  pełnych JPEG-ów kontrolnych i 40 WebP; brak błędów generowania.
- Wszystkie chronione quady mieszczą się w swoich kadrach; wymiary plików
  odpowiadają obwiedniom. Pusty quad, NaN i geometria poza obrazem są odrzucane.
- Kontrola w nowym procesie potwierdziła SHA-256 i rozmiar każdego oryginału,
  zgodność bajtów kopii oraz dokładną zgodność pikseli 40 WebP. Czas modyfikacji
  wszystkich 40 oryginałów pozostał niezmieniony.
- Przeglądarka Chrome: 40 kart, filtr Mumii daje 4 karty, nakładki pasują do
  obrazu; brak błędów JavaScript. Widok 390 px nie ma poziomego przepełnienia;
  działa okno powiększenia. Zapisano zrzuty desktop, Mumii i mobile.
- Początkowy błąd agregacji per plansza poprawiono na jeden wynik per źródło;
  błędną galerię własną usunięto po weryfikacji poprawnej. Błąd pozycjonowania
  SVG poprawiono przez ramkę o proporcjach zdjęcia. Wyniki końcowe dotyczą
  wyłącznie poprawionej galerii.

Nie uruchamiano usług, pełnych testów aplikacji, migracji ani niezależnego
audytu Claude. Dla P1 plan przewiduje wizualny odbiór operatora; ten odbiór
pozostaje oczekujący. Następny krok to obejrzenie przykładów i decyzja o P2,
z osobnym kontraktem przechowywania oraz retencją oryginałów.
