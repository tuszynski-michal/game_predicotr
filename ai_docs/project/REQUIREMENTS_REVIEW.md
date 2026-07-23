---
title: Requirements review
status: proposed
last_updated: 2026-07-23
---

# Analiza pierwotnych wymagań

## Ocena ogólna

Opis dobrze definiuje wartość produktu, główny przepływ aplikacji mobilnej oraz kierunek etapowania. Nie jest jednak jeszcze gotową specyfikacją implementacyjną, ponieważ łączy wymagania produktu, pomysły techniczne, niepewne założenia i kilka sprzecznych wariantów algorytmu.

Dokumentacja została przeorganizowana tak, aby Codex mógł pracować po jednym ograniczonym obszarze, bez samodzielnego dopowiadania zasad gry.

## Mocne strony wymagań

- jasny podstawowy przepływ: wybór gry → wprowadzenie layoutu → identyfikacja pozycji → target,
- określona kolejność uzupełniania `row-major`,
- zauważony problem zduplikowanych layoutów,
- rozdzielenie aplikacji użytkownika i modułu administracyjnego,
- zaplanowane etapowanie od mocków do importu zdjęć,
- świadomość, że kolejność rekordów jest krytyczna,
- założenie ręcznej obsługi przypadków o niskiej pewności rozpoznania.

## Problemy wymagające korekty

### 1. Trzy algorytmy były opisane jako jeden

Należy utrzymywać osobno:

1. `Layout matching` — odnalezienie pozycji sekwencji.
2. `Payout evaluation` — policzenie wypłat pojedynczego layoutu.
3. `Target forecast` — przejście przez kolejne layouty, koszty i skumulowany wynik.

Dzięki temu każdy moduł można testować niezależnie.

### 2. Id rekordu i numer układu nie mogą być tym samym

Automatyczny klucz bazy służy technicznie. Widoczny numer układu musi być osobnym `sequence_number`, ponieważ:

- może pochodzić ze zdjęcia,
- jest częścią kolejności domenowej,
- może wymagać walidacji luk,
- baza może mieć kilka wersji datasetu.

### 3. Duplikat wymaga kontekstu sekwencji

Samo pokazanie komunikatu nie rozwiązuje problemu. System musi przechować listę kandydatów i porównać kolejną planszę z następnikiem każdego kandydata. Proces może wymagać więcej niż jednego następnego layoutu.

### 4. Skala może być dziewięć razy większa

Wymagania wspominają zarówno o około 500 000 rekordów na grę, jak i o 500 000 zdjęć z 9 układami. To mogą być całkowicie różne skale: 500 000 albo 4 500 000 layoutów. Ta odpowiedź wpływa na import, czas, storage i benchmarki.

### 5. „Lekka baza” nie powinna oznaczać automatycznie SQLite

Przy milionach danych, równoległym adminie i workerze, stagingu oraz publikacji danych ważniejsza jest integralność i indeksowanie niż minimalny instalator. Dlatego jako źródło prawdy zaproponowano PostgreSQL. SQLite pozostaje sensownym formatem przyszłego snapshotu offline.

### 6. Dwa różne modele wygranych

Opis zawiera:

- konkretną linię pozycji, np. V,
- wystąpienie symbolu w kolejnych kolumnach bez znaczenia rzędu.

To nie jest jeden wzorzec. Model danych musi obsługiwać osobne `pattern_type`.

### 7. Wartość nie należy wyłącznie do symbolu ani wyłącznie do layoutu

Najbardziej elastyczna interpretacja to reguła wypłaty zależna od:

- symbolu,
- liczby kolejnych kolumn,
- typu lub konkretnego wzorca,
- reguł jokera.

Pojedynczy layout może wygenerować kilka wygranych, które następnie są sumowane według ustalonych zasad.

### 8. Import zdjęć musi być osobnym workerem

Przetwarzanie setek tysięcy zdjęć:

- nie może działać w jednym requestcie HTTP,
- musi zapisywać postęp,
- musi obsługiwać restart,
- musi tworzyć review queue,
- powinno używać stagingu przed publikacją.

### 9. Automatyczne „odkrycie wszystkich symboli” jest ryzykowne

Clustering może podpowiadać grupy podobnych kafelków, ale bez oznaczonych przykładów nie gwarantuje poprawnego zestawu symboli. Rozsądny pierwszy wariant to 10–20 oznaczonych próbek na symbol i klasyfikacja z confidence.

### 10. Mobile deployment jest nieokreślony

Sposób działania aplikacji zależy od tego, czy ma być online, offline czy hybrydowa. MVP można szybko zbudować jako klient API w lokalnej sieci, ale nie należy uznawać tego za finalną decyzję bez potwierdzenia.

## Zmiany w etapowaniu

Pierwotne etapy zostały uzupełnione o dwie ważne bramki:

- ręczny import i walidacja danych przed automatycznym OCR,
- prototyp image ingestion na małym reprezentatywnym zbiorze przed masowym workerem.

Pozwala to sprawdzić poprawność domeny bez czekania na najtrudniejszą część computer vision.

## Najważniejsza rekomendacja wykonawcza

Nie zlecaj Codexowi jednego promptu „stwórz aplikację”. Najpierw zamknij Task 0001, potem generuj zadania dla Milestone 01 i wykonuj je pojedynczo. Dokument `AGENTS.md` wymusza aktualizację stanu oraz dokumentacji po każdej iteracji.
