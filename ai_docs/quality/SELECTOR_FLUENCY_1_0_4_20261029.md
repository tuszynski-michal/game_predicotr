# Selektor Windows 1.0.4 — płynność i niezawodny wybór

TASK-1107, zaakceptowany plan TASK-1104–1107. Audyty Claude pominięte jawną
decyzją operatora 2026-10-29; brak niezależnego werdyktu PASS. Bez usług,
zmian oryginałów i ochrony, migracji, merge lub push.

## Status odbioru

Task jest in_progress. Wydanie i odbiór finalnych bajtów ZIP pozostają pending
do wykonania opisanych poniżej smoke. Fizyczny restart Windows i komputer
odbiorcy pozostają pending również po lokalnych kontrolach.

## Zmiana

TASK-1104: podgląd może wyprzedzać zapis, F/Enter przypina cel i zakres,
oczekiwanie jest jawne, retry zachowuje operationId, close rozlicza kolejkę.
TASK-1105: execute zwraca mały update bez inventory, bootstrap nadal pełny.
TASK-1106: jeden zdekodowany obiekt DOM, serial prefetch, okno ±3 i 128 MiB
estymaty bitmap. TASK-1107: bounded agregaty i odbiorczy pomiar, flagi
`smoke-release --fluency` i `--measurement`, wydanie 1.0.4.

Diagnostyka nie zapisuje na każdy klawisz. Stałe trzy metryki, ostatnie
256 próbek na metrykę i count całej serii. Zapis przy close/openLogs,
whitelista liczb i istniejąca rotacja. Brak ID/ścieżek JPEG w produkcyjnym
logu. Błąd zapisu agregatu nie zmienia wyniku operacji.

## Maszyna i metoda

Windows x64 10.0.26300, Electron 42.11.12, AMD Ryzen 7 170 with Radeon
Graphics, 16 logicznych CPU, 33 630 056 448 B RAM. Źródło, projekt i wynik
są na lokalnym D:, Lexar SSD NQ790 2TB, NVMe. Defender: produkt 4.18.26100.4,
silnik 1.1.26100.4, sygnatury 1.463.22.0; real time protection enabled.
Wersje odczytano, ustawień nie zmieniano; nie uruchamiano nagrania ETL.

Partia: 12 kopii czterech istniejących JPEG z
`services/worker/tests/fixtures/range_ocr_real_v6/`, każde 720×1280,
88 366–154 191 B. Oryginały nietknięte. Cache cold oznacza pusty cache
aplikacji albo target wypartego okna ±3; nie czyszczono cache systemu.
Warm: 30 kolejnych nawigacji 1↔2 z gotowymi bitmapami. Cold paint: cztery
naprzemienne skoki 20 na przeciwne końce partii, poza cache poprzedniego celu.
10 osobnych F/Enter sprawdza zatwierdzone zakresy, SHA JPEG i manifest po
nowym procesie. To ograniczony odbiór, nie benchmark dużego korpusu.

Input–paint: capture keydown prawdziwego zdarzenia Chromium wysłanego przez
Playwright; pierwsza klatka z widocznym właściwym obrazem i kolejny rAF.
Jest to konserwatywny wskaźnik możliwości wyrenderowania, nie pomiar fotonów
monitora ani gwarancja sprzętowego compositora. Confirmation mierzy zmianę
licznika w rendererze. `nativeExecute` obejmuje walidację, write/flush i
projekcję; nie udaje izolowanego pomiaru fsync. `snapshotIPC` to rzeczywisty
round trip preload/IPC, nie sam execute. Payload zawiera acceptedImageIds,
więc rośnie z liczbą decyzji. `photo-open-ms` nie oznacza pełnego transferu.

## Wyniki

Pełny zestaw 17 plików selektora w pięciu grupach concurrency=1, każda ≤120 s:

