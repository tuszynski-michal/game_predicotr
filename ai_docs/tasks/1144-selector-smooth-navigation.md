# TASK-1144 — Odbiór i wydanie Selektora

## Status

in_progress

## Goal

Zrealizować P3 zaakceptowanego planu.

## Relevant docs

- ai_docs/delivery/SELECTOR_SMOOTH_NAVIGATION_20261103.md
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Recommended execution

gpt-6.1-sol / medium. Bez dodatkowego audytu według zaakceptowanego planu.

## Acceptance criteria

- Kryteria P3 planu, testy zmienionego pionu, lint i typecheck.

## Outcome

W toku. Źródło odbioru operatora: 42420 zdjęć / 4487051647 B. Źródło tylko do odczytu; nowy projekt i wynik w izolowanym katalogu. Znany pomiar dużej partii ma limit 240 s po uprzedzeniu operatora. Istniejący projekt z blokadą nie jest otwierany ani zmieniany.


### Przebieg weryfikacji

- Baseline małej partii 1.0.4: warm p95 24,4 ms.
- Pierwsze pełne próbki nowego kodu na 42420 JPEG: 150 warm, p95 25,2 ms, maksimum 25,6 ms, zero pustych klatek w 165 zapisanych przejściach. RSS wszystkich procesów Electron w punktach: 819,3 / 808,1 / 760,0 / 780,7 MiB; nie jest to sam cache bitmap.
- Harness dużej partii początkowo miał błędną odpowiedź dialogu, potem zbędne ponowne skany i ukryty limit helpera 110 s. Nieudane próby zachowano w artifacts/selector-smoke-diagnostics. Wyniki próbek nie oznaczają PASS całego uruchomienia z timeoutem.
- Limit dużego pomiaru 240 s: jawny boundedSmokeStep 220 s oraz zewnętrzny timeout 240 s, bez zmiany domyślnych limitów istniejących smoke.
- W odbiorze dodano overlay ładowania, by sam komunikat nie przesuwał obrazu. Smoke porównuje bounding box JPEG przed i podczas decode barrier.
- Dwie pełniejsze grupy persistence przekroczyły 120 s, bez wykazanego błędu asercji. Dalsza weryfikacja w mniejszych grupach.

- Mniejsze grupy compact persistence: 51/51 i 32/32 PASS, w tym rzeczywiste awarie procesu i recovery.
- Pełny porównawczy odbiór 1.0.4 na 42420 JPEG: 150 warm, p95 38,9 ms, maksimum 45,6 ms; 108 pustych klatek w 165 zapisanych przejściach. Zakończenie testu PASS. Pamięć wszystkich procesów w punktach 789,8 / 944,1 / 1351,6 / 1313,1 MiB. Jest to obserwacja konkretnej serii, nie limit RAM.

- Smoke pierwszego ZIP wykrył przesunięcie y o 149,45 px: display:contents hosta ignorowało grid-area i obraz trafiał do kolejnego wiersza. Zmieniono host na display:block; test bounding box pozostaje bez osłabienia. Pierwszy kandydat z kodu 40f43052 nie jest paczką do przekazania.
