---
title: Odbiór uczenia wspólnego modelu siatek z korekt
status: active
last_updated: 2026-11-02
---

# Uczenie siatek z korekt — odbiór implementacji

## Zakres i dowód

Implementacja dotyczy zapisu korekt geometrii, przygotowania danych, treningu
istniejącego modelu, oceny oraz osobnego, ręcznie potwierdzanego zastosowania.
Nie jest to raport wzrostu jakości rzeczywistego modelu: nie wykonano treningu
ani inferencji porównawczej na danych operatora. Testy używają kontrolowanych
predyktorów lub dowodów w jasno wskazanych granicach, a operacje PostgreSQL,
blokady, registry receipts, role i odczyty plików pozostają rzeczywiste.

T1: `e1fcae27` / v1.7.517, T2: `7801ea47` / v1.7.518,
T3: `470faf46` / v1.7.519. T1–T3 mają osobny Opus 5.5/high PASS po
jednej rundzie poprawek. T4 otrzymało
[Opus 5.5/high PASS w rundzie 1](TASK-1123_AUDIT_claude-opus-5-5.md),
bez P0/P1. Audyt jest statyczny; uruchomienia testów wykonał zespół implementacji.
T4: v1.7.520; pełny hash zapisuje `task-close record-hash` w Outcome oraz stanie projektu.

## Odczyt danych operatora wykonany w T1

Populacja gry `mumie-aktu2` (246a1f54-eee8-49d5-b11a-0fde70e5eecd):
788 zdjęć, 7092 plansze, 117 aktualnych ludzkich zatwierdzeń dokładnych 24 punktów
na 89 zdjęciach. Importy 479 i 309 zdjęć; zatwierdzenia są w pierwszym. Wszystkie pliki
istniały, 788 źródeł miało atesty, brak wykrytych dokładnych kopii bajtów/pikseli.
Podobnie nazwana `mumie-a2` (8563b353-9c5c-4282-bed5-825412d8bdd1) była pusta.

Zatwierdzony przez operatora wariant kolejności z samych zweryfikowanych atestów
(zarządzane nazwy SHA zamiast utraconych seq_) pozwolił na podgląd podziału:
TRAIN 60 zdjęć / 77 plansz, VALIDATION 13 / 20, REGRESSION 13 / 17. Dwa bufory po 10 źródeł
usunęły 3 opisane plansze. To pomiar gotowości, nie zamrożenie zbioru operatora.
Nieznana niezależność sesji i nieznane użycie przez przodka pozostają ograniczeniami.
Istniejące korekty odczytano bez ponownego zapisu ani tworzenia fikcyjnych nagrań.

## Pokrycie wymagań

Poniższa mapa wskazuje regresje i dowody z T1–T4. Nie oznacza, że każdy test
uruchomiono ponownie w T4: wyniki wcześniejszych niezmienionych pionów pozostają
w ich raportach, a nowe zmiany mają własne kontrolne uruchomienia.

