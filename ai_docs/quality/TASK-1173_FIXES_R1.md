# TASK-1173 — jedna runda poprawek R1

2026-11-09. Podstawa: dokładny `TASK-1173_AUDIT_claude-opus-5-5_R1.md`,
REVISE: 0P0/2P1. To raport wykonawcy przed focused R2, nie własny audyt.

| ID | Zmiana | Dowód wykonania |
|---|---|---|
| P1-1 | Ograniczona projekcja istniejącego geometryMetrics i matches.correct/valid/iou/nme/max_error. Label jest ordinalem pierwotnego member.targets, niezależnym od positionIndex; zgodność łączy także prediction z obserwacją wariantu. Nie używamy content-dependent usable. Widoczny komunikat dopasowanej błędnej geometrii i całozdjęciowe false_boards/duplicates/complete_correct_strict; None nie staje się0/False. To zgodność z zapisaną geometrią, nie niezależna jakość. | `test_real_geometry_metrics_and_label_ordinal_are_visible_in_dom[False/True]`: rzeczywisty evaluate_photo, przesunięte nodes, z tych samych nodes produkcyjne rastry, dodatkowa fałszywa detekcja. Wykonany template: pełne zdjęcie false1 oraz partial position7/label0 i brak oceny whole-photo. |
| P1-2 | Approved fixture zawiera base/candidate finalContentState i wrongCell/tie/foreignFullSymbol. | Wykonany DOM sprawdza zachowaną/przyciętą grafikę, obce pole, niejednoznaczność i obcy pełny symbol. Test pozytywny nie ogranicza się do quadu i klasy. |
| P2-1 | Obrysy mają data-state; occluded/out_of_frame/unknown są przerywane, legenda wyjaśnia fragmenty. | Actual approved DOM, data-state i computed stroke-dasharray7 4 dla trzech stanów; toggle obrysów. |
| P2-2 | Znana klasa człowieka pozostaje widoczna przy niedostępnym klasyfikatorze; brak wyniku nie udaje braku klasy. | Actual DOM pokazuje klasę10 i brak dostępnego wyniku klasyfikatora. |
| P2-3 | Renderowany contentState dla fragmentów i unknown; jawne „pełności grafiki nie oceniamy”. | Actual approved DOM dla occluded/out_of_frame, bez sfabrykowanego assessment. |
| P2-4 | Agregat omittedTrainSources oraz statystyka strony, bez identyfikatorów lub powodów chronionych zdjęć. TRAIN false/missing flag lub unavailable pozostaje poza pikselami/public projection. | Test gate:3pominięte TRAIN, brak markerów i brak forbidden pixel reads. A/B/REG nadal poza JSON/HTML. |
| P2-5 | Jawna granica file-only: ochrona obowiązuje na moment capture; późniejsze sesje blind nie są odczytywane. Strona/dokumentacja zalecają świeży capture przed kolejną galerią. | Template, VISION_LAB oraz verification/acceptance/Outcome. Nie dodano SQL/API/inferencji. |
| P2-6 | Hidden ordinary outlines blokują także delete, wybór rogu i numeryczne XY, z guardami handlerów. Default blind bez zmiany. | Canvas ordinary/blind28PASS, disabled/reenable i brak mutation po delete; nowy build root exit0. |
| P2-7 | Jawne wymaganie paddingFraction0.08/0.0 przed stałymi etykietami, poza tym lokalne unavailable. | Test mutuje zgodnie konfigurację pary i spec na0.04 z przeliczonym SHA: wszystkie błędne base unavailable, candidate nadal dostępne. |

## Wyniki po poprawkach

- Nowy Worker moduł: **16 PASS/35,92s**, `artifacts/t1173-r1-worker-final.log`.
  Testy uruchamiają rzeczywisty template w JSDOM, nie symulację funkcji HTML.
  Początkowa próba14PASS/2FAIL dotyczyła brakującego expected SHA fixture;
  partial potrzebował też prawidłowego sequence8/range1..9. Poprawiono fixture,
  nie kontrakt. Wąskie próby full/partial, następnie cały moduł PASS.
- Relevant Canvas/blind: **28 PASS/4,01s**, `t1173-r1-admin-content.log`.
  Scoped ESLint, standardowy Admin TypeScript oraz mypy adaptera1 PASS;
  Ruff/format obu Pythonów PASS (`t1173-r1-*`).
- Finalny standardowy build root: **exitCode0**, timedOutfalse,28,64s,
  BUILD_ID `HL5cDtyH9xkxRaRsCc0zN`; receipt
  `artifacts/t1173-r1-root-admin-build.json` zapisany przed drukowaniem,
  pełny `.log` obok. Nie uruchamiano usług.
- Samodzielna kolekcja Worker bez PYTHONPATH: **3639 testów/19,20s**,
  `artifacts/t1173-r1-collection.log`; kolekcja, nie wykonanie całej suity.
- V4 rzeczywisty DOM PASS, cold CLI exit0, wszystkie551 PNG
  file/pixel SHA/wymiary PASS;552wejścia i553wyjścia identyczne SHA/mtime.
  `artifacts/TASK-1173-html-v4-receipt.json`, `t1173-r1-v4-assets.log`.

Finalny immutable raport:
`D:/game_predicotr/artifacts/grid-symbol-crop-preview-20261109-t4-v4/index.html`.
SHA `eaff2369972d84e000a93c522b9d118fb13cdf7527ab78f84f88b9f5ed4bf6f0`.
V3 i wcześniejsze raporty zachowano. Brak approved operatorowego content/class
GT i ręcznego browser PASS pozostaje jawny. PNG/DOM nie dowodzą jakości modelu.

Nie powtarzano PostgreSQL (zmiany adapter/UI bez SQL), pełnej geometrii z
udowodnionymi10baseline ani długiego treningowego workflow bez PASS. Legacy
CLI nie zmienił się w R1. Nie zmieniono API/schematu, operatorowych danych,
domyślnego modelu/marginesu, usług ani historii audytów. Nie stage'owano,
nie commitowano, nie wykonywano audytu. Root prowadzi map/docs i focused R2.
