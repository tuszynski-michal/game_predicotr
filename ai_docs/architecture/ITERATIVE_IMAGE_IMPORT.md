---
title: Iterative image import architecture
status: accepted
last_updated: 2026-08-23
release: "0.7"
---

# Architektura iteracyjnego importu

## Przepływ

```text
curated image-selection manifest
  -> durable import source
  -> atomic reservation of next N entries
  -> image import job pinned to manifest slice + symbol model + grid profile
  -> operational review
  -> immutable symbol and geometry cohorts
  -> independent candidate gates
  -> explicit activation
  -> next batch
```

## Import ręcznie nazwanych zakresów

Gdy źródłem jest folder lokalnej ręcznej selekcji, worker rozpoznaje tryb
`seq_*` po nazwach plików i zapisuje deklarację w managed manifest. Parser
akceptuje wyłącznie `seq_<start>-<end>.jpg|jpeg`, gdzie zakres obejmuje od 1 do
9 plansz. Sortowanie odbywa się po liczbie `start`, nie po tekście nazwy ani
checksumie. Duplikaty i nakładanie blokują start; luki są ostrzeżeniem.

Pipeline przypina adapter `sequence-number-from-attested-range-v1`. Adapter
pomija OCR numerów i przypisuje numery row-major tylko wtedy, gdy geometria ma
dokładnie oczekiwaną liczbę uporządkowanych plansz. Przy częściowym wykryciu
zachowuje brak numeru i kieruje obraz do korekty, bez przesuwania pozostałych
pozycji. Zakres, jego źródło i checksum pozostają w manifestach oraz wynikach
stage, dzięki czemu retry nie może zmienić deklaracji operatora.

## Model trwały

`curated_image_import_sources` przechowuje grę, run Selekcji Zdjęć, ścieżkę i
checksumę manifestu, liczbę wpisów oraz monotoniczny `next_entry_index`.

`curated_image_import_batches` przechowuje numer partii, półotwarty zakres
`[start_index, end_index)`, status i powiązany image import job. Rekord źródła
jest blokowany podczas rezerwacji. Unikalny numer partii i sprawdzenie zakresu
chronią przed podwójnym użyciem zdjęcia.

Manifest jest ponownie weryfikowany przy tworzeniu joba i przez worker. Job nie
skanuje całego katalogu: ładuje wyłącznie wpisy z przypiętego wycinka, zachowując
`groupOrder`.

## Snapshot pipeline'u

Image import schema v3 zawiera:

- identyfikator źródła i partii,
- checksumę i ścieżkę manifestu,
- początek oraz liczbę wpisów,
- snapshot modelu symboli,
- snapshot profilu kalibracji siatki.

Efektywny fingerprint obejmuje wszystkie te wersje. Aktywacja podczas pracy
joba nie zmienia jego zachowania.

Browserowy import z trwałego stagingu używa schema v5. Oprócz manifestu `seq_*`
zawiera snapshot aktywnego modelu symboli i profilu siatki oraz ich fingerprinty.
Tryb `rerun_current_models` tworzy nowy job dla terminalnego importu z innymi
snapshotami, pozostawiając poprzedni job audytowalny; identyczne żądanie jest
idempotentne. Staging nie jest ponownie przesyłany, a kanoniczne numery są
ponownie sprawdzane przed startem.

### Jawnie przypięty adapter komórek v20

Schema v5 może opcjonalnie zawierać snapshot
`board-cell-processing-v20-verified-v19-v1`. Pole nie jest dodawane domyślnie:
operator wybiera `verified_v19`, a zwykły start zachowuje historyczny v18.
Konfiguracja estymatora i croppera wchodzi do efektywnego fingerprintu.

Historyczna lista checkpointów pliku pozostaje niezmienna. V20 wykonuje
`board_cell_geometry` jako trwały, niezmienny pre-crop substage etapu
`board_crops`. Jeśli worker zakończy się po zapisaniu geometrii, resume używa
stage result bez ponownego estymowania. Replayer po zapisie oraz przy
rehydration materializuje job-local `image_board_geometry_pending`
idempotentnie, co jest konieczne również przy współdzieleniu file execution
przez dwa joby.

