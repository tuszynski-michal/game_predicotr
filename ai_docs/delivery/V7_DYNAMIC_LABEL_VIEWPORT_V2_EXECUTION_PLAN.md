---
title: V7 dynamiczny viewport etykiet V2
status: accepted
last_updated: 2026-09-21
---

# V7 dynamiczny viewport etykiet V2

## Cel

Usunąć zależność rozpoznawania numerów V7 od stałych współrzędnych całego JPEG-a. Nowa rodzina `standard_3x3_numeric_labels_v2` ma w każdym obrazie najpierw ustalić lokalną siatkę dziewięciu etykiet, a dopiero potem przeliczyć na jej podstawie cropy OCR. Dzięki temu przesunięty, przeskalowany lub lekko sfotografowany pod kątem kadr nie jest mieszany z błędną geometrią V1.

To jest wspólny, wielokrotnie używalny silnik **etykiet liczbowych 3 × 3**, ale nie zastępuje planu `GLOBAL_GEOMETRY_LIBRARY_EXECUTION_PLAN.md`: nie uczy podziału komórek plansz, nie przekazuje symboli ani payoutów między grami i nie aktywuje V7.

## Ustalenia produktu

- `standard_3x3_numeric_labels_v1` oraz wszystkie profile V1 są niezmienne i nadal odtwarzalne.
- V2 bierze pod uwagę wyłącznie lokalne dowody obrazu: składniki tekstu i regularność siatki. Nie używa oczekiwanego zakresu, kolejności zdjęć, numerów symboli ani koloru ramki.
- Dla V2 główną kalibracją są pełne kadry `small_777`; kadr częściowo zasłonięty jest materiałem odpornościowym, nie domyślnym źródłem profilu.
- Brak jednoznacznej lokalnej siatki daje brak cropów i brak automatycznego dowodu, nigdy fallback do V1 ani zgadywanie pozycji.
- Nadal obowiązują 5 różnych SHA, 2 grupy ujęć, `contained` i p95 `<= 0,04`. Residual V2 jest liczony w układzie lokalnej siatki, nie całego zdjęcia.

## Kolejność

### TASK-0606 — silnik V2 i kalibracja

1. Wprowadzić wersjonowany kontrakt lokalizatora z rodzinami V1 i V2, zachowując istniejącą serializację i fingerprint V1.
2. Dla każdej anotowanej strony V2 dopasować transformację lokalnej siatki 3 × 3 do punktów operatora. Wymagać co najmniej pięciu pełnych punktów, dwóch wierszy i dwóch kolumn; odrzucać degenerację i zbyt duży residual.
3. Implementować image-only detector kandydatów tekstu w obu polaryzacjach kontrastu i deterministyczne dopasowanie regularnej siatki 3 × 3. Przeliczyć cropy wyłącznie z wykrytej transformacji.
4. Podłączyć V2 do profilowego obserwatora, bez zmiany protokołu proofu, trackera, writera, gate’u ani historii V1.
5. Testy syntetyczne muszą objąć translację, skalę, perspektywę, dwa kontrasty, wieloznaczność i brak siatki. Test z prawdziwymi 777 ma wykazać co najmniej samą lokalizację lub jawny reason code.

### TASK-0607 — responsywność i ergonomia kalibracji

Ten task zawiera wszystkie komentarze użytkownika i zacznie się po 0606:

1. Marker kliknięcia ma pojawić się po trwałym dopisaniu do kolejki lokalnej, zanim serwer potwierdzi serię; kolejka HTTP pozostaje sekwencyjna.
2. Wybrane pole, ocena cropa i checkbox „numer zasłonięty / nieczytelny” będą bezpośrednio nad obrazem. Status gotowości zostanie przeniesiony poza tę ścieżkę pracy.
3. Grupa ujęć będzie wybierana ze stałej listy `A`, `B`, `C`; nie będzie wolnego tekstu ani literówek.
4. Domyślne tworzenie sesji wybierze pełne `small_777`; trudne kadry będą odrębnym, jawnym materiałem testowym.
5. Assety zostaną pobierane z ograniczonym prefetch/cache dla bieżącego i sąsiednich źródeł bez zapisu obrazów w IndexedDB. Kontrola checksumy i blokada drifu pozostają po stronie serwera.
6. Powstanie benchmark czasu pełnego przepływu dla 100/300/500 rzeczywistych źródeł. Gdy korpus nie ma żądanej liczby niezależnych zdjęć, raport poda `not_evaluable`, bez powielania plików.

## Kryteria odbioru

- Profil V2 może skalibrować się na pełnych 777 bez mieszania jego współrzędnych z przesuniętym kadrem; V1 pozostaje bajtowo i logicznie zgodne.
- Kadr z przesuniętą, ale wyraźną lokalną siatką dostaje te same indeksy 0–8 co kadr podstawowy; brak lub konkurencja siatek nie tworzy proofu.
- Każda zmiana panelu 0607 utrzymuje trwałą kolejkę po odświeżeniu i nie zapisuje bitmap ani ścieżek w IndexedDB.
- Żadna część planu nie odblokowuje V7, nie zapisuje JPEG-ów `cut` ani nie rozszerza danych gry o symbole/payouty.

## Audyt każdego taska

Przed commitem wykonawca porównuje diff z taskiem, uruchamia podane testy, Ruff/lint/typecheck i dokumentuje wynik oraz ograniczenia. Astra Medium przegląda finalny diff; uwagi niekrytyczne są naprawiane i audyt jest powtarzany. Krytyczny błąd zatrzymuje wyłącznie bieżący task.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0606 | gpt-5.6-terra | very high | Wersjonowany kontrakt geometrii, lokalizacja obrazu i regresje V1 wymagają dokładnej implementacji oraz testów. | gpt-6-astra, medium |
| TASK-0607 | gpt-5.6-terra | very high | Trwała kolejka, cache assetów i ergonomia UI wymagają spójnego pionu Admin/API oraz testów restartu. | gpt-6-astra, medium |