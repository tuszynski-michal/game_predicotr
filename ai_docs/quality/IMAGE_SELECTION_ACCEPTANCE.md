---
title: Image selection acceptance
status: pending_owner_acceptance
last_updated: 2026-08-09
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

## Bramka v10 accuracy-first

- regression set potwierdza brak early exit i wybór najlepszego kandydata z
  całej grupy,
- przypadki wielocyfrowe nie tracą skrajnej cyfry przez zbyt ciasny crop,
- kierunki rosnący i malejący tworzą deterministyczne zakresy bez odwracania
  kolejności plików,
- wynik zapisuje się progresywnie jako `seq_<od>-<do>.jpg`, a kolizja nie
  nadpisuje danych,
- krótki syntetyczny smoke raportuje czas, grupy, liczbę weryfikacji i błędy;
  nie jest automatyczną bramką czasu ani substytutem realnych zdjęć,
- końcowy odbiór wykonuje właściciel na realnych zestawach około 5000 i 32 000
  zdjęć. Akceptacja jakości ma pierwszeństwo przed throughputem.

Smoke v10 z 2026-08-08 przetworzył 240 zdjęć i 12 grup w 30,252698 s:
precision/recall 1.0, brak false merge/split, 144/144 dozwolonych dokładnych
weryfikacji i zachowana integralność źródeł. Raport:
`ai_docs/quality/image-selection-v10-smoke-report.json`. Realny odbiór pozostaje
otwarty.

## Bramka v10.1 — adaptacyjna weryfikacja

Baseline pierwszych 200 zdjęć z realnego stagingu 32 079 wynosi 377,530649 s,
9 grup, 99 pełnych weryfikacji, 792 wywołania OCR i 7128 cropów OCR. Wszystkie
grupy `1–9` do `73–81` otrzymały `auto_selected`; błędów skanu nie było.

TASK-0194 porównuje nową wersję dokładnie na indeksach 0–199 i wymaga:

- identycznych granic grup albo jawnie lepszego wyniku zaakceptowanego przez
  właściciela,
- braku regresji rozpoznanych zakresów i przypadku wielocyfrowego,
- porównania checksum wybranych reprezentantów oraz oględzin zmian,
- braku wymuszonej ciągłości dla poprawnego skoku numerów,
- raportu liczby geometrii, kandydatów, batchy i cropów OCR,
- pierwszego celu 113–151 s, czyli 60–70% krócej od baseline; przekroczenie nie
  jest automatycznym odrzuceniem, lecz wymaga decyzji właściciela,
- trudna grupa może wykorzystać pełne top-12 i 72 cropy bez naruszenia bramki.

Po zaliczeniu profilu 200 właściciel decyduje o runie około 5000, a następnie
32 000 zdjęć. Profil nie uruchamia publikacji ani Importu layoutów.

### Wynik techniczny TASK-0194 — 2026-08-08

Powtórny cold profile zachował dziewięć granic grup i zero błędów skanu, ale nie
osiągnął celu czasu. Dwa verifiery uzyskały 366,322600 s, a jeden verifier
310,859984 s wobec 377,530649 s baseline. Peak RSS obu wariantów wyniósł około
457 MB. Adaptacja zmniejszyła pracę do 35 weryfikacji dowodu zakresu, 249
wywołań OCR i 2211 cropów, lecz pełna geometria 99 reprezentantów nadal jest
dominującym kosztem.

Osiem zakresów pozostało zgodnych. Grupa 159–180 nie dostarczyła dowodu OCR i ma
stan `manual_required`; v10 wypełniał ten zakres z kursora, czego v10.1 celowo
nie robi z uwagi na dozwolone skoki numerów. Techniczna rekomendacja to
`optimize`. Właściciel potwierdził tę decyzję 2026-08-08. Produkcyjna aktywacja
dwóch verifierów została wycofana, run 5000/32 000 nie został uruchomiony, a
następna iteracja ma najpierw poprawić dowód OCR dla grupy 55–63 i koszt pełnej
geometrii.

### Wynik techniczny TASK-0195 — 2026-08-08

Checksum-bound regresja dla zdjęcia `1/1_010522.jpg` potwierdziła przyczynę:
OCR poprawnie odczytywał siedem etykiet `55, 56, 57, 58, 59, 60, 62`, ale
adapter v5 wymagał jednocześnie obu krawędzi 55 i 63. Nowy adapter v6 odzyskuje
55–63 z lokalnej homografii 3×3, bez użycia poprzedniej grupy. Osobny test
odrzuca siedem punktów wewnętrznych bez żadnej etykiety brzegowej.

