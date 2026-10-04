---
title: Mumie — wznowienie uczenia i odbiór partii danych
status: done
last_updated: 2026-10-04
---

# Mumie — wznowienie uczenia i partie danych

## Import i geometria

Kontrola SHA-256 rozliczyła 225/225 unikalnych plików folderu
`C:\Users\tuszy\Documents\game_predictor_traning_set\mumie` w istniejącym
katalogu laboratorium. Nie trzeba ponawiać importu do labu. Katalog Mumii ma
236 zdjęć (225 folderowych i 11 wcześniejszych), rewizja anotacji 481:
20 kompletnych, 11 rozpoczętych, 205 nowych. Nowe oznaczenia nie powstały.

Eksport `afc4f0d7755236f078f4a50e7bd60fd4805bfc1e7b63f24cd494547a412fd816`:

- 5 partii całych zdjęć: 50 / 50 / 50 / 50 / 36, bez zmiany kolejności kolejki;
- 236 nakładek siatek, osobno zapisane geometrie człowieka i propozycje modelu;
- 180 plansz z 20 kompletnych zdjęć, 2700 wycinków PNG 96 × 96 i 20 arkuszy;
- niekompletne zdjęcia nie dostarczają cropów treningowych;
- klasa symbolu i złota ramka pozostają unknown; `symbol_training_eligible=false`;
- identyfikatory, SHA źródeł, pozycje, rewizje i autorzy geometrii w manifestach.

Katalog artefaktu:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-training-20261004\batches\afc4f0d7755236f078f4a50e7bd60fd4805bfc1e7b63f24cd494547a412fd816`.
Przygotowanie trwało 91,66 s. Oddzielny proces zweryfikował checksumy wszystkich
plików. Ponowienie odzyskało identyczny katalog w 12,17 s, bez przepisywania plików.
Strona istniejącego przeglądu geometrii: `http://127.0.0.1:8105`.

## Uczenie siatek

Istniejący run `5bc981568c3f42bd96f6f9238e57aedc`, iteracja 4 / próba 4,
GPU worker PID 39560, preset F, zaplanowany trening 900 s. Pierwotny budżet
14 400 s; przed wznowieniem zużyte 2461,1 s. Trwały przydział zdjęć pozostaje
16 trening / 4 holdout. Brak nowych ręcznych etykiet: pojedyncza próba używa
`--allow-same-data`, jawnie odnotowanego w ledgerze. Nie jest to dowód uczenia
na większej liczbie zdjęć. Kolejna iteracja wymaga nowych poprawnych targetów.

Iteracja zakończona: 901 s treningu, 1922 kroki; łączny zużyty czas runu
3602 s, pozostałe 10798 s. Żaden kandydat nie poprawił holdoutu Mumii.
Bramka F pozostawiła poprzedni stan, bez nowego ONNX i bez nowych propozycji.
Odłożone zdjęcia poprzedniego modelu: 4/4 kompletne i poprawne, image-macro
0,003296. Mała próba nie dowodzi jakości całego katalogu.

| Kandydat | Holdout Mumii image-macro | 777 poziom B | 777 image-macro | Wykrycie / fałszywe |
|---|---|---|---|---|
| 1 | 0,00351 | 299/300 | 0,002751 | 100% / 0 |
| 2 | 0,00346 | 299/300 | 0,002708 | 100% / 0 |
| 3 | 0,00358 | 300/300 | 0,002695 | 100% / 0 |

Wszystkie kandydaty przeszły strażnik 777, ale pogorszyły holdout Mumii.
Profil głównej aplikacji nie został przełączony. Raport źródłowy:
`C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\finetune-D\iterations\04\report.md`.

## Symbole i Super

Lab ma słownik Mumii zatwierdzony przez operatora: 10, J, Q, K, A, Ra,
Sarkofag, Mumia, Faraon, Sfinks. Istnieją 244 decyzje `approve`, wszystkie
z 2026-09-28. Rewizje ich siatek nadal pasują, ale żadna decyzja nie dotyczy
zdjęcia obecnie kompletnego w przepływie V3; żadna nie pochodzi z nowego
przypisywania D-489. Nie włączono ich do treningu nowego klasyfikatora.

Obejrzano arkusze zdjęć `seq_10-18.jpg` i `seq_19-27.jpg`. Mają zarówno zwykłe
litery/liczby, jak i złote detale oraz obwódki symboli egipskich. Sama obecność
złotego koloru nie jest zweryfikowaną etykietą wyboru Super. Potrzebny jest
przykład wskazujący konkretną ramkę wyboru oraz negatywne przykłady podobnych
złotych detali. Operator doprecyzował semantykę: ramka wskazuje wybrany symbol,
trzy mumie nie wystarczają do określenia jego klasy. Proponowana nazwa „Super”.

Trening i wynik rozpoznawania ramki nie zostały pozornie zaliczone: brak
oddzielnych etykiet ramki i ocenionego modelu. Wypłaty oraz rozwijanie kolumn
pozostają poza bieżącym zakresem.

## Weryfikacja narzędzia

5 testów PASS: kolejność i granice partii, blokada cropów z niekompletnych
zdjęć, nieobecne pozycje, dopasowanie bajtów do właściwej gry, drift plików
i ochrona ścieżek manifestu. Ruff check/format PASS; Mypy PASS (1 moduł).
Nie uruchamiano benchmarku, shadow, nowych migracji ani usuwania danych.

## Następny krok

Dokończenie wgrywania do głównej aplikacji w TASK-0843. Potem rzeczywiste
etykiety nowych cropów i ramki Super. Kolejne porcje uczenia siatek wymagają
przeglądu 216 jeszcze niekompletnych zdjęć; propozycje pozostają propozycjami.
