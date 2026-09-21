---
title: Testowy silnik geometrii v2.0 — plan wykonawczy po audytach
status: accepted
last_updated: 2026-09-21
---

# Testowy silnik geometrii v2.0 — plan wykonawczy po audytach

## Status, cel i warunki pracy

Ten plik jest trwałą kopią zaakceptowanego planu ustalonego z właścicielem
2026-09-21. Nie zastępuje dokumentów właścicielskich w `ai_docs/`; ustalenia
każdego realizowanego etapu są przenoszone do jego karty, właściwej dokumentacji
oraz, gdy zmieniają architekturę lub dane, do `DECISION_LOG.md`.

Cel: obsłużyć import zdjęć gier 777, Blazing, Gang, Reels i Mumie przez
istniejący przepływ `staging → preflight geometrii → korekta → import →
weryfikacja komórek`. Docelowo gry korzystają ze wspólnej wiedzy wyłącznie o
geometrii, z osobnymi symbolami, modelami i payoutami. Treasure pozostaje poza
zakresem.

Praca odbywa się wyłącznie na gałęzi `codex/shape-geometry-v2` w osobnym
worktree. Bieżący katalog aplikacji i jego lokalne zmiany nie są modyfikowane.
Po ukończeniu oraz przeglądzie użytkownik podejmuje decyzję o scaleniu do
`version-0.10`/mainline.

Po każdym tasku obowiązkowe są:

1. self-review;
2. niezależny audyt `gpt-6-astra`, reasoning `medium`;
3. poprawa wszystkich wykrytych usterek;
4. ponowienie właściwych testów;
5. osobny commit i uzupełnienie `Outcome`.

Błąd krytyczny — możliwość błędnej automatycznej akceptacji, utrata lub
pomieszanie danych gry, naruszenie kolejności sekwencji, nieodtwarzalny
snapshot, wyciek danych acceptance albo błąd migracji — zatrzymuje pracę
natychmiast. Nie wolno rozpoczynać kolejnego tasku ani omijać bramki. Raport
musi wskazać dowody, wpływ i potrzebną decyzję. Błędy niekrytyczne naprawiamy w
tym samym tasku, ponawiamy audyt i kontrole, a następnie kontynuujemy plan.

Każdy task wymaga osobnego polecenia użytkownika zgodnie z `AGENTS.md`.
Każdy ukończony task ma oddzielny commit wersjonowany. Brudny worktree głównego
katalogu nigdy nie wchodzi do commitów tej gałęzi.

## Ustalone decyzje produktu

- v1.1 pozostaje silnikiem domyślnym; v2.0 jest oddzielnym, świadomie wybieranym
  wariantem testowym.
- v1.0 zostaje dostępny diagnostycznie oraz dla historii i wznowienia.
- v2.0 opiera się na kształcie, kontraście i strukturze; kolor ramki jest
  pomocniczym, wersjonowanym dowodem, domyślnie wyłączonym.
- Pierwszy działający import v2.0 nie wymaga ukończenia trwałej biblioteki.
  Współdzielenie wiedzy jest jednak wymaganiem docelowym.
- Pomiar „po jednej kotwicy” oznacza jedną pełną stronę na grę. Kotwica jest
  wybierana przed eksperymentem z puli development według utrwalonego porządku
  rodzin nagrań, pozycji i checksumy; nie wolno wybrać jej po obejrzeniu wyniku.
- Dodatkowe korekty, które wykrywają stary błąd v1.1, raportujemy osobno od
  regresji. Pełny odbiór v2.0 dla 777 wymaga zera zaobserwowanych błędnych
  automatycznych akceptacji, także zastanych w v1.1: błąd musi zostać poprawiony
  albo skierowany do korekty.
- Ucięcie góra/dół zachowuje obecną ochronę: brak automatycznej akceptacji,
  naprawa/wymiana/wykluczenie źródła. Nie projektujemy pionowego importu
  częściowego.
- Numery progów, minimalne wielkości korpusu i limity zasobów zatwierdzamy po
  G01, przed G02 i przed ujawnieniem acceptance.
- Wszystkie gry 777, Blazing, Gang, Reels i Mumie pozostają kandydatami do
  tworzenia gier. Brak corpusów, konfiguracji albo wystarczającego dowodu dla
  jednej gry nie wyklucza jej z systemu: daje jej jawny stan konfiguracji lub
  review per źródło. `development`, `calibration` i `acceptance` dzielą
  rodziny zdjęć wewnątrz każdej gry, nigdy listę obsługiwanych gier.

## Dane, pomiary i bramki jakości

### Podział danych