| Grupa | Wynik | Czas |
|---|---:|---:|
| UI/foundation/workspace/cache/intents/release/output/catalog/diagnostics | 52/52 | 12,3 s |
| native-checks | 21/21 | 5,1 s |
| project/start-resume | 72/72 | 45,0 s |
| archive/compact-persistence | 97/97 | 93,4 s |
| legacy-contract/legacy-recovery/smoke-diagnostics | 64/64 | 17,0 s |

Łącznie 306/306 w pełnych grupach. Drugi dodatkowy test whitelisty agregatów,
dodany po pierwszej grupie: celowane 2/2 PASS (łącznie 307 unikalnych testów).
Ten krótki celowany runner uruchomiono omyłkowo podczas oczekiwania na grupę
persistence; pełne grupy nie nakładały się, każda miała concurrency=1.
Nie ponawiano całej grupy bez potrzeby. Lint i typecheck PASS.
Wszystkie trzy znane testy timeoutów 150/200 ms tym razem PASS bez zmian.
Ich wcześniejsze niepowodzenia na poprzednim HEAD pozostają opisane w
Outcome TASK-1105; nie wyciągamy wniosku o naprawie workera.

Pełne logi, wszystkie próbki oraz nieudane próby harnessu są w
`artifacts/selector-fluency-20261029/` i
`artifacts/selector-smoke-diagnostics/`. Wstępny pomiar miał warm p95 26,8 ms,
max 29,5 ms, 30 próbek, zero nowych żądań aktywnych cache hitów.
15 żądań sąsiada na granicy okna ±3 to odrębny prefetch, nie ponowny odczyt
aktywnych dwóch obrazów. Nie ukryto ich przez zmianę mianownika.

Pierwsze próby nowego harnessu ujawniły: niedostępny dynamic import w evaluate,
założenie o zerowej liczbie wszystkich prefetch oraz zbyt wczesny snapshot po
historii. Następnie porównanie opaque imageId między procesami zastąpiono
trwałą tożsamością relativePath i SHA. Zmiany dotyczą harnessu; kontrola
dokładnego JPEG-a i zakresu pozostała. Nie było przekroczenia celu warm p95.

## Finalny artefakt i smoke

Pierwszy kandydat z checkpointu v1.7.502/b4251886 miał poprawne SHA/asar oraz
fluency/measurement/shortcuts PASS. Workflow wykrył regresję: range/undo
zerowało readyImageId także przy niezmienionym JPEG, który nie dostaje nowego
callbacku decode. F po edycji zakresu czekało mimo widocznej bitmapy. Poprawka
zachowuje ready wyłącznie dla tego samego project/source/image i bez błędu
decode; inny cel nadal czeka. Testy range→F, undo→F i zmiany celu dodane;
zmieniony pion intents/cache/renderer/workspace 37/37 PASS, lint/typecheck
PASS. Sam harness workflow czeka teraz na widoczny licznik i koniec operacji,
zachowując dokładne asercje manifestu. Pierwszy błąd odczytu manifestu był
race harnessu, kolejne uruchomienie ujawniło powyższą rzeczywistą regresję.
Kandydat c6d665ec8bc0b834779150c1faafd644c123d2cc0eaf7e9a1815c33f8f2266b0
zachowany w `artifacts/selector-releases/1.0.4-candidate-b4251886/`.
Nie jest finalną paczką do przekazania. Nowy build/smoke pending.

Pending: checkpoint kodu, wydanie 1.0.4, SHA-256/metadata/app.asar oraz smoke
finalnego rozpakowanego ZIP: fluency, measurement, shortcuts, workflow i
rzeczywista aktualizacja z zachowanego ZIP 1.0.3. Wpis zostanie zastąpiony
rzeczywistymi wynikami przed zamknięciem TASK-1107.

## Ograniczenia i odbiór operatora

Pomiary dotyczą opisanej maszyny i małej partii. Brak prognozy na inne
JPEG-i, dyski lub antywirusy. Fizyczny restart Windows i odbiór na komputerze
zgłaszającego pending. Zachowano historyczny ZIP 1.0.3, wcześniejsze dwa
usunięcia artefaktów oraz obcy worktree poza zakresem.
