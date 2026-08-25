---
title: TASK-0157 image selection scale quality and owner acceptance
status: done
release: "0.4"
last_updated: 2026-08-21
---

# TASK-0157 — Image selection scale, quality and owner acceptance

## Status

`done`

## Goal

Udowodnić na goldenach oraz realnym profilu, że selektor szybko redukuje
kolejne ujęcia, pozostaje bounded pamięciowo i nie scala dwóch różnych ekranów.

## Context

Bez pomiaru nowy moduł może tylko przenieść koszt albo błędy do innego miejsca.
Jest to końcowa bramka wersji 0.4 przed rozpoczęciem pracy na dużych danych
wersji 0.5 i TASK-0076.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_07_0_EXECUTION_PLAN.md`
- `ai_docs/tasks/0156-image-selection-job-resume-and-observability.md`
- `ai_docs/tasks/completed/0165-image-selection-stage-timing-and-real-corpus-baseline.md`
- `ai_docs/tasks/completed/0166-reduced-jpeg-scan-and-bounded-cpu-budget.md`
- `ai_docs/tasks/completed/0167-appearance-only-sequential-image-grouping.md`
- `ai_docs/tasks/completed/0168-first-usable-range-free-representative-selection.md`
- `ai_docs/tasks/completed/0169-range-agnostic-selection-output-and-import-handoff.md`
- `ai_docs/tasks/0170-versioned-image-scan-cache-and-resume.md`
- `ai_docs/tasks/0171-fast-selection-real-corpus-regression-and-activation.md`

## Scope

- utworzyć niezależne adnotacje zakresów, grup i poprawnych reprezentantów,
- objąć różne kąty, blur, refleks, zasłonięcie, clipping, późniejsze duplikaty,
  skoki numeracji i stronę końcową,
- zmierzyć precision/recall granic, false split, false merge i coverage ekranów,
- zmierzyć skan, throughput, peak RSS i rozmiar storage niezależnie od uploadu,
- potwierdzić zero wywołań OCR, geometrii plansz, homografii i croppera,
- uruchomić profile 10 000 oraz 30 000 z twardym timeoutem i cleanupem fixture,
- porównać liczbę wejść oraz estymowany koszt z pełnym pipeline'em,
- przeprowadzić ręczny odbiór workspace'u, modala, outputu i handoffu,
- zapisać raport i decyzję `ready | optimize | reject`.

## Out of scope

- pełne przetworzenie 500 000 layoutów,
- tuning symbol classifier,
- zmiana kolejki lub dodanie chmury bez dowodu benchmarku,
- tuning OCR i geometrii należących do `Importu layoutów`,
- modyfikowanie działającego uploadu schema v2.

## Acceptance criteria

- [ ] Golden v9 ma zero fałszywych scaleń dwóch różnych kolejnych ekranów.
- [ ] Recall unikalnych kolejnych ekranów v9 wynosi 100%.
- [ ] Każda grupa zawierająca dekodowalny JPEG publikuje reprezentanta, również
      jako jawny best-available fallback.
- [ ] Selekcja v9 nie ustala zakresu; poprawność numerów jest testowana osobno w
      `Imporcie layoutów`.
- [x] Profil 10 000 kończy się w ≤15 minut, a 30 000 w ≤45 minut na komputerze
      właściciela.
- [x] Peak RSS i storage są zmierzone oraz mieszczą się w zaakceptowanym
      budżecie raportu.
- [ ] Liczba wywołań OCR, `PageBoardDetector`, homografii i croppera w selekcji
      v9 wynosi zero.
- [ ] Kontrolny run 40 000 zdjęć raportuje pełny czas, throughput i peak RSS;
      właściciel jawnie akceptuje wynik albo kieruje go do optymalizacji.
- [x] Restart/cancel profile nie pozostawia procesu ani częściowego manifestu.
- [ ] Właściciel potwierdza nawigację, single-file fallback, Enter, strzałki,
      nazwy outputu i jawny handoff.
- [x] Raport końcowy jawnie zezwala lub blokuje użycie przed TASK-0076.

## Technical notes

Duży fixture ma powstawać w ignorowanym katalogu i może używać kontrolowanych
kopii/hardlinków, ale raport musi oddzielić koszt I/O fixture od właściwego
dekodowania i selekcji. Każda komenda ma jawny timeout; profil 30k może dostać
limit dłuższy niż 120 sekund dopiero po uprzednim komunikacie.

## Expected files

- `scripts/run_image_selection_benchmark.py`
- `scripts/run_image_selection_benchmark.ps1`
- `ai_docs/quality/image-selection-*.json`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile smoke -TimeoutSeconds 120
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 10000 -TimeoutSeconds 1200
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 30000 -TimeoutSeconds 3600
```

