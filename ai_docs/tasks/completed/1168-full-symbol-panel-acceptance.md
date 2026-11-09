---
title: Panel pełnych symboli, porównanie HTML i odbiór
status: done
last_updated: 2026-11-09
---

# TASK-1168 — Panel pełnych symboli, porównanie HTML i odbiór

## Status

`done`

## Goal

Operator widzi gotowość danych, propozycje i ocenę rzeczywistych15wycinków,
a odbiór potwierdza zgodność całego trwałego przepływu.

## Dependencies / entry conditions

T4 zakończone: v1.7.576/a9951e94f8cb7ad1912c1888f3f47eb94cb5efea, Opus R2 PASS0P0/0P1. Wcześniejszy wyjątek pracy przy limicie poniżej jest historią rozpoczęcia T5.

T0–T4 zaimplementowane. Brak operator-labels lub audytu Opus jest widoczny,
nie udaje zaliczonego rzeczywistego treningu/oceny.

Operator 2026-11-08 ponownie zatwierdził pełne T5 z testami i audytami po
ujawnieniu pozostałych4–6h i łącznego szacunku13–15h zamiast8–12h.
Nie pytać ponownie o ten zakres/koszt. Zwykła kolejność to zamknięcie T4;
operator jawnie dopuścił kontynuację kodu przy limicie Opus. Ten wyjątek
obowiązuje teraz: T4 code/QA frozen, R2 przerwany Anthropic429 reset00:00,
a pełne T5 rusza bez zastępczego PASS i bez commita T4. Oddzielna migawka
Git T4: d0ba8e63c89e89ac4eeb8cc5b314c850ced49e06; metadane
artifacts/TASK-1167_PENDING_AUDIT_BASELINE.json. Root zatwierdza taski osobno
po rzeczywistych audytach. Pakiet R2 T4 oraz jego F snapshot pozostają bez zmian.
Rzeczywisty trening, wdrożenie i dane operatora nadal wymagają odrębnych zgód.

## Recommended execution

gpt-6.1-sol/high; dodatkowy review Claude Code claude-opus-5-5/high.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T5 i ograniczenia)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-593; nowe read-only cele/asset, izolacja trybów i realny HTML)
- ai_docs/architecture/CODE_MAP.md
- ai_docs/quality/TASK-1168_AUDIT_claude-opus-5-5_R1.md (jedna runda poprawek P0-1/P1-1/P1-2; focused R2 przed commitem)

## Scope

Pełny pion kontraktu backend/OpenAPI/SDK/wrapper/requesttest; istniejący
panel uczenia i propozycji. Gotowość treningu vsautomatu, powodyzatrzymania,
wersjawejścia, zakresgier. HTML oryginał/realNNinput/baza/kandydat/15actualcrops.
Odróżnienie szerokiego podglądu od wejścia sieci. Testy odbioru planu i
instrukcje zgodności API/worker/migracji/rollback, bez wdrożenia operatora.

## Acceptance criteria

- [x] Czytelne stany loading/empty/error i rozdział propozycja/człowiek/automat.
- [x] Braki danych i zakres dowodu nie udają jakości nowych gier.
- [x] HTML pokazuje rzeczywiste wycinki i to, co analizowała sieć.
- [x] Żadna operacja propozycji nie zatwierdza geometrii/symboli człowieka.
- [x] Testy realONNX/24vs15/rząd/wrongcell/neighbor/perspective/occlusion/bounds.
- [x] Partial/unknown/stalereport/restart/lostresponse/budget są spójne.
- [x] API/worker/PG/UI/lint/types/build/docs/map wykonane z uczciwym raportem.
- [x] Wszystkie taski mają Outcome/audyt/commit/close albo jawny blocker,
  bez merge/push/migracji/operatortraining/importu.

Nowe odczyty ordinary/selection UI i plikowy eksport15rastrów mają dokładny
kontrakt D-593 zapisany przed nowym API pionem. Lista targetów nie ujawnia
geometrii/labels, asset jest snapshot-bound i no-store, a CLI sam buduje
pinned pakiet eksportu. Nie wymagać ręcznego wpisywania UUID/SHA lub JSON
w głównym flow operatora.

