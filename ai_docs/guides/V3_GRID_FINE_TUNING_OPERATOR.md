---
title: Doszkalanie geometrii V3 — instrukcja operatora
status: active
last_updated: 2026-11-04
---

# Doszkalanie geometrii V3 — instrukcja operatora

Instrukcja opisuje cały przebieg doszkalania siatek V3 z poprawek w aplikacji:
od kontroli jakości do aktywacji nowej wersji i ponownego rozpoznania. Dotyczy
gier V3 (np. Mumie, 777a2). Historyczna gra 777 (kod `7`) pozostaje archiwalna
i nie bierze udziału w tym procesie. Modele symboli są osobne dla każdej gry i
nie są doszkalane tym przebiegiem.

Źródła prawdy: plan
[V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md),
decyzje D-548–D-560 w
[DECISION_LOG_2026](../process/decisions/DECISION_LOG_2026.md) oraz wymagania
„Pełna sekcja Geometria V3” w [ADMIN_APP](../requirements/ADMIN_APP.md).
Wynik odbioru: [V3_GRID_FINE_TUNING_ACCEPTANCE](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md).

## 1. Warunki wstępne

- Dla nowego przepływu pełnych plansz wymagany jest head
  `0181_validation_purposes`; kolejność i osobne zgody opisuje sekcja6.
  To wymaganie wdrożenia, nie potwierdzenie stanu bazy operatora. Rola capability
  z D-554 musi istnieć przed `0161` i zostać poprawnie doprowadzona do v8.
- Usługi z `D:\game_predicotr`: API (`npm run api:dev`), Admin
  (`npm run admin:dev`), Reviewer (`npm run reviewer:dev`).
- Workery (sterowane skryptem `scripts/manage_worker_lanes.ps1`):
  - `npm run workers:start` — tylko lane `general` (kohorty, ocena kandydata,
    ponowne rozpoznanie, importy);
  - `npm run workers:start:all` — `general`, `image-selection` oraz
    `grid-training`, ale ten ostatni tylko wtedy, gdy skrypt znajdzie
    interpreter CUDA (niżej);
  - `npm run workers:start:grid-training` — tylko lane `grid-training` (trening na
    GPU); bez interpretera odmawia startu;
  - `npm run workers:status` i `npm run workers:stop` obejmują zawsze wszystkie
    lane i wszystkie procesy zapisane przez skrypt, niezależnie od interpretera.
  - Trener GPU potrzebuje interpretera z CUDA, torch i onnxruntime. Skrypt bierze
    go kolejno z parametru `-GridTrainingPython <ścieżka>`, ze zmiennej
    `GAME_PREDICTOR_GRID_TRAINING_PYTHON` (procesu albo użytkownika Windows) albo z
    `.venv-vision-lab\Scripts\python.exe` checkoutu. Bez interpretera
    `-Lane grid-training` odmawia startu, a `-Lane all` pomija ten lane. Worker
    uruchomiony ręcznie (`npm run worker:grid-training:poll`) bez zmiennej startuje,
    ale każdy run kończy się kodem `GRID_TRAINING_PYTHON_UNSET`.
  - Stan 2026-10-16: środowisko `D:\game_predicotr\.venv-vision-lab` (torch
    2.12.1+cu130) istnieje, więc skrypt znajduje interpreter sam, bez parametru
    i zmiennej. Środowisko w starym checkoucie na C nie jest już używane.
    Odtworzenie: [VISION_LAB_LOCAL](VISION_LAB_LOCAL.md), sekcja „Izolowane
    środowisko treningowe T04”.
- Lane `grid-training` ma jeden slot GPU. Drugi run czeka w kolejce; zajęte
  GPU nie jest błędem runu. Orientacyjnie: kohorta 30 plansz TRAIN, preset
  `grid-only-v1`, 1200 kroków to około 5 minut treningu na lokalnym GPU (pomiar
  odbioru TASK-1001 na danych syntetycznych).

## 2. Przebieg w Adminie