## Risks / open questions

- Budżet jest provisionalny do pierwszego pomiaru na komputerze właściciela;
  może zostać zaostrzony, ale nie rozluźniony ponad proces wielogodzinny bez
  nowej decyzji produktowej.

## Outcome

Techniczna część bramki jest ukończona. Dodano niezależny kontrakt adnotacji,
benchmark używający produkcyjnego taniego skanu, wewnętrzny i zewnętrzny timeout,
atomowy raport oraz bezpieczny cleanup fixture. Profile smoke, 10 000 i 30 000
przeszły z zerem fałszywych scaleń, pełnym grouping/auto-selection precision i
niezmienionym inventory źródłowym. Profil 10k trwał 252,51 s i zużył dodatkowo
76,2 MiB peak RSS, a 30k 792,43 s i 194,0 MiB. Sparse verification zachowało
limit `grupy × top-k`.

Raport `quality/IMAGE_SELECTION_ACCEPTANCE.md` po syntetycznych profilach nadawał
decyzję techniczną `ready`. Pierwszy rzeczywisty run zmienił ją na `optimize` do
czasu regresji v4; odbiór właściciela nawigacji, single-file fallbacku, Entera,
strzałek, nazw outputu i jawnego handoffu również nadal oczekuje. Z tego powodu
zadanie pozostaje `in_progress`, nie jest przenoszone do `completed/`, a
TASK-0076 nadal jest zablokowany.

Przed odbiorem właściciela usunięto wykrytą lukę odświeżania Admina: aktywny run
jest odpytywany co 2 s, pojedynczy request jest anulowany po 10 s, a cała sesja
pollingu ma limit 45 minut i cleanup przy zmianie gry lub stanu terminalnego.
Klient API jawnie przekazuje `AbortSignal`; powtarzające się błędy odświeżania są
widoczne, ale nie blokują pozostałych akcji.

Cykl manualnego fallbacku został również domknięty transakcyjnie. Ostatnia
decyzja dla runu blokuje rekord joba, potwierdza brak nierozwiązanych grup i
wykonuje idempotentne `waiting_for_review -> created` z zachowaniem checkpointu
oraz liczników. Admin natychmiast odczytuje ten stan i kontynuuje polling; ręczne
`Ponów` w osobnym workspace nie jest potrzebne.

Workspace odbiorowy pokazuje teraz postęp i wyniki selektora bez konieczności
przechodzenia do `Jobów`: status i etap, `X/N`, procent, grupy, wybory
automatyczne, manualne przypadki, pominięcia, błędy, liczbę kosztownych
weryfikacji oraz oddzielne czasy uploadu i obliczeń. Identyfikatory runu, joba i
manifestu wejściowego zostały przeniesione do zwijanych szczegółów technicznych.

Pierwszy rzeczywisty przebieg 180 zdjęć ujawnił nieakceptowalny manual rate
`32/32`. Przyczyną była zmienna liczba wykrywanych czerwonych ramek, odrzucenie
OCR przed pełną weryfikacją oraz ocena ekspozycji całej ciemnej obudowy.
`fast-image-selector-v2` wprowadził stabilny fingerprint HSV ekranu, pełny
fallback OCR przestrzennej siatki etykiet i guard, który nie tworzy grupy z
jednej klatki przejściowej. Kontrolny przebieg tych samych 180 plików zakończył
się w 44,2 s: 7 poprawnych zakresów wybrano automatycznie, 4 grupy oznaczono
jako powtórzenia, a manual review wyniósł `0`. Odbiór UI nadal wymaga
powtórzenia runu przez właściciela na uruchomionych usługach.