Odbiór przejmuje trzy wskazane P2 po pozytywnym R2 T4, bez przepisywania
jego audytu ani commita: P2-4 bounded bundle reader w production_cell_input;
P2-5 fail-closed przy obcej bazowej detekcji przypisanej do pozycji podmienionej;
P2-6 domyślny, niezależny od env test node-identical BASE/WIDE stale stamp.
To uszczelnienie istniejącego dowodu wejścia i testów odbioru, bez zmian sieci,
progu jakości, nowego API lub treningu. Zmiany są osobną deltą T5 względem
audytowanego T4 i podlegają audytowi T5. T4P2-1 koszt inspektora pozostaje
jawnie zaakceptowanym residualem, bez pozornego cache lub benchmarku.

## Expected files

- Istniejące: `apps/admin/src/features/model-quality/grid-model-workspace.tsx`
  (`GridModelWorkspace`), `grid-correction-learning-panel.tsx`
  (`GridCorrectionLearningPanel`, `LearningReport`), state/CSS. Istniejący
  `grid-quality-measurement-panel.tsx` wyznacza miejsce wpięcia pomiaru.
- Proponowane, faktycznie montowane: `grid-content-reference-workspace.tsx`
  (`GridContentReferenceWorkspace`), mały moduł stanu/komend i canvas
  w `apps/admin/src/features/model-quality/`; dedykowane testy stanu/interakcji.
- Istniejące kontrakty pod `services/api/src/game_predictor_api/`:
  `schemas/grid_correction_learning.py`, `schemas/grid_model_evaluations.py`,
  `schemas/grid_cell_content.py` (T2), `api/grid_correction_learning.py`,
  `api/grid_quality_measurements.py`; pola i wersje po integracji T2–T4.
- Istniejące: `packages/admin-api-client/openapi/openapi.json`,
  `src/generated/{sdk,types}.gen.ts` (wyłącznie generator), `src/index.ts`
  (właściwe metody wrappera/eksporty); request testy uczenia, oceny i jakości.
  Proponowany `packages/admin-api-client/test/grid-content-reference-request.test.mjs`.
  `apps/admin/src/api/admin-api-client.ts` i odpowiednik Reviewera tylko
  konfigurują klienta; zmieniać je wyłącznie przy rzeczywistej potrzebie.
- Potwierdzone: `scripts/render_grid_correction_comparison.py` (`render`, `main`),
  `scripts/templates/grid-correction-comparison.html`,
  `scripts/tests/test_grid_correction_comparison.py`,
  `scripts/tests/test_grid_comparison_diagnostics.py`,
  `scripts/tests/verify_grid_correction_comparison.mjs`.
- Regresje: `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`,
  `grid-model-workspace.test.mjs`, `grid-quality-measurement.test.mjs`,
  `apps/admin/test/grid-correction-learning-state.test.mjs` oraz istniejące
  testy Reviewera edycji/propozycji. Mapa: `artifacts/TASK-1168_PREP.md`.

## Technical notes

### Runda poprawek po Opus R1, 2026-11-09

Rzeczywisty terminalowy Opus R1: REVISE,1P0/2P1/3P2. Raport i receipt
zachowano jako `_R1`. Jedna runda poprawek w dotychczasowym zakresie:
HTML korzysta z content-addressed korzenia `pages/{manifestSha256}.json`
oraz testu prawdziwego publish_json; targets pobiera istniejącą nazwę
logiczną źródła i sprawdza ją w PG; interakcje pokrywają empty/error/retry
oraz opóźnione odpowiedzi starego scope i błąd odczytu budżetu. Dodatkowo
ograniczyć zasięg unavailable i nie nadpisywać obcych PNG/indexu. Ścisłej
tożsamości nodes nie rozluźniać: P2-2 pozostaje jawnym ryzykiem do pomiaru
na prawdziwym zestawie. Wynik poprawki i focused R2 muszą poprzedzić commit.

Przygotowanie z 2026-11-08 jest analizą, nie rozpoczęciem T5. Implementacja
startuje po sygnale root; jawny wyjątek limitu Opus opisano w Dependencies. Sprawdzone symbole, zależności
i scenariusze są w `artifacts/TASK-1168_PREP.md`.