Admin → Jakość modelu → wybór gry V3 → sekcja **Geometria V3**. Wejście na ekran,
zmiana gry i odświeżenie strony tylko odczytują dane. Każda zmiana jest
osobnym przyciskiem. Identyfikatorów nie trzeba wpisywać; sekcje
„Zaawansowane” są potrzebne tylko w nietypowych przypadkach.

1. **Przypisana wersja** — aktualna wersja geometrii gry, rodzina i powód
   kwalifikacji.
2. **Nagrania i role** — grupy nagrań gry i ich role: `TRAIN`, `VALIDATION`,
   `REGRESSION`. Nagranie kontrolne nie może być jednocześnie treningowym; ta
   sama treść zdjęcia w dwóch rolach jest odrzucana jako alias.
3. **Kontrola jakości (próbka)** — losowa próbka siatek do oceny w Reviewerze.
   Poprawki człowieka w Reviewerze są jedynym źródłem etykiet treningowych.
4. **Dane do doszkalania (kohorty)** — rodzina i baza pochodzą z przypisania
   gry. Wybierz import po nazwie i dacie, zaznacz nagrania i ich role, potem
   „Podgląd”. Podgląd pokazuje kwalifikację i powody blokad. „Utwórz kohortę”
   zamraża niezmienny snapshot; późniejsze poprawki go nie zmieniają.
5. **Trening** — wybierz zamrożoną kohortę po etykiecie. Podgląd pokazuje
   blokady; start jest dostępny tylko bez blokad. Opcjonalnie dołącz kohorty
   innych gier V3 tej samej rodziny, aby wytrenować kandydata wspólnego.
   Run można anulować i wznowić według jego stanu. Wynik runu to kandydat ze
   stanem `not_evaluated`, nigdy aktywna wersja.
6. **Porównanie z bazą** — wybierz run i uruchom ocenę. Kohorty wspólnego
   treningu są oceniane zawsze; inne gry rodziny można dodać po nazwie. Raport
   ma werdykt dla każdej gry osobno (polityka `grid-model-per-game-gate-v1`):
   - brak pogorszenia na `photo_complete_correct`, `boards_correct`,
     `boards_matched`, `false_boards`, `duplicate_predictions` i `image_macro`;
   - gra treningowa musi się poprawić.
   „Sprawdź aktualność” porównuje dowody kohort z bazą. Stan `stale`,
   `missing` albo `unavailable` blokuje publikację do czasu nowej oceny.
7. **Wersje** — publikacja kandydata wymaga oceny `PASS` z aktualnymi
   dowodami wszystkich kohort. Po publikacji: „Aktywuj dla gry”, „Ustaw jako
   domyślną” dla nowych gier oraz przywrócenie wcześniejszej wersji z historii
   gry. Każda z tych operacji jest osobną decyzją operatora.
8. **Ponowne rozpoznanie** — podgląd i uruchomienie dla wybranego zakresu
   siatek aktywną wersją (domyślnie zgłoszone „Złe siatki” i odroczone sloty;
   siatki niepotwierdzone i wszystkie automatyczne to osobne zakresy). Skutek
   zależy od stanu celu:
   - zgłoszona „Zła siatka” — trwała propozycja w Korekcie cięcia siatki
     Reviewera; zmienia się dopiero po decyzji człowieka, a aktualne wycinki i
     zgłoszenie zostają bez zmian;
   - geometria chroniona albo decyzja człowieka — brak nadpisania, raport
     przyczyny ochrony;
   - odroczony slot bez konfliktu — **zapis automatyczny** po bramce i ponownej
     kontroli aktualnego stanu;
   - niechroniona automatyczna plansza z wybranego zakresu — **zapis
     automatyczny** po bramce i sprawdzeniu rewizji oraz właściciela;
   - zmienione źródło, rewizja albo właściciel — konflikt, stary wynik nie jest
     zapisywany.
   Każde uruchomienie zaczyna się od pilota do 100 zdjęć; szerszy zakres wymaga
   oceny raportu pilota i osobnego potwierdzenia. Raport rozdziela propozycje,
   zapisy automatyczne, ochronę, brak zmiany, konflikty i brak źródła; ani
   propozycja, ani zapis automatyczny nie są dowodem poprawy jakości.

