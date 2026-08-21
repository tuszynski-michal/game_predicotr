---
title: TASK-0245 image selection v10.20 sequence-validated range assignment
status: done
release: "0.6"
last_updated: 2026-08-18
---

# TASK-0245 — Image selection v10.20 sequence-validated range assignment

## Goal

Wykorzystać deterministyczną kolejność zakresów jako walidację dwóch lokalnie
odczytanych numerów, bez przypisywania zakresu zdjęciom niejednoznacznym i bez
ponownego zawyżania liczby grup logicznych.

## Accepted decisions

1. Niezależny automat nadal akceptuje mocny dowód v10.19 z co najmniej trzech
   pozycji. V10.20 może dodatkowo zaakceptować dwie dokładne pozycje z pełnej
   geometrii albo trzy pozycje częściowego viewportu, jeżeli jedna jest
   dokładna, pozostałe mają dystans OCR najwyżej jeden, a dowód obejmuje dwa
   wiersze i dwie kolumny.
2. Oczekiwany zakres jest hipotezą sprawdzającą OCR, a nie źródłem prawdy.
   Jeden numer, brak wymaganego pokrycia, mocny inny zakres, konflikt albo słaba jakość
   pozostawiają `range_required` bez kanonicznego zakresu.
3. Wybranie w kolejce zakresu, który ma już właściciela, zapisuje audytowaną
   decyzję `duplicate_range` i ustawia `skipped_existing_range`; nie zwraca
   błędu i nie tworzy drugiej grupy logicznej ani pliku wynikowego.
4. `manual_required` i `range_required` mają osobne liczniki. Do sumy wyborów
   zdjęcia zalicza się `selected + manual`, nigdy `range_required`.
5. V10.19 i jego fingerprint pozostają rozwiązywalne i zachowują dawne
   zachowanie. V10.20 ma osobny adapter v18, manifest i fingerprint.
6. Pełny run 32 079 zdjęć nie startuje przed testami, benchmarkiem i audytem
   małego rzeczywistego zestawu właściciela.

## Implementation

- `SequenceValidatedVisibleSequenceLabelRangeRecognizer` zachowuje dwa
  wysokiej pewności odczyty zakotwiczone w pozycjach plansz jako sugestie.
- Końcowa projekcja blokuje mocne zakresy jako kotwice i rozwiązuje monotoniczne
  przypisanie fizycznych fragmentów do oczekiwanych slotów. Promuje tylko
  kandydata spełniającego jawny dowód pozycyjny; nadmiarowe fragmenty zostają
  duplikatami istniejących właścicieli i nie zawyżają liczby logicznych grup.
- Jeżeli wczesny kwantyl wskazuje inny slot niż oczekiwany, maksymalnie pięć
  kwantyli pozwala rozdzielić sklejone sąsiednie zakresy bez skanowania całej
  grupy.
- Ręcznie opisany manifest wiąże checksumami 17 czytelnych zakresów i trzy
  zdjęcia odrzucane jakościowo z korpusu 283 JPEG-ów w kolejności malejącej.
- `SequenceBounds.group_index_for_range` używa obliczenia O(1), dzięki czemu
  przypadek 2583 fragmentów / 2201 slotów nie wykonuje zagnieżdżonego skanowania
  całej siatki.
- API automatycznie zamienia potwierdzenie istniejącego zakresu na decyzję
  duplikatu i zwalnia flagę wybranego kandydata fragmentu.
- Checkpoint, API, OpenAPI, Admin i runner operatorski rozdzielają liczniki
  `manual` oraz `rangeRequired`.
- Skrypt testów Pythona używa izolowanego katalogu tymczasowego z PID-em; stary
  niedostępny `pytest-of-user` został usunięty i odtworzenie sprawdzono z nowego
  procesu.

## Verification

- testy reconciliacji: `23/23`,
- skupione testy selektora, adapterów, recovery i benchmarku: `222/222`,
- testy API i kontraktu joba: `41/41`,
- regresje adaptera v18, cache i dwu-workerowej fabryki przechodzą,
- syntetyczna reconciliacja 2583 fragmentów do 2201 slotów: `1,922 s`, bez
  automatycznej promocji nieczytelnych grup,
- OpenAPI i klient Admina wygenerowane ponownie.
- zimny benchmark 283 JPEG-ów: `68,298789 s`, 48 weryfikacji, 17 logicznych
  właścicieli, pokrycie 17/17, 9 pominiętych fragmentów, adnotacje 20/20 i zero
  naruszeń automatycznego dowodu.
- pełny zestaw Pythona: `1109 passed, 26 skipped`; skupiona końcowa regresja
  selektora: `222/222`.
- Ruff przechodzi, mypy nie zgłasza problemów w 329 plikach, Prettier, lint i
  typecheck wszystkich workspace'ów przechodzą.
- Admin `201/201`, Mobile `82/82`, Reviewer `25/25`, Admin API Client `38/38`
  oraz Shared TS `24/24` przechodzą; składnia 34 skryptów PowerShell jest
  poprawna.

## Next owner gate

- Kontrolowany run `1–19809` (2201 oczekiwanych zakresów) pozostaje świadomie
  niewystartowany. Po jego odbiorze kolejny test ma użyć świeżego stagingu
  prawidłowego `E:\777 zd\19810 - 45162` (2817 grup).

## Outcome

V10.20 przeszedł wszystkie bramki repozytorium oraz checksumowany audyt
rzeczywistych zdjęć. Nie ma aktywnego joba ani kontrolera kolejki; pełny run
pozostaje osobną decyzją właściciela.