Obecny `BoardGeometryCorrectionEditor` nie realizuje blind2pass: wymaga
sugerowanych narożników, ładuje saved/suggested lattice i lokalny szkic,
obsługuje podpowiedzi symboli, nie ma niezależnych content15. Istniejący
pomiar próbki również pokazuje wcześniejszą geometrię. Root potwierdził
minimalny workspace etykietowania w istniejącym miejscu jakości Admina.
Aktywny tryb ślepy zastępuje zwykłe narzędzia tego przepływu, używa plain
assetu i metadanych celu T2, nigdy wcześniejszych etykiet/propozycji.
Każdy session/pass/source/position ma własny klucz i pusty canvas. Operator
wyznacza 24 węzły oraz osobno 15 quadów/visibility; przesunięcie geometrii
nie przesuwa etykiet zawartości. Nie dodawać martwego helpera zamiast UI.

Pełne T5 obejmuje również zwykły, rzeczywiście zamontowany edytor content15
(poza ślepym TRAIN/A), w tym adnotacje B/REG. Używa istniejących T2 get/write,
CAS i jawnej akceptacji człowieka, bez zmiany geometrii ani symboli. Nowy
canvas quadów/visibility może być współdzielony, ale kontrolery zwykły i ślepy
są osobne. Ślepy kontroler nie importuje zwykłych odczytów/predykcji/szkiców;
przełączenie trybu odmontowuje i czyści canvas. Wykonawca potwierdził ten zakres
w zatwierdzonych4–6h. Test obejmuje zapis/ponowny odczyt B/REG i brak przecieku
do ślepego pomiaru. Nie dodawać równoległej ścieżki backendu ani modeli typów.

Użyć `ContentSessionCreate`, `ContentSessionResponse`, `ContentBlindWrite`,
`ContentSessionAdvance`, compact `ContentSessionCommandResponse` z T2.
Identyfikator sesji służy wznowieniu; odpowiedź nie ujawnia dawnych nodes/cells.
Po utracie odpowiedzi zachować dokładny UUID/body do retry, ale nie pokazywać
payloadu ani nie odtwarzać z niego canvasu po reload. CAS konflikt wymaga
odczytu stanu; brak automatycznego zapisu zmienionej komendy. Nie używać
szkicu zwykłego edytora ani endpointu zapisującego bieżącą geometrię.
Zwykłe etykiety poza pomiarem używają odrębnych komend T2. AI-origin wymaga
jawnej akceptacji człowieka; sam status propozycji nie tworzy ludzkiego GT.

Brak etykiet blokuje właściwy dowód/automat, nie zwykłe propozycje do ręcznej
oceny. Gotowość uczenia, dowód zawartości, u/δ/oracle, kwalifikacja automatu,
zakres gier i wariant wejścia pozostają osobnymi stanami z backendu.
Najmniejsze wpięcie sesji jest lokalnie w Adminie; obecna allowlista zdalnego
Reviewera nie udostępnia tras T2 i nie należy rozszerzać jej bez decyzji root.
Legacy V3 i domyślne zachowanie wspólnego edytora pozostają chronione.

Istniejący generator sprawdza tożsamość run/game/version/sourceSHA i renderuje
zapisane wyniki, bez inferencji i domenowych zapisów. Reuse tych kontroli.
Obecna reguła `paired` opiera się na dziewięciu detekcjach i indeksie pozycji;
nowy raport nie może uznać samej liczby9 za dowód jednoznacznego przypisania.
Użyć wersjonowanego dopasowania T3; przy braku dowodu pokazać całość i brak
powiązania. Piętnaście rastrów pochodzi z produkcyjnego renderer/snapshotu,
nie z browserowego viewportu. Stopka może deklarować CPU/oryginalne piksele
tylko przy zapisanym dowodzie; brak metadanych pozostaje jawny.

### Handoff po T2

P2-5 przekazane z Opus T2/R2: content_readiness_views nie może przerwać całej
odpowiedzi przy konflikcie żywej sekwencji i zasłonić poprawnego frozenPinCoverage.
Policzyć live konflikt per plansza jako unresolved z powodem; pokrycie pinami
liczyć niezależnie. Test żądania, typy/SDK i stany UI zgodnie pionem T5.
P2-2 nadal wymaga izolowanego blind workspace bez zwykłego GET content-references,
starych szkiców/prefill i danych innego przebiegu. Raport T2 PASS z jawnymi granicami.

