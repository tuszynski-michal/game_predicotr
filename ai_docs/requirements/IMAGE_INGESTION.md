---
title: Image ingestion requirements
status: proposed
last_updated: 2026-07-23
---

# Import i rozpoznawanie zdjęć

## Cel

Przetworzyć duży katalog zdjęć wykonanych telefonem, wyodrębnić z każdego zdjęcia do 9 layoutów, odczytać ich numery oraz rozpoznać symbole w komórkach.

## Ważne założenie

Nie należy traktować tego jako pojedynczego endpointu HTTP. Jest to długotrwały, wznawialny pipeline uruchamiany przez osobny proces Python.

## Etapy pipeline'u

### 1. Discovery

- skanowanie wskazanego folderu,
- obsługa wybranych formatów obrazów,
- zapis ścieżki, rozmiaru, czasu modyfikacji i checksum,
- pomijanie plików już przetworzonych w tym samym imporcie.

### 2. Normalizacja

- odczyt orientacji EXIF,
- obrót,
- korekta jasności i kontrastu tylko w kopii roboczej,
- zachowanie oryginału bez modyfikacji.

### 3. Detekcja obszaru

- znalezienie obszaru strony/ekranu,
- korekta perspektywy,
- wykrycie oczekiwanej siatki 9 layoutów,
- confidence score dla detekcji.

### 4. Wycięcie layoutów

Dla każdego z 9 obszarów zapisz:

- indeks pozycji na zdjęciu,
- bounding box,
- ścieżkę do wycinka roboczego,
- status detekcji.

### 5. Odczyt sequence number

- wytnij obszar numeru pod layoutem,
- wykonaj OCR cyfr,
- zapisz surowy tekst, wartość znormalizowaną i confidence,
- sprawdź monotoniczność numerów na zdjęciu oraz względem sąsiednich zdjęć.

### 6. Podział na komórki

- użyj wymiarów gry,
- podziel layout na stabilną siatkę,
- zapisz wycinek każdej komórki do cache roboczego lub katalogu datasetu.

### 7. Klasyfikacja symbolu

Faza początkowa powinna być nadzorowana:

1. administrator dostarcza 10–20 oznaczonych przykładów na symbol,
2. system tworzy reprezentację referencyjną,
3. klasyfikator zwraca `symbol_id`, confidence i kilka alternatyw,
4. niski confidence trafia do manual review.

Nie zakładamy, że system samodzielnie odkryje poprawną liczbę klas bez danych oznaczonych. Grupowanie podobnych kafelków może wspierać administratora, ale nie zastępuje zatwierdzenia klas.

### 8. Manual review

Element trafia do review, jeżeli:

- nie wykryto strony lub layoutu,
- OCR numeru jest niepewny,
- numer koliduje z istniejącym,
- symbol ma confidence poniżej progu,
- siatka jest uszkodzona,
- layout ma nieprawidłową liczbę komórek.

### 9. Walidacja i commit

Dane są najpierw zapisywane do tabel stagingowych. Publikacja do kanonicznej sekwencji wymaga:

- poprawnej liczby komórek,
- poprawnych symboli należących do gry,
- zaakceptowanych numerów,
- raportu luk i konfliktów,
- idempotentnego importu.

## Statusy zadania

```text
created
scanning
processing
waiting_for_review
validating
completed
failed
cancelled
```

## Wznawianie

- postęp zapisywany co plik lub małą partię,
- błąd jednego zdjęcia nie przerywa całego importu,
- ponowne uruchomienie nie tworzy duplikatów,
- wersja pipeline'u i modelu klasyfikacji jest zapisywana z wynikiem.

## Przechowywanie plików

MVP lokalny:

```text
data/
  originals/
  working/
  crops/
  training/
  exports/
```

Baza przechowuje ścieżki względne, checksumy i metadane. Nie przechowuje wszystkich dużych zdjęć w kolumnach binarnych.

## Metryki jakości

- skuteczność detekcji strony,
- skuteczność detekcji 9 layoutów,
- accuracy OCR numerów,
- accuracy symbol classifier,
- odsetek elementów manual review,
- czas na zdjęcie,
- liczba błędów trwałych.

## Dane potrzebne przed implementacją

- co najmniej 20 oryginalnych zdjęć dobrej i słabej jakości,
- opis rozmieszczenia 9 layoutów,
- przykładowe numery,
- przykłady wszystkich symboli,
- informacja o wariantach rozdzielczości i orientacji,
- zasady mapowania zdjęć do gry.