Podczas odbioru doprecyzowano, że ręczny plik jest pomocą, a nie warunkiem
kontynuacji. Dodano append-only decyzję `missing_image`, endpoint
`continue-without-image`, migracje `0029_image_selection_missing_images` i
`0030_image_selection_optional_exceptions` oraz obsługę wznowienia i publikacji
częściowego zestawu przez worker. Główna akcja pomija wszystkie nierozpoznane
grupy bez wymyślania zakresu. Modal pozostaje opcjonalny; znany brak pokazuje
`Brak zdjęcia dla layoutów X–Y`, a nieznany `Nierozpoznany zestaw zdjęć` zamiast
technicznego numeru grupy.
Admin podpowiada zakres tylko dla jednoznacznej, bounded luki maksymalnie
dziewięciu layoutów między dwoma rozpoznanymi zakresami. Dzięki temu bieżąca
luka między `64–72` i `82–90` jest pokazana jako `73–81`, ale skoki numeracji
nie są automatycznie uzupełniane.

Zestaw wynikowy używa nazw `seq_<start>-<end>.jpg`. Admin udostępnia dwie jawne
akcje: checksumowany eksport wszystkich pewnych zdjęć do folderu wybranego
natywnym pickerem przeglądarki oraz handoff tego samego, zweryfikowanego
manifestu do `Importu layoutów`. Backend nie przyjmuje dowolnej ścieżki
docelowej z komputera użytkownika.

Podczas testu eksportu poprawny manifest i JPEG-i nie były dostępne dla Admina,
ponieważ uruchomiony wcześniej proces API nie zawierał nowych endpointów outputu
i odpowiadał `404`. Nie była to utrata ani konflikt danych runu. `api:dev` ma
teraz jawny, ograniczony do `services/api/src` reload, test kontraktu entrypointu
oraz instrukcję jednorazowego restartu starszego procesu. Admin pokazuje też
instrukcję naprawczą, gdy nie może odczytać listy outputu. Zweryfikowane zdjęcia
i checksumowany manifest istnieją nadal; nie trzeba powtarzać selekcji.

Po załadowaniu bieżącego API ujawniła się zgodność wsteczna istniejącego runu:
jego niezmienny managed JPEG ma historyczną nazwę z paddingiem i suffixem
checksumy. Backend wyprowadza teraz publiczne `seq_<start>-<end>.jpg` z zakresu
manifestu i mapuje pobranie z powrotem na rzeczywisty managed file. Regresja API
używa celowo historycznej nazwy wewnętrznej, a test runtime potwierdził dla
bieżącego runu listę `seq_1-9.jpg`, `seq_10-18.jpg` oraz zgodność rozmiaru i
SHA-256 pobranego pliku.

Na życzenie właściciela kontrakt pojedynczego browser stagingu zwiększono z
30 000 do 100 000 JPEG-ów bez uruchamiania długiego benchmarku. Backend i Admin
stosują ten sam limit, a `100 001` jest odrzucane stabilnym błędem. Po wyborze
folderu Admin najpierw renderuje loader przygotowania listy, a następnie pokazuje
zwykły postęp uploadu. Techniczna bramka wydajności pozostaje oparta na już
zaliczonych profilach 10k/30k; rzeczywisty run właściciela będzie obserwacją
operacyjną rozszerzonego limitu.

Pierwszy rzeczywisty upload 32 079 JPEG-ów ukończył się i utworzył run selekcji,
ale trwał 2346,44 s, ponieważ po każdym pliku schema v1 sortowała, serializowała
i zapisywała cały rosnący inventory oraz odsyłała je ponownie w odpowiedzi HTTP.
Staging schema v2 rozdziela mały stały `_upload_state.json` od liniowego,
append-only `_upload_files.jsonl`; pojedynczy PUT zwraca tylko liczniki.
Odtworzenie z dziennika, idempotentny retry, migracja niedokończonego schema v1
i finalny manifest mają testy regresyjne. Checkpointy właściwego selektora co 32
pliki, lease/fencing oraz crash recovery pozostają bez zmian.

Podczas pierwszego rzeczywistego skanu 32 079 zdjęć wykonano nieinwazyjny pomiar
pracującego procesu. W oknie 30,5 s postęp wzrósł z 12 992 do 13 248, czyli do
8,39 zdjęcia/s; heartbeat był świeży, błędów było zero, a RSS spadł z około 721
do 701 MiB. Przy checkpointcie 13 408 selektor miał jednak 1166 grup, 3461
weryfikacji, 1042 przypadki manualne i tylko 99 wyborów automatycznych. Średnio
11,5 zdjęcia na grupę zamiast typowych 50–100 wskazuje, że zmiana perspektywy i
brak stabilnej geometrii fragmentują rzeczywistą sekwencję, a każda fałszywa
granica uruchamia top-k verification.