Ponowne rozpoznanie działa także bez treningu, aktualną bazą (krok 8 bez
kroków 4–7).

## 3. Utrata odpowiedzi, restart i ponowienie

- Polecenia runu, oceny i wersji zapisują klucz idempotencji i treść przed
  wysłaniem. Gdy odpowiedź zginie (zamknięta karta, restart API), panel po
  powrocie pokazuje oczekujące polecenie z przyciskiem ponowienia. Ponowienie
  z tym samym kluczem zwraca ten sam wynik zamiast tworzyć drugi run.
- Joby są trwałe w PostgreSQL. Po restarcie workera wygasła dzierżawa wraca do
  kolejki, a trening wznawia się od ostatniego zapisanego punktu.
- Usługi uruchamia i zatrzymuje operator. Po scaleniu zmian kodu Admin i
  Reviewer wymagają restartu albo przebudowy (`npm install`, build).

## 4. Typowe blokady

Panel pokazuje etykietę każdej blokady; nieznany kod ma postać
„Inny powód (KOD)”. Najczęstsze przypadki:

- kohorta bez danych `TRAIN` albo bez nagrań kontrolnych — dodaj poprawki w
  Reviewerze lub nagrania z właściwą rolą;
- źródło zmienione po zamrożeniu kohorty — utwórz nową kohortę;
- ocena nieaktualna — uruchom nową ocenę;
- `REVISE` albo `NOT_EVALUABLE` — kandydat nie jest publikowany; to
  dopuszczalny wynik eksperymentu, nie podstawa do osłabienia bramki.
- `GRID_TRAINING_ONNX_PARITY_FAILED` — eksport ONNX różni się od modelu torch
  ponad tolerancję względną 1e-4 (D-561). Pomiar różnic jest w
  `artifacts/grid-training/runs/<run>/parity-failed.json`; run można wznowić
  dopiero po wyjaśnieniu przyczyny.

## 5. Czego proces nie robi

- Nie wdraża i nie aktywuje modeli automatycznie.
- Nie uruchamia treningu na danych operatora bez polecenia operatora.
- Nie zmienia historycznej gry 777 ani modeli symboli.
- Nie przetwarza masowo zdjęć poza wybranym zakresem ponownego rozpoznania.

## 6. Pełne plansze: przygotowanie wdrożenia T0–T6

Ta sekcja jest instrukcją do osobnego zatwierdzenia. Odbiór kodu, testów i audytu
nie oznacza zgody na migrację, zapis diagnostyk, usługi, trening, inferencję,
publikację, aktywację lub integrację. Zestaw dowodów i jawne niewykonane kroki
zawiera [TASK-1160_VERIFICATION](../quality/TASK-1160_VERIFICATION.md).

### Migracje i zgodność wersji

1. Zapisz planowany commit wydania oraz obecne wersje, przypisania, default i ich
   rewizje z istniejących odczytów. Zweryfikuj rzeczywisty revision bazy; nie opieraj
   go na historycznej informacji z czatu. Operator zatwierdza okno i zatrzymuje
   API oraz wszystkie odpowiednie workery, aby nie powstawały nowe dowody podczas
   zmiany schematu. Agent nie przejmuje procesów ani portów.
2. Po osobno zatwierdzonej integracji wdrażaj ten sam release API, workerów i UI/SDK.
   Alembic prowadzi liniowo przez `0179_empty_replacement_search`,
   `0180_screen_grid_corrections`, następnie `0181_validation_purposes`.
   Jeśli wcześniejszych migracji brakuje, użyj istniejącej ścieżki Alembic;
   nie zastępuj jej ręcznym DDL i nie pomijaj migracji.
