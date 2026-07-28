---
title: Manual data import requirements
status: accepted
last_updated: 2026-07-28
---

# Wymagania ręcznego importu danych

## Cel

Ręczny import przyjmuje duże, zewnętrznie przygotowane pliki layoutów bez OCR,
zdjęć i bezpośredniej edycji SQL. Dane zawsze trafiają do stagingu i mogą zostać
opublikowane dopiero po pełnej walidacji.

## Wspólny kontrakt `layout-import-v1`

- `schemaVersion` / `schema_version` ma dokładnie wartość `1`,
- `sequenceNumber` / `sequence_number` jest dodatnią liczbą całkowitą,
- `cells` jest niepustą tablicą dodatnich kodów symboli z zakresu `1..32767`,
- komórki są zapisane w kolejności row-major,
- plik używa ścisłego UTF-8 bez BOM,
- każda linia danych opisuje dokładnie jeden layout,
- wymiary planszy i przynależność symboli do gry są walidowane względem
  wybranej wersji reguł poza parserem formatu,
- powtórzona sygnatura layoutu jest dozwolona, ale powtórzony
  `sequence_number` blokuje publikację.

## CSV v1

Pierwsza linia ma dokładnie nagłówek:

```csv
schema_version,sequence_number,cells
```

Każdy kolejny niepusty wiersz ma dokładnie trzy pola. `cells` jest tablicą JSON
w cytowanym polu CSV:

```csv
1,1,"[1,2,3,4,5,6]"
```

Nazwy, kolejność, wielkość liter oraz liczba kolumn nagłówka są częścią
kontraktu. Dodatkowe kolumny nie są ignorowane.

## JSON Lines v1

JSON w M4 oznacza JSON Lines z rozszerzeniem `.jsonl`. Każda niepusta linia jest
samodzielnym obiektem i ma dokładnie pola:

```json
{"schemaVersion":1,"sequenceNumber":1,"cells":[1,2,3,4,5,6]}
```

Monolityczny dokument z tablicą wszystkich layoutów nie należy do v1, ponieważ
docelowy import musi działać strumieniowo dla około 500 000 rekordów.

## Stabilne błędy kontraktu

| Kod | Znaczenie |
|---|---|
| `import_format_unsupported` | format nie jest CSV ani JSONL v1 |
| `import_encoding_invalid` | bajty nie są poprawnym UTF-8 |
| `import_encoding_bom_forbidden` | plik zaczyna się od UTF-8 BOM |
| `import_header_invalid` | nagłówek CSV nie jest dokładnym nagłówkiem v1 |
| `import_record_invalid` | rekord CSV/JSONL ma nieprawidłową strukturę |
| `import_schema_version_unsupported` | wersja nie jest liczbą `1` |
| `import_sequence_number_invalid` | numer sekwencji nie jest dodatnim integerem |
| `import_cells_invalid` | komórki nie są poprawną niepustą tablicą kodów |

Komunikat może zawierać numer linii i bezpieczny opis, ale kod jest stabilnym
kontraktem dla API, workera i panelu.

## Lokalny katalog wejściowy

- operator umieszcza plik w katalogu `GAME_PREDICTOR_IMPORT_ROOT`, domyślnie
  `imports/`,
- panel/API przekazuje wyłącznie względną ścieżkę POSIX do `.csv` albo `.jsonl`,
- ścieżka absolutna, backslash, dwukropek, `.` i `..` są odrzucane,
- rozwiązana ścieżka musi nadal znajdować się pod skonfigurowanym katalogiem,
  także po uwzględnieniu symlinka lub junction,
- plik musi być zwykły, niepusty i nie większy niż
  `GAME_PREDICTOR_IMPORT_MAX_BYTES`, domyślnie 1 GiB,
- API sprawdza nagłówek/pierwszy rekord i samo liczy SHA-256 partiami,
- klient nie podaje formatu, rozmiaru ani checksumy,
- job utrwala kanoniczną ścieżkę względną, format, wersję kontraktu, rozmiar i
  checksumę,
- ta sama gra, treść, format i wersja kontraktu identyfikują ten sam import
  niezależnie od nazwy pliku.

Plik może zostać zmieniony po utworzeniu joba, dlatego worker przed stagingiem
ponownie porównuje utrwalony checksum. Inspekcja API dodatkowo odrzuca zmianę
wykrytą podczas samego odczytu.

## Strumieniowy staging

- worker czyta fizyczne linie w bounded partiach po domyślnie 1000 niepustych
  rekordów i nigdy nie materializuje całego pliku,
- checkpoint wskazuje końcowy offset bajtowy i numer fizycznej linii, a nie
  `sequence_number`,
- puste linie nie tworzą rekordów stagingu, ale pozostają częścią fizycznego
  kursora i checksumy prefiksu,
- każda niepusta linia tworzy dokładnie jeden rekord stagingu: parserowo
  poprawne `sequence_number/cells` albo stabilny kod i bezpieczny opis błędu,
- fizyczna linia dłuższa niż 1 MiB jest drenowana bounded fragmentami i
  izolowana jako błąd rekordu; kolejne linie nadal są przetwarzane,
- worker ponownie sprawdza pełny SHA-256 przed pierwszym zapisem i po odczytaniu
  całego źródła,
- przed wznowieniem worker odtwarza łańcuch checksumy fizycznego prefiksu i
  usuwa wyłącznie rekordy znajdujące się za ostatnim trwałym checkpointem,
- kolejność zapisu to `idempotentny upsert partii → checkpoint`; awaria między
  tymi operacjami bezpiecznie powtarza tę samą partię,
- surowy staging jest związany z jobem i nie jest `dataset_version`, rekordem
  `layouts` ani źródłem wydania mobilnego.

