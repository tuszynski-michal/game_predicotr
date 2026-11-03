# Odbiór przyrostowego uczenia korekt — 2026-11-03

TASK-1147 pozostaje `in_progress`. Migracja, uruchomienie usług i kontrola
panelu są potwierdzone; pojedynczy przebieg uczenia oczekuje na wynik.
Ten raport nie potwierdza sukcesu treningu ani zastosowania modelu.

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
