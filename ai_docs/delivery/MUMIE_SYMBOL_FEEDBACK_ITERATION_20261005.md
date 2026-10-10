---
title: Mumie — kwalifikacja korekt i ograniczona iteracja feedback
status: accepted
last_updated: 2026-10-06
---

# Iteracja po 18 korektach

Operator zakończył 18 crop-review i jawnie zlecił dalszą pracę bez rutynowych
pytań o kontynuację. Zakres obejmuje kwalifikację, ograniczoną nową parę
modeli i jej ocenę, do rzeczywistej granicy wymagającej danych operatora.
Nie obejmuje DB, migracji, aktywacji, merge/push ani wdrożenia.

## Stan i jawne reguły

TASK-0859: 18 approve, revision18; V1 RGB/gray/fuzja11/10/10 i V2 10/13/11.
Wszystkie warianty83/84 na starej walidacji. Automatyczna podmiana gałęzi
nie przechodzi bramki błędów per klasa. Używamy rzeczywistych nowych etykiet,
zamiast kolejnych losowych prób na tych samych dawnych danych.

Anotacja symbolu zatwierdza dokładny crop i klasę. Kwalifikacja dla CNN może
wykorzystać tylko ten raster, po sprawdzeniu jego geometrii/bindingu, PNG,
źródła, aktualnej decyzji i rozłącznego podziału. Nie zatwierdza planszy,
innych pól, siatki dla uczenia geometrii ani sequence_number. Pierwotne
batch_crop_review pozostają trainable=false; osobny manifest pochodny ma
purpose=symbol_crop_feedback. Istniejący D-498 i jego adapter nie zmieniają
swoich domyślnych bramek. Ta interpretacja zostaje jawnie zapisana jako D-502.

Operator potwierdził relację nagrania481537–500000 do walidacji76555–103221:
„Tak, inne nagranie”. Potwierdzenie różnicy względem
1–23175 już istnieje; nie prosimy o nie ponownie. Relacja do156538 nie
przecina części, gdyż obie grupy są development. Nie wolno utożsamiać różnych
folderów z niezależnymi filmami. Brak deklaracji blokuje freeze trainable i
trening, lecz nie przygotowanie dokładnego pakietu i preview bramek.

## TASK-0860 — dokładny pakiet i kwalifikacja feedbacku

Nowy proponowany `vision_lab/symbol_feedback.py` buduje create-only pakiet
aktualnych 18 approve z `BatchReviewStore`, zachowując pełne decyzje, PNG,
quad, sourceSHA i już zatwierdzony słownik. Zwykłe review/unreadable/grid_issue
nie są targetami. Pod geometry-first locks weryfikuje stan i render exact crop;
nie tworzy zgód ani nowego AnnotationStore. Preview ma trainable=false i
jawnie raportuje bramkę nagrania, liczbę rodzin, klasy i duplikaty.

Drugi krok freeze tworzy pochodny manifest wyłącznie po spełnieniu wszystkich
bramek. Reuse `SymbolTrainingAdapter` dla bazowych339 etykiet. Pełny graf
dawnych/aktualnych komponentów, SHA aliases i całego nowego folderu pozostaje
w jednym przydziale. Chronione/cross-game/comparison członki oraz powiązanie
nowego development z walidacją blokują przed pikselami. Oryginalne źródła,
historia i stare assignments pozostają niezmienione.

Nowy podział: pierwszy pełny komponent nagrania1–23175 staje się
diagnostic_test wyłącznie dla tej nowej iteracji. Usuwamy jego9 targetów
z development. 246 dawnych development +18 feedback daje264 unikalne
targety; validation nadal84; diagnostic_test9 (Mumia1/Sfinks8).
Wszystkie10 klas pozostają w development/validation. Cała rodzina first
folder jest wyłączona z uczenia nowej iteracji. Ten test nie jest ślepy
względem poprzednich modeli i obejmuje tylko2 klasy; raport ujawnia ten limit.

