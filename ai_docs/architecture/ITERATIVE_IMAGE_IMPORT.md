---
title: Iterative image import architecture
status: accepted
last_updated: 2026-08-09
release: "0.5"
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

## Podgląd Reviewera

Etap OCR zachowuje quad obszaru etykiety numeru. Reviewer pobiera checksum-bound
oryginał i renderuje w canvasie viewport będący sumą planszy oraz etykiety.
Nie tworzy kolejnego dużego artefaktu. Dla danych historycznych viewport
rozszerza quad planszy o margines z przewagą dolnej części.

Pierwszy `sourceContextBounds` pozostaje metadanym kadrem referencyjnym przez
wszystkie ręczne rewizje geometrii. Rewizja nadal materializuje nową planszę
roboczą i 15 cropów bezpośrednio z oryginału, ale nie zmienia kadru ani skali
prawego podglądu. Zwykły podgląd i canvas używają osobnych kluczy cache oraz
CORS, aby ponowne otwarcie edytora nie dziedziczyło niezgodnej odpowiedzi obrazu.

## Obserwowalność

Każdy etap pipeline'u zapisuje czas wykonania. Raport skali agreguje czas,
throughput i liczbę elementów bez skanowania całej historii przy każdym
checkpointcie. Obowiązują istniejące lane'y i kolejki; wersja 0.5 nie dodaje
Redis, Celery, mikroserwisu ani nowego workera.

## Model neuronowy — ścieżka awaryjna

Jeżeli kalibracja nie osiąga akceptowalnej jakości, te same niezmienne kohorty
stają się datasetem `image -> four corners`. Przyszły model otrzyma augmentacje
perspektywy, ekspozycji i częściowych zasłonięć wyłącznie w train. Bramka
porówna go z aktywną kalibracją na odseparowanych sesjach; aktywacja nadal
pozostanie jawna i odwracalna.