| Zbiór | Dozwolone użycie |
| --- | --- |
| Development | Projektowanie, diagnoza, regresje. |
| Calibration | Ustalenie progów i limitów przed zamrożeniem. |
| Acceptance | Ocena zamrożonego rozwiązania bez strojenia. |

Podział następuje po rodzinach nagrań i podobnych klatkach. Duplikaty bajtowe i
bliskie kopie nie przekraczają granicy development/acceptance. G00 może
przygotować manifest acceptance, ale obrazy, anotacje, wyniki i porażki
acceptance nie są ujawniane wykonawcy dobierającemu algorytm. Ujawniona rodzina
przestaje być niezależna.

`reels_test` jest zarezerwowany dla V7 i nie wchodzi do geometrii v2.0.
`rells_big` nie jest niezależnym holdoutem.

### Protokół kotwicy

Kotwica pochodzi z wydzielonej puli pomocniczej w development. Nie należy do
ocenianych źródeł ani rodzin acceptance.

1. Uporządkować pulę według rodziny nagrania, pozycji źródła i checksumy.
2. Wybrać pierwszą ręcznie zakwalifikowaną, kompletną stronę o zgodnej topologii
   i widocznej siatce.
3. Zapisać checksumę, anotację, odrzuconych kandydatów oraz czas wyboru i
   oznaczania.
4. Zamrozić tę samą kotwicę dla wszystkich wariantów i nagrań danej gry.

Nie wybieramy kotwicy na podstawie skuteczności na zbiorze ocenianym. Brak
odpowiedniej strony oznacza niedostępny pomiar „po kotwicy”, a nie ukryte użycie
kilku stron. Kotwica pozostaje lokalna dla gry i nie zasila profilu używanego do
oceny tej samej gry.

### Jednostki raportowania

Raport dla każdej gry podaje: poprawność propozycji planszy, poprawne automaty
plansz, poprawne źródła bez interwencji, błędne automaty, źródła i plansze
wymagające interwencji, tylko-potwierdzenia oraz aktywny czas operatora.
Osobno zapisuje koszt konfiguracji ramki, próbki koloru i pierwszej kotwicy.

Mianowniki pochodzą z zamrożonego manifestu. Nieudane dekodowanie,
nierozstrzygnięcie i wykluczenie po uruchomieniu nie znikają z raportu ogólnego.
Osiem poprawnych propozycji nie oznacza ośmiu automatycznych importów, jeżeli
workflow wymaga potwierdzenia. Pusty mianownik to `not_evaluable`.

Dokument bramek G01 określa per gra:

- minimalny automat plansz i źródeł;
- maksymalny nakład korekt;
- tolerancje geometrii;
- minimalne liczby rodzin, zdjęć i automatów;
- pokrycie trudnych warunków;
- limity czasu i pamięci;
- minimalną korzyść ze wspólnej wiedzy.

Zmiana bramek wymaga nowej wersji i ponownego odbioru.

### 777: trzy rozłączne wyniki

1. Niezmienność v1.1 — te same decyzje, geometria i wiedza przy tych samych
   wejściach.
2. Brak regresji v2.0 — każdy wcześniej poprawny automat zostaje poprawny,
   zero nowych błędnych automatów.
3. Pełny odbiór bezpieczeństwa — zero wszystkich zaobserwowanych błędnych
   automatów na wymaganym materiale.

Poprawienie jednego błędu nie kompensuje innego. Błąd obejmuje obrys, siatkę
wewnętrzną, slot, utratę zawartości i fałszywą kompletność pikseli.

## Kontrakty silnika, integracji i biblioteki

### Geometria, kolor i niepełność

Nowy wariant: `shape_frame_geometry_v2_0`. Wszystkie quady są w istniejącej
przestrzeni `exif-normalized-rgb-pixels-v1`; skalowana analiza i rektyfikacja
mają odwracalną transformację do tej przestrzeni.

Silnik rozdziela obrys ramki, obszar analizy, finalną siatkę, widoczność i
decyzję. Oczekiwane sloty są źródłem prawdy: 8 z 9 nie oznacza krótszej strony.
G00 potwierdza topologię 3×5 każdej gry; niezgodność zatrzymuje jej wdrożenie.

Neutralna gałąź wykrywania ma własny budżet. Kolor nie usuwa jej hipotez ani nie
może sam odrzucić wyniku. Hipoteza kolorowa bez niezależnego dowodu nie wpływa
na decyzję. Inna hipoteza z niezależnym dowodem geometrycznym powoduje korektę,
nawet jeśli wynik neutralny byłby automatyczny. Równoważne hipotezy są
deterministycznie deduplikowane.