| Wymaganie | Dowód / ścieżka | Warunek odbioru |
|---|---|---|
| Istniejące etykiety bez ponownego zapisu | services/api/tests/integration/test_grid_cohort_review_prerequisites_postgres.py; T1 actual-data preflight | Pełny legacy cohort e2e PASS: istniejące zatwierdzenia odczytano przez snapshot/dataset bez ponownego zatwierdzania. |
| Częściowe obie role i zgodność liczników | services/worker/tests/test_grid_correction_evaluation_pipeline.py; services/worker/tests/test_grid_cohort_dataset.py | Obie kontrole zawierają wyłącznie opisane cele, bez whole-photo claim. |
| Zakaz fikcyjnej kolejności | services/api/tests/test_grid_correction_split.py | Brak wiarygodnych atestów oznacza indivisible import; identyfikatory służą wyłącznie remisom. |
| Konflikt nazwa/atest | services/api/tests/test_grid_correction_split.py | Nierozdzielny import przy niezgodności. |
| Bufory wszystkich zdjęć i kolejnych iteracji | services/api/tests/test_grid_correction_split.py; services/api/tests/integration/test_grid_correction_registry_postgres.py | Ochrona bez etykiet, trwałość, nowe źródła, alias między grami. |
| Sesje, kopie i prior uses | services/api/tests/test_grid_correction_split.py; services/api/tests/test_grid_correction_workflow.py | Bez przecieku ról, historyczne bazy zachowane. |
| Provisional preview, atomic freeze | services/api/tests/test_grid_correction_split_adapter.py; services/api/tests/integration/test_grid_correction_registry_postgres.py | Rollback/nowe połączenie/idempotency. |
| Checkpoint i restart | services/worker/tests/test_durable_v3_grid_training.py; services/worker/tests/test_grid_correction_metrics.py | Lexicographic VALIDATION, wcześniejszy krok przy remisie, REGRESSION poza selekcją. |
| Poprawa wyłącznie walidacji nie daje PASS | services/api/tests/test_grid_correction_evaluation.py | Obowiązkowa poprawa current-game REGRESSION. |
| Regresja wymaganej gry i pełnych zdjęć | services/api/tests/test_grid_correction_evaluation.py; services/worker/tests/test_grid_correction_metrics.py | Gate z epsilon i full-only false/duplicate. |
| Brak fikcyjnego historical scope | services/api/tests/test_grid_correction_workflow.py | Tylko zweryfikowane jawne game IDs. |
| Jawne zawężenie | services/api/tests/test_grid_correction_evaluation.py; apps/admin/test-interactions/grid-correction-learning-panel.test.mjs | Powód/potwierdzenie, bez automatycznego przypisania wyłączonej gry. |
| Retry, restart, utrata odpowiedzi | services/api/tests/integration/test_grid_correction_learning_postgres.py; services/api/tests/test_grid_correction_apply.py | Te same dzieci/budżet/receipts; częściowy sukces i CAS. |
| Historyczne polityki i kontrakty | services/api/tests/test_grid_model_evaluation_report.py; services/api/tests/test_dynamic_grid_snapshots.py; services/worker/tests/test_grid_cohort_dataset.py | Legacy interpretacja bez rozluźniania nowych bramek. |
| Nowy import i stara ręczna historia | services/api/tests/integration/test_grid_correction_apply_postgres.py | Test T3 i rozszerzenie T4: realne mutacje/replay/fresh process, kontrolowana granica dowodu treningu. |
| Publikacja, aktywacja i concurrent default | services/api/tests/test_grid_model_publication_scoped.py | P1-1/P1-2 zamknięte przez Opus R2 PASS w T2; realne execute i scoped testy. |


## Zmiany i sprawdzenia T4

P2-3/P2-5/P2-6 audytu R2 T3: resume failed/cancelled pod registry lock odrzuca
inny aktywny apply; GET historii nie rzuca przy sprzecznej zewnętrznej publikacji,
a adopcja zgodnej publikacji wymaga ukończenia poprzedzających porównań.
Konflikt nadal blokuje preview/advance. Inne uszkodzenia własnych receipts
pozostają fail-closed. Format API i snapshotów nie został zmieniony.

- Unit apply/worker: 33 PASS (3.19 s); nowe regresje obejmują konflikt historii,
  nieukończone porównania oraz odmowę konkurencyjnego wznowienia bez mutacji.
- APPLY PostgreSQL po zmianie T4: 2 PASS (42.28 s), warianty first_apply i
  different_evidence. Istniejąca historia pozostaje dostępna po obcej publikacji;
  preview/start nadal odrzucają ten dowód. Inny aktywny przebieg blokuje resume.
  Zachowane także receipts/replay, claim waitingForJobId, stara geometria/pliki,
  nowy import pin oraz odczyt w nowym interpreterze.
- W T3 przeszły wszystkie 3 warianty APPLY PostgreSQL, także manual; wyniki są w
  TASK-1122_VERIFICATION. T4 nie powtarza niezmienionych przypadków bez potrzeby.
- Ruff zmienionych modułów i scoped strict mypy produkcyjnego apply: PASS.
  Tymczasowy wyjątek wnętrza torch.* jest opisany poniżej; config repo bez zmian.
