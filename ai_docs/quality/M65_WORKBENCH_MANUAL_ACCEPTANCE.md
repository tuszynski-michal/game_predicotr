---
title: M6.5 workbench manual acceptance
status: prepared
last_updated: 2026-07-29
---

# M6.5 — ręczny odbiór stanowiska weryfikacji

## Stan

Automatyczny profil 3000 plansz przeszedł. Ten dokument obejmuje wyłącznie
krótki odbiór operatorski, którego nie wolno zastępować testem jednostkowym ani
czasem wykonania automatu.

W lokalnej bazie sprawdzonej 2026-07-29 istnieje aktywna gra, ale nie ma import
joba `image_directory`. Przed odbiorem trzeba wskazać albo utworzyć prawdziwy
import zdjęć z nierozwiązanymi planszami. Nie należy używać syntetycznego
profilu PostgreSQL jako dowodu jakości obrazów — jego baza jest zawsze usuwana
po pomiarze.

## Uruchomienie

W trzech oknach PowerShell, z katalogu repozytorium:

```powershell
npm run db:up
npm run api:dev
npm run admin:dev
```

Następnie otworzyć `http://127.0.0.1:3000/#operational-reviews`. Rozdzielczość
okna ustawić na 1366 × 768, zoom przeglądarki na 100%.

## Scenariusze

### 1. Układ i dostępność

- [ ] brak poziomego paska przewijania strony,
- [ ] cały układ 5 × 3, wszystkie etykiety i przycisk `Zatwierdź` są widoczne
  bez przewijania,
- [ ] oryginalne zdjęcie zaczyna się dopiero poniżej głównej siatki,
- [ ] fokus klawiatury jest zawsze widoczny,
- [ ] nazwy gry, importu, widoku, komórek i nawigacji są zrozumiałe bez koloru.

### 2. Poprawna plansza wyłącznie klawiaturą

- [ ] `Enter` otwiera potwierdzenie i przenosi fokus na `Potwierdź zapis`,
- [ ] powtórzenie przytrzymanego `Enter` nie zapisuje,
- [ ] drugi świadomy `Enter` zapisuje dokładnie jedną rewizję,
- [ ] strzałka w prawo przechodzi do następnej planszy,
- [ ] po odświeżeniu panel zaczyna od pierwszej nierozwiązanej planszy i nie
  pokazuje zapisanej ponownie w `Do weryfikacji`.

### 3. Korekta symbolu

- [ ] kliknięcie komórki pokazuje 3–4 uporządkowane sugestie,
- [ ] klawisze `1`–`9`, `0`, a następnie `QWERTY` odpowiadają legendzie,
- [ ] skrót nie działa podczas pisania numeru układu,
- [ ] zmieniona etykieta jest widoczna przed zapisem,
- [ ] zapis ma status `Poprawiona`, a historia zawiera poprzednią rewizję.

### 4. Ponowna edycja kompletnej planszy

- [ ] w `Plansze kompletne` można wrócić do accepted/corrected,
- [ ] zapis bez żadnej zmiany jest zablokowany,
- [ ] rzeczywista zmiana dopisuje nową rewizję i nie usuwa poprzedniej.

### 5. Korekta geometrii

- [ ] `Edytuj siatkę` otwiera cztery narożniki na oryginale,
- [ ] podgląd pokazuje ukośną siatkę, wyprostowaną planszę i 15 cropów,
- [ ] anulowanie niczego nie zapisuje,
- [ ] zapis tworzy nowe cropy, ponownie otwiera planszę i nie kopiuje starych
  etykiet na nowe `cropSampleId`.

### 6. Błędy i dwie karty

- [ ] po otwarciu tej samej planszy w dwóch kartach zapis pierwszej przechodzi,
- [ ] zapis drugiej pokazuje kontrolowany konflikt i przycisk wczytania
  aktualnej rewizji,
- [ ] odłączenie odpowiedzi po wysłaniu, a następnie exact retry tego samego
  klucza nie tworzy drugiej rewizji.

## Próba czasu operatora

Zmierz stoperem co najmniej 10 kolejnych plansz i zapisz:

| Metryka | Wynik |
|---|---:|
| liczba plansz |  |
| łączny czas |  |
| poprawne bez zmiany |  |
| plansze z korektą symbolu |  |
| skorygowane komórki |  |
| korekty geometrii |  |

Do czasu tej próby raport używa jawnej prognozy, a nie wyniku pracy człowieka:
8 s dla poprawnej planszy, 25 s dla korekty symbolu i 90 s dla korekty
geometrii. Prognoza nie jest podstawą do włączenia automatycznego importu.
