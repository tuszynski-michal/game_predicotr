---
title: Mumie — contract for a new symbol-label dataset version
status: accepted
last_updated: 2026-10-05
---

# Mumie — nowa wersja zbioru do etykietowania symboli

## Status i decyzja operatora

Operator zaakceptował kontrakt 2026-10-05. TASK-0850
zakończył iterację 5 i przygotował 4185 wycinków. Istniejący panel etykiet
odrzuca je przez `HOLDOUT_POLICY_UNRESOLVED`, ponieważ dawny zamrożony split
geometrii jest nieaktualny. Architektura VISION_LAB zachowuje stale i zakaz
ponownego freeze; guide wymaga jawnego kontraktu wersji przed ponownym użyciem.

Foldery `1 - 23175 cut` oraz `481537- 500000 cut` pochodzą z różnych nagrań,
zgodnie z deklaracją operatora. Ta deklaracja nie weryfikuje automatycznie
rodzin obecnych 31 zdjęć i nie zastępuje etykiet symboli.

## Problem i wynik

Potrzebna jest osobna, jawnie wersjonowana referencja do obecnych 31
zatwierdzonych zdjęć Mumii, umożliwiająca pracę istniejącego edytora symboli.
Źródłem są aktualne ręczne zgody na geometrię, nie nowe zgody wygenerowane
przez migrację. Stary zbiór, split, runy oraz wcześniejsze etykiety pozostają
w dotychczasowych lokalizacjach. Główna gra Mumie pozostaje bez plansz.

## TASK-0851 — wersja zbioru i podłączenie istniejącego edytora

1. Odczytowy preview wiąże katalog SHA, 31 źródeł i ich SHA, aktualne
   geometrie/review oraz oryginalne zdarzenia zgody, słownik v1 i stary split.
   Obecne wejście: rewizja 591, 31 zdjęć, 279 plansz, 4185 komórek.
2. Nowy create-only manifest ma pełne pochodzenie z poprzedniej wersji.
   Nie kasuje ani nie naprawia w miejscu frozen splitu. Nie wolno zastosować
   istniejącego rebase na nieobsługiwanym payloadzie lub ręcznie usunąć splitu.
   Kontrakt przeniesienia zgód/historii musi jawnie wskazać oryginalne rewizje
   i checksumy; nie nadawać nowych zgód operatora.
3. Chronione role Reels/final_test i Treasure/unseen_game oraz wszystkie
   powiązania źródeł pozostają zachowane. Nie losować ponownie dawnych ról.
   Zachować również historyczne użycie Mumii w runach i role 25/6 runu 3;
   nie przedstawiać tych 6 zdjęć jako nowego, niezależnego testu symboli.
4. Edytor i magazyn symboli pozostają istniejącym pionem. Nie tworzyć
   równoległego niekontrolowanego formatu etykiet. Słownik ma te same klasy
   i tożsamości; żadne pole nie otrzymuje automatycznie rozpoznanego symbolu.
   Zmiana API, jeśli konieczna, wymaga OpenAPI i wygenerowanego klienta.
5. Wersja dotyczy etykietowania. Nie zatwierdza trainability, podziału
   symboli, rodzin, cechy Super, modelu ani jego aktywacji. Samodzielne uczenie
   symboli pozostaje zablokowane do dostarczenia klas i właściwego podziału
   rodzin. Ramkę oznaczać jako osobną cechę; złota obwódka planszy nie jest
   zgodą na etykietę komórki.
6. Start korzysta z jawnych ścieżek i kontrolowanych procesów. Jednoczesny
   zapis 8105 i 8102 do tej samej geometrii pozostaje zabroniony. UI od razu
   pokazuje komórki pełnych zatwierdzonych plansz; zmiana symbolu nie wymaga
   poruszenia siatki. Korekta geometrii unieważnia zależne stare etykiety.

## Odbiór

Przed apply: preview źródeł, ról i dziedziczonych zgód. Po wykonaniu:
zgodność dawnych checksumów, nowy proces i gotowa poczekalnia 4185 aktualnych
komórek, poprawne klasy słownika, zero etykiet nadanych przez agenta.
Testy obejmują restart, ponowienie po utracie odpowiedzi, zmianę geometrii,
zablokowanie całego komponentu holdoutu, uszkodzenie manifestu i zachowanie
dotychczasowego edytora bez nowej konfiguracji. Właściwe lint/typecheck/build
po testach. Nie osłabiać `HOLDOUT_POLICY_UNRESOLVED` w starym workflow.

## Format i granica referencji

Nowy moduł `symbol_dataset_version` zapisuje create-only `manifest.json`
z checksumowaną kopertą. ID katalogu jest digestem payloadu. Payload zawiera
pełną kopię oryginalnych stanów/historii/receipts geometrii i symboli, listę
źródeł, słownik oraz dowody historycznego użycia i deklarację operatora.
To referencja uprawnienia do etykietowania, bez nowego splitu lub AnnotationStore.
Pierwotny frozen split jest sprawdzany przez jego fingerprint; suma dawnych
i aktualnych powiązań chroni cały komponent final_test/unseen_game.
Tylko przypięte, zaakceptowane źródła mają dostęp do renderera.

Istniejący magazyn symboli dostaje opcjonalną ścieżkę referencji. Pod blokadą
sprawdza checksum manifestu, katalog i oryginalny payload geometrii oraz aktywny
słownik przed odczytem pikseli i zapisem. Drift zatrzymuje operację kodem
`SYMBOL_DATASET_VERSION_STALE`; uszkodzenie daje błąd integralności.
Ponowienie create-only zwraca tę samą wersję; utracona odpowiedź zapisu etykiet
używa istniejącego receipt. Domyślny workflow bez tej konfiguracji zachowuje
dotychczasowe guardy. Format HTTP i tożsamość cropa pozostają bez zmian;
decyzje mają lineage wersji w istniejącym metadata. Limit wersji: 10000 komórek,
pełne renderowanie tylko bieżącej strony. Nowy launcher zapisuje jawne ścieżki
oraz PID/czas utworzenia kontrolowanych procesów, bez automatycznego treningu.

## Granice i ryzyka

Bez DB, migracji, materializacji, shadow, aktywacji, kasowania, push i merge.
Budowa właściwego kontraktu przeniesienia wersji jest pracą aplikacyjną;
sam skopiowany state.json z wyczyszczonym splitem nie spełnia tego planu.
Jeżeli materiał pochodzi z jednego filmu, większa liczba klatek nie daje
niezależnego testu na nowym nagraniu. Nie obiecywać poprawy po kolejnej porcji.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0851 — wersja referencji i działający edytor symboli | gpt-6.1-sol | high | Pochodzenie zgód, ochrona dawnych ról i spójny istniejący workflow etykietowania. | Własny audyt integralności, regresji i nowego procesu; bez delegacji. |
