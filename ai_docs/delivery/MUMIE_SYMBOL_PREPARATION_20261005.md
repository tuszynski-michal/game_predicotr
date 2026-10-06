---
title: Mumie — przygotowanie aktualnych etykiet do kwalifikacji treningu
status: accepted
last_updated: 2026-10-05
---

# Mumie — aktualne etykiety

Operator zakończył przypisywanie i zlecił dalszą pracę bez swojej obecności,
korzystając z obecnych przykładów. 27 Mumii jest dopuszczalną licznością
pilota; 30 nie jest bramką. Obecny stan rev63 zawiera 339 nowych przypisań
wersji D-496 oraz 244 starsze decyzje bieżące. D-489 wyklucza te starsze
decyzje z przygotowywanego zbioru.

## TASK-0853 — przygotowanie i kontrola zbioru

Zbudować niezmienny, sprawdzalny pakiet dokładnych zatwierdzonych cropów,
bez ponownego cięcia, zmiany anotacji lub udawania kwalifikacji treningowej.
Właściciel walidacji pozostaje `SymbolLabelStore.local_row`; pod jego
geometry-first lock sprawdzamy D-496, bieżące decyzje, słownik i integralność.
Pobieramy tylko najnowsze approve z metadata.dataset_version_id równej
aktywnej referencji. Chronione źródło jest odrzucane przed crop bytes.

Nowy moduł proponowany `vision_lab/symbol_preparation.py` publikuje atomowo
pakiet `lab-symbol-preparation-v1`, purpose=qualification_only, trainable=false,
bez assignments. Pakiet zawiera pełną kopertę symboli/historię/receipts,
manifest źródeł i rodzin, bindingi decyzji, dokładne PNG i sumy. Powtórzenie
identycznego wejścia sprawdza istniejący pakiet; nie nadpisuje go. Osobny
verify działa w nowym procesie i wykrywa brak, drift oraz uszkodzenie cropa.
Limit: 10000 próbek i 64 MiB metadanych; wycinki mają dotychczasowy limit
256 KiB. Bez API, DB, nowych zależności lub zmian bramek szkolenia.

Raport przedstawia liczności klas/źródeł/komponentów, duplikaty pikseli,
sprzeczne klasy identycznych pikseli i powody braku kwalifikacji. Weryfikacja
nie przeprowadza wizualnej korekty klas za operatora. Premium/Super nie ma
osobnych decyzji w obecnym schemacie; nie wnioskujemy takiej etykiety z klasy.

Wymagania VISION_LAB i T06b wymagają zweryfikowanego pochodzenia oraz osobnego
splitu symboli. Wszystkie źródła Mumii mają unresolved/missing; stale split
geometrii nie może zostać użyty jako split symboli. Pytanie o trzy nagrania
pozostaje pending. Do jego rozstrzygnięcia przygotowujemy pakiet i kontrolę
integralności, ale nie rozpoczynamy T07, treningu, kalibracji ani final test.
Nazwy folderów i numery sekwencji nie dowodzą niezależności.

## Odbiór i wyłączenia

Testy: świeże/stare/superseded/withdrawn decyzje, błędny binding i checksum,
chronione źródło przed odczytem, duplikat klas, restart, create-only retry i
tamper. Lint, format, scoped typecheck oraz regresje D-496. Operacyjny odbiór
na istniejących danych: weryfikacja nowym procesem, ponowienie i identyczne
SHA magazynów przed/po. Nie uruchamiamy benchmarku ani powtórnego treningu
geometrii bez nowych siatek. Bez aktywacji, push, merge lub wdrożenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0853 — przygotowanie i kontrola aktualnych etykiet Mumii | gpt-6.1-sol | high | Integralność decyzji, historyczne holdouty i brak niejawnych zgód. | Testy regresji i osobny samodzielny przegląd, bez delegowania |
