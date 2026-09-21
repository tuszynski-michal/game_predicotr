---
title: Semi-automatic and automatic representative selection v7 execution plan
status: accepted
last_updated: 2026-09-20
---

# Plan wykonawczy: selekcja reprezentantów v7

## Cel i granice

V7 zastępuje sekcję nowych uruchomień półautomatu, zachowując odczyt, wznowienie i historyczne widoki v1–v6. Wybiera niezmieniony bajtowo JPEG strony 3×3 jako `seq_<mniejszy>-<większy>.jpg` w sąsiednim katalogu `<źródło> cut`. Automat nie wycina, nie rekompresuje i nie przypisuje zakresu wyłącznie z sąsiedztwa.

Zakres nie obejmuje klasyfikacji symboli, treningu, importu plansz, dodatkowej usługi, Redis/Celery ani zmian użytkownika spoza taska. V1 obsługuje lokalny NTFS, odrzuca udziały, junctions i dowiązania. Praca idzie na `version-0.10`, bez worktree.

## Kontrakt produktu

- Formularz zawiera katalog źródłowy, domyślny tryb `semi_automatic`, domyślny kierunek `ascending`, pierwszy/ostatni zakres, liczbę grup i styl ramki. `10` normalizuje się do `10–18`; kierunek opisuje kolejność stron w nagraniu, nie cyfry w stronie ani nazwę pliku.
- Style to `top_and_sides`, `full_frame`, `irregular_or_none`; opisują dekorację, nigdy utratę symboli. Automat obsługuje pełne 3×3, a końcowa rzeczywiście niepełna strona 1–8 ma ręczny workflow z potwierdzeniem numeracji.
- Mocny dowód to pięć wiarygodnych etykiet, jednoznaczna geometria i brak konfliktu. Dowód 3+3 wymaga dwóch własnych hipotez z jednego wystąpienia, różnych klastrów wizualnych i bez innego potwierdzonego zakresu między nimi. Ponownie zakodowana kopia nie jest drugim dowodem. Nieczytelna etykieta nie jest konfliktem, wiarygodna sprzeczna blokuje automat.
- Pełna `1–9` ucięta z lewej/prawej, z pięcioma zgodnymi etykietami, pozostaje `seq_1-9.jpg` i dostaje warning jakości. `A-B-A` nie cofa kursora, ale późne A bierze udział w rankingu po EOF; `A-C-B` zachowuje lukę B do późniejszego dowodu. Indeks skanu, kursor sekwencji i podgląd użytkownika są osobne.
- Finalizacja i zapis następują po kompletnym zweryfikowanym manifeście. Ranking działa po bramce dowodu i porównuje utratę symboli, czytelność najgorszej planszy, widoczność, rozmycie, zasłonięcie, dekorację i środek wystąpienia. Pełny kadr z lekkim rozmyciem, ale nadal czytelny, wygrywa z ostrym kadrem tracącym symbole; pełny kadr nieczytelny przegrywa z czytelnym kadrem o niewielkim, potwierdzonym przycięciu. `unknown` nie jest brakiem utraty. Ucięcie góry/dół zawsze tworzy warning i pozwala ręcznie wybrać sąsiada.
- Pierwszy zapis wymaga braku targetu; `manual_replace` wymaga aktualnego SHA targetu; ręczny wybór bez OCR wymaga potwierdzenia i nie liczy się jako sukces OCR.

## Zapis i recovery

Target ma `decision_generation`, bieżącego właściciela i historię. Po O1/H1 → O2/H2 historyczna O1 nie wymaga H1 pod wspólną nazwą; integralność sprawdza bieżącego właściciela. Idempotency key musi zachować źródło, zakres i generację.

Worker, API i recovery pobierają wspólną blokadę katalogu. Pod nią sprawdzają lease, rewizję, generację i target przed publikacją. Ręczna decyzja superseduje starego writera. Test z barierą zatrzymuje G1 przed publikacją, zatwierdza G2 i dowodzi, że G1 nie zapisze pliku. Zewnętrzna zmiana NTFS kończy się konfliktem, nie nadpisaniem.

Journal i output operation mają stany `prepared`, `publishing`, `published`, `committed`, `cancelled`, `superseded`, `conflict`, z SHA, generacją i właścicielem. Recovery rozróżnia brak, poprawny i inny SHA temp/targetu, niepełny journal oraz awarię po publikacji przed commitem.

## Dane i odbiór

Korpus jest konfiguracją operatora, nigdy ścieżką w kodzie. Obejmuje małe/duże grupy, Treasure, zasłonięte plansze i `wybrane mumie`; mumie oceniają tylko reprezentanta. Manifest przypina katalog, scenariusz, styl, kierunek, split i oczekiwany wynik; zmiana blokuje automatyczne zapisy.

