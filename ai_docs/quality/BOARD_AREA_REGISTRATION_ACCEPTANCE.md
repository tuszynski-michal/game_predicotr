---
title: Board area registration bounded acceptance
status: experimental_not_accepted
last_updated: 2026-09-05
---

# Odbiór rejestracji ograniczonej do obszaru plansz

## Wynik

Wariant `verified-page-registration-v2-board-area-mask-v1` pozostaje opcją
testową. Nie spełnił bramek jakości ani kosztu i nie może zostać ustawiony jako
domyślny. Produkcyjnym ustawieniem nowych preflightów pozostaje
`standard_v0_10`.

Odbiór był operacją tylko do odczytu. Nie zmieniał profili, preflightów,
stagingów, ręcznych decyzji ani aktywnych jobów.

## Próba i izolacja źródeł

W bazie znaleziono 21 kompletnych, ręcznie skorygowanych źródeł, czyli 189
plansz z pełnymi 36 narożnikami. Do porównania weszło 19 źródeł:

- jedno pominięto z powodu braku pliku managed original;
- jedno pominięto, ponieważ po wykluczeniu ocenianego źródła nie pozostawała
  żadna niezależna kotwica tej gry.

Każde oceniane źródło i jego dokładne duplikaty były usuwane z zestawu kotwic
po SHA-256. Limit narzędzia wynosi 50 źródeł. Aktualny materiał nie pozwalał
osiągnąć planowanych 50, dlatego wynik jest odbiorem ograniczonym, a nie pełną
kwalifikacją jakościową.

## Porównanie

| Metryka | Standardowe v0.10 | Obszar plansz — testowe |
|---|---:|---:|
| Rozpoznane źródła | 14/19 (73,68%) | 13/19 (68,42%) |
| Mediana błędu narożników | 6,20 px | 6,36 px |
| Mediana czasu na źródło | 1,12 s | 1,35 s |
| p95 czasu na źródło | 2,36 s | 4,03 s |
| Łączny czas | 27,52 s | 34,87 s |

Maska obniżyła pokrycie o 5,26 punktu procentowego i zwiększyła łączny czas o
26,67%. Nie było przypadku rozpoznanego wyłącznie przez wariant maskowany.
Wszystkie 11 odrzuceń obu wariantów zakończyło się kodem
`PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`.

Wynik nie spełnia bramki narzutu do 10%, nie poprawia błędu i nie poprawia
pokrycia. Nie stwierdzono nowej automatycznej akceptacji właściwej tylko dla
maski, ale tak mała próba nie wystarcza do szerszej deklaracji bezpieczeństwa.

## Przypadek `seq_53119-53127.jpg`

Oceniono rzeczywisty JPEG stagingu o oczekiwanej checksumie, nie zrzut ekranu
z overlayem. Dla tego źródła nie istnieje ręczna referencja 36 narożników,
dlatego przypadek służy wyłącznie diagnostyce:

- standard: odrzucenie `PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`;
- maska: odrzucenie `PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`;
- oba warianty wykonały po 15 przypiętych prób;
- ciaśniejszy obraz ani maska kotwicy nie usunęły przyczyny odrzucenia.

Dokładność tego zdjęcia można ocenić dopiero po zapisaniu pełnych 36 ręcznych
narożników. Obecny wynik nie potwierdza, że ciaśniejsze lokalne przycięcie samo
w sobie naprawia rejestrację strony.

## Ręczne korekty i dalszy test

Zapis kompletnej korekty 36 narożników jest wejściem następnego preflightu i
może kwalifikować źródło do kohorty geometrii. Nie oznacza samodzielnie
treningu, aktywacji profilu ani utworzenia etykiet modelu symboli.

Porównanie oryginału z katalogiem `cut` należy wykonywać jako dwa nowe,
oddzielne preflighty tego samego wariantu. Każdy run musi zachować własny
manifest i fingerprint. Nie wolno zastępować managed originals istniejącego
importu ani porównywać runów z różnymi profilami lub progami.

Narzędzie odbiorcze znajduje się w
`scripts/evaluate_page_registration_variants.py`. Zawsze jest ograniczone do
50 źródeł, działa tylko do odczytu i nigdy nie aktywuje wariantu automatycznie.
