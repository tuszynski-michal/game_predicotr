---
title: Mumie — nowe oznaczenia pierwszego filmu i izolowana diagnostyka RGB
status: accepted
last_updated: 2026-10-06
---

# Stan, cel i zakres

Operator ukończył kolejkę ośmiu symboli, revision8. Wcześniejsze polecenie
autonomicznego dalszego działania oraz zgoda na wewnętrzne AI nadal obowiązują.
TASK-0868 pozostaje zakończonym, odrzuconym eksperymentem pary: gray/fuzja
regresują Ra do J. Nie zmieniamy tego wyniku ani jego blokady sidecara.
Nowy RGB osiągnął26/26 późniejszych kontroli człowieka i jest zachowany
eksperymentalnie. Ten etap najpierw ocenia nowe8, potem warunkowo porównuje
wyłącznie RGB na już istniejących8100 wycinkach. Nie kwalifikuje produkcji.

Pierwszy film pozostaje w całości poza development symboli. Nowe zatwierdzenia
służą ocenie; nie wolno przenieść ich do treningu ani dopasowania kalibracji.
Geometria była wcześniej częściowo trenowana na tym filmie. Osiem przypadków
dobrano kierunkowo według niepewności, więc nie reprezentują całego katalogu.

## TASK-0869 — ocena ośmiu nowych decyzji człowieka

1. Istniejący `symbol_feedback.prepare/verify_pack` zamraża najnowsze approve
   aktywnej priority8 referencji. Sprawdzić8/8, pełne history/receipts/revision,
   dictionary, source, PNG i quad re-render. Utrzymać origin operatora i
   trainable=false. Zmiana bieżącej historii blokuje publikację zależnego wyniku.
2. Związać zamrożone proofy V4/R2/human26/AI60 i actual sześć eksportów ONNX.
   Reuse `symbol_batch.preprocess/classify_logits` z wyłącznie dotychczasowymi
   temperaturami/fuzją/progiem. Sprawdzić model SHA i klasy oraz actual V3/V4
   parity z poprzednimi propozycjami. Nie wybierać nowego modelu ani progu na8.
3. Zmierzyć oddzielnie human kontrolne/kierowane przypadki, klasy i błędy.
   Osobno pokazać prior AI consensus versus human; human ma pierwszeństwo
   bez nadpisywania starego AI proofa. Raport dla60 może jawnie rozdzielać
   human8 i pozostałe AI-only; nie raportować60 jako human accuracy.
4. Weryfikować source/photo/pixel exclusion od development312/327,
   stare artefakty i oba61-output zestawy. Fresh-process actual inference i
   byte-identical replay, guards dla history/source/PNG/perclass drift.
   Focused tests, Ruff/format/types, independent audit, DoD i commit.

## TASK-0870 — warunkowa diagnostyka samego RGB

1. Przed inference zamrozić eligibility: każde dotychczasowe human perclass
   porównanie R2 RGB versus V4 RGB z84/18/19/9, held22/diagnostic4 i nowych8
   musi nie regresować. Nie stosować sumy zamiast perclass/group gate.
   Zły gate oznacza zakończony raport odrzucenia i zero nowych8100 outputs.
2. Przy PASS wykonać wyłącznie actual RGB inference, bez gray/fuzji i bez
   tworzenia nowej pary. Reuse preprocess oraz validated istniejące quady,
   source/photo exclusion i exact RGB96 SHA. Oddzielny create-only
   `rgb-only-diagnostic` sidecar przechowuje old/new RGB class/confidence,
   model/proof IDs oraz source/quad/pixel binding. Stare wyniki nie są zmieniane.
3. Maksymalnie20 zdjęć w finite120s kroku; resume waliduje istniejące pliki
   zamiast liczyć je ponownie. Zestaw:60 istniejących zdjęć/8100 cropów,
   bez dodatkowego datasetu, treningu, refitu, kalibracji ani etykiet.
   Raportować zmiany klas i flag, accuracy całego folderu pozostaje null.
4. Fresh process potwierdza dokładne renderowanie i actual RGB logits oraz
   zachowanie source/model/history/old-output SHA. Osobny audit/DoD/commit.
   Brak PASS lub drift nie powoduje fallbacku do złagodzonych reguł.

## Odbiór i granice

Źródłami prawdy są pierwotne decyzje operatora i pinned artefakty. Helpery
lokalne w nowych artifact roots, taski i raporty jakości są jedynym zakresem
zmian. Bez API/UI/schema/DB/migracji/usuwania, model activation, Super labels,
geometry approvals, merge/push/wdrożenia. Nic nie zmienia combined gate
TASK-0868 ani qualified pary V4. Nie potrzeba ponownej zgody lub nowego folderu.
Każdy task ma osobny audyt i commit; następny patch rzeczywistego HEAD
v1.7.216 to v1.7.217, potem v1.7.218.

Ryzyka: osiem celowo trudnych przypadków ma ograniczone pokrycie klas;
AI agreement nie jest human accuracy; istniejąca geometria nie jest tutaj
niezależnym benchmarkiem. Wynik diagnostic nie zezwala na produkcyjną aktywację.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0869 — nowe human8 i zamrożone modele | gpt-6.1-sol | high | Pełna historia, source isolation i porównanie actual eksportów wymagają kontroli pochodzenia. | Niezależny artifact audit: gpt-6.1-sol, high; wcześniejsza zgoda na wewnętrzne AI |
| TASK-0870 — izolowany RGB diagnostic | gpt-6.1-sol | high | Warunkowa inferencja z exact pixel bindings i trwałym wznowieniem bez zmiany kwalifikacji pary. | Niezależny artifact/replay audit: gpt-6.1-sol, high; wcześniejsza zgoda na wewnętrzne AI |
