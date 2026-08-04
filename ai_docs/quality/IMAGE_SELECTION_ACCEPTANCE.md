---
title: Image selection acceptance
status: pending_owner_acceptance
last_updated: 2026-08-04
---

# Odbiór selekcji zdjęć 0.4

## Decyzja techniczna

`optimize`

Profile smoke, 10 000 i 30 000 przeszły kontrolowany benchmark na komputerze
właściciela. Pomiar uruchamiał produkcyjny tani skan JPEG, miniatury, geometrii i
fingerprintu, a niezależne adnotacje deterministyczne dostarczały oczekiwane
granice, zakresy i bezpieczne reprezentanty. Sparse range verification było
liczone, ale nie ładowało prywatnego modelu OCR; jego liczba wyniosła dokładnie
`grupy × top-k`, a nie liczbę wszystkich zdjęć.

| Profil | Czas selektora | Limit | Przepustowość | Peak RSS delta | Wynik |
|---|---:|---:|---:|---:|---|
| smoke / 240 | 6,11 s | 120 s | 39,28 pliku/s | 17,6 MiB | pass |
| 10 000 | 252,51 s | 900 s | 39,60 pliku/s | 76,2 MiB | pass |
| 30 000 | 792,43 s | 2700 s | 37,86 pliku/s | 194,0 MiB | pass |

Każdy profil uzyskał `groupingPrecision = 1`, `groupingRecall = 1`,
`automaticSelectionPrecision = 1`, pełne coverage i zero fałszywych scaleń.
Checksum całego źródłowego inventory był identyczny przed i po każdym
przebiegu. Fixture i proces były objęte twardym timeoutem oraz cleanupem; nie
pozostał katalog roboczy ani częściowy manifest.

Pierwszy rzeczywisty run 32 079 zdjęć zmienił decyzję z `ready` na `optimize`.
Przy 13 408 wejściach v2 utworzył 1166 grup, wykonał 3461 kosztownych
weryfikacji i pozostawił 1042 grupy manualne przy 99 wyborach automatycznych.
Proces był zdrowy, miał zero błędów i stabilną pamięć, ale średnio 11,5 zdjęcia
na grupę wobec typowych 50–100 oznacza nadmierną fragmentację realnych ujęć.
Syntetyczna bramka czasu pozostaje wartościowym pomiarem, lecz nie dowodzi już
gotowości jakościowej na docelowym materiale.

`fast-image-selector-v3` dodał temporalną kotwicę ostatniej obserwacji i
rozróżnił brak geometrii od zmiany geometrii. `fast-image-selector-v4` zachowuje
te reguły, traktuje progi jakości jako sygnały rankingowe i potrafi odzyskać
jedną lukę 1–9 pomiędzy dwoma pewnymi zakresami. Uszkodzony lub jawnie zasłonięty
obraz pozostaje twardo odrzucony. V2 i v3 pozostają niezmienne dla trwających
runów oraz retry po restarcie. Pierwszy przebieg v2 zakończył się przy
14 144 przez nieobsłużoną medianę pustego przypisania siatki; po izolacji błędu
pojedynczego pliku ten sam job wznowiono z checkpointu i potwierdzono postęp do
14 336. Decyzja może wrócić do `ready` dopiero po kontrolowanym rerunie v8 na tym
samym stagingu, z porównaniem liczby grup, verification rate, manual rate,
throughput i braku fałszywych scaleń.

Rerun v4 zakończył się wynikiem 40 automatycznych wyborów oraz 703 grup
wymagających review na 743 grupy, dlatego nie przeszedł bramki. Poprawka v5
usuwa potwierdzone przyczyny: zbyt wąski fallback widocznych numerów oraz veto
historycznej kotwicy `topK` przy zmianie strony. Ograniczona regresja rozpoznała
24/29 rzeczywistych próbek odrzuconych przez v4 oraz poprawnie rozdzieliła sześć
kolejnych pełnych zakresów na pierwszych 160 zdjęciach. Był to wynik pośredni;
decyzja pozostaje `optimize` do pełnego, kontrolowanego rerunu v8 i odbioru
właściciela.

Raporty maszynowe:

- `image-selection-smoke-report.json`,
- `image-selection-10000-report.json`,
- `image-selection-30000-report.json`,
- `image-selection-acceptance-report.json`.

Właścicielski przypadek regresyjny z layoutami `73–81` zmienił politykę nowych
runów na `fast-image-selector-v7`. Dokładnie wskazany JPEG został odczytany przez
produkcyjny lokalny OCR jako `73–81` z confidence `0.962379` i otrzymał
`auto_selected`, mimo częściowego zasłonięcia obszaru plansz. Zasłonięcie, blur i
słabe plansze są od tej wersji ostrzeżeniami rankingowymi; twardo blokowane są
niedekodowalne pliki, błędy skanu i konflikty zakresu. Ręczny JPEG ma osobną
regresję CORS dla nagłówka `X-Image-File-Name`, która potwierdza przejście
preflightu `PUT`.

V8 zachowuje skuteczność adaptera v7, ale wybiera pierwszy dostatecznie czytelny
kandydat z jednoznacznym zakresem i kończy dalszy OCR grupy. Regresja jednostkowa
potwierdza spadek typowego kosztu z trzech do jednej pełnej weryfikacji oraz
fallback do drugiego obrazu, kiedy pierwszy nie daje zakresu.

## Odbiór właściciela — oczekuje po regresji v8

TASK-0157 pozostaje otwarty do realnej regresji v8 i krótkiego odbioru
zachowania produktu. Nie należy powtarzać syntetycznych benchmarków 10k/30k;
następny pomiar ma użyć istniejącego, niezmiennego stagingu 32 079 zdjęć.

1. Uruchom lokalny PostgreSQL, API, worker i Admin, a następnie wybierz szkic lub
   aktywną grę.
2. W `Selekcji zdjęć` wskaż mały folder JPEG, rozpocznij run i potwierdź, że
   postęp oraz końcowe liczniki są czytelne.
3. Jeżeli są wyjątki, potwierdź, że główna akcja
   `Kontynuuj z wybranymi zdjęciami` nie wymaga wpisania numerów ani JPEG-a,
   pomija nierozpoznane zestawy i wznawia ten sam job.
4. Opcjonalnie otwórz ręczne uzupełnienie. `ArrowLeft` i `ArrowRight` mają
   wyłącznie nawigować, a `Enter` zapisać dokładnie jedną decyzję. Techniczne
   `#N` nie może być jedyną informacją o wyjątku.
5. Po opublikowaniu outputu kliknij `Zapisz wybrane zdjęcia do folderu`, wskaż
   katalog i potwierdź nazwy `seq_<start>-<end>.jpg`, np. `seq_1-9.jpg`.
   Folder wejściowy musi pozostać bez zmian. Backend mapuje także starsze
   wewnętrzne nazwy content-addressed na ten publiczny format; nie wolno w tym
   celu przepisywać istniejącego manifestu.
6. Użyj `Przekaż do Importu layoutów`. Import ma otrzymać to samo,
   zweryfikowane źródło, ale nie może rozpocząć ciężkiego pipeline'u bez
   osobnego kliknięcia `Rozpocznij import`.

Po potwierdzeniu tych punktów status zmienia się na `accepted`, TASK-0157 można
przenieść do `completed/`, a wersję 0.4 zamknąć. TASK-0076 pozostaje osobno
zablokowany do bramek dużych rzeczywistych danych i `massImportAllowed` w 0.5.
