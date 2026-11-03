# Odbiór przyrostowego uczenia korekt — 2026-11-03

Odbiór operacyjny zakończony: migracja0179, usługi, liczniki oraz rzeczywiste uczenie i końcowe porównanie PASS. Model domyślny pozostał Mumie v1. Końcowy wynik i ograniczenia są w ostatniej sekcji; wcześniejsze sekcje zachowują historyczne checkpointy.

## Wersja i dowody

Prowadzący wdrożył root/main `5cfe292b` (v1.7.544), po checkpoincie integracji
`08a9ffcf` i synchronizacji z `be10f90e`. Operacje wykonał po uzgodnieniu okna
z koordynatorem wcześniejszego wdrożenia 0177. Autor tego dokumentu odczytał
dowody, bez wykonywania operacji na usługach lub danych operatora.

Dowody znajdują się w `D:/game_predicotr/artifacts/grid-growth-deploy-20261103/`.
Nazwy plików poniżej odnoszą się do tego katalogu. Stary
`coordination-state.json` opisuje wcześniejsze oczekiwanie na przekazanie okna;
aktualny stan potwierdzają datowane logi i snapshoty opisane poniżej.

## Migracja i zachowanie danych

`database-before.json` potwierdza bazę `game_predictor` na `127.0.0.1:5432`
z rewizją `0177_source_replacement_purge`. `migrate-1.log` dokumentuje rzeczywisty
upgrade do `0178_grid_correction_growth`, a `database-after.json` potwierdza
końcową rewizję. Kontrola roli aplikacyjnej w `migrate-2.log`: `compliant=true`,
brak błędów uprawnień recording, brak superuser/bypassRls i zapisu do tabel
przeznaczonych tylko do odczytu. P2-5 audytu zamknięte odczytem właściwej
tożsamości i rewizji przed migracją.

| Miara | Przed i po migracji |
|---|---:|
| Źródła | 166971 |
| Plansze | 1500019 |
| Komórki przeglądu symboli | 22248975 |

Hashe aktywacji modeli symboli i profili siatek są identyczne przed i po.
Po migracji `purged_sources=0`. Te snapshoty poprzedzają start nowego uczenia;
nie stanowią dowodu ukończenia ani zastosowania jego wyniku.

## Standardowy build i usługi

Standardowe `npm run typecheck --workspace @game-predictor/admin` oraz
`npm run build --workspace @game-predictor/admin` w głównym checkout przeszły
bez tymczasowych aliasów. Dowody: `root-typecheck.log` i `root-build.log`.
P2-2 audytu zamknięte; wcześniejszy wynik z aliasami worktree nie jest już
jedynym dowodem buildu po integracji.

`services-after.json`: API PID 26164 na porcie 8000, Admin PID 53204 na 3000,
uruchomione 11:07:46 UTC. `latest-ready.json` zawiera health `ok`.
`start-workers-0.log`: general running, launcher 48620, worker 44044,
7 wątków, start 11:11:19 UTC. `start-workers-1.log`: grid-training running,
launcher 33008, worker 11192, 1 wątek, start 11:11:22 UTC.
PID opisuje ten odczyt, nie upoważnia do późniejszego zatrzymania procesu bez
ponownego sprawdzenia jego tożsamości. `workers-status-0.log` pochodzi z etapu
przejściowego i nie opisuje końcowego stanu po uruchomieniu.

## Panel i liczniki przed nowym uczeniem

Prowadzący sprawdził rzeczywisty Admin: odświeżanie pokazuje stan ładowania
i nowy czas aktualizacji. Weryfikacja aktualności istniejącej oceny zakończyła
się stanem verified; zaznaczenie potwierdzenia odblokowało przycisk Apply.
Nie kliknięto Apply, nie opublikowano ani nie zastosowano modelu.

`latest-ready.json` potwierdza:

| Kategoria | Plansze | Zdjęcia/źródła |
|---|---:|---:|
| Zatwierdzone | 196 | 133 |
| Dostępne TRAIN | 146 | 98 |
| W zapisanych zestawach TRAIN | 77 | 60 |
| Nowe TRAIN | 69 | 38 |
| VALIDATION | 17 | 13 |
| REGRESSION | 21 | 13 |
| Rezerwa VALIDATION / REGRESSION | 0 / 0 | 0 / 0 |
| Bufory | 12 | 53 |
| Wyłączone zatwierdzone | 12 | 9 |

Powód wyłączenia: `GRID_CORRECTION_BUFFER`. Bufory obejmują także źródła bez
zatwierdzonych etykiet; ich 53 źródeł nie należy sumować z liczbą zatwierdzonych
zdjęć. Zapis w zestawie TRAIN oznacza zamrożone etykiety, nie dowód ukończenia
wcześniejszego treningu.

## Pojedynczy start z UI — trwałe potwierdzenie