Cold profile wyłącznie problematycznej grupy indeksów 159–180 zakończył się w
25,701488 s, bez błędów skanu. Przeanalizował 22 zdjęcia i 12 kandydatów pełnej
weryfikacji, wybrał checksum
`2ea1a6bf2708d384537ddcf2ce11cad80c6d5c8fa7c45da959242447af9b4037`
oraz zwrócił `auto_selected` z zakresem 55–63. Pełny run 5000/32 000 nie został
uruchomiony. Następna iteracja może skupić się na dominującym koszcie geometrii.

### Wynik techniczny TASK-0196 — 2026-08-08

Profil funkcji wykazał 163 194 powtarzane wywołania `numpy.mean` oraz 81 769
alokacji masek podczas refinementu 22 zdjęć. Skalowanie do 1280 px zmieniło
semantyczny wynik 14/22 obrazów, a szeroki crop również powodował regresje,
dlatego oba skróty odrzucono. Dokładna suma integralna zachowała kanoniczny hash
22 wyników
`2f7397d516eda85f9ac4f05ff2df2f3e9a971298f6865fec5c3f51c59238806c`,
a czas samego detektora spadł z 8,720996 s do 1,862312 s.

Celowany profil grupy 55–63 spadł z 25,701488 s do 9,245810 s, zachowując ten
sam checksum reprezentanta i zakres. Powtórny cold profile indeksów 0–199
trwał 91,714346 s wobec 310,859984 s TASK-0194 i 377,530649 s v10. Zachował
dziewięć granic, zwrócił wszystkie zakresy 1–9 do 73–81, nie zmienił żadnego z
ośmiu wcześniej wybranych reprezentantów i miał zero błędów skanu. Geometria
99 kandydatów spadła z 170,748913 s do 35,158739 s. Run 5000/32 000 nie został
uruchomiony automatycznie.

### Powtórka TASK-0194 po optymalizacji — 2026-08-08

Kontrolowana powtórka na indeksach `0–199` trwała 109,111404 s, czyli 71,10%
krócej niż baseline v10. Wszystkie dziewięć granic grup, zakresy `1–9` do
`73–81` oraz checksumy reprezentantów są identyczne z pierwszym profilem po
TASK-0196. Błędów skanu nie było. Peak RSS wyniósł 449 204 224 B, a delta wobec
stanu początkowego 132 567 040 B.

Wynik jest o 18,97% wolniejszy od poprzedniego pomiaru 91,714346 s, ale nadal
spełnia cel czasu TASK-0194 i nie pokazuje regresji jakościowej. Raport:
`artifacts/image-selection-v101-first-200-task0194-repeat.json`.

Po tym wyniku właściciel 2026-08-09 jawnie zastąpił etap pośredni 5000
bezpośrednią bramką całego dostępnego stagingu 32 079 zdjęć. Profil pozostaje
read-only i nie publikuje outputu; decyzja odbiorowa nadal wymaga ręcznej oceny
wynikowych reprezentantów. Pierwsza próba kontrolna została zatrzymana przy 180
źródłach, gdy tempo wskazało około dziewięciu godzin i przekroczenie pierwotnego
limitu sześciu godzin. Finalny profil otrzymuje limit bezpieczeństwa 43 200 s;
raport końcowy ma powstać jako
`artifacts/image-selection-v101-exact-geometry-full-32079-task0197.json`.

### Produkcyjny rerun TASK-0197 z zapisem przyrostowym — 2026-08-09

Właściciel odrzucił dalsze wykonywanie pełnego profilu read-only, ponieważ nie
zapisywał on wybranych zdjęć podczas pracy. Proces został bezpiecznie zatrzymany
i zastąpiony rerunem tego samego stagingu 32 079 zdjęć. Każda rozstrzygnięta
grupa jest teraz zapisywana atomowo podczas selekcji jako
`seq_<od>-<do>.jpg`; nie ma końcowego etapu kopiowania wszystkich wyników.

Aktualny run `8d86fb77-531a-4999-a9c1-d02ed15d0af0` używa fingerprintu
`286b652ea8f19e3afb73017b54f096c0eb5dff828f0020f0b7454e9e42b76f40`.
Kontrola przy 128/32 079 potwierdziła trzy zapisane JPEG-i (`1–9`, `10–18`,
`19–27`) w katalogu właściciela. Decyzja jakościowa nadal wymaga obejrzenia
wyników po zakończeniu całego przebiegu.