Nowy proponowany `SymbolFeedbackAdapter` zwraca istniejące
`SymbolTrainingInputs` z composite samples i osobnym immutable PNG bundle.
Waliduje pełną historię decyzji, exact latest binding, słownik, SHA wejść,
inventory, counts i brak pixel/photo duplicates między częściami.
Dispatch adaptera jest opcjonalny/format-bound w lokalnym managerze;
dotychczasowy SymbolTrainingAdapter odrzuca nowy format.
Identyczny retry/new-process verify zachowuje jeden pakiet i manifest.
Drift daje jawny błąd bez automatycznej korekty albo wznowienia starego raportu.

## TASK-0862 — trwała lokalizacja przeniesionych źródeł

Wykonać przed wznowieniem0861. To naprawa lokalizacji, bez zmiany etykiet,
rastrów, podziału, manifest_id, checkpoint binding ani settings istniejącego
runu. Proponowany create-only sidecar `<manifest_id>.sources.json`, checksum
envelope, jawnie wiąże manifest, oryginalny folder, aktualny source_root,
digest pełnego inventory i referencję operatora. Dopuszczalne jest wyłącznie
przeniesienie całego nagrania z identycznymi nazwami i wszystkimi SHA.
Metadata/role/alias gates pozostają przed pikselami. Exact re-render wszystkich
18 zatwierdzonych rastrów i pełna historia pozostają wymagane.

Adapter używa lokalizacji tylko do odczytu zdjęć, zachowując oryginalną logiczną
przestrzeń ścieżek w manifestach i decyzjach. Nie remapuje etykiet, katalogu,
PNG bundle ani innych metadanych. Domyślny brak sidecara zachowuje strict gates.
Manager chroni również aktualny source_root przed overlapem wyników. Nowy
proces i identyczny retry dowodzą trwałości, bez junctionów i kopiowania zdjęć
do starego folderu. Failed RGB run wznowić z tym samym ID i budżetem.

Testy: full-folder drift/extra/missing file, zła tożsamość/relative root,
re-render/label drift, create-only retry, default adapter i output overlap.
TASK-0862 ma własny review i commit. Następnie kontynuować0861.

## TASK-0861 — jedna ograniczona iteracja i ocena

Po oddzielnym commicie0860 i kwalifikacji danych kontynuować automatycznie.
Aktualizacja 2026-10-06: przed wznowieniem wykonać naprawę TASK-0862 opisaną
powyżej. Operator podał nowy parent C:\Users\tuszy\Documents\mumie i potwierdził,
że trzeci katalog oraz każdy kolejny nowy katalog pochodzą z odrębnych filmów.
Addytywna generacja3: mumie-symbol-rgb-v3/mumie-symbol-gray-v3, od zera,
oryginalny preprocessing RGB64/gray3 i spatial4×4, dotychczasowa deterministyczna
augmentacja wyglądu. Nie kopiować checkpointu ani słownika777. Każda gałąź
ma jeden run do20 epok/1800s/10000kroków, seed20261005, batch32, AdamWlr.001.
Nowe18 przykładów mają wagę4 w samplerze development; nie tworzymy nowych
etykiet ani fikcyjnej liczności. Ocena development używa unikalnych264 pól.
Walidacja84 bez augmentacji; wybór epoki i temperatury tylko na niej.

Reuse durable `SymbolRunManager`, neutralnych checkpointów/RNG, admission,
budżetów, watchdog i fenced artefaktów. Wznowienie sampler/generator/optimizer
jest dokładne. Oryginalne rooty i generacje1/2 zostają nienaruszone.
Raport porównuje all10 classes, macro/confusion oraz hard-case regression18
użytych teraz w uczeniu. Nigdy nie nazywa tych18 niezależnym testem.
Ocena diagnostic_test9 następuje dopiero po finalnym wyborze epoki; nie
zmienia kalibracji, treningu ani wyboru modelu. ONNX parity obejmuje84 pola.