Rzeczywisty przycisk Admin utworzył dokładnie jeden nowy przebieg:
`cc7e739e-027c-4f44-87d8-8088c0d86bb1`, gra
`246a1f54-eee8-49d5-b11a-0fde70e5eecd`, utworzony 11:16:12.734418 UTC.
`learning-start-origin.json` zapisuje pochodzenie `actual Admin UI button`
i `doNotPostAgain=true`. `learning-start-response.json` oraz późniejszy odczyt
`history-after-ui-start.json` zawierają ten sam identyfikator. Jest to zapisane
potwierdzenie pojedynczego startu; dalsza obserwacja używa tego identyfikatora,
bez ponownego POST lub kliknięcia startu.

Odczyt `latest-status.json` z `updatedAt=2026-11-03T11:17:19.434303+00:00`
ma status `processing`, etap `learning`, kohortę
`8c4d3ab4-4d01-59fe-a826-46883b72ddfe`, `trainingRunId=null` i brak błędu.
Trening, ocena i raport nie są jeszcze potwierdzone. Prowadzący monitoruje
ten sam przebieg i dopisze końcowy wynik; nie uruchamiać duplikatu.

## Przejściowa odmowa zatrzymania w Windows

Według obserwacji prowadzącego standardowy Stop general zwrócił
`KillAccessDenied` podczas wychodzenia conhost. Świeży odczyt CIM potwierdził
brak właściwego launchera, workera i helpera; pojedyncze idempotentne
powtórzenie zakończyło oba Stop kodem 0 (`stop-workers-0.log`,
`stop-workers-1.log`). Nie zmieniano produktu i nie dublowano usług.

Instrukcja operatorska: przy tej odmowie sprawdzić zakończenie procesu oraz
tożsamość PID w świeżym odczycie. Dopiero po potwierdzeniu braku własnych
procesów powtórzyć standardowy Stop. Nie zabijać nieznanego PID ani nie
uruchamiać kolejnej kopii usługi na podstawie samej odmowy.

Ignorowany runner wdrożenia poprawiono tak, aby zapisywał wyjście do plików.
Początkowy helper PID 4632 zakończono po sprawdzeniu jego tożsamości. To
obejście narzędzia operacyjnego, nie naprawa mechanizmu Stop w produkcie.

## Pozostały odbiór

Odczytać końcowy wynik wskazanego uczenia, zapisać identyfikatory runu i oceny
oraz potwierdzić brak zastosowania modelu. Dopiero prowadzący rozliczy pełny
odbiór, dalszy push/sprzątanie i zamknięcie TASK-1147. Ten checkpoint ich nie
potwierdza.

## Checkpoint rzeczywistego odbioru — blokady1149/1150

Pierwszy freeze parenta `cc7e739e-027c-4f44-87d8-8088c0d86bb1` przekroczył60s. Normalny replay tego samego polecenia `freeze:163` i oryginalnego klucza zamroził kohortę `8c4d3ab4-4d01-59fe-a826-46883b72ddfe` do rewizji164 w53,515s; blokady wejść33,641s. To dowód poprawnego zapisu, ale nie trwała naprawa kosztu; TASK-1149 ogranicza per-row SQL do partii200 bez zmiany blokad/limitów.

Oficjalne resume tego samego parenta zachowało historię i utworzyło tylko run `7a1b3835-639c-4439-8f49-3dfaea5e650a`. Dziecko zakończyło się na kroku488: `PermissionError [WinError5]` w atomowym `os.replace` pliku postępu. Budget pozostał488/8000 kroków i161,969/7200 sekund, attempt1; brak kandydata i zmiany defaultu. TASK-1150 dodaje krótki ograniczony retry tej samej podmiany. Nie wznowiono ponownie przed poprawką.

Bramka odbioru pozostaje otwarta: sam PASS statycznego audytu1147 i poprawne liczniki nie stanowią sukcesu uczenia. Źródła: root `artifacts/grid-growth-deploy-20261103/freeze-profile-result.json`, `failed-training-job.json`, `latest-training.json` oraz diagnostyka runa. Zakres naszego178 nie został jeszcze wypchnięty.


## Checkpoint po audytach 1149/1150 i pauza operacyjna

TASK-1149 zamknięto jako v1.7.546 / `4827f2a6`; TASK-1150 jako v1.7.547 / `5efb3ea0`. Oba rzeczywiste audyty Claude Code Opus 5.5/high zakończyły się PASS bez P0/P1. Drobne uwagi P2 rozliczono testami. Zmiany pozostają na gałęzi roboczej; root/main nadal `5cfe292b`, DB0178, origin/main `be10f90e`.

Kontrolowany odczyt blokad nowym helperem na tej samej kohorcie trwał 3,968s zamiast poprzednich 33,641s; transakcja została jawnie wycofana, stan frozen/revision164 pozostał niezmieniony. Testy Windows obejmują rzeczywisty uchwyt pliku bez FILE_SHARE_DELETE. Są to dowody napraw mechanizmu, nie ukończenia treningu.

