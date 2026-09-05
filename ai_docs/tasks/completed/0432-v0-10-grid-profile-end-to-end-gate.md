# TASK-0432: Bramka końcowej geometrii dla profilu strony v0.10

Status: done

## Cel

Uniemożliwić oznaczenie 36-punktowego profilu strony jako `candidate_ready`, jeżeli nie przeszedł wersjonowanej, source-disjoint walidacji całego produkcyjnego toru: od rejestracji dziewięciu plansz po końcową geometrię siatek symboli 3×5.

## Zakres

- Dodać jawny, wersjonowany raport bramki end-to-end do profilu schema v2.
- Wymagać co najmniej 100 źródeł, 500 aktywnych plansz, pięciu bucketów oraz znanych przypadków regresyjnych.
- Wymagać co najmniej 98% końcowych plansz gotowych do cięcia, zerowych naruszeń niezmienników i regresji nie większej niż 0,5 pp wobec baseline'u na tym samym korpusie.
- Brak lub niekompletny raport ma pozostawiać profil niegotowy.
- Profile schema v2 bez nowego raportu mają być niekwalifikowane do nowych snapshotów, bez zmiany snapshotów już istniejących jobów.
- Zachować historyczne profile i ich dane.
- Dodać test odtwarzający false-success: kompletne 36 narożników przy wyniku 2/19 800 nie może dać `candidate_ready`.

## Poza zakresem

- Bramka ochronna pojedynczego dużego importu i zmiany Admina (osobny task).
- Uruchomienie walidacji na danych gry `777` (osobny etap operatorski).
- Zmiana progów `incomplete_lattice`, residualu lub source support.
- Usuwanie profili albo artefaktów historycznych.

## Relevant docs

- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/tasks/completed/0424-v0-10-nine-board-page-calibration.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Plan

1. Ustalić bieżący kontrakt tworzenia, persystencji i aktywacji profilu oraz sposób generowania raportu bez dublowania kodu produkcyjnego.
2. Dodać wersjonowany kontrakt raportu i deterministyczną walidację polityki.
3. Włączyć raport w status profilu, fingerprint i eligibility nowych snapshotów.
4. Dodać regresyjne i kompatybilnościowe testy API, repozytorium i workera.
5. Zaktualizować dokumentację i zamknąć task osobnym commitem.

## Definition of Done

- Profil schema v2 bez pełnego raportu nie jest `candidate_ready` dla nowych jobów.
- Raport zawiera wersję polityki, checksum korpusu, liczby źródeł i plansz, skuteczność rejestracji, skuteczność końcowego cięcia 3×5, baseline oraz agregację powodów odroczenia.
- Wynik `2/19 800` jest deterministycznie odrzucany mimo kompletnej geometrii strony.
- Nie ma automatycznego fallbacku ani obniżenia progów jakości.
- Historyczne rekordy i snapshoty pozostają odtwarzalne.
- Testy skoncentrowane, lint, typecheck i build są wykonane zgodnie z zakresem.

## Outcome

- Dodano kontrakt i deterministyczną walidację raportu
  `grid-profile-end-to-end-gate-report-v1`, z minimalnym pokryciem korpusu,
  progami jakości, baseline'em, bucketami, niezmiennikami i powodami odroczeń.
- Profil schema v2 bez raportu jest odrzucany, a resolver aktywnego profilu
  blokuje stary raport przed utworzeniem nowego snapshotu. Historyczne joby nie
  są modyfikowane.
- Raport jest częścią checksummy profilu. Migracja 0094 pozwala zachować wiele
  niezmiennych rewizji bramki dla jednej kohorty, bez nadpisywania historii.
- Worker otrzymał deterministyczny agregator wyników produkcyjnych. Test
  regresyjny potwierdza kontrolowane odrzucenie wyniku 2/19 800 mimo kompletnej
  geometrii 36 narożników.
- Admin pokazuje osobno skuteczność rejestracji 3×3 i końcowej siatki 3×5 oraz
  liczność korpusu bramki.