Poprawkę wdrożono jako osobny `fast-image-selector-v3`, bez zmiany zachowania i
fingerprintu rozpoczętego runu v2. V3 przechowuje w bounded checkpointcie
ostatnią obserwację grupy, porównuje fingerprint z kotwicami jakościowymi i
czasową oraz używa geometrii tylko wtedy, gdy obie sygnatury istnieją i są
porównywalne. Test regresyjny potwierdza, że stopniowa zmiana obrazu pozostaje w
jednej grupie, natomiast kolejna strona nadal jest oddzielana. Rejestr
manifestów po fingerprintcie zachowuje możliwość dokładnego wznowienia v2 po
restarcie. Bieżący job nie został obciążony drugim skanem. Zakończył się
naturalnie przy checkpointcie 14 144 błędem `StatisticsError`, wywołanym próbą
policzenia mediany pustego przypisania wiersza albo kolumny geometrii. Walidacja
niepełnej siatki zwraca teraz brak geometrii, a adapter izoluje również ten błąd
na poziomie pojedynczego pliku. Ten sam job wznowiono jako próbę nr 3 z
checkpointu 14 144 i potwierdzono postęp do 14 336 bez ponownego uploadu oraz bez
zmiany jego fingerprintu v2. Pełna regresja v4 na tym samym stagingu pozostaje
kolejnym krokiem po zakończeniu wznowionego przebiegu v2.

Wznowiony run v2 ukończył 32 079 źródeł i utworzył 2795 grup. Właścicielski
odbiór wyjaśnił dwa mylące liczniki: `25` oznacza pominięte grupy-duplikaty
(73 zdjęcia źródłowe), a `2288` oznacza pozostałe nierozpoznane zestawy, nie
brakujące zdjęcia ani layouty. Zbiorcza kontynuacja częściowo zapisała decyzje,
po czym ujawniła konflikt: kilka nierozpoznanych grup pomiędzy tymi samymi
kotwicami dostało identyczny sugerowany zakres.

Regresję usunięto bez osłabiania unikalności domenowej. Zbiorcza akcja zapisuje
`missing_image` bez zakresu, a sugestia w modalu powstaje tylko dla jednej
nierozwiązanej grupy w jednoznacznej luce. Modal odczytuje bounded kandydatów
bieżącej grupy i pokazuje `Zakres layoutów nierozpoznany`, numer zestawu, liczbę
źródeł oraz ich nazwy. Dzięki temu użytkownik wie, których plików szukać, ale UI
nie przedstawia numeru zestawu jako numeru layoutu.

Analiza przypadku `73–81` wykazała, że grupa zawierała trzy dostatecznie ostre
kandydaty, lecz v2 odrzucał wszystkie przez zestaw miękkich ostrzeżeń jakości i
brak rozpoznanego zakresu. `fast-image-selector-v4` rozdziela twarde błędy
(uszkodzony plik, błąd skanu, jawne zasłonięcie) od miękkich progów jakości. Z
samych słabych zdjęć wybiera deterministycznie najlepszy dostępny kandydat i
oznacza go `QUALITY_BEST_AVAILABLE`. Jedna nierozpoznana grupa pomiędzy pewnymi
`64–72` i `82–90` otrzymuje bounded zakres `73–81` oraz
`RANGE_INFERRED_FROM_BOUNDED_GAP`; dwie grupy w tej samej luce ani luka większa
niż dziewięć nie są uzupełniane. V4 nie zwiększa `topK`, liczby OCR ani pełnych
weryfikacji. Testy jednostkowe v2/v3 kompatybilności, v4 jakości, zasłonięcia i
bounded inference przechodzą; realny rerun v4 oraz odbiór właściciela pozostają
otwarte.

Realny rerun v4 na tym samym stagingu zakończył się technicznie poprawnie, ale
nie przeszedł bramki jakości: z 743 grup tylko 40 zostało wybranych
automatycznie, a 703 wymagały review. Diagnostyka wykazała, że 700 grup miało
niepełną geometrię, 692 nie znalazły siatki widocznych etykiet, a historyczne
kotwice `topK` po pierwszym fałszywym scaleniu blokowały następne granice.

