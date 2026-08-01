---
title: Open product and architecture questions
status: active
last_updated: 2026-07-31
---

# Otwarte pytania

Ten dokument wskazuje pytania nadal otwarte i krótki indeks ostatnio
rozstrzygniętych pytań. Obowiązującym źródłem zaakceptowanych odpowiedzi jest
`DECISION_LOG.md` oraz właściwe wymagania.

Q-001–Q-015 oraz Q-018 zostały rozstrzygnięte. Obowiązujące decyzje znajdują
się w [Decision Log](../process/DECISION_LOG.md), a dokładny zapis odpowiedzi
właściciela w
[ukończonym Task 0001](../tasks/completed/0001-architecture-clarification.md).

## Obraz i import

### Q-016 — Stabilność układu strony

**Status: closed 2026-07-28.** Strona ma maksymalnie dziewięć mini-layoutów
w siatce 3 × 3. Ostatnia strona ciągu może zawierać mniej pozycji, ponieważ
liczba layoutów gry nie musi być podzielna przez dziewięć. Pozycje występują
bez luk od indeksu 0 w kolejności row-major. Pełna strona nadal wymaga
dziewięciu pozycji.

### Q-017 — Zestaw treningowy

**Status: closed 2026-07-28.** Właściciel potwierdził możliwość zebrania około
100 przykładów na symbol. Obecne 43 zdjęcia obejmują 387 layoutów i 5805
automatycznie utworzonych cell crops. Właściciel nie wycina ich ręcznie;
manualna praca dotyczy zatwierdzenia lub korekty etykiety. Podział
train/validation/test nadal odbywa się według zdjęcia źródłowego.

## Administracja i wdrożenie

### Q-019 — Wielu administratorów

**Status: closed 2026-07-29.** Lokalny panel początkowo obsługuje właściciela,
ale docelowo zdalny moduł review ma umożliwić pracę co najmniej jednej innej
osobie. Każda decyzja musi mieć aktora, sesję, append-only audyt i optimistic
revision. Zdalny recenzent ma dostęp wyłącznie do wskazanej gry i review, nie do
pełnej administracji.

### Q-021 — Transport zdalnego review

**Status: closed 2026-07-30.** Dla czasowego zdalnego review v0.1 wybrano
Cloudflare Quick Tunnel do publicznego originu samej aplikacji Reviewer.
Połączenie jest wychodzące, używa losowego adresu HTTPS i nie otwiera portu
routera. API, Admin i PostgreSQL pozostają na loopback. Tryb nie ma SLA i służy
testom/pilotowi; stały adres wymaga później named tunnel.

### Q-020 — Aplikacja referencyjna

Czy istnieje zgoda właściciela aplikacji Windows na analizę jej zachowania, plików i ruchu sieciowego? Bez zgody prace należy ograniczyć do obserwacji funkcji, dostarczonych zdjęć i ręcznego tworzenia specyfikacji.

## Panel Admin 0.2

Poniższe pytania są omawiane przed zadaniem `0.2`, którego semantykę zmieniają.
Nie blokują TASK-0119, kontrolowanego resetu TASK-0120 ani wydania `0.1`.

### Q-022 — Fizyczne usuwanie gry

**Status: closed 2026-07-31.** Docelowe `Usuń` ma fizycznie usunąć grę oraz
wszystkie rekordy należące do niej. Ponieważ operacja będzie rzadka i wymaga
dokładnego kontraktu zależności, nie powstaje w wersji `0.2`. W `0.2` katalog
udostępnia filtry `Aktywne`, `Szkice`, `Zarchiwizowane` oraz odwracalną
archiwizację. Kaskadowe usuwanie wróci jako osobne zadanie w późniejszej wersji.

### Q-023 — Usuwanie wydania Android

**Status: closed 2026-07-31.** `Usuń wydanie` ma całkowicie usunąć rekord
wydania, APK, snapshot, manifest, checksumy i pozostałe dedykowane artefakty.
Właściciel nie potrzebuje powrotu do starszych wersji, gdy świadomie uzna je za
zbędne. Operacja wymaga dokładnego wskazania wersji i mocnego potwierdzenia, nie
ma automatycznego rollbacku. Pozostaje wyłącznie minimalny append-only wpis
audytowy opisujący wykonanie usunięcia, bez zachowania dostępnego wydania.

### Q-024 — Retencja jobów

**Status: closed 2026-07-31.** W `0.2` joby pozostają możliwie proste i nie
otrzymują automatycznej retencji ani dodatkowej logiki cleanupu. Są przeniesione
do trzeciej głównej zakładki `Joby`, aby nie mieszały się z zarządzaniem grami i
wydaniami Android. Widok pokazuje postęp oraz zapewnia proste filtrowanie po
statusie joba. Rozbudowana retencja może powstać dopiero wtedy, gdy rzeczywista
liczba danych pokaże taką potrzebę.

