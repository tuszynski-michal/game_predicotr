---
title: Iterative image import requirements
status: accepted
last_updated: 2026-08-09
release: "0.5"
---

# Iteracyjny import zdjęć i ulepszanie pipeline'u

## Cel

Wynik Selekcji Zdjęć może zawierać kilka tysięcy uporządkowanych zdjęć i
kilkanaście tysięcy layoutów. Import Layoutów musi pozwalać właścicielowi
przetwarzać kolejne małe partie, zweryfikować rezultat, ulepszyć rozpoznawanie i
dopiero potem uruchomić następną partię.

## Granica modułów

- Selekcja Zdjęć oraz jej manifest pozostają bez zmian w wersji 0.5.
- Źródłem iteracyjnego importu jest ukończony, checksum-bound manifest Selekcji
  Zdjęć.
- Zwykły import ręcznie wybranego katalogu pozostaje oddzielnym workflow.
- Liczba partii oznacza liczbę zdjęć źródłowych, nie liczbę layoutów.

## Kolejne N zdjęć

- Domyślna partia ma 10 zdjęć.
- Użytkownik może podać od 1 do liczby pozostałych zdjęć.
- Każda akcja pobiera kolejne N nieużytych wpisów według `groupOrder`.
- Po partii 10 i kolejnej partii 20 system wykorzystał dokładnie pierwszych 30
  wpisów manifestu.
- Zakres jest rezerwowany atomowo i nie może nakładać się z inną partią.
- Nieudany job zachowuje swój zakres i jest wznawiany z istniejących
  checkpointów. Nie tworzy nowej partii dla tych samych zdjęć.
- Postęp źródła jest trwały po restarcie API, workerów i komputera.

Panel pokazuje liczbę wszystkich, zarezerwowanych, przetworzonych, błędnych i
pozostałych zdjęć, a także zakres oraz job każdej partii.

## Iteracyjne ulepszanie

Po ręcznym zatwierdzeniu layoutów użytkownik może niezależnie:

1. utworzyć nowego kandydata modelu symboli z kumulacyjnej kohorty,
2. utworzyć nowego kandydata kalibracji siatki z zatwierdzonych geometrii,
3. ocenić bramkę jakości,
4. jawnie aktywować albo odrzucić każdą wersję.

Nowe wersje dotyczą wyłącznie jobów utworzonych po aktywacji. System nie
przelicza automatycznie wcześniejszych `pending` i nigdy nie zmienia decyzji
`accepted`, `corrected` ani `rejected`.

## Kalibracja siatki

Wersja 0.5 wykorzystuje istniejący detektor i uczy wersjonowane korekty jego
narożników. Kohorta zawiera pierwotny quad detektora oraz finalny quad
zaakceptowany przez człowieka. Akceptacja bez edycji siatki jest prawidłowym
przykładem zerowej korekty.

Profil jest ograniczony do gry, źródła Selekcji Zdjęć i pozycji planszy 1–9.
Brak pasującego profilu oznacza jawny fallback do detektora. Kandydat nie staje
się aktywny bez bramki jakości i potwierdzenia właściciela.

Jeżeli po dwóch iteracjach i reprezentatywnej partii ponad 10% layoutów nadal
wymaga korekty siatki albo błąd p95 nie poprawia się na odseparowanych
zdjęciach, należy zaproponować przejście na model neuronowy. Dataset pod taki
model zachowuje oryginalny obraz, cztery zatwierdzone narożniki, pozycję i sesję;
podział train/validation/test odbywa się po zdjęciu i sesji.

## Reviewer i jakość obrazu

- Prawy podgląd pokazuje natywny fragment oryginalnego zdjęcia obejmujący
  planszę oraz obszar numeru sekwencji.
- Numer ma być widoczny bez otwierania edytora siatki.
- Dla historycznych danych bez geometrii etykiety stosowany jest bezpieczny
  rozszerzony viewport.
- Oryginalny JPEG i pełnowymiarowa normalizacja pozostają niezmienne.
- Artefakt `500×300` pozostaje deterministycznym wejściem pipeline'u, ale nie
  może być prezentowany jako podgląd jakości oryginału.

## Skalowanie

Oczekiwana złożoność jest liniowa względem liczby zdjęć, layoutów i komórek.
Pomiary 10, 100, 1000 oraz później 5000 zdjęć mają raportować czas całkowity,
czas na zdjęcie/layout, throughput, pamięć i udział etapów. Pomiar ma wykryć
degradację jednostkowego kosztu, ale nie może zmieniać zachowania pipeline'u.

## Kryteria akceptacji

- dwie kolejne partie nie mają luk ani wspólnych zdjęć,
- retry nie przesuwa kursora i nie duplikuje wyników,
- nowa partia przypina aktywną wersję symboli i siatki,
- wcześniejsza partia zachowuje swój snapshot,
- Reviewer pokazuje planszę i numer z oryginalnego źródła,
- kalibracja nie może zostać aktywowana po regresji na zbiorze testowym,
- żadna automatyczna operacja nie zmienia decyzji człowieka.