Wynik strony może zawierać udane i odroczone pozycje. Tylko udane pozycje
tworzą 15 cropów v19 i przechodzą przez numer z poświadczonego zakresu oraz
model symboli. Odroczone pozycje tworzą zero cropów i zero predykcji. Nie
istnieje przejście z błędu v19 do v18. Dzięki temu historyczne checkpointy i
manifesty są odtwarzalne, a rollback nowych jobów polega na ponownym jawnym
wyborze `historical_v18`.

Oczekujący deferred geometrii należy do granicy `waiting_for_review`. Blokuje
przedwczesną walidację ciągłości i nie jest interpretowany jako brakująca
sekwencja.

### Stan rollout'u i rollback

Cross-staging benchmark obejmujący 300 stron i 2700 plansz potwierdził jakość
automatycznych trafień v19, ale osiągnął `2532/2700 = 93,78%` pokrycia przy
bramce co najmniej `98%`. Z tego powodu `historical_v18` pozostaje domyślnym
snapshotem, a `verified_v19` jest wyłącznie staging-local opt-in. Jawna decyzja
właściciela pozwoliła zintegrować i używać bezpiecznego adaptera v20, lecz nie
zmieniła wyniku bramki ani domyślnego trybu.

Rollback nie mutuje działającego ani historycznego joba. Operator wybiera
`historical_v18` podczas tworzenia kolejnego joba z tego samego lub innego
stagingu. Efektywny fingerprint i checkpointy v18/v20 są rozłączne, więc retry
zawsze zachowuje snapshot pierwotnego joba.

### Ręczne rozwiązanie deferred komórek

Końcowy fallback nie tworzy równoległej kolejki plansz. Dla jednego
`image_board_geometry_pending` API odczytuje niezmienny source i detekcję
planszy oraz snapshot modelu symboli z tego samego importu. Cztery narożniki
przechodzą przez ten sam source-direct cropper v19 co zwykła korekta. Preview
pozostaje read-only; zapis jest dozwolony dopiero po uzyskaniu dokładnie 15
cropów i 15 predykcji w kolejności 3 × 5.

Repozytorium serializuje zapis na rekordzie deferred i w jednej transakcji
tworzy `recognized_board`, 15 `cell_observations`, `image_review_item` oraz
`image_board_geometry_revision`. Istniejący trigger kolejki projektuje nowy
item we właściwe miejsce `sequence_number + position_index`; nie istnieje
druga implementacja kolejki. Wcześniejsza materializacja planszy kończy próbę
statusem `superseded`. Klucz idempotencji i checksumę komendy sprawdza się
przed kosztownym preview/inferencją oraz ponownie pod blokadą zapisu.

Artefakty ręcznych komend używają niezmiennych, command-scoped namespace'ów o
stałej długości ścieżki zgodnej z Windows. Model ONNX jest ładowany wyłącznie z
checksum-bound snapshotu źródłowego joba; aktualnie aktywny model gry nie może
zmienić wyniku historycznego importu.

Reviewer prezentuje trwałe wyjątki jako osobny tryb UI, ale konsumuje istniejące
scope-bound API zamiast budować drugą projekcję domenową. Lista używa
`status=pending`, limitu jednego elementu i stabilnego kursora; klient zachowuje
jedynie bounded historię odwiedzonych stron. Źródło jest wersjonowane checksumą,
a preview i resolution niosą checksumę manifestu oraz oczekiwane rewizje.

Stan klienta wiąże wygenerowany preview z dokładnym zestawem czterech narożników.
Zmiana komendy unieważnia podgląd i jej idempotency key. Ten sam klucz pozostaje
wyłącznie dla ponowienia niezmienionej komendy po niejednoznacznym błędzie
transportu. Konflikt rewizji, manifestu lub statusu powoduje odczyt kolejki od
początku. Po materializacji Reviewer odświeża wyjątki, a zwykłą kolejkę pobiera
ponownie przy powrocie do zatwierdzania symboli, dzięki czemu nowy item przechodzi
przez istniejący bounded bufor plansz.

## Kohorta i profil geometrii

Kohorta jest game-scoped, kumulacyjna i niezmienna. Dla każdej zaakceptowanej
planszy zapisuje źródło, pozycję, zatwierdzony numer, pierwotny quad detektora,
finalny quad review i provenance pipeline'u.