## Test cases

- Blind2pass: interakcja operatora tworzy measuredNodes24 i cells15; każdy
  nowy przebieg/cel ma pusty canvas bez previous pass, localStorage zwykłego
  edytora, propozycji i predykcji w DOM, canvasie i odczytach API.
- Lattice drag nie przesuwa content quadów; visible wymaga poprawnego quadu;
  unknown/occluded/out_of_frame nie udają sukcesu; bounds/EXIF/wymiary,
  „10” jako jedna komórka, jawne wyniki u/δ/oracle.
- Reload, wznowienie po sessionId, CAS konflikt i utrata odpowiedzi: ten sam
  UUID/body bez pokazywania dawnych etykiet, bez podwójnego submitu i wysyłki
  zmienionej komendy w tle; zmiana gry/pass/celu czyści stan.
- Sukces i unqualified, loading/empty/error/retry-refresh, brak/nieaktualność
  dowodów, gry/wariant/budżet. Niedobór labels nie wyłącza propozycji.
  AI-origin bez jawnej akceptacji nie jest GT; propozycja nie nadpisuje
  ręcznych geometrii/symboli.
- HTML: rzeczywiste 15 rastrów, renderer/classifier/padding snapshot,
  wersjonowane dopasowanie T3, SHA/ścieżki/indeksy. Braki są jawne;
  kadrowanie/filtry nie zmieniają pikseli. Wrong-cell/remis/sąsiad, górny rząd,
  perspektywa/zasłona/bounds/partial/unknown i stare wersje.
- Backend/OpenAPI/SDK/wrapper/request test oraz regresje Admin/Reviewera;
  trwałość po nowym procesie. To planowane sprawdzenia, przygotowanie
  nie uruchamia testów ani usług i nie etykietuje danych operatora.

## Verification

Testy zmienionego pionu, PG, ONNX, Admin/Reviewer interakcje, lint/types/build,
OpenAPI/SDK/docs/map. Znane buildy kontrolowane, timeouty i brak osieroconych
procesów. Wyniki quality/TASK-1168_VERIFICATION.md.

## Outcome

Commit: v1.7.577 (hash dopisuje kolejny commit).

### Changed

- Admin ma dwa faktycznie zamontowane tryby: zwykłe niezależne etykiety
  zawartości zdjęć (w tym B/REG) oraz izolowany pomiar powtarzalności.
  Wybór kohorty/zdjęć/slotów jest jawny; unresolved blokuje dany cel.
- Nowy wspólny canvas obsługuje ręczne 24 punkty oraz niezależne 15 quadów/
  visibility. Zoom/pan zachowuje sourceXY; nowy tryb/cel/przebieg resetuje
  viewport. Nieaktywnych kontrolek nie pokazuje się w drugim trybie.
- Ordinary używa T2 get/write/CAS i jawnego human approval bez zmiany
  geometrii/symboli. Blind nie czyta zwykłych referencji, sugestii ani
  szkiców. Exact pending UUID/body po reload służy wyłącznie retry,
  nigdy odtworzeniu canvasu. Konflikt CAS nie wysyła nowej komendy w tle.
- Panel pokazuje content v6 oddzielnie od rawQuality i kwalifikacji
  automatu, właściwe warianty wejścia, zakres gier, braki oraz budżet workera.
  Zielone primary/secondary, odstępy i loading są zachowane w zakresie UI.
- Pion API/SDK dostarcza snapshot-bound targets/asset bez etykiet i geometrii
  oraz naprawia P2-5 bez osłabienia frozen/currentness. Istniejący CLI HTML
  eksportuje realne 15 wycinków na model i wejście NN ze ścisłym T3 matching,
  bez fallbacku9/indeksu; mały handoff po T4 domyka bounded reader i dowód WIDE.
- Runda po rzeczywistym Opus R1 naprawia adres manifestu według publish_json,
  istniejące nazwy zdjęć, lokalny brak renderu i ochronę obcych PNG/indexu.
  Nowe deferred/error/retry testy wykryły i naprawiły brak empty sesji oraz
  retry budżetu dla niezmienionego przebiegu. Ścisłe nodes pozostają bez zmian.

