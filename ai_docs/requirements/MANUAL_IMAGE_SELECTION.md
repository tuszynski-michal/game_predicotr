---
title: Local manual image selection
status: accepted
last_updated: 2026-08-18
---

# Lokalna ręczna selekcja zdjęć

## Cel

Zakładka `Ręczna selekcja` jest awaryjnym, deterministycznym narzędziem do
przypisania pojedynczych JPEG-ów do kolejnych dziewięcioplanowych zakresów.
Pozwala kontynuować pracę, gdy automatyczny selektor nie daje wystarczającej
pewności, bez uruchamiania API, workera, OCR ani uploadu do stagingu.

## Przebieg

- Przed rozpoczęciem operator wybiera grę, pierwszy numer layoutu, kierunek
  kolejności zdjęć, folder źródłowy i folder wynikowy.
- Folder źródłowy jest odczytywany rekurencyjnie. Uwzględniane są wyłącznie
  `.jpg` i `.jpeg`, sortowane naturalnie po względnej ścieżce (tak jak numery w
  nazwach plików), z możliwością odwrócenia kolejności.
- Początkowe indeksowanie nie otwiera zawartości każdego JPEG-a. Podczas pracy
  aplikacja wyprzedzająco odczytuje i dekoduje ograniczone okno trzech zdjęć z
  każdej strony bieżącej pozycji, aby nawigacja nie wymagała stagingu.
- Zakres jest inkluzywny i zawsze ma dziewięć pozycji: `start–start+8`.
  Po zaakceptowaniu następny zakres zaczyna się od `start+9`.
- `Enter` zapisuje bieżące zdjęcie jako `seq_<start>-<end>.jpg` w wybranym
  folderze i przechodzi do następnego zdjęcia oraz zakresu.
- `Tab` pomija bieżące zdjęcie dla zakresu i przechodzi do następnego zakresu,
  pozostawiając ten sam obraz do ponownego wykorzystania.
- Strzałki zmieniają wyświetlane zdjęcie bez zmiany zakresu ani decyzji.
  Operator wybiera trwały skok `1, 2, 5, 7, 10, 15` albo `20` zdjęć; Enter po
  zapisie nadal przechodzi dokładnie o jedno zdjęcie.
- Podgląd ma natywny tryb pełnoekranowy oraz zoom `100–200%`; oba dotyczą
  wyłącznie prezentacji bieżącego JPEG-a i nie zmieniają pliku zapisywanego na
  dysku. Pełny ekran zawsze pokazuje także bieżący zakres, pozycję i nazwę
  pliku.
- `Ctrl+Z` cofa ostatnią decyzję i usuwa tylko plik, który aplikacja wcześniej
  zapisała oraz którego checksum nadal odpowiada źródłu.

## Trwałość i bezpieczeństwo

Stan sesji (foldery, indeks zdjęcia, zakres i decyzje) jest zapisywany w
IndexedDB per gra i odtwarzany po ponownym wejściu do zakładki. Uchwyt folderu
może wymagać ponownego nadania uprawnień przez przeglądarkę.

W danym momencie może być aktywne tylko jedno okno wyboru folderu. Oba przyciski
wyboru są blokowane podczas aktywnego pickera, a ponowne kliknięcie jest
obsługiwane jako komunikat zamiast drugiego wywołania przeglądarkowego dialogu.

Zapis korzysta z File System Access API i kopiuje oryginalne bajty JPEG-a, bez
skalowania, obrotu ani zmiany perspektywy. Istniejący plik wynikowy jest
idempotentny, gdy checksum jest taki sam; obcy plik o tej samej nazwie blokuje
nadpisanie. Nie są wysyłane obrazy ani decyzje do backendu.

Ta zakładka jest narzędziem lokalnym i nie zmienia automatycznego kontraktu
selekcji zdjęć, stagingu ani importu layoutów.
