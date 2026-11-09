---
title: TASK-1173 — HTML i końcowy odbiór pełnych wycinków
status: done
last_updated: 2026-11-09
---

# TASK-1173 — HTML i końcowy odbiór pełnych wycinków

## Status

`done`

## Goal

Dowodowy raport wizualny i odbiór całego pionu.

## Context

Operator zaakceptował cały plan i koszt 6–10 h; audyty tylko terminalowe.
Zatwierdzenie kosztu nie obejmuje operatorowego treningu, wdrożenia ani merge.

## Dependencies / entry conditions

TASK-1172 zamknięty. Przed kodem ponownie odczytać przypisaną sekcję zaakceptowanego planu.

## Recommended execution

gpt-6.1-sol/high. Uzasadnienie: Dowodowy raport wizualny i odbiór całego pionu. Nierozwiązane P0/P1 blokują commit;
nie zmieniać modelu niejawnie. Review Claude Code claude-opus-5-5/high.

## Relevant docs

- `ai_docs/delivery/GRID_SYMBOL_CROP_PREVIEW_PLAN_20261109.md` — T4 i kryteria wspólne.
- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html`.
- D-590/D-591/D-592 w tym samym pliku, przez wyszukanie odpowiednich sekcji.
- D-594/D-595/D-596/D-597 w tym samym pliku (przez indeks i konkretne sekcje).
- `ai_docs/quality/TASK-1172_VERIFICATION.md` i `TASK-1172_FIXES_R1.md` —
  ostateczny zakres pinów oraz granice testów; wynik audytu sprawdzić po zamknięciu T3.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Sekcja T4 planu i niezbędne testy regresji. Oryginał/siatka/content/input NN/15 rastrów obecnych i porównywanych; porażki jawne; brak GT nie udaje jakości; PostgreSQL/Admin/lint/typy/build/docs/map i cold read.

## Out of scope

Aktywacja modelu/marginesu, operatorowy GPU/trening/import691, mutacje etykiet,
restarty usług, migracja operatora, merge/push oraz klasyfikator nowej architektury.

## Follow-up z audytu T1 (zaakceptowane P2)

- P2-7: przy wyłączonej warstwie obrysów kliknięcia content nie mogą niewidocznie
  zmieniać quadu. Zablokować rysowanie i pokazać krótki komunikat; test interakcji.
- P2-8: niechronione TRAIN bez zapisanych nodes nadal pokazuje aktualną adnotację
  w HTML z jawnym brakiem siatki/cropu (lub przynajmniej jawne pominięcia/powody).
  Preferowane: karta z obrazem/adnotacją, bez sfabrykowanej siatki. Protected nadal
  odrzucane przed odczytem pikseli. Test rzeczywistego eksportu.
- T1 P2-4 pozostaje jawnym ograniczeniem ochrony zapisanych sesji (bez rozszerzenia).
- Odbiór ma wskazać ograniczenia T3: per-board resolver bez pomiaru/cache,
  nieukończony długi workflow treningowy (inne objawy T3/main, przyczyna
  nieustalona) oraz konserwatywny wyjątek D-597 wymagający pełnej widoczności.
  Nie powtarzać zaliczonych kosztownych prób ani nie przedstawiać ich jako
  pełnego PASS modelu. Nowe PG JSONB/advance ma osobny dowód T3.
- Odbiór trwałości receipt: ograniczony `checkout-index` jednego raportu z
  core.autocrlf=true odtworzył CRLF i inny SHA niż receipt. Dodać celowaną regułę
  LF dla checksum-bound raportów `TASK-*_AUDIT_*.md` w `.gitattributes` i test
  nowego procesu/checkoutu; nie przepisywać treści ani hashy raportów audytora.
  Dowód: artifacts/t1171-receipt-checkout-probe.json. To domknięcie przenośności
  dowodu odbioru na Windows, bez zmian procedury/modelu audytora.

## Acceptance criteria

- [x] Każdy punkt T4 planu ma implementację lub jawny warunek zależny od danych.
- [x] Oryginał/siatka/content/input NN/15 rastrów obecnych i porównywanych; porażki jawne; brak GT nie udaje jakości; PostgreSQL/Admin/lint/typy/build/docs/map i cold read.
- [x] Istniejące historyczne kontrakty i ręczne korekty są zachowane.
- [x] Właściwe testy, lint, typy i docs/map; niezależny Opus audit i receipt.

## Technical notes

Audyt obejmuje kod, testy, dokumentację i tekstowe wyniki kontroli. Zdjęcia,
operatorski HTML/public JSON, baza operatora, `.tmp` i sekrety są poza pakietem
oraz odczytem audytora. Odtworzenie obrazów potwierdzają lokalne testy i receipt;
nie przekazujemy pikseli ani danych operatora do Anthropic.

Źródłem prawdy są rewizje zapisanych adnotacji, frozen snapshot i pinned render.
Nie zamieniać pudełka podglądu w GT. Nie wyświetlać podpowiedzi w blind; chronić
całe źródła użyte w pomiarze. Brak danych jest jawnym stanem, nie PASS.
Artykuły pomocnicze są w root artifacts/full-symbol-training-20261109; nie nadpisywać
ich ani bazy. Odczyt operatorski tylko read-only; wyniki do artifacts tego worktree.

## Expected files

Odczytano bounded projekt artifacts/TASK-1173_READONLY_HANDOFF.md. Faktyczny zakres:

- `services/worker/src/game_predictor_worker/images/comparison_production_crop_report.py`
  i `services/worker/tests/test_comparison_production_crop_report.py` (nowe).
- `scripts/render_grid_correction_comparison.py`, nowy
  `scripts/templates/production-crop-comparison.html` oraz
  `scripts/tests/verify_production_crop_report.mjs`.
- `scripts/export_grid_content_preview.py` i
  `services/api/tests/test_grid_content_preview_export.py` (missing nodes).
- `apps/admin/src/features/model-quality/grid-content-canvas.tsx` i
  `apps/admin/test-interactions/grid-content-reference.test.mjs` (hidden edit).
- `.gitattributes`, nowy `scripts/tests/test_audit_report_checkout.py`.
- Wymagania/architektura VISION_LAB, `TASK-1173_VERIFICATION.md` i
  `GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md`, `TASK-1173_FIXES_R1.md`.

Bez zmian API ani frozen kodu T2/T3. Root prowadzi process docs/map/audit/close.

## Test cases

Kryteria planu: ghost quad, wspólne granice/perspektywa, J/10/obramowania/ciemne
symbole, sąsiad, brak pikseli/rzędu, blind isolation, CAS/currentness i restart/replay.
Testy specyficzne dla taska doprecyzować przed implementacją w raporcie weryfikacji.

## Verification

Z katalogu worktree: właściwe testy pytest przez D:/game_predicotr/.venv/Scripts/python.exe
z PYTHONPATH własnego services/api/src i services/worker/src; testy Admin
`npm run test:geometry --workspace @game-predictor/admin`, scoped lint/typecheck,
`npm run docs:check`, `npm run code-map:check`. Każda komenda ma timeout.
Szerszy build dopiero po testach pionu. Audyt według CROSS_AUDIT do 1800 s.

## Risks / open questions

Brak GT i rodowodu może blokować wynik jakości, nie implementację narzędzia.
Nie deklarować poprawy wytrenowanego modelu bez rzeczywistego eksperymentu.

## Outcome

Commit: v1.7.585 / `ae323963249c73cf7b24f8e53a5ab8883b0dac3f`.

Implementacja odebrana z Opus R2 PASS; wyniki i ograniczenia końcowe poniżej.
Jawny `--crop-report` istniejącego CLI tworzy immutable samodzielny HTML z sealed
reportu T2, z osobnym adapterem/template i bez zmiany historycznego `--directory`.
TRAIN+visualExportAllowed jest sprawdzane przed pikselem/public JSON; internal A
nie trafia do strony. Wspólne24punkty, approved outline albo jawny brak, źródło,
rzeczywiste wejścia NN i15par8%/0% dla human/actual model są oddzielne. Found i
usable indices nie są łączone po nazwie. Unknown/brakujące/ambiguous pozostają
bez pozytywnej oceny. Instrukcja ordinary/HTML wyraźnie obejmuje ozdobną ramkę
bez tła/sąsiada i niezależne rozmiary J/10; blind pozostaje bez nowych hintów.

T1 P2-7/8 naprawione: wyłączona warstwa blokuje niewidoczne rysowanie, a TRAIN
bez nodes zachowuje ordinary obraz/adnotację z komunikatem. Reguła LF i actual
fresh-process checkout gwarantują raw SHA raportu zgodny z receipt na Windows;
treści/hashów audytów nie zmieniono.

Finalny raport po R1: `D:/game_predicotr/artifacts/grid-symbol-crop-preview-20261109-t4-v4/index.html`.
1TRAIN/9plansz,540cropów+10actual NN inputs+oryginał=551PNG. Cold CLI exit0:
552pliki źródłowe i553wyjściowe mają identyczne SHA/mtime, wszystkie PNG
sprawdzone file/pixel SHA/wymiary. Receipt artifacts/TASK-1173-html-v4-receipt.json;
v3 i jego wcześniejszy receipt zachowane.
Brak approved content/class GT oznacza brak operatorowego dowodu poprawy modelu.

Testy: nowy pion21PASS, końcowy Worker13PASS +wąski malformed-quad1PASS,
ordinary export8PASS, legacy Worker39PASS iCLI3PASS (po testowym TEMP/TMP),
Admin content28PASS, actual template DOM PASS, disposable PG reader1PASS z
coldRead/readOnly/15manifest/alias i cleanup0. Standard TypeScript, scoped ESLint,
Ruff/format6 i mypy3 PASS. Świeża kolekcja Worker bez PYTHONPATH: 3636 testów
w23,18s (osobny log), nie wykonanie całej suity. Pełny Admin geometry427PASS/11FAIL:
10udowodnionych baseline supergames +przejściowy picker; picker osobno2PASS.
Końcowy standardowy Admin build root PASS exitCode0/29,38s, trwały JSON/log
artifacts/t1173-root-admin-build.*. Pierwszy helper nie zapisał child code przed
błędem drukowania Unicode — jawnie opisany, nie uznany samodzielnie za PASS.

Ręcznego screenshot/browser PASS nie ma (CUA blokuje file://); root obejrzał
jedynie kilka zweryfikowanych PNG. Odbiór strony pozostaje użytkownikowi.
Ograniczenia T1 ochrony zapisanych sesji, T2 LAB/aktorów/assignment/measurement
i T3 per-board cost/fully-visible/PG fixture/v2 selection zapisano w końcowym
raporcie odbioru. Długi workflow1200step T3 bez PASS, odmienne objawy main,
przyczyna nieustalona; nie powtarzano go ani nie udawano wspólnego Torch baseline.

Szczegóły i punktowe DoD: ai_docs/quality/TASK-1173_VERIFICATION.md oraz
GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md. Root wykona mapy/docs gate,
niezależny audyt/receipt i close przed commitem. Bez operatorowych DB writes,
etykiet, inferencji/GPU/treningu, defaultu/marginesu/importu691, usług,
migracji/deploy/merge/push; bez stage/commit przez wykonawcę.

Root po freeze:16 wykonawczych SHA i SHA strony/receipt sprawdzone przed
edycją metadanych. Mapa zregenerowana; docs:check i code-map:check PASS
(startup43612B). Oczekuje niezależnego audytu, bez deklaracji PASS.

Opus R1: REVISE0P0/2P1. Dokładny report/receipt zachowane jako _R1;
trwa jedna dozwolona runda poprawek P1-1/P1-2 i rozliczenia P2.
Bez commita ani zamknięcia.

Jedna runda poprawek wykonana; mapa ID→zmiana/test w TASK-1173_FIXES_R1.md.
P1-1: rzeczywiste geometryMetrics.matches, jawny incorrect match i false/duplicate
detekcje względem zapisanych punktów; label ordinal nie positionIndex. Actual
evaluator/DOM test pełny i partial pos7/label0, None pozostaje brakiem oceny.
P1-2: wykonany approved DOM dla preserved/clipped/wrongCell/tie/foreignFullSymbol.
P2-1/2/3: fragmenty przerywane z legendą i contentState, znana klasa człowieka
przy braku classifier. P2-4: tylko agregat pominiętych TRAIN. P2-6: hidden
ordinary delete/numeric disabled, default blind bez zmiany. P2-7: dokładnie
padding0.08/0.0 przed etykietami, poza tym lokalne unavailable.

Końcowe testy R1: Worker16PASS/35,92s, Canvas/blind28PASS/4,01s, Ruff/format2,
mypy1, ESLint i standard TS PASS; kolekcja3639/19,20s bez PYTHONPATH,
nie wykonanie całej suity.
Build root po Canvas PASS exitCode0/28,64s, BUILD_ID HL5cDtyH9xkxRaRsCc0zN,
trwały artifacts/t1173-r1-root-admin-build.json/log. V4 DOM/cold replay/551PNG
PASS i niezmienność552źródeł/553wyjść. PG/pełnego geometry/training nie powtarzano.

P2-5 przyjęte jawnie: file-only HTML chroni na moment capture i nie odczytuje
późniejszych blind sessions. Przed kolejną galerią przygotuj świeży capture;
istniejące wyeksportowane pliki nie są automatycznie wycofywane. Bez nowego
SQL/API/inferencji. Ograniczenia danych, baseline i ręcznego odbioru pozostają.
Gotowe do focused R2 root; bez audytu/stage/commit/close wykonawcy.

Root po rundzie poprawek:17 frozen SHA i SHA v4/receipt sprawdzone;
mapa zregenerowana, docs:check i code-map:check PASS(startup43612B).
Focused R2 jest następny; bez deklaracji niezależnego PASS.

## Końcowy odbiór root — 2026-11-09

Focused R2 przez terminal: **PASS, 0 P0 / 0 P1**, rzeczywisty model główny
`claude-opus-5-5`, High żądane (bez niezależnego dowodu ustawienia effort).
Czas243,62s; receipt potwierdzony po rzeczywistym zakończeniu procesu.
Pakiet SHA `293ed2a525aa0176ef022b1890705afd7e4c352736518203abccb1c68b93f45a`;
raport SHA `de0b237218f0719c5c3e43cd76b2daabee88c7f6496b8479e87ad051dafa2186`.
Raport i receipt: `TASK-1173_AUDIT_claude-opus-5-5.md` i plik `.receipt.json`;
oryginalna runda1 zachowana w plikach `_R1`. Audyt był statyczny, nie zastępuje
wykonanych testów ani operatorowego pomiaru jakości modelu.

Przyjęte resztkowe P2 rundy2: P2-8 — niedostępny wycinek może zgubić opis
istniejącej oceny `missing` i wyświetlić zbyt ogólny brak odniesienia; porażka
pozostaje widoczna jako niedostępność, bez pozytywnej oceny. P2-9 — stan
`borderline` ma surową angielską etykietę zamiast polskiego opisu. Obie uwagi
dotyczą opisów zatwierdzonego content GT, którego pilot nie ma. Nie wykonano
kolejnej rundy zmian po zaakceptowanym focused review; nie osłabiono kontroli.

T1–T4 mają osobne Opus PASS. Wszystkie powyższe ograniczenia testów, danych,
ochrony capture i ręcznego odbioru pozostają aktualne. Gotowość narzędzia nie
jest rekomendacją zmiany marginesu ani dowodem poprawy modelu. Bez operatorowych
mutacji, treningu, wdrożenia i merge/push. Końcowe docs/map i task-close są
kontrolą metadanych po audycie, bez zmiany audytowanego kodu.