Splity `development`, `calibration`, `validation`, `holdout` są rozłączne. Odbiór wymaga 95% poprawnych zakresów możliwych do automatycznego odzyskania, 95% poprawnie zapisanych kwalifikowanych reprezentantów, zero błędnych automatycznych zapisów z liczbą przypadków oraz 100% oznaczonych ucięć góra/dół. Raportuje fałszywe warningi, manual review, czasy etapów i RAM/VRAM.

## Kalibracja geometrii etykiet

Profil `standard_3x3_numeric_labels_v1` opisuje wyłącznie cropy numerów 3×3,
nie geometrię ramek plansz ani symbole. Anotacja wskazuje środek widocznej
etykiety w obrazie po EXIF; niewidoczny slot jest `unavailable`. Dla każdej
pozycji wymagane jest pięć SHA-256 i dwie grupy ujęć. Środek jest medianą, a
residual euklidesowy w całym obrazie ma globalną bramkę nearest-rank p95 `0,04`.
Szerokości, wysokość i granice aspektu cropu wraz z oceną `contained` są częścią
profilu. Ponowne użycie przez inną grę wymaga jawnej adopcji po walidacji na jej
własnym korpusie; styl bordera nie wystarcza.

## Zadania

| Zadanie | Rezultat |
|---|---|
| T00 | Model, Paddle, korpus i artefakty; wymagany rzeczywisty batch OCR na JPEG-u. |
| T01 | Manifest korpusu, splity, generator zakresów, oba kierunki i style z Treasure. |
| T02 | Lokalizator etykiet v7, dowód 5/3+3, konflikty i boczne cięcie. |
| T03 | Wystąpienia, luki, kursory, checkpoint, EOF i restart. |
| T04 | Jakość per plansza, `unknown`, ranking i warningi. |
| T05 | Kalibracja progów oraz mierzalne metryki. |
| T06 | Addytywna migracja v7, API/OpenAPI i blokada startu przed T12. |
| T07 | Trwały skan/finalizacja, idempotentne wznowienie i manifest drift. |
| T08 | Pierwszy zapis, journal, blokada, generacje i recovery. |
| T09 | Podmiana, ręczny pierwszy zapis, no-OCR i zakres 1–8. |
| T10 | Formularz v7 i trwały podgląd sąsiadów. |
| T11 | Pomiar CPU/GPU/RAM i deterministyczna równoległość. |
| T12 | Holdout, recovery, kompatybilność i aktywacja po odbiorze. |
| T13a | Odrębny evaluator nowego holdoutu `reels_test`, bez używania go do kalibracji. |
| T13b | Pion workerowy V7: schema v4, lokalny manifest i trwały runtime bez fallbacku do legacy. |

## Audyt

Każdy task ma dokument `TASK_TEMPLATE.md`, osobny commit, audyt przed commitem i raport z niezmiennikami, scenariuszami, uruchomionymi testami oraz ryzykiem. Po każdym tasku wykonuje się review `gpt-6-astra medium`, gdy jest dostępny; znaleziska są naprawiane i ponownie testowane. Zmiana zachowania albo obniżenie progu wymaga decyzji operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T00 | `gpt-5.6-terra` | `xhigh` | Model i hardware. | `gpt-6-astra medium` |
| T01 | `gpt-5.6-terra` | `xhigh` | Kontrakt korpusu. | `gpt-6-astra medium` |
| T02 | `gpt-6-astra` | `high` | Lokalizacja i OCR. | `gpt-6-astra medium` |
| T03 | `gpt-5.6-terra` | `xhigh` | Checkpointy i restart. | `gpt-6-astra medium` |
| T04 | `gpt-6-astra` | `high` | Ranking jakości. | `gpt-6-astra medium` |
| T05 | `gpt-5.6-terra` | `xhigh` | Kalibracja. | `gpt-6-astra medium` |
| T06 | `gpt-6-astra` | `high` | Migracja i API. | `gpt-6-astra medium` |
| T07 | `gpt-6-astra` | `high` | Trwałe wznowienie. | `gpt-6-astra medium` |
| T08 | `gpt-6-astra` | `xhigh` | Recovery plików. | `gpt-6-astra medium` |
| T09 | `gpt-6-astra` | `xhigh` | Wyścigi podmian. | `gpt-6-astra medium` |
| T10 | `gpt-5.6-terra` | `xhigh` | Workflow UI. | `gpt-6-astra medium` |
| T11 | `gpt-5.6-terra` | `xhigh` | Pomiar wydajności. | `gpt-6-astra medium` |
| T12 | `gpt-6-astra` | `high` | Odbiór i aktywacja. | `gpt-6-astra medium` |
| T13a | `gpt-5.6-terra` | `xhigh` | Niezależny evaluator holdoutu. | `gpt-6-astra medium` |
| T13b | `gpt-5.6-terra` | `xhigh` | Integracja checkpointu i handlera bez aktywacji. | `gpt-6-astra medium` |