Profil stosuje odporne mediany znormalizowanych przesunięć narożników względem
quada detektora. Korekty są grupowane według runu Selekcji Zdjęć i pozycji
planszy, a próbki bez runu pozostają pełnoprawnym wejściem do fallbacku pozycji.
Inferencja najpierw szuka zgodnego runu, a następnie fallbacku pozycji. Numer
sekwencji nie bierze udziału w inferencji geometrii, ponieważ OCR jest
późniejszym etapem pipeline'u; eliminuje to zależność cykliczną i ryzyko
ukrytego przecieku błędu OCR do cięcia. Nieznana pozycja używa detektora.

Walidacja jest source-image-disjoint. Kandydat porównuje średni i p95
znormalizowany błąd narożników oraz kompletność poprawnych projekcji quada z
wynikiem bazowego detektora. Właściwe 15 cropów pozostaje deterministycznym
wynikiem croppera i podlega manualnemu review. Rejestr aktywacji jest
append-only i umożliwia rollback.

### Przyrostowe kotwice preflightu strony

Preflight strony może zbudować tymczasową kohortę auto-kotwic dla jednego
niezmiennego stagingu. Kohorta nie jest modelem aktywnym gry i nie zmienia
profilu bazowego. Obejmuje wyłącznie wyniki kompletne, które przeszły
zaostrzoną bramkę, ma ograniczenie dwóch przebiegów i 21 nowych kotwic na
przebieg. Dzięki temu kolejne kąty kamery mogą zostać rozwiązane automatycznie,
ale błąd nie propaguje się przez obniżanie bramek ani syntetyczną geometrię.

Manifest końcowy jest również planem częściowego wykonania: `registered`
wchodzi do pipeline'u, `review_required` pozostaje w stagingu do późniejszego
ponowienia lub ręcznej korekty. Kolejny import ze świeżym manifestem ponownie
wykorzystuje rejestr kanoniczny, więc wcześniej zatwierdzone plansze nie są
przetwarzane drugi raz.

## Walidacja geometrii w Reviewerze

Etap OCR zachowuje quad obszaru etykiety numeru. Reviewer pobiera checksum-bound
oryginał i renderuje w canvasie viewport będący sumą planszy oraz etykiety.
Nie tworzy kolejnego dużego artefaktu. Dla danych historycznych viewport
rozszerza quad planszy o margines z przewagą dolnej części.

Pierwszy `sourceContextBounds` pozostaje metadanym kadrem referencyjnym przez
wszystkie ręczne rewizje geometrii. Rewizja materializuje nową planszę roboczą
i `rows × columns` cropów bezpośrednio z oryginału, ale nie tworzy obrazu z
narysowanym overlayem. Overlay jest wyłącznie warstwą canvasa w lokalnym
Reviewerze.

Kolejka game-wide korzysta z jednego właściciela logicznego numeru oraz
bounded keysetu. Szybkie zatwierdzenie i edycja wiążą rewizję decyzji,
geometrii, checksumę i wymiary źródła oraz snapshot topologii. Edytor używa
czterech narożników w kolejności LT, PT, PD, LD; linie wewnętrzne i cropy są
wyprowadzane z topologii planszy. Nowy widok nie ładuje katalogu symboli.

Rollout pozostaje lokalny. Remote Reviewer nadal używa dotychczasowego,
scope-bound API i jego proxy nie dopuszcza nowych game-wide endpointów.

## Obserwowalność

Każdy etap pipeline'u zapisuje czas wykonania. Raport skali agreguje czas,
throughput i liczbę elementów bez skanowania całej historii przy każdym
checkpointcie. Obowiązują istniejące lane'y i kolejki; ten pion nie dodaje
Redis, Celery, mikroserwisu ani nowego workera.

Końcowy raport rollout'u oraz przypięte checksumy benchmarków znajdują się w
`ai_docs/quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md`.

## Model neuronowy — ścieżka awaryjna

Jeżeli kalibracja nie osiąga akceptowalnej jakości, te same niezmienne kohorty
stają się datasetem `image -> four corners`. Przyszły model otrzyma augmentacje
perspektywy, ekspozycji i częściowych zasłonięć wyłącznie w train. Bramka
porówna go z aktywną kalibracją na odseparowanych sesjach; aktywacja nadal
pozostanie jawna i odwracalna.