- Bieżący frontend ma aktualny Next build PASS z T3 (exit 0, 17.52 s). T4 nie zmienia
  kodu frontendu, klienta ani schematów HTTP. T3: 137 client, 13 nowych interakcji,
  29 state/contract tests oraz scoped TypeScript/ESLint/OpenAPI/SDK PASS.

Końcowe wyniki po poprawkach P2 audytu T4: legacy bridge PostgreSQL 1 PASS
(30.26 s), z rzeczywistym downgrade/upgrade i ścisłą asercją głowy odczytanej
przez ScriptDirectory (w tym drzewie 0171). Legacy evaluation e2e: 1 PASS (72.69 s),
z pełnym writer → bind/prove → publish → blokujący notice i odrzuconym ponownym
potwierdzeniem wycofanej etykiety. Krótkie ścieżki fixture usunęły błąd _write_atomic;
bez zmiany asercji jakości ani zmniejszania 120 etykiet / 20 zdjęć.
Cohort e2e: 1 PASS (84.13 s), wszystkie 120 etykiet / 20 zdjęć, nowy proces
datasetu i stale-ready rollback z zerem nowych use receipts oraz niezmienionym
headerem. Wszystkie trzy testy mają ścisły limit 110 s, bez zmniejszania danych.
Niezależny odczyt journali potwierdził dla każdej fixture brak pozostałej bazy,
ról i połączeń; nie pozostały własne PID-y pytest. Ruff trzech fixture files PASS.

Końcowy OpenAPI artifact, generated-client drift check, `docs:check`,
`code-map:check` oraz `git diff --check`: PASS.

P2-9 T1: obserwacja pierwszego odbioru zwykłych, pełnych testów mieści się w limicie. W cohort
freeze replay/get/eligibility trwały łącznie 1.343 s, dataset w nowym procesie
9.735 s; w evaluation ocena i proof 4.422 s. Nie jest to porównawczy benchmark
nakładki SQL ani dowód skalowania do wielkich bibliotek. Lead akceptuje
pozostałe ryzyko wydajności jako P2: zabezpieczeń nie pominięto, a pełny pion
na obecnej fixture działa w limicie. Szczegóły i komendy są w
`artifacts/task1123-legacy-verification.md`. Pierwszy błąd tworzenia rodzica tmp_path
wystąpił przed utworzeniem bazy i jest oddzielnie zachowany, bez zaliczenia jako PASS.

## Dyspozycja uwag audytu T4

- P2-1 naprawiono w jednej rundzie: każda fixture tworzy własny podkatalog UUID
  także pod wspólnym env parent. Evaluation i cohort uruchomiono kolejno z tym
  samym parentem; powstały dwa różne podkatalogi. Journale evaluation były
  niezmienione po cohort, a odczyt cleanup potwierdził brak ich baz/ról/połączeń.
- P2-2 naprawiono w tej samej rundzie: expected head pochodzi z konfiguracji
  Alembic; zachowano rzeczywisty downgrade/upgrade i wszystkie ścisłe asercje.
- P2-3 zaakceptowano: pełny mypy pozostaje jawnie otwarty, bez deklaracji PASS.

Końcowe trzy przebiegi po zmianie fixture mają PASS, bez nowych zmian
produkcyjnych. Ponowny audyt nie był wymagany dla poprawek wyłącznie P2.
Pierwsze poprawne przebiegi 29.40/78.64/83.70 s zachowano oddzielnie od końcowych
30.26/72.69/84.13 s; nie są dodatkowymi niezależnymi przypadkami testowymi.

## Odtworzenie testów T4

Z katalogu worktree, z lokalnym PostgreSQL i istniejącą konfiguracją testową.
Nie podawać danych połączenia operatora. Każdy test integracyjny tworzy własne
oznaczone zasoby. Poniższy przykład uruchamia jeden test; pozostałe ścieżki są
w tabeli pokrycia. `--basetemp` musi wskazywać nowy, krótki katalog. W razie
timeoutu zatrzymać odbiór i sprawdzić journal własności przed sprzątaniem zasobów.