3. Z wdrożonego `D:/game_predicotr` istniejące `npm run db:migrate` najpierw
   przygotowuje rolę recording capability, wykonuje Alembic upgrade head, potem
   końcowe provisioning ról. Sprawdź `npm run db:current` i `npm run db:roles:check`.
   Oczekiwane v8 publiczne capabilities obejmują `recording_cohort_command_v5`,
   `recording_photo_context_v3`, `recording_training_scope_v1` i
   `recording_diagnostic_use_v1`. Funkcje wewnętrzne zachowują prywatne uprawnienia,
   stałego właściciela i search_path. Brak praw nie jest zgodą na szerokie GRANT.
4. Nowy kod ze schema0180 nie jest gotowy do nowych A/B/v4 lub registration.
   Stary worker przy schema0181 nie może rozpoznawać B jako A: legacy SQL fences
   odmawiają nowego użycia. Nie obiecujemy poprawnego mieszania wersji API i workerów.
   Historyczne formaty v6/v7 i piny zachowują semantykę, co nie zastępuje zgodności
   nowego release. Po sprawdzeniu schematu i uprawnień operator uruchamia usługi.

Każdą skończoną komendę administracyjną ogranicz do120s. Poniższy helper działa
w nowym procesie z zapisanej konfiguracji wdrożonego checkoutu. Zwrócony błąd lub
timeout zatrzymuje procedurę; najpierw ustal stan własnego procesu i migracji,
nie uruchamiaj drugiej kopii. Nie zmieniaj globalnego PATH ani środowiska .venv.

```powershell
Set-Location D:/game_predicotr
$gridOperatorPython = (Resolve-Path .venv/Scripts/python.exe).Path
function Invoke-GridOperatorCheck {
    param([string[]]$Command)
    & $gridOperatorPython -c 'import subprocess,sys; subprocess.run(sys.argv[1:],timeout=120,check=True)' @Command
    if ($LASTEXITCODE -ne 0) { throw 'Kontrola nie powiodła się; zatrzymaj procedurę.' }
}
# Odczyty gotowości; nic nie migrują i nie uruchamiają usług.
Invoke-GridOperatorCheck -Command @('npm.cmd', 'run', 'db:current')
Invoke-GridOperatorCheck -Command @('npm.cmd', 'run', 'db:roles:check')
# WYŁĄCZNIE po osobnej zgodzie na migrację i zatrzymaniu usług przez operatora:
# Invoke-GridOperatorCheck -Command @('npm.cmd', 'run', 'db:migrate')
```

### Diagnostyki przed nowym B/REG

Ściśle zarejestrować trzeba rzeczywiste użycie diagnostyczne T1 wraz z zamknięciem
znanych kopii/grup, zanim przygotuje się nowe VALIDATION-B lub REGRESSION. Sam
odczyt readiness134 zdjęć nie był takim użyciem i nie wchodzi do tej rejestracji.
Nie wolno hardkodować źródeł w produkcie ani ręcznie zmieniać dawnych ról.

Manifest przygotowany w T4 ma status **staged_not_registered**:
`D:/game_predicotr/artifacts/full-board-detection/operator-diagnostic-registration/task1158-v1.json`.
Oczekiwany SHA256:
`e4a3a120404f225e478ac13aba708e048706e1a3e73f3eb7a11f7b4e4523e172`.
Dwa record bindings odpowiadają jednemu source-use po deduplikacji. Payload jest
prywatny, poza Git i pakietami audytu; instrukcja nie potwierdza wykonania zapisu.

Po osobnej zgodzie na wdrożenie/migrację0181 i ten zapis, z tego samego checkoutu
i helpera120s, najpierw porównaj SHA. Niezgodność blokuje wykonanie:

```powershell
# Get-FileHash uruchomiony w ograniczonym procesie, bez odczytu/drukowania payloadu.
Invoke-GridOperatorCheck -Command @('powershell.exe', '-NoProfile', '-Command',
    "if ((Get-FileHash -Algorithm SHA256 -LiteralPath 'D:/game_predicotr/artifacts/full-board-detection/operator-diagnostic-registration/task1158-v1.json').Hash.ToLowerInvariant() -ne 'e4a3a120404f225e478ac13aba708e048706e1a3e73f3eb7a11f7b4e4523e172') { throw 'Manifest SHA mismatch' }")
# WYŁĄCZNIE po zgodzie operatora; nie wykonywano w odbiorze T6:
# Invoke-GridOperatorCheck -Command @($gridOperatorPython, 'scripts/register_grid_diagnostics.py', 'execute',
#     '--manifest', 'D:/game_predicotr/artifacts/full-board-detection/operator-diagnostic-registration/task1158-v1.json',
#     '--actor', 'local-owner', '--approved-deployment')
```