### Q-025 — Wybór folderu zdjęć

**Status: closed 2026-08-01.** Podstawowy workflow udostępnia przycisk
`Wybierz folder`, który otwiera standardowy selektor folderu przeglądarki i
przesyła wybrane JPEG-i do kontrolowanego lokalnego stagingu. Nie uruchamia
PowerShella ani blokującego requestu wyboru. Backend waliduje liczbę, rozmiar,
nazwy i zawartość plików przed wydaniem jednorazowego tokenu. Ręczne wklejanie
ścieżki nie jest wymagane w interfejsie `0.2`.

### Q-026 — Jeden widoczny zestaw reguł

**Status: closed 2026-07-31.** Admin pokazuje jeden bieżący workspace reguł.
Historia nie zaśmieca głównego interfejsu, ale backend przy każdej publikacji
tworzy nową, niezmienną wersję. Opublikowanych reguł nie nadpisuje się w miejscu.

### Q-027 — Docelowa liczba layoutów

**Status: closed 2026-07-31.** Oczekiwana liczba layoutów jest prostą
konfiguracją gry/datasetu, domyślnie `500 000`. Obecnie właściciel zakłada tę
samą wartość dla każdej docelowej gry, ale pole pozostaje konfigurowalne, jeśli
nie zwiększa istotnie złożoności. Testowy dataset `0.2` zapisuje własną małą
wartość. Konfiguracja nie oznacza generowania syntetycznych rekordów w
rzeczywistym imporcie.

### Q-028 — Źródło numeru brakującej sekwencji

**Status: closed 2026-07-31.** Administrator może opcjonalnie wpisać lub
poprawić `sequence_number`, z walidacją zakresu i konfliktów. Ręczna korekta nie
jest wymagana: właściciel może zamiast niej doładować nowe lub lepszej jakości
zdjęcia, aby pipeline uzupełnił braki.

### Q-029 — Wybór lepszego zdjęcia duplikatu

**Status: closed 2026-07-31.** Pipeline automatycznie wybiera najlepsze zdjęcie
danej sekwencji według jawnych metryk jakości, ale Reviewer pozwala
administratorowi obejrzeć kandydatów i ręcznie zmienić wybór. Automatyczna
decyzja zachowuje ranking i pochodzenie.

### Q-030 — Niezgodna liczba wykrytych symboli

**Status: closed 2026-07-31.** Pipeline zatrzymuje automatyczne utworzenie
katalogu i pokazuje konflikt do decyzji użytkownika. Nadmiar klastrów może
oznaczać wariant jakości tego samego symbolu, a niedobór — błędne scalenie dwóch
symboli. Użytkownik scala, rozdziela albo przypisuje propozycje; system nie
zmienia oczekiwanej liczby po cichu.

### Q-031 — Własność plików wybranego folderu

**Status: closed 2026-07-31.** Po wyborze folderu system kopiuje oryginały do
kontrolowanego, content-addressed storage i zachowuje checksumę oraz pierwotne
pochodzenie. Przeniesienie folderu użytkownika nie psuje importu, wznowienia ani
Reviewera. Polityka może zostać ponownie oceniona, jeśli praktyczne testy
wykażą problem z rozmiarem lub obsługą plików.

### Q-032 — Zakres operacji „Usuń layouty”

**Status: closed 2026-07-31.** Operacja dla wskazanej gry przywraca jej stan
sprzed wczytania layoutów. Gra pozostaje, ale usuwane są wszystkie dograne
layouty oraz wszystkie należące do nich dane i pliki pochodne: importy,
kontrolowane kopie źródeł, cropy, OCR/geometria, review, datasety, payouty,
symbole/reguły utworzone dla tego workflow oraz wydania i ich artefakty.
Operacja pokazuje pełny preview zależności i wymaga mocnego potwierdzenia.
Fizyczny blob współdzielony z inną grą jest usuwany dopiero po zaniku ostatniej
referencji. Pozostaje minimalny append-only audyt wykonanego resetu.

## Warunek rozpoczęcia etapów

- M1 nie ma otwartych pytań blokujących.
- Techniczne decyzje toolchain/build podejmowane w M1.1 nie wymagają odpowiedzi
  produktowej, ale muszą zostać zapisane w Decision Log.
- Q-016/Q-017 są zamknięte. D-057 dopuszcza M6 na przejrzanych goldenach i
  automatycznych cropach, przy OCR pozostającym w trybie manual-review-only.
- M2 i lokalny M6.5 mogą używać panelu właściciela na loopback. Q-019 jest
  zamknięte; zdalna autoryzacja wielu recenzentów należy do M8.7 i wymaga
  rozstrzygnięcia Q-021.
- Analiza aplikacji referencyjnej poza obserwacją wymaga odpowiedzi na Q-020.
- Q-022–Q-032 zostały rozstrzygnięte przed rozpoczęciem implementacji Admina
  `0.2`.
