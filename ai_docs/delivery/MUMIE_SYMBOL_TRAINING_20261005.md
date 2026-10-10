---
title: Mumie — kwalifikacja i pierwszy trening symboli
status: accepted
last_updated: 2026-10-05
---

# Mumie — uczenie bieżących symboli

Operator potwierdził, że trzy grupy `1 - 23175`, `76555 - 103221`,
`156538 - 182853` pochodzą z różnych ujęć i innych nagrań. Wcześniejsze
polecenie pracy do najdalszego etapu bez obecności operatora pozostaje zgodą
na przygotowanie danych i ograniczone uczenie. Nie pytamy ponownie o te nagrania.
Nie oznacza to zgody na aktywację, DB, merge, wdrożenie lub wypłaty Super.

## Stan i decyzje

Pakiet TASK-0853 ma 339 ważnych świeżych approve w 10 klasach, w tym 27 Mumii.
D-489 nadal wyklucza starsze etykiety i stare modele z uczenia. Oryginalne
siatki rev591, symbolstore rev63, reference D-496 i stale split geometrii
pozostają niezmienione. Nowa kwalifikacja jest osobna, per gra i per pełny
komponent nagrania. Nie zmienia niezmiennego pakietu qualification_only.

## TASK-0854 — kwalifikacja i split symboli Mumii

Nowy proponowany `vision_lab/symbol_training_manifest.py` używa sprawdzonych
`symbol_preparation.build_bundle/verify_bundle` oraz grantu D-496 do ponownej
kontroli bieżących etykiet. Typed/operator request wiąże jawne trzy rodzinne
deklaracje i przypisanie całych grup: `156538…` oraz `1…` do development,
`76555…` do validation. Wszystkie 10 klas musi występować w obu częściach.
255/84 jest stanem zmierzonym, nie stałą kodu. Nie tworzymy final_test z
grupy zawierającej tylko Mumię i Sfinksa. Raport nie przedstawia walidacji jako
niezależnego testu końcowego. Mniejsza grupa ma po 4 J/Sfinksy; ocena jest wstępna.

Kwalifikacja obejmuje wszystkie członki komponentów, także aliases poza
próbkami, z przechodnią sumą dawnych i aktualnych powiązań D-496. Konflikt
rodziny, gry, comparison_only/protected albo ról między komponentami blokuje
całą operację przed pikselami. Kontrola SHA pełnego grafu i porównanie pikseli
pełnych wybranych zdjęć wykrywają duplikaty między częściami. Podobieństwo
prostych obrazów jest tylko dowodem pomocniczym, nie dowodem niezależności.
Deklaracja operatora i nierozstrzygnięty konflikt muszą być jawne.

Freeze publikuje create-only checksumowany `<id>.json` o formacie
`lab-symbol-training-manifest-v1`, D-498, z qualification, assignments, klasami,
pełnym dowodem komponentów, ID przygotowania i live_bindings SHA magazynów,
referencji i wybranych źródeł. Pakiet PNG pozostaje niezmienny. Adapter przy
starcie/checkpoint/finish odtwarza kontrakt, sprawdza inventory/piksele/SHA
oraz live_bindings; drift zatrzymuje run. Stale split geometrii nie jest kasowany
ani uznawany za split symboli. Stary qualify_symbol_sample zachowuje wszystkie
bramki bez nowej konfiguracji. Format szkoleniowy jest dostępny wyłącznie
lokalnemu adapterowi, bez rozszerzenia API lub przypadkowego wejścia geometrii.

Testy: brak zgody, błędna grupa/role/component/protected/klasy, duplikat
przecinający części, drift etykiet/źródła/geometrii, create-only/restart i retry.
Odbiór realnego splitu w nowym procesie, sumy oryginałów bez zmian, raport,
własny audyt i commit v1.7.200 (po potwierdzeniu rzeczywistej historii).

## TASK-0855 — RGB, szarość i ocena pierwszych modeli

Nowe proponowane `vision_lab/symbol_training.py`, `symbol_runs.py` i
`symbol_models.py`. Bez DB i bez przepisania produkcyjnego training_job.
Reuse `SpatialSymbolCnn`, preprocess resize64/normalize-half, neutralnych
checkpoint v2/RNG oraz `RunManager`, fenced artefaktów i trwałych budżetów.
Osobny manager/launcher CLI korzysta z tego samego protokołu; żadnego nowego
endpointu, ręcznych typów HTTP lub zmian domyślnego registry geometrii.

Dwa runy od zera, jeden RGB i jeden gray powielony na 3 kanały, seed20261005,
20 epok, batch32, AdamW lr0.001/weight_decay0.0001; każdy maksymalnie1800s
i 10000 kroków. Wyłącznie rzeczywiste 339 próbek; bez benchmarku/sztucznych
dużych zbiorów. Mała deterministyczna augmentacja treningu wykorzystuje
istniejącą bounded-affine-color-v1; grayscale po augmentacji. Walidacja bez
augmentacji. Wybrana epoka: najlepsze macro accuracy na validation, następnie
loss i wcześniejsza epoka. Wybór nie korzysta z final_test/unseen.

Launcher zapisuje settings/PID/log przed pracą, worker claim/creation time,
watchdog1800s, heartbeat, step reservation i checkpoint po każdej epoce.
Run admission dopuszcza najwyżej jeden train na wariant w tej kohorcie;
retry nie zwraca budżetu. Wznowienie odtwarza optimizer, RNG, historię i best.
Test przerwania/lost response/restart musi wykazać zachowanie budżetu i brak
drugiego procesu. Izolowany istniejący runtime torch2.12.1+cu130, bez instalacji.

Raport zawiera accuracy/macro/per-class/confusion/logloss, train–validation
różnicę, liczności, czasy, błędy i coverage. Kalibracja temperature tylko na
validation, fuzja RGB wagami 0/0.1/0.2/0.3. Porównanie oraz review przy
disagreement; nie udaje się pewności z małego zbioru. Parity/ONNX kandydata
w budżecie runu, jeśli dostępne; nigdy aktywacja domyślna. Zachować wszystkie
wagi/metadane i wybrany raport. Własny audyt, osobny commit następnego patcha.

## Odbiór całości i granica

Po osobnym commicie kwalifikacji kontynuujemy trening zgodnie z poleceniem
pracy do najdalszego etapu. Kończymy raportem dwóch modeli i ograniczeń.
Super pozostaje odrębnym atrybutem bez obecnych etykiet; nie dopisujemy ich
automatycznie i nie implementujemy wypłat. T06b/T07 dla pozostałych gier
pozostają poza tym scoped pilotem. Bez aktywacji, push, merge i wdrożenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0854 — kwalifikacja i split Mumii | gpt-6.1-sol | high | Rzeczywiste zgody, pełne komponenty i ochrona historycznych ról. | Samodzielny odrębny przegląd, testy integralności; bez delegowania |
| TASK-0855 — ograniczone dwa modele i ocena | gpt-6.1-sol | high | Trwałość runów, neutralne checkpointy i walidacja na innym nagraniu. | Samodzielny odrębny przegląd i regresje runów; bez delegowania |