```powershell
@'
import os, subprocess, sys
from pathlib import Path
from uuid import uuid4
root = Path.cwd()
env = dict(os.environ)
env['GAME_PREDICTOR_RUN_POSTGRES_TESTS'] = '1'
env['PYTHONPATH'] = os.pathsep.join(str(root / p) for p in
    ('services/api/src', 'services/worker/src', 'services/test_support'))
env['GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT'] = str(root / 'artifacts/t4r' / uuid4().hex)
base = Path('D:/game_predicotr/artifacts/t4l') / uuid4().hex[:8]
base.parent.mkdir(parents=True, exist_ok=True)
command = [sys.executable, '-m', 'pytest',
    'services/api/tests/integration/test_grid_training_cohort_e2e_postgres.py',
    '-vv', '-s', '--basetemp', str(base)]
process = subprocess.Popen(command, env=env)
try:
    sys.exit(process.wait(timeout=110))
except subprocess.TimeoutExpired:
    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], timeout=10, check=False)
    process.wait(timeout=10)
    raise
'@ | D:/game_predicotr/.venv/Scripts/python.exe -
```

Pozostałe przebiegi legacy: `test_grid_model_evaluation_bridge_postgres.py` oraz
`test_grid_model_evaluation_e2e_postgres.py` w tym samym katalogu integration.
Nowe regresje T4: `services/api/tests/test_grid_correction_apply.py`,
`services/worker/tests/test_grid_correction_apply_handler.py` i
`services/api/tests/integration/test_grid_correction_apply_postgres.py`
(filtr `-k 'first_apply or different_evidence'`). Wyniki wcześniejszych pionów,
ich polecenia i jawne ograniczenia pozostają w raportach TASK-1121 i TASK-1122.

## Ograniczenia kontroli typów i środowiska

Kanoniczne `mypy services/api/src services/worker/src scripts` przekroczyło 110 s.
Nie ma pełnego projektowego PASS. Dodatkowa próba ze wspólnym tymczasowym
wyjątkiem tylko dla wnętrza torch.* również przekroczyła 110 s. 18 diagnostyk jest
w 8 plikach niezmienionych od bazy c65823fd; większość wynika z Module=Any po
pominięciu Torch, pozostałe dotyczą starszych modułów. Nie ukończono porównania
pełnego baseline, więc nie deklarujemy zielonego baseline ani pełnej jakości repo.
Nie zmieniono globalnego pyproject i nie maskowano diagnostyk. Scoped checks
zmienionych modułów (także main.py/cli.py) mają osobne wyniki PASS w T2/T3.
Dowody lokalne: artifacts/t1121-full-mypy-preacceptance.json,
artifacts/t1123-first-party-mypy*, artifacts/t1123-typecheck-limitations.json.
Po obu timeoutach nie pozostał własny proces mypy.

Audyt T4 zaakceptował ograniczenie jako P2-3 przy 22 liniach zmienionego
modułu produkcyjnego i sprawdzeniach scoped. Pełny baseline z dłuższym,
uzgodnionym limitem pozostaje osobnym punktem w `CURRENT_STATE.md`.
Nie jest warunkiem ukrytym pod wynikiem PASS tego audytu.

## Niewykonane operacje i warunki uruchomienia

Nie migrowano bazy operatora do 0170/0171, nie restartowano usług, nie uruchamiano
GPU smoke/treningu, nie publikowano ani nie zmieniano defaultu/przypisań operatora.
Brak merge/push i cleanup worktrees. Te operacje wymagają odrębnych zgód.
Nie wykonano fizycznego testu Androida ani pomiaru jakości na prawdziwym modelu.

Po instalacji operator wybiera właściwą grę, sprawdza gotowość i klika
„Ulepsz siatki z korekt”. Trening i ocena nie przełączają modelu. Dopiero pozytywny
wynik pozwala jawnie potwierdzić „Zastosuj wersję”. Starsze importy i ręczne
korekty pozostają zachowane; nowy default dotyczy nowych gier, a istniejące
nieocenione gry nie są automatycznie przełączane.
