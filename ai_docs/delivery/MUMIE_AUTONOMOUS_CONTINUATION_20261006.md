---
title: Mumie — dalsza ocena AI i drugi eksperyment bez operatora
status: accepted
last_updated: 2026-10-06
---

# Cel, zakres i zgoda

Operator po TASK-0866 wyraźnie polecił dokończyć jak najwięcej bez zatrzymania
na nowej kolejce. Wcześniejsza zgoda na wewnętrzne AI i trening nadal obowiązuje.
Realizujemy cały poniższy etap: dwa osobne taski z audit/commit każdego.
Istniejące D-505 adaptery, formaty, modele generacji4 i durable run protocol
pozostają bez zmian. Druga para ma nowy manifest i własny katalog runów;
nazwa wyniku V4-R2 oznacza nowy eksperyment tej samej architektury.

## TASK-0867 — ocena AI pierwszej próby

1. Zamrozić blind input dla dokładnych60 cropów TASK-0866 oraz dotychczasowych
   20 human development kotwic. Dwa osobne przeglądy AI widzą wyłącznie PNG,
   kotwice i słownik, bez predykcji, grup, kolejki decyzji albo innych ocen.
   Użyć istniejącego review schema/`consensus`; origin AI, human_approved=false.
2. Sprawdzić wszystkie SHA i grupy50/10, piny modeli/source/render oraz pełną
   historię aktualnych oznaczeń. Porównać frozen V3/V4 z high/high readable
   consensus; resztę oznaczyć unresolved. Raportować AI agreement per class,
   nie human accuracy. Obserwacje gold_frame osobno, bez treningu Super.
3. Zachować cały pierwszy film poza development. Nie wpisywać ocen AI do
   human store. Odrębny immutable raport i kolejka priorytetowa tylko dla
   uncertain/disagreement z AI; jeśli istnieją human decyzje, zachować je i
   zastosować ich pierwszeństwo bez zmiany origin. Nie wymagamy60 human
   oznaczeń do dalszego treningu. Zakończyć audit/replay/docs/commit, następnie
   automatycznie rozpocząć TASK-0868.

## TASK-0868 — nowe przykłady i druga ograniczona para

1. Reuse qualified third-film60 batch, optional19 human feedback pack oraz
   stary base V3. Przygotować do100 exact przypadków:19 human approve,
   29 dotychczasowych AI development,22 dawnych AI audit oraz do30 nowych
   development cropów z różnorodnych klas, preferując niepewne propozycje.
   Nowe targety są blind assessed przez dwóch reviewerów. Nie stosować CNN
   predykcji jako targetów. Wykluczyć wszystkie26 human audit rastrów i ich
   całe zdjęcia z nowego development; starych22 audit nie trenować. Pierwszy
   film i frozen validation pozostają poza development. Oryginalne19 human
   i5 unreadable mają pierwszeństwo, zachowane receipt/history/pixel bindings.
2. Reuse `symbol_ai_experiment.freeze` i strict adapter. Wymagane minimum20
   high/high AI audit i dodatnie zwiększenie AI development względem29;
   niewystarczający consensus kończy kwalifikację bez nowego runu, lecz nie
   blokuje innych analiz etapu. Wszystkie źródła/decoded pixels/whole-film
   aliases, słownik, protected roots i poprzednie input/output SHA sprawdzane.
3. Jedna nowa RGB/gray para, osobne runy i actual exports. Ten sam seed20261005,
  20epochs,batch32,lr.001,max1800s/10000steps na gałąź, feedback weight4/AI1.
   Jeden aktywny run naraz, trwałe checkpoint/RNG/PID/watchdog; GPU proces
   kontrolowany, krok CLI120s. Nie zmieniać seed/progu/calibration po audit.
   Calibration i best epoch wyłącznie z dotychczasowych84 human validation.
4. Recompute perclass gates względem frozen V4: human84,old18,new19,diag9;
   osobna zamrożona human26 ocena bez treningu i dopasowania do tych etykiet.
   ONNX parity oraz AI audit agreement. Pierwsze60 AI ocen z0867 służy tylko
   ocenie transferu; wyniki kontrolne50 i kierowane10 osobno. Jeśli human
   regresja, zachować V4 jako qualified candidate i raportować dokładny błąd;
   żadnej automatycznej aktywacji lub sztucznego poprawiania referencji.
5. Reclassify tylko symbole identycznych pierwszych8100 cropów, jeśli gates
   przejdą. Oddzielny V4-R2 sidecar, bez mutacji geometrii/old results/human
   store. Fresh process/replay, independent audit, DoD/docs/commit. Na końcu
   oddać konkretne wyniki i wyłącznie pozostałe niejednoznaczne przypadki;
   brak nowego katalogu i ponownego pytania o pochodzenie filmów.

## Odbiór, błędy i granice

SHA/source/label history drift blokuje zależny krok. Brak consensus nie jest
accuracy i nie tworzy human approvals. Wszystkie stare rastry i modele mają
oryginalne piny; output wyłącznie w nowych artifact roots. Testy istniejących
consensus/adapter/training/sampler/metrics plus negatywne drift i stricte nowe
helper checks. Każdy task: focused tests, lint/format/scoped types, independent
review i osobny commit. Bez nowych API/UI, DB/migracji/usuwania, Super targetów,
produkcyjnej aktywacji, merge/push/wdrożenia ani nowej płatnej usługi.
AI może zgodnie popełnić błąd; agreement pozostaje oddzielny od human truth.
Jeden film nie opisuje populacji; reused84 nie jest świeżą walidacją.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0867 — blind AI ocena i kolejka niejednoznacznych | gpt-6.1-sol | high | Exact-raster ocena z zachowaniem granicy AI/human i frozen film exclusion. | Dwa visual review oraz niezależny artifact audit: gpt-6.1-sol, high; jawna zgoda operatora |
| TASK-0868 — rozszerzone AI development i druga para | gpt-6.1-sol | high | Istniejący strict adapter/run protocol, większy cohort i perclass human gates. | Dwa visual review nowych rasterów i niezależny eksperyment audit: gpt-6.1-sol, high; jawna zgoda operatora |
