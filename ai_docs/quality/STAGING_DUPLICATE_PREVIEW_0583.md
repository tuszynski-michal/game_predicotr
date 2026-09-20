# Preview duplikatu importu stagingu `9c7de0ca-6eda-4b43-977d-d4684cb6b58b`

Data audytu: 2026-09-20. Odczyt wykonano w transakcji read-only dla gry
`bfc4f949-5c14-4850-b02a-db99610bcfa5`. Dokument nie wykonuje i nie zleca
usunięcia danych.

## Porównane importy

| Import | Utworzony | Plansze | Stan plansz | Wniosek |
|---|---:|---:|---|---|
| `7d10ae0a-60ee-404c-a8b6-38fb3c416ba3` | 2026-09-14 14:44:33 UTC | 10 235 | 10 191 odrzuconych, 44 oczekujące | Zachować: 44 plansze są unikalne. |
| `f4ef3449-4ac2-46de-9dbc-23525cd864ed` | 2026-09-14 20:15:17 UTC | 10 191 | 10 191 oczekujących | Zachować: jest bieżącą kolejką przeglądu. |

Oba importy mają identyczne 1 160 źródeł. Porównanie checksumy źródła,
pozycji i numeru sekwencji wykazało, że 10 191 plansz drugiego importu jest
ścisłym podzbiorem pierwszego. Pierwszy import ma ponadto 44 plansze, których
nie ma drugi.

## Zależności blokujące

Dla 10 191 pokrywających się, starszych plansz istnieją: 10 191
zastąpionych elementów przeglądu, 10 191 rewizji predykcji symboli, 10 191
zdarzeń rozstrzygnięcia oraz 152 865 obserwacji komórek. Są to dane
proweniencji i historii; ich zwykłe skasowanie mogłoby uszkodzić audyt albo
uczenie. Starszy import ma też 205 oczekujących korekt geometrii, w tym dane
dla 44 unikalnych plansz.

Drugi import ma 10 191 aktywnych elementów przeglądu, 198 oczekujących
korekt geometrii oraz 152 865 oczekujących komórek symboli. Nie może zostać
usunięty jako „duplikat”, ponieważ usunęłoby to bieżącą pracę przeglądową.

## Rekomendacja

Nie usuwać teraz żadnego całego importu ani stagingu. Ewentualnym kandydatem
do osobnego, zatwierdzanego cleanupu jest wyłącznie podzbiór 10 191
zastąpionych plansz ze starszego importu. Taki cleanup wymaga osobnego
preview relacji proweniencji, decyzji czy historię odłączyć czy zachować,
oraz jawnej zgody przed modyfikacją danych. Należy pozostawić 44 unikalne
plansze starszego importu i cały nowszy import.
