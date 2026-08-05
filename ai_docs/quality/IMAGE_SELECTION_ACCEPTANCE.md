---
title: Image selection acceptance
status: pending_owner_acceptance
last_updated: 2026-08-05
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

## Korekta bramki — range-free v9

Obserwacja kolejnego realnego przebiegu wykazała, że v8 nadal przekracza godzinę.
Samo ograniczenie liczby kandydatów OCR nie usuwa pełnego dekodowania JPEG-a,
geometrii wykonywanej dla każdego pliku ani kosztu fałszywych granic. Decyzja
pozostaje `optimize`, a pełny rerun v8 nie jest już zalecaną bramką końcową.

Zaakceptowany plan TASK-0165–0171 wprowadza `fast-image-selector-v9`, który:

- wykonuje reduced JPEG decode i lekki deskryptor wyglądu,
- wykrywa tylko kolejne wizualne grupy,
- wybiera first-usable albo best decodable fallback,
- wykonuje zero OCR, zero `PageBoardDetector`, zero homografii i zero cropów,
- publikuje range-free output, a numerację przekazuje do `Importu layoutów`,
- nie zmienia działającego uploadu schema v2.

Nowa bramka wymaga krótkich realnych profili, zera false merge, 100% recall
różnych kolejnych ekranów oraz jednego pełnego runu 40 000 zdjęć. Nie ma
sztywnego limitu czasu: raport poda całkowity czas, throughput i peak RSS, a
właściciel zdecyduje, czy wynik jest satysfakcjonujący. Pełny run może rozpocząć
się dopiero po zaliczeniu profili 500–1000 i 3000 zdjęć.

## Odbiór właściciela — oczekuje po regresji v9

TASK-0157 pozostaje otwarty do realnej regresji v9 i krótkiego odbioru
zachowania produktu. Nie należy powtarzać syntetycznych benchmarków 10k/30k.
Najpierw obowiązują realne profile 500–1000 i 3000 zdjęć; dopiero po ich
zaliczeniu jeden profil użyje kontrolowanego wejścia 40 000 zdjęć.

### Wynik krótkiej bramki TASK-0171 — 2026-08-05

Golden `image-selection-real-corpus-golden-v1.json` został przygotowany
niezależnie od selektora przez ręczną identyfikację kolejnych ekranów. Obejmuje
pierwsze 500 naturalnych zdjęć, 20 ekranów i dopuszczalne okna początku każdej
granicy. Binarny pHash pierwszej próby był niestabilny dla podobnych klatek, więc
przedaktywacyjny v9 otrzymał ciągłą, znormalizowaną sygnaturę DCT i
wycentrowaną odległość cosinusową. Jego selector fingerprint to
`eaca91fd6f6c169f25436a81b1059810152899953d3eecdef980391df7124afb`.

| Profil | Cold czas | Throughput | Peak RSS delta | Grupy / output | Wynik goldena |
|---:|---:|---:|---:|---:|---|
| 500 | 16,725 s | 29,8947 pliku/s | 82 014 208 B | 20 / 20 | recall 100%, false merge 0, false split 0 |
| 3000 | 131,558 s | 22,8036 pliku/s | 99 037 184 B | 217 / 217 | przypięte pierwsze 500 bez regresji |

Warm-cache przebiegi były identyczne i trwały 2,281 s oraz 18,822 s przy
odpowiednio 500 i 3000 trafień. Oba raporty mają zero wywołań OCR,
`PageBoardDetector`, homografii, cropów i symbol inference. Raporty:

- `image-selection-real-v9-500-w4-report.json`, SHA-256
  `ce70b70adbac77b1e1f34c1aca3810a0a69130ee189a805f90f05a085bd760ef`,
- `image-selection-real-v9-3000-w4-report.json`, SHA-256
  `ab37f1f4d2c3903bb47626dccef5e6676b74ccb47f5d81182e49dfeb3c19e10c`.

Status krótkiej bramki: `passed`. Status aktywacji: `optimize / pending full
corpus`, ponieważ dostępne jest 32 079 naturalnych JPEG-ów, a D-146 wymaga
dokładnie 40 000. Wyniku 217 grup dla 3000 wejść nie należy interpretować jako
pełnego pomiaru jakości poza przypiętymi 500: punktowe oględziny dalszego korpusu
potwierdzają bezpieczną nadsegmentację, lecz nie zastępują goldena. V9 pozostaje
nieaktywny do pełnego profilu i decyzji właściciela `accepted | optimize`.

Baseline TASK-0165 uruchamia się wyłącznie na niezmienianym stagingu po
zwolnieniu workera. Przykład dla pierwszych 500 zdjęć:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 `
  -RealSourceRoot "C:\path\to\browser-selections\<selection-id>" `
  -RealLimit 500 -ScanWorkers 4 -TimeoutSeconds 300
```

Raport `image-selection-real-500-report.json` musi zawierać fingerprint kodu,
throughput, peak RSS, liczbę skonfigurowanych i faktycznie użytych wątków,
p50/p95/max każdego etapu oraz trzy największe składniki czasu. Timeout krótkiego
profilu nie jest docelowym limitem pełnego runu 40 000 zdjęć.

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
   katalog i potwierdź nazwy `selection_<groupOrder>.jpg`. Folder wejściowy musi
   pozostać bez zmian. Historyczny output v2–v8 nadal może używać `seq_*`; nie
   wolno w tym celu przepisywać istniejącego manifestu.
6. Użyj `Przekaż do Importu layoutów`. Import ma otrzymać to samo,
   zweryfikowane range-free źródło, ale nie może rozpocząć OCR, geometrii i
   ciężkiego pipeline'u bez osobnego kliknięcia `Rozpocznij import`.

Po potwierdzeniu tych punktów status zmienia się na `accepted`, TASK-0157 można
przenieść do `completed/`, a wersję 0.4 zamknąć. TASK-0076 pozostaje osobno
zablokowany do bramek dużych rzeczywistych danych i `massImportAllowed` w 0.5.