## Normalizacja i walidacja wierszy

- zakończony surowy import jest wejściem osobnego joba `validate` z
  `validationKind = layout_import`,
- operator wskazuje opublikowaną wersję reguł tej samej gry; jej wymiary i
  aktywne konfiguracje symboli są niezmiennym alfabetem walidacji,
- worker pobiera surowe wiersze rosnąco po fizycznym `line_number` w bounded
  partiach po domyślnie 1000 rekordów,
- błąd parsera jest kopiowany do znormalizowanego stagingu, a parserowo poprawny
  wiersz zachowuje `sequence_number` i `cells` także przy błędzie domenowym,
- poprawny wiersz ma dokładnie `rows * columns` komórek, wyłącznie aktywne kody
  symboli wybranej wersji i stałoszeroką sygnaturę codec v1,
- `signature_cell_width` jest wyprowadzana raz z największego aktywnego
  `mobile_code` całej wersji reguł, nigdy z pojedynczego layoutu,
- stabilne błędy domenowe wiersza to `import_cell_count_mismatch` oraz
  `import_symbol_not_in_rules`,
- klucz `(validation_job_id, line_number)` i kolejność
  `upsert partii → checkpoint` pozwalają bezpiecznie powtórzyć partię,
- ten sam surowy import może zostać zwalidowany względem innej opublikowanej
  wersji reguł jako inny job; nie nadpisuje poprzedniego wyniku,
- znormalizowany staging nadal nie jest `dataset_version`, tabelą `layouts` ani
  źródłem release. Luki i duplikaty numerów należą do raportu TASK-0047.

## Raport integralności znormalizowanego stagingu

- raport jest dostępny dopiero po zakończeniu joba walidacji
  `layout_import`,
- rzeczywista liczba znormalizowanych wierszy jest porównywana z
  `progress.total` zakończonego joba,
- ciąg poprawnych layoutów zaczyna się od `1` i kończy na największym poprawnym
  `sequence_number`,
- wiersz z błędem parsera albo walidacji domenowej blokuje gotowość i nie
  wypełnia luki w ciągu poprawnych layoutów,
- brak poprawnych layoutów, niezgodna liczba wierszy, luka albo duplikat
  `sequence_number` są blokadami,
- duplikat sygnatury jest dozwolonym ostrzeżeniem i zawiera numery sekwencji
  oraz fizyczne numery linii,
- wszystkie liczniki obejmują pełny staging; próbki luk i grup duplikatów są
  deterministyczne, ograniczone do 100 elementów i jawnie oznaczają obcięcie,
- lista znormalizowanych wierszy używa bounded keyset pagination po
  `line_number` oraz filtrów statusu `valid/invalid` i stabilnego kodu błędu,
- raport ani podgląd nie tworzą `dataset_version` i nie publikują danych.

## Granice odpowiedzialności

- TASK-0043 definiuje format i walidację pojedynczego rekordu.
- TASK-0044 odpowiada za katalog wejściowy, rozszerzenie, rozmiar, checksum,
  idempotencję i utworzenie joba.
- TASK-0045 odpowiada za strumieniowe czytanie, checkpoint i staging.
- TASK-0046 odpowiada za wymiary, alfabet symboli, sygnaturę i błędy wierszy.
- TASK-0047 odpowiada za dokładne agregaty integralności, bounded próbki i
  stronicowany odczyt znormalizowanych wierszy.

## Odrzucenie stagingu

- operator wskazuje zakończony job walidacji `layout_import`, a API rozstrzyga
  dokładny powiązany job importu,
- potwierdzenie w panelu wymaga przepisania pełnego `importJobId`,
- odrzucenie usuwa wszystkie znormalizowane wiersze powiązane z importem, a
  następnie jego surowe wiersze; joby nie są usuwane ani przepisywane,
- operacja jest idempotentna dla stagingu już pozbawionego wierszy,
- aktywna walidacja tego samego importu oraz jakikolwiek dataset wskazujący job
  importu lub jego walidacji blokują usunięcie,
- staging po odrzuceniu nie może zostać opublikowany; ponowne przetworzenie
  wymaga nowego jawnego importu.

## Publikacja datasetu ze stagingu

- operator może publikować wyłącznie zakończony job walidacji
  `layout_import`, którego ponownie obliczony raport nie ma blokad,
- API blokuje powiązany job importu, wszystkie jego walidacje, wersję reguł i
  rekord gry, a następnie ponownie ocenia te same agregaty co raport,
- `dataset_versions` oraz `layouts` powstają w jednej transakcji; błąd nie
  pozostawia stagingowej ani częściowo opublikowanej wersji,
- layouty są kopiowane setowym `INSERT ... SELECT`, bez materializowania
  pełnego importu w procesie API,
- nowa wersja datasetu jest od razu niezmienna i `published`, ma serwerowy
  `published_at`, wymiary i szerokość codeca walidowanych reguł,
- `source_job_id` wskazuje dokładny job walidacji, `generator_version` ma
  wartość `layout-import-v1`, a historycznie wymagany `generation_seed` ma
  neutralną wartość `0`,
- niepusty `source_job_id` jest unikalny; ponowienie publikacji tej samej
  walidacji zwraca ten sam dataset bez utworzenia nowego numeru lub layoutów,
- duplikat sygnatury pozostaje dozwolony, ale każdy inny blocker raportu
  uniemożliwia publikację,
- staging pozostaje po publikacji jako audyt i nie może zostać odrzucony,
- publikacja nie uruchamia automatycznie payoutów, snapshotu ani Android build;
  istniejący release pipeline używa nowego datasetu w kolejnych jawnych
  operacjach.