### Verification results

- Własny pion Admin: wcześniejsza dedykowana regresja 92/92 PASS;
  rozszerzony zestaw panel/content 60/60 PASS; końcowy zmieniony workspace
  10/10 interakcji PASS. Zestawy częściowo się pokrywają, nie sumować ich.
- Scoped ESLint, Admin tsc i produkcyjny build PASS. Build: kompilacja
  4,7 s, TypeScript12,3 s, strony statyczne3/3; standardowe ostrzeżenie
  wielu lockfile w worktree bez awarii.
- Końcowe plikowe fixture zrzuty obejrzane: desktop viewport1280/
  scrollWidth1265, mobile412/412; akcje w bounds, gap12px, zielone tokeny.
  Pierwszą awarię Edge i wcześniejszy nieważny mobile crop rozliczono w raporcie.
- Strict UI manifest: `artifacts/TASK-1168_UI_MANIFEST.json`, 15 ścieżek
  z SHA/bytes względem zamrożonego drzewa T4 `d0ba8e63...`, bez cudzych zmian T4.
- Pełny zapis wyników i ograniczeń: `ai_docs/quality/TASK-1168_VERIFICATION.md`.
- Końcowe raporty helperów odebrane: API 20 PASS, kontrola zastosowania 5 PASS,
  targets 8 PASS, dedykowany PG 1 PASS z usunięciem wszystkich własnych zasobów,
  SDK 3 PASS; strict mypy 5 plików PASS od root. Dodatkowy test stale stamp
  1 PASS. HTML/worker 55 PASS, potem wyłącznie dotknięte P2 guards 15 PASS;
  scoped Ruff/mypy/format/drift checks PASS. Testy częściowo
  pokrywają istniejące piony, bez sumowania ich jako rozłącznych przypadków.
- Reviewer:60 testów geometrii/propozycji/proxy PASS, typecheck i pełny build
  PASS. Root strict API mypy5 PASS. Globalne docs:check i code-map:check PASS;
  szczegółowe logi oraz ograniczenia opisano w raporcie weryfikacji.
- Po poprawkach R1:78 interakcji/lint4/tsc/nowy Admin build PASS;50 HTML
  regression/lint3/mypy2 PASS;9 API unit+1realPG/cold/cleanup0/0/Ruff3/
  strictmypy1 PASS. Poprzednie błędne fixture oraz EPERM builda zachowano
  w raporcie jako pierwotne niepowodzenia, nie PASS.
- Rzeczywisty Opus R2 PASS0P0/0P1; raport i receipt:
  `ai_docs/quality/TASK-1168_AUDIT_claude-opus-5-5.md`. R1 REVISE zachowany
  oddzielnie. Sześć tasków planu ma sprawdzone zgodne reportSHA/model/receipt.
  Szczegółowy odbiór punkt po punkcie: FULL_SYMBOL_CROPS_ACCEPTANCE_20261109.

### Not completed

- Pozostają zaakceptowane P2-2 (exactnodes a pokrycie HTML) i P2-4 (brak
  testu producenta detail). Root potwierdził wspólny artifact root i pin
  wąskim odczytem producenta, bez nazywania go testem lub zmianą audytu.
  Sprawdzenie rzeczywistego zestawu należy do pierwszej operacji operatora.
  Koszt replayu T3/T4 pozostaje wcześniejszym residualem.
- Nie etykietowano danych operatora, nie wykonano rzeczywistego treningu/
  kwalifikacji nowych gier, migracji operatora, restartów, aktywacji,
  zmiany defaultu, importu691, merge ani push.

### Documentation updates

- Raport jakości, ścisłe manifesty obu rund i rzeczywiste raporty audytu.
  D593, wymagania/architektura/API, mapa, stan i instrukcja operatora są
  zaktualizowane; zamknięcie wykonuje task-close po pozytywnym audycie.

### Recommended next task

- Akceptacja operatora oraz osobno zatwierdzone merge/push, migracje0182/0183
  i wdrożenie. Następnie gotowość danych, zgoda i limit rzeczywistego treningu;
  pierwsze porównanie sprawdza residuale HTML. Bez automatycznego defaultu/importu.