Writer używa statement_timeout10s/lock_timeout3s. Dokładny retry odtwarza receipt,
nie tworzy drugiego użycia. Potwierdź trwały wynik i closure z nowej sesji odczytu
przed nowym B/REG. Sama obecność pliku manifestu nie potwierdza rejestracji.

### NTFS, wznowienie i przywrócenie

- Artefakty ratunku wymagają same-volume hard links z publikacją no-replace.
  D: był potwierdzony jako NTFS. Rezerwacja jest zapisana przed obliczeniem;
  brak wyniku po crash nadal zużywa próbę. Zmiana wariantu nie odnawia budżetu1+1.
  Alias innych pozycji nie może przedstawiać wcześniejszej próby jako własnej.
- Sprawdzenie crash/replay procesu nie dowodzi odporności na utratę zasilania.
  Nie ma gwarancji directory fsync ani automatycznego GC orphan `.rescue-pending-*`.
  Nie usuwaj tych plików lub receiptów jako kroku tej instrukcji. Inny filesystem
  wymaga odrębnej weryfikacji; błąd dowiązania pozostaje fail-closed.
- Downgrade0181 odmawia po historii kohort v4, niepustym validation_purpose lub
  diagnostic_comparison use: `Purpose history prevents downgrade.` Downgrade0180
  odmawia po chronionej historii v3. Nie kasuj historii, aby ominąć te warunki.
  Wycofanie kodu musi zachować zgodny czytnik i schema; pełne odtworzenie bazy
  wymaga osobnego planu backup/restore operatora.
- Przywrócenie modelu jest osobną operacją istniejącego `rollbackGameGridModel`:
  wybierz wcześniejszy target z historii tej samej gry, sprawdź aktualną eligibility,
  użyj nowego klucza i bieżącej expectedRevision. Default ma osobną komendę.
  Nie obiecuj odtworzenia modelu, którego artefakt/dowód już nie spełnia kontraktu.
  Exact retry starej operacji zachowuje jej pin **razem z polityką**, bez ponownego
  wyboru kwalifikacji lub budżetu. Apply/rollback dotyczy nowych operacji i nie
  przelicza historycznych importów ani nie zmienia ręcznych geometrii i symboli.

### Jak czytać gotowość i porównanie

Raw-quality PASS, automatic qualification i human approval to różne fakty.
Brak B/REG blokuje kwalifikację automatu, ale nie inaczej dopuszczalny trening,
propozycje lub ręczne zastosowanie. Screen TRAIN/A wymaga pełnych zdjęć; grid-only
zachowuje częściowe A, a B/REG ocenia wszystkie opisane cele bez uznawania reszty za tło.
Rzeczywiste zatwierdzenie wszystkich9 slotów tworzy full-photo GT; dostępność obrazu
lub otwarcie edytora nie tworzy GT. TRAIN uczy, A wybiera checkpoint/routing/menu,
B dobiera progi, REG pozostaje końcowym zamrożonym odbiorem.

Raport pokazuje wszystkie propozycje, także zatrzymane, oraz oddzielnie poprawne
i błędne dopuszczenia, przycięcia/unknown coverage i udział zatrzymanych celów.
Porównuje tę samą bazę z polityką T0 oraz oddzielny pre-T0 comparator; odrzucenie
wszystkiego nie jest poprawą. Liczby B i REG wymagają per gra po30 dedup dobrych
i30 złych źródeł bazy, z raportem nakładania i zależności. Nie oznacza to60
niezależnych sesji ani gwarancji statystycznej. Szczegóły liczników i brakujące
rzeczywiste pomiary są w raporcie odbioru T6; partial GT nie daje FP/whole-photo claims.
