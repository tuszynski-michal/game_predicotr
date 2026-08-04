---
title: Milestone 07.0 fast representative image selection execution plan
status: accepted
release: "0.4"
last_updated: 2026-08-05
---

# M7.0 — Selekcja reprezentatywnych zdjęć

## Cel

Dostarczyć osobny moduł, który redukuje folder 10 000–30 000 kolejnych zdjęć do
jednego bezpiecznego reprezentanta na unikalny zakres sekwencji, zanim zostanie
uruchomiony kosztowny `Import layoutów`.

## Pozycja w planie

- M7.0 należy do wersji 0.4 i może być implementowany po zamknięciu odbioru 0.2.
- Nie wymaga zakończenia treningu M6.6, ponieważ nie klasyfikuje symboli.
- Handoff do pełnego pipeline'u i masowe użycie wymagają późniejszych bramek
  M6.6 oraz M7, rozpoczynanych w wersji 0.5.
- TASK-0076 należy do wersji 0.5 i nie może rozpocząć pełnego importu przed
  przejściem TASK-0157.

## Kolejność zadań

| Kolejność | Zadanie | Rezultat |
|---:|---|---|
| 1 | TASK-0151 | model domenowy, migracja i typowany kontrakt runu |
| 2 | TASK-0152 | czwarty workspace oraz skalowalny upload folderu |
| 3 | TASK-0153 | szybkie grupowanie, quality gate i wybór automatyczny |
| 4 | TASK-0154 | niezmienny output, nazwy, manifest i handoff do importu |
| 5 | TASK-0155 | kolejka manualna i wybór pojedynczego zdjęcia |
| 6 | TASK-0156 | joby, checkpointy, retry, anulowanie i diagnostyka |
| 7 | TASK-0165 | pomiar etapów i realny baseline 500–1000 zdjęć |
| 8 | TASK-0166 | reduced JPEG decode i bounded budżet CPU |
| 9 | TASK-0167 | grupowanie po wyglądzie bez geometrii oraz OCR |
| 10 | TASK-0168 | pierwszy użyteczny reprezentant i best-available fallback |
| 11 | TASK-0169 | range-free output i przeniesienie numeracji do importu |
| 12 | TASK-0170 | wersjonowany cache lekkich obserwacji i bezpieczne resume |
| 13 | TASK-0171 | regresja realnego korpusu i aktywacja v9 |
| 14 | TASK-0157 | końcowy odbiór właściciela i zamknięcie bramki 0.4 |

## Piony wykonawcze

### M7.0.1 — Fundament

TASK-0151–0152 tworzą schemat, API, generowany klient, upload i pusty workspace.
Nie implementują jeszcze automatycznej decyzji jakościowej.

### M7.0.2 — Automatyczna selekcja

TASK-0153 implementuje `fast-image-selector-v1` na małym korpusie golden.
Wynik nie może jeszcze uruchamiać pełnego importu, dopóki nie powstanie
checksumowany output TASK-0154.

### M7.0.3 — Domknięcie użytkowe

TASK-0154–0155 dodają wynik, handoff i manualne rozstrzygnięcia. Oryginały
użytkownika pozostają nietknięte.

### M7.0.4 — Operacje i skala

TASK-0156 dostarcza niezawodność, a otwarty TASK-0157 pozostaje nadrzędną bramką
odbioru. Rzeczywiste obserwacje wykazały, że historyczny v8 nadal wykonuje zbyt
dużo pracy w selekcji, dlatego przed zamknięciem bramki obowiązuje korekta
TASK-0165–0171.

### M7.0.5 — Szybka selekcja bez rozpoznawania danych

TASK-0165–0166 najpierw mierzą istniejący koszt i usuwają pełne dekodowanie oraz
nadsubskrypcję CPU bez zmiany grupowania. TASK-0167–0168 wprowadzają v9:
appearance-only grouping oraz wybór pierwszego czytelnego obrazu bez OCR,
geometrii i pełnej weryfikacji. TASK-0169 zmienia output na range-free i oddaje
numery, dokładne plansze, cropy oraz deduplikację właściwemu `Importowi
layoutów`. TASK-0170 przyspiesza zgodne retry/rerun cache'em, a TASK-0171
uruchamia jeden pełny realny profil dopiero po zaliczeniu krótkich bramek.

Każde zadanie jest osobną iteracją. Nie wolno łączyć implementacji kilku kroków
w jednym niezmierzonym pełnym rerunie ani stroić algorytmu podczas działającego
joba właściciela.

## Bramka M7.0

- workspace pokazuje aktywną grę, upload, postęp, wynik i kolejkę manualną,
- selekcja nie przewiduje zakresów ani luk; skoki rozstrzyga późniejszy import,
- każda kolejna wizualna grupa z dekodowalnym JPEG-em ma reprezentanta,
- częściowo zasłonięte, przycięte i słabe zdjęcia pozostają kandydatami
  best-available; blokowany jest tylko niedekodowalny plik albo twardy błąd
  integralności,
- output ma jedno zdjęcie na wykrytą grupę, bez modyfikacji folderu wejściowego,
- output v9 używa `selection_<groupOrder>.jpg`; zakres powstaje dopiero w
  `Imporcie layoutów`,
- manualny modal działa myszą i klawiaturą zgodnie z wymaganiami,
- handoff uruchamia istniejący import dopiero po jawnej akcji,
- restart workera wznawia run bez powtarzania zakończonych grup,
- selekcja wykonuje zero OCR, detekcji plansz, homografii i cropów,
- krótkie realne profile nie wykazują regresji jakości, a pełny run 40 000 zdjęć
  raportuje rzeczywisty czas, throughput i peak RSS bez sztywnego limitu,
- właściciel akceptuje zmierzony czas 40 000 zdjęć albo kieruje zadanie do
  kolejnej optymalizacji,
- golden ma zero false merge różnych kolejnych ekranów i 100% recall ekranów,
- benchmark nie pozostawia osieroconego procesu i ma własny twardy timeout.

## Zakres świadomie odłożony

- automatyczne uczenie progów z decyzji manualnych,
- wiele równoległych workerów,
- przechowywanie źródeł w chmurze,
- obsługa formatów innych niż JPEG,
- automatyczne kasowanie historycznych wyników selekcji,
- pełny import 500 000 layoutów przed bramką M6.6/M7 i rozpoczęciem wersji 0.5.
