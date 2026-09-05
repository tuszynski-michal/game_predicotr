---
title: Fast symbol verification acceptance
status: accepted
last_updated: 2026-09-01
---

# Odbiór szybkiej Weryfikacji symboli

## Zakres

Odbiór TASK-0359–TASK-0363 wykonano na istniejącej projekcji PostgreSQL i
rzeczywistych cropach gry `80f3c7ec-6110-4e20-a263-2675ee5b15d6`. Nie
utworzono sztucznych danych ani benchmarkowej kopii bazy.

Pomiar jest powtarzalny poleceniem:

```powershell
.venv\Scripts\python.exe scripts/measure_symbol_review_page.py `
  --game-id 80f3c7ec-6110-4e20-a263-2675ee5b15d6 `
  --symbol-id ae123a1e-9914-4e3d-8502-a1230e3a7133 `
  --state pending `
  --limit 500 `
  --metadata-runs 10
```

Skrypt jest read-only dla danych domenowych. Renderuje wyłącznie te same
regenerowalne atlasy cache, które zamawia Admin.

## Wyniki

| Pomiar | Wynik |
|---|---:|
| metadane strony 500, p95 pierwszej serii | 1,110 s |
| metadane strony 500, p95 przebiegu ciepłego | 0,174 s |
| pierwszy atlas 100 cropów, pierwszy przebieg | 0,488 s |
| wszystkie atlasy strony, pierwszy przebieg | 2,209 s |
| wszystkie atlasy po powrocie na stronę | 0,085 s |
| requesty atlasów dla 500 cropów | 5 |
| łączny rozmiar pięciu atlasów WebP | 291 298 B |
| ponownie wykorzystane klucze cache | 5 z 5 |

Pierwszy przebieg wykonano bez ręcznego czyszczenia cache, aby nie mutować
środowiska operatorskiego. Różnica względem powrotu na stronę oraz identyczne
pięć kluczy potwierdzają skuteczne wykorzystanie stabilnego cache.

Zmierzona strona zawierała 500 assetów `legacy_file`. Bieżąca baza nie zawierała
właściciela `virtual_source`, dlatego rzeczywisty pomiar wariantu
`structured_v0_10` nie był możliwy bez tworzenia sztucznych danych. API i Admin
zachowują w tej sytuacji wymagane zachowanie fail-closed: pokazują `Brak v0.10`
bez podstawienia obrazu legacy i bez mutacji danych.

## Pamięć i liczba odczytów

- zapytanie seek pobiera najwyżej 501 wąskich kandydatów przed hydracją;
- Admin zachowuje najwyżej trzy strony, czyli 1500 rekordów metadanych;
- DOM renderuje ograniczone okno kart i overscan, a nie pełne 500 elementów;
- jedna strona dzieli się na najwyżej pięć atlasów po 100 cropów;
- globalne liczniki są niezależne i nie blokują listy;
- odpowiedź listy nie zawiera binariów ani base64.

Ograniczenia potwierdzają testy reduktora stron, wirtualnego viewportu i kolejki
atlasów. Żaden odczyt Admina nie materializuje całej projekcji gry w pamięci
przeglądarki.

## Wniosek

Bramka metadanych p95 do 2 sekund została spełniona z zapasem. Pierwsze obrazy
pojawiają się progresywnie, pełna strona nie generuje setek requestów, a powrót
na stronę korzysta z content-addressed cache. Eksperymentalny podgląd v0.10
pozostaje wyłącznie warstwą read-only i nie jest źródłem decyzji.

## Odbiór po dużym zasileniu nowej gry — 2026-09-03

Gra `b73c7a42-dfce-498c-be26-0df015721990` miała kompletny read model 19 914
plansz i 298 710 bieżących komórek. Przed maintenance `last_analyze` oraz
`last_autoanalyze` były puste dla komórek, fast documents, recognized boards i
cell observations, a `n_mod_since_analyze` odpowiadało praktycznie całemu
nowemu wsadowi. Plan pierwszego seeku estymował jeden rekord gry.

Po ograniczonym `ANALYZE` pięciu tabel `n_mod_since_analyze` spadło do zera,
estymacja seeku wzrosła do 310 232 rekordów i PostgreSQL użył indeksu
`ix_image_symbol_review_cells_game_sequence`. Jeden rzeczywisty odczyt strony
`wszystkie symbole / wszystkie stany / limit 500` zakończył się wynikiem 500
elementów w 1,475 s z dostępnym następnym kursorem. Nie tworzono sztucznych
danych, nie renderowano benchmarkowych atlasów i nie modyfikowano danych
domenowych ani treningowych.