Koordynator drugiego okna potwierdził osobną regresję wyszukiwania plansz w filtrze źródeł 0175/0176. Zarezerwował TASK-1151 i migrację0179. Uzgodniono pauzę: bez kolejnych freeze, restartów i resume do gotowej, przetestowanej i audytowanej poprawki oraz ustalenia jednego właściciela wspólnego wdrożenia. Nie uruchomiono nowych zadań GPU. Zachowano parent `cc7e739e-027c-4f44-87d8-8088c0d86bb1`, dziecko `7a1b3835-639c-4439-8f49-3dfaea5e650a` i ich dotychczasowe zużycie budżetu.


## Odbiór końcowy — 0179 i rzeczywiste uczenie PASS

Po skoordynowanym wdrożeniu root/main i origin/main `d01a0f07cc72d44f54711cd1a1a60a27df4823df` baza ma jedyny head `0179_empty_replacement_search`. Kontrola ról compliant, API/Admin działają, worker general7 i grid-training1 uruchomione z nowego procesu. Dane przed/po179 identyczne:166971źródeł,1500019plansz,22248975pól, purged0, te same hashe aktywacji. TASK-1151 zamknięto osobno po rzeczywistym wyszukiwaniu; naprawa nie zmienia danych ani zakresu modeli.

Oficjalne resume12:53:41UTC wznowiło ten sam parent `cc7e739e-027c-4f44-87d8-8088c0d86bb1` i dziecko `7a1b3835-639c-4439-8f49-3dfaea5e650a`. Nie powstał drugi run ani nowy budżet. Attempt2 poprawnie zapisał checkpointy i eksport; wykonał2400kroków, zakończył przez early_stopping i wybrał checkpoint1200 na VALIDATION. Progress3600/3600 oznacza zamknięcie planu, nie wykonanie3600kroków. Łączne zużycie2888/8000kroków zawiera wcześniejsze488; czas865,313/7200s, bez resetu/odnowienia. `result-1.json` zachowuje wcześniejszy błąd, `result-2.json` potwierdza exported/early_stopping.

Automatyczna ocena `eeb70311-2ab7-4e2e-9961-4ff9aac6821a` zakończyła się13:07:04UTC wynikiem PASS, raport `0cd1539a-412f-561c-a022-838577c09f62`, kandydat `3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e`. Porównano te same oryginalne zdjęcia:

| Rola | Zdjęcia / opisane plansze | Poprawne baza / kandydat | Średni znormalizowany błąd baza / kandydat | Spadek błędu |
|---|---:|---:|---:|---:|
| VALIDATION |13/17|12/14|0,01734436/0,01316342|24,11%|
| REGRESSION |13/21|15/17|0,01442749/0,01180831|18,15%|

Wykryte odpowiednio17/17 i21/21 dla obu modeli. Gate v2 PASS i ONNX parity PASS. Wszystkie zdjęcia kontrolne są częściowo opisane: ocena dotyczy opisanych plansz, bez miary fałszywych detekcji poza nimi. Dowód photo-only nie potwierdza niezależności sesji ani nieznanego wykorzystania danych przez przodków; zweryfikowany zakres obejmuje wyłącznie MumieA2. Nie deklarujemy jakości innych gier ani istotności statystycznej.

Po freeze liczniki:196zatwierdzonych/133zdjęcia, TRAIN146/98; zapisane TRAIN146/98 i nowe0/0, VALIDATION17/13, REGRESSION21/13. Nowe69plansz z poprzedniego podglądu weszły do zamrożonego TRAIN; dlatego licznik nowych spadł do0. Bufor12opisanychplansz/53źródła, wyłączone12/9 bez zmian. Zachowano niezależną od TRAIN pulę testową i ochrony.

Rzeczywisty Admin po restarcie pokazał PASS i powyższe liczniki. Przycisk sprawdzenia aktualności przeszedł w loading, zakończył się potwierdzeniem i nowym preview. Zaznaczenie potwierdzenia odblokowało Apply; checkbox następnie odznaczono, Apply nie kliknięto. Default oraz przypisanie MumieA2 pozostały Mumie v1, revision1. Kandydat oczekuje na osobne zastosowanie operatora. Starsze importy i ręczna geometria nie zostały przeliczone.

Dowody w root `artifacts/grid-growth-deploy-20261103`: `before-resume-afterfix.json`, `learning-resume-afterfix-intent.json`, `learning-resume-afterfix-response.json`, `afterfix-history.jsonl`, `latest-afterfix.json`, `final-evaluation.json`, `latest-ready.json`, `database-before179.json`, `database-after179.json`, `final-panel-pass.png`. Rzeczywisty obraz panelu pokazuje tabelę15→17poprawnych w kontroli końcowej. Historyczne checkpointy raportu powyżej pozostają zapisem kolejnych etapów, nie aktualnym blockerem.

DoD: kod i kontrakt, migracje/restart, liczniki, aktualność i rzeczywisty trening/ocena potwierdzone. Audyty1139/1140/1145/1147/1149/1150 i1151 rzeczywiste, bez otwartych P0/P1; P2 oraz zastane niepowiązane FAIL opisane w raportach. Nie zgłaszamy pełnego globalnego quality/mypy PASS. Końcowy commit dokumentuje odbiór, a późniejszy metadata commit zapisze jego hash oraz finalny push.
