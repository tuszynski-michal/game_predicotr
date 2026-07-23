---
title: Requirements review
status: superseded
last_updated: 2026-07-24
---

# Analiza pierwotnych wymagań

> Dokument historyczny. Obowiązujące źródła prawdy znajdują się w
> `ai_docs/requirements/`, `ai_docs/architecture/` oraz
> `ai_docs/process/DECISION_LOG.md`.

## Ocena ogólna

Pierwotny opis dobrze definiował wartość produktu i główny przepływ, ale łączył wymagania, pomysły techniczne i nieustalone warianty algorytmu. Task 0001 zamknął pytania blokujące M1. Ten dokument zachowuje uzasadnienie najważniejszych korekt; obowiązujące szczegóły znajdują się w wymaganiach, architekturze i Decision Log.

## Mocne strony pierwotnego opisu

- jasny przepływ: wybór gry → wprowadzenie layoutu → identyfikacja pozycji → Target,
- określona kolejność `row-major`,
- zauważony problem zduplikowanych layoutów,
- rozdzielenie mobile i administracji,
- etapowanie od mocków do zdjęć,
- kolejność rekordów traktowana jako domenowa,
- ręczna obsługa przypadków o niskiej pewności obrazu.

## Rozstrzygnięte korekty

### 1. Trzy algorytmy pozostają oddzielne

1. `Layout matching` odnajduje pozycję lub duplikat.
2. `Payout evaluation` liczy wypłatę pojedynczego layoutu podczas builda.
3. `Target forecast` skanuje lokalne gotowe payouty, koszty i maksima.

Każdy moduł ma osobne testy i nie zależy od HTTP ani UI.

### 2. `sequence_number` nie jest kluczem technicznym

Numer layoutu:

- jest częścią cyklicznej kolejności,
- jest ciągły bez luk w opublikowanej wersji,
- jest unikalny w dataset version,
- pozostaje niezależny od `id` bazy.

### 3. Duplikat nie jest rozstrzygany łańcuchem

Pierwotna rekomendacja confirmation chain została odrzucona przez właściciela. Duplikat blokuje Target, a Reset rozpoczyna nowe wyszukiwanie następnego layoutu. Nie powstają tokeny ani stan serwerowy.

### 4. Skala jest znana

`500 000` oznacza layouty na grę, nie zdjęcia. Przy około 15 grach projektuje się około 7,5 miliona rekordów. Zdjęcia nie trafiają do mobile.

### 5. PostgreSQL i SQLite pełnią różne role

- PostgreSQL jest lokalnym kanonicznym źródłem administracyjnym.
- SQLite jest niezmiennym snapshotem generowanym do APK.

Nie ma synchronizacji ani mobilnego połączenia z backendem.

### 6. Istnieje tylko jeden typ wzorca

Jedynym wzorcem jest konkretna `PAYLINE` wskazująca jedno pole w każdej kolumnie. Nie występuje `CONSECUTIVE_COLUMNS_ANY_ROW`.

### 7. Payout zależy od symbolu i długości

Wypłata:

- używa ciągu co najmniej 3 kolejnych kolumn bez luki,
- może zacząć się w dowolnej kolumnie,
- dla jednego ciągu wybiera najdłuższą długość,
- uwzględnia jokera według niezależnej interpretacji payline,
- sumuje wszystkie prawidłowe pary payline/symbol.

### 8. Target używa wyniku netto

- spin 0 nie kosztuje i nie daje payoutu,
- każdy kolejny spin dodaje swój payout i koszt,
- payouty kumulują się także przed wyjściem na plus,
- pełny cykl ma `N - 1` spinów,
- tabela pokazuje dodatnie lokalne maksima, nie pierwszy plus ani rekordy globalne.

### 9. Import zdjęć jest osobnym workerem

Przetwarzanie:

- jest wznawialne,
- zapisuje postęp,
- używa stagingu i manual review,
- nie działa w jednym requestcie HTTP,
- ma wymienne adaptery geometrii, OCR i klasyfikacji.

### 10. Prototyp obrazu wymaga większego zbioru

Trzy przekazane zdjęcia wystarczają do prototypu geometrii. Finalna walidacja wymaga 20–100 zdjęć i około 100 wycinków na symbol, z podziałem według zdjęcia źródłowego.

### 11. Mobile jest offline od M1

M1 nie jest klientem lokalnego API. Jest instalowalnym APK z dołączonym SQLite, pełnym matching i Target. Zmiana danych oznacza nowe wydanie.

## Zachowane bramki etapowania

- działający offline mock M1 przed panelem,
- panel i wersje danych przed zautomatyzowanym wydaniem,
- ręczny import przed automatycznym OCR,
- prototyp obrazu przed masowym workerem,
- benchmark 500 000 layoutów przed zatwierdzeniem docelowej wydajności.

## Rekomendacja wykonawcza

Implementację należy prowadzić małymi zadaniami z jawnym zakresem. Po Task 0001 następnym zalecanym zadaniem jest bootstrap fundamentu offline M1, ale jego utworzenie i wykonanie czeka na osobne polecenie właściciela.
