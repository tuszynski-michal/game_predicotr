# TASK-1144 — Odbiór i wydanie Selektora

## Status

`done`

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

- [x] Finalny ZIP ma sprawdzone SHA-256, ASAR i metadane czystego kodu aplikacji.
- [x] Regresje projektu, recovery, IPC, skrótów, zoom/scroll/fullscreen, zgodność 1.0.4–1.0.5 oraz lint/typecheck PASS.
- [x] Finalna paczka spełnia p95 warm <=50 ms i zero pustych klatek na 42420 zdjęciach.
- [x] Raport, Outcome i zamknięcie przez task-close; merge/push poza zakresem.

## Outcome

Commit: v1.7.539 (hash dopisuje kolejny commit).

### Changed

Wydanie Selektor 1.0.5 z ciągłym podglądem, prefetch według skoku i lekkimi aktualizacjami nawigacji. Poprawiono overlay i potwierdzono ścisłym testem pozycję JPEG. Dodano ograniczony harness dużej istniejącej kolekcji oraz test zgodności 1.0.4–1.0.5. Kod artefaktu: v1.7.538 / 1f1131c15c70c6c040db3e2a69d6d9927044a673, czysty build.

### Verification results

Finalny ZIP: fluency, workflow, measurement, shortcuts, full offline i rzeczywiste 1.0.4 do 1.0.5 PASS. Na 42420 zdjęciach: 150 warm, p95 25,4 ms, max 54,9 ms; zero pustych klatek w 165 próbkach. Baseline 1.0.4: p95 38,9 ms, 108 pustych klatek. 10/10 zapisów i SHA zachowane po nowym procesie. Zestawy testów 46/46, 51/51, 32/32 i 110/110 PASS; wcześniejszy pion project/intents/workspace 78/78 PASS (zestawy pokrywają się). Format/lint/typecheck oraz docs:check i code-map:check PASS.

### Not completed

Bez merge/push, wdrożenia do uruchomionej aplikacji operatora, fizycznego rebootu i odbioru na innym komputerze. Duży pomiar używa nowego izolowanego projektu; istniejący projekt operatora z blokadą nie był otwierany. Zapis manifestu nadal O(D). Audyt nie jest wymagany przez zaakceptowany plan.

### Documentation updates

Raport quality/SELECTOR_SMOOTH_1_0_5_20261103.md zawiera dokładne dane, SHA, nieudane próby i ograniczenia. Zaktualizowane wymagania, architektura, mapa kodu, plan i katalog dokumentów. Taski zamykane przez task-close.

### Recommended next task

Odbiór operatora z ZIP 1.0.5; scalenie dopiero po akceptacji wyniku i wyraźnej zgodzie.

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