TASK-0160 wprowadza `fast-image-selector-v5`. Ograniczona regresja rzeczywistych
danych rozpoznała 24 z 29 próbek odrzuconych przez v4 (v4 rozpoznał 1/29), w tym
`271–279` z dziewięcioma zgodnymi etykietami. Na pierwszych 160 uporządkowanych
zdjęciach v5 wydzielił kolejno sześć pełnych zakresów `1–9` do `46–54`; jedyną
manualną grupą był niepełny ostatni obraz. Pełny rerun 32 079 zdjęć oraz odbiór
właściciela pozostają otwarte i nie są zastępowane tą ograniczoną regresją.

Odbiór rzeczywistego JPEG-a `73–81` ujawnił dwie niezależne przyczyny. Adapter
v2 odrzucał ciepło zabarwione etykiety, mimo że lokalny OCR rozpoznawał liczby,
a przeglądarka zatrzymywała ręczny `PUT` na preflightcie CORS. Wprowadzono
wersjonowany `fast-image-selector-v7` z adapterem
`visible-sequence-label-range-v3` oraz polityką best-available, w której blur,
zasłonięcie i słabe plansze nie blokują jednoznacznego zakresu. Historyczne
manifesty v2–v6 pozostają niezmienne i rozwiązywalne po fingerprintach.

Dokładnie wskazany przez właściciela plik przeszedł produkcyjny adapter jako
`73–81`, confidence `0.962379`, `auto_selected`. Testy selektora, adapterów, API
i CORS zakończyły się wynikiem `73 passed`; Ruff przeszedł, a skupiona kontrola
mypy zmienionej logiki przeszła z pominięciem zewnętrznych importów. Pełna
kontrola mypy repozytorium przekroczyła limit 120 s. Ręczny upload dopuszcza teraz
`X-Image-File-Name` w trwałej konfiguracji CORS; kolejny pełny rerun i końcowy
odbiór właściciela nadal pozostają otwarte, więc status zadania nie zmienia się.

Po zgłoszeniu spowolnienia pełnej weryfikacji wprowadzono
`fast-image-selector-v8` (`9dc754…`). Nowy run zachowuje pierwszego dostatecznie
czytelnego kandydata, sprawdza bounded kandydatów w kolejności źródłowej i kończy
OCR po pierwszym jednoznacznym zakresie. Test regresyjny potwierdza redukcję z
trzech do jednej weryfikacji dla typowej grupy oraz przejście do drugiego zdjęcia,
gdy pierwsze nie daje zakresu. Historyczny v7 zachowuje fingerprint `21d634…` i
dotychczasowe zachowanie wznowień. Pełny rerun właścicielski nadal pozostaje
otwarty i nie jest zastępowany krótką regresją.

Kolejna obserwacja właściciela wykazała, że samo zatrzymanie OCR po pierwszym
wyniku nie usuwa głównego kosztu: każdy plik nadal jest dekodowany w pełnej
rozdzielczości, przechodzi detekcję plansz, a fałszywe granice uruchamiają
kosztowną weryfikację. Właściciel zaakceptował przeniesienie całego OCR,
geometrii, numeracji i deduplikacji zakresów do `Importu layoutów`.

Przed zamknięciem tego zadania powstanie range-free `fast-image-selector-v9` w
małych iteracjach TASK-0165–0171. Plan zaczyna od instrumentacji i profilu
500–1000 zdjęć, następnie obejmuje decoder-side reduction i kontrolę wątków,
appearance-only grouping, first-usable selection, range-free handoff,
wersjonowany cache oraz pojedynczą końcową regresję 40 000 zdjęć. Upload schema
v2 nie należy do zakresu i nie będzie zmieniany. Implementacja pierwszego kroku
nie została jeszcze rozpoczęta.

## Closure

Zamknięto jako zastąpione 2026-08-21. Kryteria dotyczą historycznego selektora
v9 z wersji 0.4; obecny proces używa ręcznej selekcji jako pełnoprawnego
fallbacku oraz późniejszych adapterów. Nie wolno reaktywować tego zadania bez
nowego planu i aktualnych danych jakościowych.