Kompletna siatka może być automatyczna. Brak dekoracyjnego dołu nie jest
niepełnością, jeśli granice komórek mają osobny dowód. Ucięcie boczne korzysta
z istniejącej maski i ręcznego potwierdzenia; tylko dostępne pola mogą być
renderowane. Ucięcie pionowe i zasłonięte wnętrze pozostają do korekty.

### Izolacja v1.1 i snapshoty

Zakres wiedzy jest jawny: `legacy` dla v1.0/v1.1 i `shape_v2` dla v2.0.
Backend wyprowadza go z przypiętego wariantu. Addytywna migracja rozdziela
rewizje korekt według gry, SHA źródła i zakresu. Dane historyczne pozostają
legacy. Korekta v2.0 nie może dodać ani usunąć kotwicy v1.1, także gdy JPEG ma
tę samą checksumę.

Snapshot preflightu zawiera wariant, topologię, progi, limity, konfigurację
ramki, próbkę koloru, kotwice i opcjonalny profil wspólny; całość jest
checksummowana. Zmiana konfiguracji tworzy nowy preflight. Brak profilu na
cold-starcie jest poprawny; brak przypiętego profilu jest błędem integralności.
Finalna geometria zachowuje obecnego właściciela source geometry revisions.

### Biblioteka: tożsamość, deduplikacja i spóźnione zdarzenia

Tożsamość wkładu to `game_id + knowledge_scope + source_sha256 +
geometry_revision + slot + extractor_version`. Idempotencja dostarczenia używa
identyfikatora zdarzenia i checksummy pełnej treści. Niezależność przykładu jest
oddzielna: kopia JPEG-a w innej grze nie zwiększa liczności dowodów.

Każda linia `(game_id, knowledge_scope, source_sha256)` ma rosnącą generację.
Konsument stosuje wyłącznie najnowszą: starsze zdarzenie zapisuje diagnostykę,
ale nie zmienia przyszłych profili; zgodne powtórzenie jest idempotentne; różna
treść dla tej samej generacji to konflikt. Wycofanie przy usunięciu gry jest
trwałe we wspólnym magazynie, dlatego opóźniony retry nie przywraca wkładu.
Historyczne snapshoty pozostają odtwarzalne.

## Zadania

### G00 — korpus, protokół pomiaru i baseline

Utworzyć manifest SHA, wystąpień, rodzin, duplikatów i ról danych. Potwierdzić
topologię, aktywne sloty i trudności. Utrwalić definicje metryk oraz protokół
kotwicy. Przygotować anotacje development/calibration niezależnie od predykcji.
Zamrozić v1.1 i uruchomić baseline na ograniczonych partiach, najpierw do 10
źródeł na grę. Odbiór wymaga wykrycia driftu i duplikatów oraz raportu per gra;
brak danych jest jawny.

### G01 — eksperyment i bramki

Porównać na development/calibration: konfigurację per gra, kształt/kontrast bez
i z kolorem, bez i z kotwicą oraz bez i z eksperymentalnym profilem transferu
wykluczającym badaną grę. Wynik: algorytm, pseudokod decyzji, format dowodów,
reguły konfliktów, tolerancje, limity i dokument bramek. Użytkownik zatwierdza
bramki przed G02. Brak wykonalności zatrzymuje pracę; brak korzyści transferu
wymaga decyzji o zakresie biblioteki.

### G02 — izolowany silnik v2.0

W proponowanym pakiecie `images/shape_geometry_v2/` zaimplementować
zatwierdzony algorytm bez zmiany historycznych masek, progów i fingerprintów.
Oddzielić ramkę, sloty, siatkę, widoczność oraz decyzję; utrzymać deterministykę
i transformacje współrzędnych. Testy obejmują kolor, konflikt hipotez, tła,
monitor, kolejność, ucięcia i limity. v1.1 nie zmienia wyników.

### G03 — izolacja danych, API, preflight i worker

Rozszerzyć wariant silnika, korekty, resolver profili, kwalifikację kohort i
handler preflightu. Dodać migrację zakresu wiedzy oraz konfigurację v2.0.
Zintegrować backend, OpenAPI, klient, wrapper i test HTTP. Testy obejmują
restart, utraconą odpowiedź, konflikt rewizji, wspólny JPEG w obu zakresach,
równoległe gry i brak wpływu v2.0 na nowy oraz stary preflight v1.1.

### G04 — Admin i kotwica

Udostępnić wybór v1.1/v2.0, diagnostyczny v1.0, konfigurację ramki/próbki,
szkic powiązany z preflightem oraz zapis jednej pełnej kotwicy v2.0. Wszystkie
niewiadome pozostają w kolejce. Odbiór obejmuje odświeżenie, konflikt rewizji,
brak mieszania wariantów i regresję v1.1.

