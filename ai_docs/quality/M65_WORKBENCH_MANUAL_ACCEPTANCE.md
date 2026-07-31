---
title: M6.5 workbench manual acceptance
status: completed
last_updated: 2026-07-31
---

# M6.5 — ręczny odbiór stanowiska weryfikacji

## Stan

Automatyczny profil 3000 plansz przeszedł. Ten dokument obejmuje wyłącznie
krótki odbiór operatorski, którego nie wolno zastępować testem jednostkowym ani
czasem wykonania automatu.

Lokalny import `Blazing Hot 7 Deluxe` zawiera 387 rzeczywistych plansz. Szybki
odbiór obejmuje pierwszych 50 layoutów; pomiar czasu nadal wymaga co najmniej
10 kolejnych plansz. Nie należy używać syntetycznego profilu PostgreSQL jako
dowodu jakości obrazów — jego baza jest zawsze usuwana po pomiarze.

## Uruchomienie

W czterech oknach PowerShell, z katalogu repozytorium:

```powershell
npm run db:up
npm run api:dev
npm run admin:dev
npm run reviewer:dev
```

Następnie otworzyć `http://127.0.0.1:3000/#operational-reviews`, utworzyć link i
kod dla wybranego importu oraz przejść do osobnej aplikacji pod portem 3001.
Kod należy podać na ekranie wejścia. Rozdzielczość okna Reviewera ustawić na
1366 × 768, zoom przeglądarki na 100%.

## Scenariusze

### 1. Układ i dostępność

- [x] brak poziomego paska przewijania strony,
- [x] wszystkie 15 cropów symboli jest kwadratowych, czytelnych i nie rozciąga
  się na całą szerokość ekranu,
- [x] cały układ 5 × 3, wszystkie etykiety i przycisk `Zatwierdź` są widoczne
  bez przewijania,
- [x] obok siatki znajduje się wycięty obraz dokładnie bieżącej planszy, a nie
  pełne zdjęcie zawierające do dziewięciu layoutów,
- [x] fokus klawiatury jest zawsze widoczny,
- [x] nazwy gry, importu, widoku, komórek i nawigacji są zrozumiałe bez koloru.

### 2. Poprawna plansza wyłącznie klawiaturą

- [x] pojedyncze świadome `Enter` zapisuje dokładnie jedną rewizję bez modala,
- [x] po poprawnym zapisie `Enter` przechodzi do następnej planszy,
- [x] powtórzenie przytrzymanego `Enter` nie tworzy kolejnej rewizji,
- [x] strzałka w prawo zatwierdza lub przechodzi dalej tak samo jak `Enter`,
- [x] strzałka w lewo wraca do poprzedniej planszy także wtedy, gdy została
  właśnie zatwierdzona,
- [x] nawigacja obejmuje zawsze wszystkie plansze importu i nie kurczy się po
  zmianie statusu; sieć nadal pobiera najwyżej jedną planszę na żądanie,
- [x] po odświeżeniu Reviewer zaczyna od pierwszej nierozwiązanej planszy,
- [x] gdy wszystkie plansze są rozwiązane, ponowne wejście zaczyna od pierwszej
  planszy importu.

### 3. Korekta symbolu

- [x] kliknięcie komórki pokazuje 3–4 uporządkowane sugestie,
- [x] klawisze `1`–`9`, `0`, a następnie `QWERTY` odpowiadają legendzie,
- [x] skrót nie działa podczas pisania numeru układu,
- [x] zmieniona etykieta jest widoczna przed zapisem,
- [x] zapis ma status `Poprawiona`, a historia zawiera poprzednią rewizję.

### 4. Ponowna edycja kompletnej planszy

- [x] w kolejce wszystkich plansz można wrócić do accepted/corrected,
- [x] niezmieniona kompletna plansza przechodzi akcją `Dalej` bez pustej rewizji,
- [x] rzeczywista zmiana dopisuje nową rewizję i nie usuwa poprzedniej.

### 5. Korekta geometrii

- [x] `Edytuj siatkę` otwiera cztery narożniki na oryginale,
- [x] podgląd pokazuje ukośną siatkę, wyprostowaną planszę i 15 cropów,
- [x] anulowanie niczego nie zapisuje,
- [x] zapis tworzy nowe cropy, ponownie otwiera planszę i nie kopiuje starych
  etykiet na nowe `cropSampleId`.

### 6. Błędy i dwie karty

- [x] po otwarciu tej samej planszy w dwóch kartach zapis pierwszej przechodzi,
- [x] zapis drugiej pokazuje kontrolowany konflikt i przycisk wczytania
  aktualnej rewizji,
- [x] odłączenie odpowiedzi po wysłaniu, a następnie exact retry tego samego
  klucza nie tworzy drugiej rewizji.

## Próba czasu operatora

Zmierz stoperem co najmniej 10 kolejnych plansz i zapisz:

| Metryka | Wynik |
|---|---:|
| liczba plansz | 11 |
| łączny czas | 198 s |
| poprawne bez zmiany | 10 |
| plansze z korektą symbolu | 1 |
| skorygowane komórki | 1 |
| korekty geometrii | 0 |

Przed tą próbą raport używał jawnej prognozy, a nie wyniku pracy człowieka:
8 s dla poprawnej planszy, 25 s dla korekty symbolu i 90 s dla korekty
geometrii. Prognoza nie jest podstawą do włączenia automatycznego importu.

## Wynik

Właściciel zatwierdził i ponownie przejrzał układy do `#55`. Próbę czasu
odtworzono z utrwalonych `resolvedAt` dla 11 nowych decyzji `#28–#42`; przerwy
na już kompletne pozycje pozostają w całkowitym czasie 198 sekund. Dodatkowy
odbiór 1366 × 768 potwierdził brak poziomego overflow, 15 kwadratowych komórek
w viewport, widoczny przycisk główny i wyrównanie obrazu porównawczego.
