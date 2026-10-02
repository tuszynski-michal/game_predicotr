---
title: Laboratorium wizji — etap B, bramki i dowody
status: active
last_updated: 2026-09-26
---

# Etap B — anotacje, rdzeń treningowy i hybryda

## Zlecenie i zakres

Użytkownik uruchomił T03–T05 autonomicznie według zaakceptowanego planu,
z osobnymi audytami i commitami. T03 wykonuje Sol medium, T04/T05 Sol high;
niezależny audyt każdego z tych tasków: Astra medium. Nie ma zgody na
automatyczną aktywację, push, merge, operacje DB ani etap C.

## Pochodzenie danych i bramka człowieka

Snapshot T02 zawiera 1180 wystąpień / 1160 unikalnych SHA-256.
Użytkownik wyjaśnił, że nazwy mają różne konwencje zależnie od gry,
a różnie nazwane zdjęcia mogą przedstawiać ten sam układ plansz.
Nazwy/prefiksy nie dowodzą niezależności nagrań. SHA-256 wykrywa identyczne
bajty, nie wszystkie powtórzenia układu przy innym kadrze lub kompresji.

Wspólna grupa podziału musi obejmować rodzinę nagrania, pochodne i duplikaty.
Nierozstrzygnięte pochodzenie nie może być automatycznie potwierdzone przez
agenta. Historyczne 777 pozostaje wyłącznie porównawcze. Kandydatura
`gang zd` jako niewidzianej gry wymaga kontroli rodzin i pokrycia topologii;
nie została zamrożona na podstawie liczby prefiksów.

Na wejściu do B brak ręcznie zatwierdzonych anotacji. Agent może dostarczyć
edytor i propozycje, ale nie może oznaczyć swoich decyzji jako
`lab_human_approved` ani zastąpić rzeczywistego pomiaru pracy człowieka
czasem pracy programu. Pilot: do 40 zdjęć/grę, co najmniej 10 rodzin jeśli
dostępne, początkowo 30 pełnych siatek na grę–topologię; czas pierwszych
10 zdjęć/grę. Braki mają być raportowane bez pozorowania spełnienia bramki.

## Kontrola wstępna środowiska — bez instalacji

- `nvidia-smi`: NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB,
  sterownik 591.62. Sam ten odczyt nie potwierdza działania PyTorch/CUDA.
- Oficjalna [lista wersji PyTorch](https://pytorch.org/get-started/previous-versions/)
  potwierdza parę PyTorch 2.12.1 / torchvision 0.27.1 dla Windows i CUDA 13.0.
  Nie sprawdzono jeszcze wielkości pełnego zestawu pobrań ani nie pobierano
  pakietów lub wag. Ich rozstrzygnięcie należy do wejścia w T04.
- Główne środowisko projektu pozostaje bez zmian.

## Status wykonania

T03: część narzędziowa odebrana, całość `blocked` na rzeczywistych danych.
T04 i T05 nie zostały rozpoczęte. Sam kod narzędzi nie domyka wymagań
rzeczywistego splitu i pomiaru anotacji; nie pominięto zależności planu.

## Weryfikacja implementacji

- Wykonawca Sol medium: 9/9 testów anotacji, 19/19 istniejącego API,
  5/5 UI i 3/3 klienta. Ruff/format, ESLint, kontrola typów Python
  (11 modułów) i TypeScript, OpenAPI oraz generated-check zaliczone.
- Root: końcowy production build zaliczony; API i UI uruchomione ponownie
  jako nowe procesy. Odczyt rzeczywistego magazynu po restarcie: rewizja 0,
  brak anotacji, rodzin, pomiarów i splitu. Oryginalne zdjęcia nietknięte.
- Przeglądarka: 24 i 16 uchwytów, przeciągnięcie węzła, jawny wybór pełnego
  sprawdzenia oraz blokada zapisu bez osoby; wybór zdjęcia do rodziny
  zachowany na kolejnej stronie. Nie zapisano ręcznych zatwierdzeń.
  Lokalny dowód: `artifacts/vision-lab/stage-b-editor.png` (niezatwierdzony
  szkic, nie przykład poprawnej referencji). Fizyczny Android niesprawdzony.
- Backup/restore, konflikt rewizji, utrata odpowiedzi/retry i odczyt
  trwałych danych są pokryte testami w odizolowanych katalogach testowych;
  nie wykonywano odtworzenia nad rzeczywistymi danymi użytkownika.

## Niezależny audyt i poprawki

Astra medium: końcowy **PASS kodu**, bez otwartych P0–P2. Audytor niezależnie
uruchomił wcześniejsze 7 testów anotacji; rozszerzone końcowe zestawy
9 i 3 testów zostały uruchomione przez wykonawcę.

Zamknięte uwagi: zachowanie zamrożonych przydziałów po edycji zamiast
kasowania splitu; brak zaliczania nieobecnej planszy do pokrycia topologii;
historia zawierająca kompletne wynikowe decyzje; jawne body JSON backupu
w kontrakcie i kliencie, zgodne z ochroną proxy. Poprawki mają regresje.

## Porównanie z DoD i planem T03

- Edytor obu topologii, rewizje, backup/restore i spójny pion API: zaliczone.
- Ochrona przed przeciekiem rodzin: mechanizm zaliczony; wiarygodność grup
  na rzeczywistym materiale nadal nierozstrzygnięta, nazwy nie są dowodem.
- Interpolacja nie staje się pełną referencją; nieobecne plansze nie
  udają przykładów geometrii: zaliczone testami.
- 777 V2: wykluczone bez dowodu; ścieżka dopuszczenia po udokumentowanej
  proweniencji i porównaniu podobieństwa nie została zrealizowana na danych.
- Ręczny pilot, czas 10 zdjęć/grę, prognoza pracy i zamrożony split:
  niezaliczone. Brak instalacji/treningu T04/T05 i pełnych testów repozytorium.
- Zadanie pozostaje aktywne i blokuje zależne taski; PASS audytu kodu
  nie oznacza ukończenia T03 ani etapu B.
