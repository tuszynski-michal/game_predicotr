---
title: Wdrożenie wykrywania pełnych plansz i przygotowanie danych
status: active
last_updated: 2026-11-07
---

# Wdrożenie i stan danych Mumie A2

Operator zatwierdził integrację T0–T6, push, migracje0180/0181, rejestrację
diagnostyk i ponowne uruchomienie działających usług. Zlecił także trening
oraz import brakujących zdjęć, zależne od gotowości rzeczywistych danych.
Nie zatwierdzamy propozycji AI jako geometrii ocenionej przez człowieka.

## Wykonane wdrożenie

- Main został fast-forward do `119f47166fa666d0d8c74d0af3b4e2f4c1099236`,
  następnie do `e15b5d6a03d3d85a287ba7c77cf2a98ff0caa414` z naprawą CLI.
  Niniejszy zapis jest metadanymi odbioru; wynik push i cleanup zapisujemy
  w lokalnym `artifacts/full-board-rollout-20261106/integration-result.json`.
- Własny TASK panelu przenumerowano1159→1161, zachowując historyczne hashe
  i raporty audytów. Kolizje wersji558/559 z równoległym main zachowano bez
  przepisywania historii. Kod z main nie wniósł zmian funkcjonalnych.
- Baza operatora:0179→0181 przez `npm run db:migrate`; kontrola ról PASS.
- SDK build PASS5.14s. Rzeczywisty standardowy build Reviewera PASS34.94s.
  Admin działa w trybie dev; nie deklarujemy nowego pełnego builda Admina.
- API, Admin, Reviewer i general worker zatrzymano i uruchomiono z main.
  Końcowe odczyty trzech usług HTTP200; general worker PID11992 działa.
  Image-selection i grid-training pozostają zatrzymane, jak przed wdrożeniem.
- Odczyt z nowego interpretera wskazuje moduły API/workera w głównym checkout.
  Przypisania gier, wspólny default,197 geometrii człowieka i309 źródeł
  dotychczasowego importu pozostały identyczne.

## Naprawa wykryta podczas wdrożenia

CLI rejestracji diagnostyk zwracało `GAME_STORAGE_SCOPE_REQUIRED` bez zapisu.
TASK-1162 dodaje istniejący router WRITE po lokalnych timeoutach, przed SQL.
Rzeczywisty test disposable PostgreSQL/CLI PASS29.75s obejmuje maintenance,
blokadę zapisu, commit i ponowienie z nowego procesu. Audyt Opus5.5/high R1
PASS bez P0/P1; zaakceptowane P2 i granice testu są w jego raporcie.
Zamknięcie `08c2fd7487e7927c8607c234fa434689dcd6fc54`, record-hash `e15b5d6a`.

Początkowe32 rejestracje wykonano jawnie oznaczonym obejściem z tym samym
routerem i funkcją SQL; po naprawie oficjalne CLI odtworzyło dokładnie te same
receipty bez nowych wpisów. Następne30 rejestracji wykonało już poprawione CLI.
Łącznie62 unikalne bindingi dotyczą31 źródeł. Chronione role pozostały bez zmian;
użytych diagnostycznie zdjęć nie przedstawiamy jako świeżego niezależnego testu.

## Faktyczna blokada treningu

Końcowy podgląd HTTP nowej polityki `application-grid-corrections-v4`,
`screen+grid` zwraca `canStart=false`, `SCREEN_FULL_PHOTOS_REQUIRED`:
0 pełnych zdjęć,134 częściowe.197 zatwierdzonych plansz nie stanowi pełnych
zdjęć9/9. Brakuje minimum10 pełnych TRAIN i5 pełnych VALIDATION-A.
Podgląd nie zamraża ról i nie uruchamia treningu. Odrębne bramki REG/B
pozostają aktywne;15 pełnych zdjęć nie gwarantuje kwalifikacji automatu.

Przygotowano HTML do sprawdzenia15 zdjęć:10 istniejących TRAIN i5 zgodnych
z przeznaczeniem A, bez przejmowania REG/B/buforów.135 plansz zawiera44
zachowane, dokładnie zweryfikowane ludzkie zatwierdzenia i91 propozycji AI.
Nie powstało żadne nowe zatwierdzenie ani zapis geometrii w bazie.

Root obejrzał trzy pełne zdjęcia z nakładkami, nie wszystkie135 plansz.
Surowy ordinal detekcji mieszał dwie pozycje pod perspektywą w prywatnym
generatorze raportu; użycie istniejącego produkcyjnego `associate_quad_slots`
poprawiło przypisanie. Nie jest to dowód błędu importera aplikacji.
HTML ma sprawdzoną zgodność danych i składnię JS, bez wizualnego testu w browserze.

## Materiał dla operatora i następny krok

Trwały katalog: `D:/game_predicotr/artifacts/full-board-rollout-20261106`.

- `label-pack/review.html`: lista zdjęć, numery plansz, szerszy podgląd,
  zapisane punkty i propozycje. Link prowadzi do rzeczywistego Reviewera.
- `label-pack/proposals.json`, `verification.json`, `manifest.json`:
  propozycje, dowód44 zatwierdzeń i sumy kontrolne. Sam HTML niczego nie zapisuje.
- W Reviewerze otworzyć „Geometria zdjęć”, odszukać podane numery,
  sprawdzić wszystkie9 plansz zdjęcia i zapisać brakujące zatwierdzenia.
  Potem ponowić podgląd, sprawdzić rozłączne role/A/B i dopiero uruchomić
  zatwierdzony trening z trwałym budżetem. Nie odnawiamy go automatycznie.
- `final-verification.json`: rzeczywiste odczyty po wdrożeniu;
  `permanent-cli-verification.json`: identyczne32 receipty po cold replay;
  `final-screen-ready.json`: podgląd blokujący trening.

Staging `e3a392fe-b6b7-4093-95da-a10c7fe5d856` ma1000 unikalnych zdjęć:
309 już zapisanych i691 brakujących; wszystkie pliki istnieją i rozmiary się
zgadzają. Nie wykonano pełnego ponownego hashowania1000 plików.
Browser preflight całego stagingu nadal opisuje1000 źródeł, nie691;
nie jest bezpiecznym zleceniem importu samych braków. Należy przygotować
obsługiwany, jawny wybór691 z nowym przypięciem modelu, bez zmiany starego
anulowanego joba i bez ponownego przetwarzania309 źródeł.

**Nowy model nie został wytrenowany, a import691 nie został uruchomiony.**
Pozostają zależne od zatwierdzeń człowieka i ponownego przejścia bramek.
Default i Mumie A2 nadal używają `3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e`,
revision2. Żadnej propozycji bez etykiety nie nazwano potwierdzoną poprawą.

Wyniki testów T0–T6 i ograniczenia historycznych gate'ów pozostają w
[odbiorze T6](TASK-1160_VERIFICATION.md); nowa naprawa w
[weryfikacji1162](TASK-1162_VERIFICATION.md) i jej raporcie Opus.
Nie wykonano pełnego nowego mypy ani ponownego kompletu wcześniejszych buildów.