Jeśli kwalifikacja walidacji nie osiąga83/84 lub pogarsza klasę względem
zamrożonej V1 referencji, zakończyć raportem bez ponownych losowych runów.
Po udanej kwalifikacji można wykonać ograniczoną inferencję nowych źródeł
nagrania1–23175: wykluczyć użyte/chroniczne source/crop duplicates i oznaczyć
wynik jako nieopisany diagnostyczny, bez accuracy. Przygotować konkretne
nowe przypadki do istniejącego crop-review, gdy potrzebne będą etykiety.
Brak nowej referencji człowieka kończy autonomiczną pracę w tym etapie.

## Weryfikacja i granica

Testy nowych bramek, protected/alias/family/role conflicts, dictionary/label/
source/pixel drift, duplicates, inventory, create-only/restart/retry i
niezmienność oryginałów. Regresje dotychczasowych adapterów/runów/batch.
Scoped lint/format/mypy; brak zmiany HTTP, więc bez nowego OpenAPI/UI build.
Każdy task: własny odrębny review, osobny commit, Outcome i CURRENT_STATE.
Polecenia przez istniejący absolutny timeout runner120s; GPU worker ma
kontrolowany background/PID i trwały watchdog1800s. Bez nieograniczonego wait.
Testy są planowane; wynik wymaga rzeczywistego uruchomienia i raportu.

## TASK-0863 — trzeci niezależny katalog zdjęć

Operator jawnie zlecił użycie trzeciego katalogu. Po0861 wykonać ograniczoną
inferencję60 rozłożonych po nagraniu zdjęć z24517–50112 cut, z filename-count
cap, istniejącym modelem geometrii i dotychczasowym artefaktowym workflow.
Zbiór jest nieopisany; nie tworzyć accuracy ani etykiet bez człowieka.
Jeśli generation3 przejdzie bramkę, użyć jej zamrożonej pary i kalibracji.
Jeśli nie, zachować wynik treningu i użyć poprzedniej kwalifikowanej pary V2
do diagnozy nowego nagrania, jawnie oznaczając wersję. Nie uruchamiać kolejnego
losowego treningu. Wybrać ograniczone konkretne crop-review do istniejącego
edytora, jeśli wynik wymaga nowych etykiet. Bez DB i aktywacji modeli.

Generacja3 wymaga jawnego dowodu all-class qualification oraz obu realnych
eksportów. Batch zachowuje pełne wykluczenia obu części i diagnostic_test,
zewnętrzne SHA pełnego feedback-folderu i aktualną lokalizację źródeł.
Przy przygotowaniu crop-review sprawdzić pełny composite cohort, lecz w
referencji UI reuse bazowego D-498 approval provenance z identycznym słownikiem,
immutable manifest/batch i exact case sources. Nie wymuszać hashowania wszystkich
niepowiązanych2052 zdjęć przy każdej operacji UI. Dotychczasowe referencje/defaulty
zachowują zachowanie; wynik nie nadaje trainable ani zgody całej geometrii.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0860 — dokładny feedback i kwalifikacja | gpt-6.1-sol | high | Granularne zgody, pełny graf i spójność immutable cropów/splitu. | Własny odrębny przegląd i testy integralności; bez delegowania |
| TASK-0862 — lokalizacja przeniesionych źródeł | gpt-6.1-sol | high | Zachowanie exact bindings i pełnych bramek przy zmianie ścieżki. | Własny odrębny przegląd i regresje; bez delegowania |
| TASK-0861 — ograniczona iteracja i ocena | gpt-6.1-sol | high | Trwałe runy, sampler/RNG i ocena regresji każdej klasy. | Własny odrębny przegląd oraz regresje resume; bez delegowania |
| TASK-0863 — nowy niezależny katalog | gpt-6.1-sol | high | Rozłączność źródeł i ograniczona inferencja z exact crop-review. | Własny odrębny przegląd i replay artefaktów; bez delegowania |
