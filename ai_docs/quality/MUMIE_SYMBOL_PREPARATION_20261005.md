---
title: Mumie — kontrola bieżących ręcznych etykiet i przygotowanie danych
status: active
last_updated: 2026-10-05
---

# Wynik TASK-0853

Przygotowano 339 aktualnych, technicznie ważnych przypisań z 13 zdjęć,
w 10 klasach. Każdy oryginalny crop PNG96 przeszedł kontrolę byte SHA,
pixel SHA, aktualnej geometrii/photo review, słownika i decyzji. Nie wykonano
treningu: wszystkie próbki mają nierozstrzygnięte pochodzenie i brak osobnego
podziału symboli. Liczność 27 Mumii nie blokuje pilota.

## Rzeczywiste liczności

| Klasa | Próbki | Zdjęcia | Komponenty | Grupa 156538–182853 | Grupa 76555–103221 | Grupa 1–23175 |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 30 | 3 | 2 | 18 | 12 | 0 |
| J | 30 | 3 | 2 | 26 | 4 | 0 |
| Q | 30 | 3 | 2 | 20 | 10 | 0 |
| K | 30 | 3 | 2 | 21 | 9 | 0 |
| A | 30 | 3 | 2 | 19 | 11 | 0 |
| Ra | 30 | 8 | 2 | 25 | 5 | 0 |
| Sarkofag | 49 | 8 | 2 | 37 | 12 | 0 |
| Mumia | 27 | 11 | 3 | 18 | 8 | 1 |
| Faraon | 46 | 9 | 2 | 37 | 9 | 0 |
| Sfinks | 37 | 8 | 3 | 25 | 4 | 8 |
| Razem | 339 | 13 | 3 | 246 | 84 | 9 |

Nie znaleziono identycznych pikselowo cropów ani sprzecznych klas dla takich
samych pikseli. Ten wynik nie dowodzi niezależności nagrań ani braku podobnych
klatek. Nazwy grup są istniejącymi kandydatami rodzin, nie nowymi decyzjami
verified. Dwa główne komponenty pokrywają wszystkie 10 klas. Po potwierdzeniu
niezależności nagrań możliwy jest pilot z całymi komponentami, np. 255 train
i 84 validation; nie zamrożono żadnego takiego przydziału. Cztery przykłady J
i Sfinksa w mniejszej grupie oznaczałyby niską precyzję oceny tych klas.

Magazyn symboli ma revision63, 1045 zdarzeń historycznych i 583 ostatnie
decyzje approve Mumii. 244 starsze decyzje nie należą do nowej wersji D-496
i nie są próbkami przygotowanego zbioru. Pełna historia jest zachowana
wyłącznie jako dowód pochodzenia, zgodnie z D-489.

## Pakiet i trwałość

Katalog:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-preparation-20261005\7fb60ce3edc52081d5f9cf016083a8cd6b048766db30d8df8b008fca0dccb1c8`.

ID `7fb60ce3edc52081d5f9cf016083a8cd6b048766db30d8df8b008fca0dccb1c8`;
341 plików, 9 219 147 bajtów, manifest 1 363 029 bajtów. Format
`lab-symbol-preparation-v1`, purpose `qualification_only`, trainable=false,
bez assignments. Full symbol payload z receipts/historią, dokładne decyzje,
geometria i snapshot przypięte SHA, metadata pełnych bieżących komponentów,
523 chronione źródła oraz oryginalne PNG. Nie jest modelem ani wejściem treningu.

Pierwsza publikacja 24,44 s. Verify w oddzielnym procesie 11,44 s.
Ponowne przygotowanie w nowym procesie odzyskało ten sam ID i zweryfikowało
cały pakiet. Kontrola retry + magazynów 23,81 s. To ograniczone operacje na
istniejących danych, nie benchmark skali.

Sumy magazynów przed i po kontrolach są identyczne i zgodne ze stanem
sprzed rozpoczęcia TASK-0853:

- geometry: `06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43`;
- symbols: `fa518e34b5547eec3b09e7158126a3c01b976bc989b472fa0c21ac54cb046e02`.

Dowód: `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-preparation-20261005\operational-verification.json`.
Podgląd 7 rozłożonych przykładów każdej klasy:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-preparation-20261005\examples.jpg`.
Podgląd obejrzany; prezentuje warianty jakości i kolorów. Nie jest ponownym
zatwierdzeniem wszystkich klas ani oceną accuracy.

## Testy i własny przegląd

- 13 testów nowego modułu + 7 regresji D-496 = 20 PASS (32,37 s).
- Fresh/legacy/superseded/withdrawn, protected przed crop bytes, brak referencji,
  nieważny label, checksum/inventory/lineage, create-only retry, przerwana
  publikacja bez częściowego final, nowy proces i zakaz overlapu PASS.
- Ruff check i format PASS. Mypy scoped: 1 moduł PASS.
- Własny przegląd: brak odblokowania bramek, treningowych assignments,
  zapisu do magazynów użytkownika, niejawnej zmiany decyzji lub API.
- API, klient i UI nie zmienione; nie uruchamiano ich buildów ani restartów.

## Granica dalszej pracy

Każda z 339 próbek raportuje `SYMBOL_SPLIT_NOT_FROZEN`,
`SYMBOL_PROVENANCE_UNRESOLVED` oraz `HOLDOUT_POLICY_UNRESOLVED`. To nie błąd
etykiet. Dawny split geometrii jest stale i nie jest podziałem symboli.
Wymagania `VISION_LAB.md` i T06b zabraniają zgadywania verified z numeracji
albo dzielenia jednego nagrania pomiędzy uczenie i ocenę.

Wysłano jedno pytanie o relację folderów `1 - 23175`, `76555 - 103221` oraz
`156538 - 182853`. Dawna deklaracja niezależności `1 - 23175 cut` i
`481537- 500000 cut` nie rozstrzyga relacji obecnych trzech grup. Potwierdzenie
pochodzenia jest potrzebne przed kwalifikacją i zamrożeniem splitu.
Nie potrzeba teraz kolejnych ręcznych przypisań klas.

Obecny schemat nie zawiera decyzji o obecności ramki Super; zero takich
etykiet. Nawet jeśli obraz przedstawia ramkę, istniejące approve zatwierdza
klasę, nie odrębny atrybut. Nie zgadywano ramek i nie uczono ich detektora.
T06b/T07 pozostają nieodebrane. Bez treningu geometrii, DB, migracji,
aktywacji, shadow, materializacji, push, merge lub wdrożenia.

## Ponowna weryfikacja przez operatora

W nowym PowerShell, z dowolnego katalogu, poniższa konfiguracja i ścieżki
działają bez zmian PATH. Każde wywołanie ograniczyć runnerem do 120 s.

```powershell
$runtime = Get-Content -LiteralPath 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-dataset-version-20261005\runtime.json' -Raw | ConvertFrom-Json
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
$env:PYTHONIOENCODING = 'utf-8'
& $runtime.Python 'C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\run_step.py' --timeout 120 --cwd $runtime.Repository --name verify-mumie-symbol-preparation -- $runtime.Python -m game_predictor_worker.vision_lab.symbol_preparation verify --bundle 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-preparation-20261005\7fb60ce3edc52081d5f9cf016083a8cd6b048766db30d8df8b008fca0dccb1c8'
```

Verify sprawdza historyczny niezmienny pakiet. Aktualne decyzje ponownie
sprawdza prepare z tymi samymi snapshot/annotations/symbols/dataset-version;
zmiana etykiet tworzy inny pakiet, nie nadpisuje poprzedniego.
