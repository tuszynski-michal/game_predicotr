---
title: Mumie — większy test transferu na pierwszym nagraniu
status: accepted
last_updated: 2026-10-06
---

# Stan, cel i zgoda

Trzy katalogi są dostarczone i operator potwierdził odrębne nagrania. Nie
potrzeba kolejnego katalogu ani powtórnego potwierdzenia. Po TASK-0865 model
eksperymentalny V4 osiągnął 22/22 human audit w częściowo trenowanym filmie.
Teraz przygotowujemy większą próbę na filmie `1 - 23175 cut`, wyłączonym
z development symboli. Wcześniejsze polecenie samodzielnej kontynuacji
obejmuje przygotowanie testu i gotowej kolejki; człowiek dopiero nada referencję.

## TASK-0866 — zamrożone porównanie i gotowy pakiet człowieka

1. Sprawdzić katalogi w `C:/Users/tuszy/Documents/mumie`, rzeczywiste źródła
   development V3/V4, SHA i pełne wykluczenia. Reuse `symbol_batch.freeze`
   generacji3, `choose_rows`, qualified V3 i istniejący model geometrii.
   Zamrozić 60 równomiernie rozłożonych eligible zdjęć pierwszego filmu.
   Każde źródło i whole-photo pixels przechodzą istniejące guardy. Technical
   overlap ma pierwszeństwo przed deklaracją filmu; brak eligible blokuje,
   bez omijania adapterów. Geometry model był trenowany na części tego filmu,
   dlatego zakres wniosku to transfer symboli, nie niezależna ocena geometrii.
2. Przed nowym inference przypiąć deterministyczną regułę 50 kontroli: zdjęcia
   równomiernie z 60, board/field wybrane hashem source SHA i stałego seed
   `20261006`. Brak cropu jest brakiem kontrolnej obserwacji, nie cichym wyborem
   łatwiejszego pola. Odrębne 10 przypadków kierowanych wybrać po inference,
   preferując różne zdjęcia oraz rozbieżności V3/V4 i małą pewność. Dokładny
   podział zapisać; nie łączyć jego wyników w reprezentatywną accuracy filmu.
3. Uruchomić V3 po maksymalnie20 zdjęć/120s. Zastosować istniejące filename
   count cap, reading order i clipped cells. Odrębny lokalny wynik V4 na
   identycznych cropach przez `reclassify_photo`, istniejący preprocess,
   rzeczywiste ONNX i frozen calibration TASK-0864. Bez nowego treningu,
   dopasowania progów, aktywacji lub kwalifikowania generacji4 jako production
   batch. Każdy drift source/geometry/pixels/report/model blokuje etap.
4. Raportować zasięg, low confidence, disagreements i class changes,
   accuracy=null. Reuse `symbol_batch_labels.prepare`, `BatchReviewStore`
   i `publish_portal` na qualified V3 batch: packet nadaje wyłącznie reference
   dla dokładnego rastra, niezależnie od propozycji V4. Kategorie nie pokazują
   przewidywanej klasy. Oddzielny immutable sidecar przypina V3/V4 i grupy.
   Nie dopisywać żadnej human decyzji, nie włączać tych pól do treningu.
5. Preserve poprzednią kolejkę26/revision27, modele, runy, human pack i dane.
   Backup saved runtime, wskazać nowy packet w istniejącym lokalnym editorze
   i sprawdzić controlled restart, read-only API queue i exact crop HTTP.
   Produkcyjne API8000 pozostaje poza zakresem. Fresh-process retry potwierdza
   byte-identical wyniki/pakiet i nienaruszone piny. Odrębny audyt, DoD,
   dokumentacja, Outcome/CURRENT_STATE oraz osobny commit.

## Odbiór i ryzyka

Ready packet ma kontrolną i kierowaną grupę, źródła/pixels poza development,
zero decyzji człowieka, trwałą konfigurację i działającą edycję bez ruszania
siatki. Testy skoncentrowane na batch/review/feedback i negatywnej kontroli
source/pixel/geometry drift; lint/format/scoped typecheck helperów. Próba
kontrolna nie daje jeszcze accuracy bez etykiet i ma ograniczoną liczność.
Gold frame/Super pozostaje osobną referencją; sam symbol CNN nie rozwiązuje
Super. Bez DB/migracji/usuwania, nowych API/UI, produkcyjnej aktywacji,
merge/push/wdrożenia. Każdy skończony krok używa istniejącego runnera120s.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0866 — test transferu i gotowa referencja | gpt-6.1-sol | high | Zamrożenie porównania i izolacji źródeł bez mieszania propozycji z referencją. | Niezależny audyt danych, deterministyczności i ready packet: gpt-6.1-sol, high; wcześniejsza jawna zgoda na wewnętrzne AI |
