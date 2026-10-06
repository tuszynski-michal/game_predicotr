---
title: Czytelny wynik preflightu sieci Mumii
status: completed
last_updated: 2026-10-07
---

# Preflight sieci — wynik bez obowiązku akceptacji każdej planszy

## Stan, cel i zatwierdzony zakres

Użytkownik zgłosił, że wszystkie2575 zdjęć wyglądają na błędy ręcznej
korekty. Odczyt faktycznego joba1e5c0d7d i niezmiennego manifestu potwierdza
neural-grid Run3, eksport iteration03-f896da7196431be2. Wszystkie23175
przypisanych siatek spełniają istniejącą politykę neural-auto-crop-v1.
Status review_required i NEURAL_GRID_GATE_UNCALIBRATED oznaczają brak
zatwierdzenia/kalibracji, nie obowiązek poprawy każdej siatki przed importem.
Nie jest to pomiar dokładności cięcia względem ręcznej prawdy.

TASK-0891 naprawia prezentację raportu i instrukcję. Wymaganie osobnej,
wspólnej zakładki Laboratorium zapisujemy w istniejącym rejestrze funkcji;
jej pełna integracja wymaga osobnego pionu, nie pozornego linku do portu3102.

## Reguły implementacji

- Źródłem rozróżnienia jest przypięty neural snapshot joba, nie sama nazwa gry.
- Licznik review w neural oznacza propozycje zdjęć do przeglądu; nie nazywamy
  go liczbą błędów ani ręcznych korekt. Klasyczne raporty zachowują znaczenie.
- Pokaż przeanalizowane zdjęcia i rzeczywisty eksport sieci zamiast licznika
  ręcznie zarejestrowanych geometrii. Start importu pozostaje jawną akcją.
- Podgląd neural pobiera szczegóły dopiero po rozwinięciu. Zamknięty details
  nie montuje edytora wszystkich źródeł; podmiana nadal otwiera go od razu.
- Pełne, przypisane siatki idą automatycznie do symboli. Brakujące/częściowe
  trafiają do korekty; konflikt numeracji pozostaje w edytorze zdjęcia.
- Laboratorium: dane i wersje kandydatów przypisane do gry, zapis w głównej
  bazie oraz ścieżki/checksumy artefaktów. Rejestracja kandydata po treningu
  nie oznacza automatycznej aktywacji. Nie łączymy danych różnych gier.

## Zadanie i odbiór

TASK-0891: image-folder-import-state.ts i ImageFolderImportPanel; testy
stanów neural/legacy oraz interakcji przy wszystkich zdjęciach review,
odtworzeniu strony i braku wywołań zapisu przy samym podglądzie.
Wspólny PageGeometryCorrectionPanel dostaje opcjonalną prezentację neural
bez opisu klasycznych wzorców; domyślna korekta zachowuje dotychczasowy UI
i test regresji page-geometry-qualification.
Instrukcja operatora i APP_V3_FUNCTIONAL_INVENTORY otrzymują aktualne
znaczenie licznika oraz wymagania Laboratorium.

Odbiór: skupione testy, scoped lint/format, typecheck, Admin build i świeży
odczyt faktycznego raportu MAIN. Komendy mają timeout120s. Bez importu,
treningu, aktywacji, migracji, cleanupu, zmiany API lub danych siódemek.
Ryzyko: kwalifikacja strukturalna nie gwarantuje poprawnego cięcia wszystkich
pikseli; ujawnia to zbiorcza weryfikacja i zgłoszenia Zła siatka.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0891 | gpt-6.1-sol | high | Ograniczona naprawa prezentacji wymaga rozróżnienia gotowości operacyjnej i prawdy treningowej. Konfiguracja dostępna w sesji; bez zmiany modelu lub delegowania. | Samodzielny przegląd diffu i regresji; niezależny review niewymagany przy braku zmiany kontraktów/danych. |