### G05 — import i pilot

Przekazać manifest v2.0 do aktualnego importera i renderera z zachowaniem
proweniencji, masek oraz właściciela sekwencji. Gra bez modelu korzysta tylko z
istniejącego `unclassified_cold_start_allowed`. Test EXIF obejmuje orientacje
1–8, skalowaną analizę, korektę, restart i import: render końcowy musi obejmować
te same piksele co zatwierdzony quad. Pilot nie jest niezależnym odbiorem.

### G06 — trwała biblioteka wkładów

Dodać wspólne repozytorium, wersje profili, rejestr wkładów i historię
kwalifikacji przez migrację Alembic. Intencja publikacji powstaje w transakcji
gry; konsument publikuje osobno. Wdrożyć tożsamość, deduplikację i generacje z
tego dokumentu. Testy obejmują retry, kopię JPEG-a w dwóch grach, nowszą korektę
przed starszą publikacją, wycofanie i opóźnione retry oraz usunięcie gry.

### G07 — adopcja wspólnej wiedzy

Resolver wybiera tylko zgodny aktywny profil i przypina go do preflightu.
Kandydat służy pomiarowi, nie automatycznej adopcji. Brak profilu zachowuje G05,
wycofanie blokuje nowe adopcje, a historyczne joby zostają odtwarzalne. Transfer
do gry nieużytej w budowie profilu musi spełnić bramkę korzyści.

### G08 — niezależny odbiór

Zamrozić kod, konfigurację, profile, kotwice i bramki. Wykonać acceptance bez
strojenia i raportować metryki plansz, źródeł, operatora i zasobów. Sprawdzić
restart i wycofanie dostępności. Niepełny materiał pozostawia grę w pilotażu;
v1.1 pozostaje domyślny.

## Weryfikacja i dokumentacja

Każde zadanie dostaje kartę zgodną z `ai_docs/process/TASK_TEMPLATE.md`.
Najpierw uruchamiane są testy zmienionego pionu, potem formatowanie, Ruff,
mypy/typecheck oraz testy API/UI i build. Zmiana API wymaga
`npm run openapi:check`; UI wymaga właściwych testów Admina, lintu, typechecku
i builda. Testy migracji oraz routingu wykonujemy na izolowanym PostgreSQL.
Domyślny timeout kroku wynosi maksymalnie 120 sekund.

Po każdym zadaniu aktualizowane są wymagania/architektura/Decision Log, jeśli
zmienił się ich kontrakt, a zawsze `CURRENT_STATE.md` i `Outcome`. Zadanie
`done` przenosimy do `ai_docs/tasks/completed/`. Do mainline nie scalamy
częściowego zadania bez jego audytu Astra Medium i zielonych kontroli.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| G00 — korpus i baseline | gpt-5.6-terra | xhigh | Protokół, korpus i baseline wymagają ścisłej proweniencji. | gpt-6-astra, medium — niezależność danych i mianowniki. |
| G01 — eksperyment i bramki | gpt-5.6-terra | xhigh | Porównanie metod, transferu i kosztu operatora. | gpt-6-astra, medium — metodologia i brak strojenia na acceptance. |
| G02 — silnik v2.0 | gpt-5.6-terra | xhigh | Deterministyczna geometria i bezpieczeństwo wyników. | gpt-6-astra, medium — konflikty, współrzędne i false-accept. |
| G03 — izolacja i integracja | gpt-5.6-terra | xhigh | Migracja, zakres wiedzy, API i snapshoty. | gpt-6-astra, medium — izolacja legacy i recovery. |
| G04 — Admin i kotwica | gpt-5.6-terra | xhigh | Trwałe szkice i decyzje operatora. | gpt-6-astra, medium — regresja UI i tożsamość decyzji. |
| G05 — import i pilot | gpt-5.6-terra | xhigh | Integracja renderowania i danych gry. | gpt-6-astra, medium — EXIF, proweniencja i separacja. |
| G06 — trwała biblioteka | gpt-5.6-terra | xhigh | Idempotencja, deduplikacja i kolejność zdarzeń. | gpt-6-astra, medium — wycofanie, retry i usunięcie gry. |
| G07 — adopcja wiedzy | gpt-5.6-terra | xhigh | Profile i transfer między grami. | gpt-6-astra, medium — kwalifikacja i replay. |
| G08 — niezależny odbiór | gpt-5.6-terra | xhigh | Pełna ocena bramek na zamrożonym rozwiązaniu. | gpt-6-astra, medium — kompletność dowodów i DoD. |
