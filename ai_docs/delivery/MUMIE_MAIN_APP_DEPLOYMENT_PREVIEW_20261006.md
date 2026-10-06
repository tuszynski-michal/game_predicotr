---
title: Mumie — konkretny preview wdrożenia do głównej aplikacji
status: prepared_pending_operator_approval
last_updated: 2026-10-06
---

# Zakres operacji

Wdrożenie TASK-0884 obejmuje scalenie odebranych zmian0879–0883, kopię bazy,
migracje0144/0145, instalację przygotowanych plików, import i aktywację
jednego kandydata RGB Mumii oraz pierwszą partię100 zdjęć.
Nie obejmuje nowego refitu V5, automatycznego treningu, usuwania danych,
push ani zmiany aktywnego modelu777.

To preview, nie potwierdzenie wykonanego wdrożenia. Wszystkie dotychczasowe
sprawdzenia bazy operatora były read-only. Przygotowane modele, zdjęcia i
dowody znajdują się w odrębnym katalogu artifacts/mumie-main-app-pilot-20261006.
Warunek operacji wynika z zaakceptowanego planu, sekcja TASK-0884:
„konkretny preview migracji/importu/aktywacji i zgoda na wykonanie na bazie”.

## Zweryfikowany stan wejściowy

Odczyt bazy:2026-10-06T14:13:50Z. Przed operacją ponownie odczytać stan.

| Element | Zweryfikowana wartość |
|---|---|
| Główny checkout | C:\Users\tuszy\Documents\game_predicotr |
| Główna gałąź | v1.1-vision-lab-hybrid-geometry |
| MAIN HEAD | v1.7.222 /48b6e0e104e19e915bde30cd89a80d508e81c0b3 |
| Worktree implementacji | C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3 |
| Gałąź implementacji | feat/grid-engine-v3 |
| Odebrany commit0882 | v1.7.224 /8b37241fdd6eb9d29b35691d4e91f3d6a88cb18e |
| Baza | game_predictor |
| Alembic current | 0143_merge_share_grid_shadow |
| Oczekiwany jedyny head | 0145_neural_page_geometry_binding |
| Gra Mumie | fea55cc1-ebf4-4cee-b3ab-a520017ed1be; code mumie |
| Storage Mumii | game_data_v2; generation2; manifest-v5; active |
| Źródła / plansze / pending / page overrides / kohorty Mumii | 0 /0 /0 /0 /0 |
| Obecne iteracje wszystkich gier | 2; obie dotyczą777 |
| Aktywny model777 | d5b3e588-f2f2-4d4b-b2fb-9b5a72a6d52b |
| Aktywne public.jobs / niedokończone lifecycle | 0 /0 |
| Rozmiar bazy | 51 637 237 439 bajtów, około48,1GiB |
| Wolne C: podczas preview | 82 466 676 736 bajtów, około76,8GiB |

Rzeczywiste powierzchnie: Admin3000, Reviewer3001, API8000,
Vision Lab3102.3102 służy obecnie laboratorium i pozostaje poza restartem
głównego Admina. API działa w kontrolowanym procesie; w odczytanych argumentach
nie ma --reload. Mimo tego zatrzymać API przed scaleniem i migracją.
PID są informacją historyczną; przed zatrzymaniem ponownie zweryfikować
exe, start time, command line, port i katalog właściwego procesu.

Równoległe RGB0878 nadal ma procesy previewCLI. Brak public.jobs nie oznacza
braku tej pracy. Nie przerywać ani nie usuwać jej plików. Wdrożenie przejdzie
przez bezpieczny checkpoint potwierdzony aktualnym logiem i stanem procesów.

## Dokładne zmiany danych

0144 dodaje provenance lab_import, dopuszcza brak kohorty wyłącznie dla
lab_import, dodaje idempotency importu i append-only deactivate.
Obie istniejące iteracje dostają zgodną domyślną wartość production_training.
Ich kohorty, modele, metryki i aktywacja777 zostają zachowane.

0145 dodaje nullable neural_proposal_binding w istniejących page overrides,
kontroluje dokładny binding oraz dopuszcza engine_kind neural_grid_v1.
Obecne override i source revisions zachowują dotychczasowe dane.
Nie usuwa ani nie rekonstruuje żadnego zdjęcia lub zatwierdzenia.
Migracje mają lock_timeout5s, statement_timeout120s i guard lifecycle.

Po migracji powstanie jeden VALIDATE import i jedna iteracja lab_import
Mumii. Receipt po utraconej odpowiedzi odtwarza te same obiekty.
Aktywacja dopisze jeden wpis historii wyłącznie dla Mumii.
Nie tworzyć fikcyjnej kohorty, epochów ani nowych ludzkich zatwierdzeń.
Potem import100 zdjęć utworzy źródła i propozycje wymagające korekty.
Liczba opublikowanych plansz zależy od potwierdzonych zakresów/przypisań;
nie obiecywać900 automatycznie zatwierdzonych plansz.

## Przypięte pliki

| Artefakt | Identyfikator |
|---|---|
| R2 RGB candidate fingerprint | 5e0489db5f0b1aaa03854e5dabe7104ad85e444d077ff20d5c747f67d062a480 |
| Candidate manifest SHA | 72125739eec0e03e212de5b586ed5b417837e00b0f4382903f88405b0331a5c2 |
| Protected descriptor SHA | 25fedbdf124dfd1cf8038addb9f8a176817b2b2361cff62fe0f8f9a18f1d7812 |
| Prepared kontrolne pliki | 24 oryginały,136 dowodów,127 rzeczywistych ludzkich ocen |
| Model siatki | grid_profile_mumie_v1/v1; iteration03-f896da7196431be2 |
| Selection100 SHA | a05827b5dac322d5d1d9c3f02c8a92f04e69630c36a2dae4439f2c2e275af922 |

Kandydat: C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\prepared.
Kontrole: ...\prepared-feedback.
Upload: ...\pilot-upload-100,100 plików/31 167 375 bajtów.
W rzeczywistych poleceniach używać pełnych ścieżek absolutnych.
Kontrole nie są dodatkowym uploadem gry; instalator kopiuje je do managed
training storage. Preview nie zapisuje, --apply publikuje create-only,
descriptor jako ostatni. Identyczny retry nie tworzy nowych plików.

## Przebieg wykonywany przez agenta po zgodzie

1. Potwierdzić HEAD/status obu gałęzi, current/head, lifecycle, joby, porty,
   modele i checkpointRGB. MAIN ma być czysty. Zmiana wejść unieważnia preview
   dla zmienionego zakresu. Stare dirty metadata worktree pozostają poza merge.
2. Zablokować nowe importy na czas operacji i zatrzymać właściwe procesy
   głównego API/Admin/Reviewer/worker po zakończeniu zapisów.
   Vision Lab i obca pracaRGB nie są celami zatrzymania.
3. Wykonać pełny pg_dump --format=custom --lock-wait-timeout=5s bazy
   game_predictor w kontenerze game-predictor-postgres-1 jako game_predictor.
   Przechować backup pod
   C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\backups.
   Strumień binarny zapisać bezpośrednio z procesu do pliku; nie używać
   przekierowania binarnego przez Windows PowerShell5.1.
   Zapisać wielkość/SHA i sprawdzić pg_restore --list. Niedokończony dump
   nie jest backupem i nie odblokowuje migracji.
4. Przygotować odtworzenie do osobnej, jednoznacznie nazwanej bazy *_test.
   Restore nie może wskazać game_predictor podczas próby. Rezerwować rozmiar
   danych, archiwum oraz zapas miejsca. Obecne wolne miejsce nie gwarantuje
   dwóch nieskompresowanych kopii. Jeśli miejsca albo ograniczonego czasu
   brakuje, zatrzymać wdrożenie przed migracją i podać rzeczywistą przeszkodę.
   Nie deklarować przetestowanego pełnego restore przed jego wykonaniem.
5. Scalić feat/grid-engine-v3 do v1.1-vision-lab-hybrid-geometry,
   zachowując aktualnyRGB0878. Próbny merge-tree0882 wykazał tylko dwa
   konflikty dokumentów CURRENT_STATE/DECISION_LOG; kod i SDK połączyły się.
   Zaktualizować tę próbę po commicie0883, zachować obie historie dokumentów,
   sprawdzić wygenerowany kontrakt i regresję po realnym scaleniu.
6. W MAIN wykonać npm install, npm run admin:build, npm run reviewer:build.
   Każdy krok ograniczony runnerem; znane buildy z limitem120s.
   Nie wykonywać ogólnego formatowania cudzych plików.
7. W MAIN wykonać npm run db:migrate i potwierdzić jedyny current/head
   0145_neural_page_geometry_binding oraz zachowanie obu iteracji777.
   Jeśli guard/lock timeout odrzuci migrację, nie wymuszać jej.
8. Zweryfikować zainstalowane modele przez istniejący
   scripts/install_grid_engine_models.py --check.
   Zainstalować create-only kandydata i frozen controls, sprawdzić je
   w nowym procesie przed uruchomieniem aplikacji.
9. Uruchomić API przez scripts/start_controlled_api.ps1, główny Admin
   na3000, Reviewer na3001 i odpowiednie lanes przez
   scripts/manage_worker_lanes.ps1. Start-Process -WindowStyle Hidden,
   zapisać PID/logi/start time. Readiness odczyty2s, całość maksymalnie10s.
   Nie uruchamiać drugiej kopii usługi po nieudanym starcie bez sprawdzenia
   pierwszego procesu.
10. W Admin gry Mumie: Sprawdź model → potwierdzony import, poczekać na
    candidate_ready, podgląd aktywacji → potwierdzona aktywacja.
    Sprawdzić exact candidate manifest SHA i brak wcześniejszego modelu Mumii.
    Nie używać nowego idempotencyKey przy odtwarzaniu utraconej odpowiedzi.
11. Wgrać przygotowaną partię100 zgodnie z instrukcją operatora.
    Odczytać liczbę źródeł, review i nieprzypisanych pozycji.
    Nie zatwierdzać automatycznie predykcji ani trenować bez ludzkich decyzji.
    Większe partie500/2000 po odbiorze pierwszego przepływu.

## Recovery

Problem ograniczony do pilota: zatrzymać nowe importy Mumii, wykonać
deactivation preview i append-only deactivate Mumii. Rozpoczęte zadania
zachowują swój snapshot; źródła, korekty, joby i historie pozostają zapisane.
To nie zmienia aktywacji777.

Nie stosować automatycznego Alembic downgrade po powstaniu historii
lab_import/neural binding. Downgrade jest świadomie zablokowany.
Recovery schematu/danych wymaga zatrzymanych zapisów, zweryfikowanego backupu
oraz odtworzenia do osobnej bazy przed kontrolowanym przełączeniem.
Nie wykonywać drop/overwrite bazy operatora jako domyślnego rollbacku.

## Co pozostaje do zatwierdzenia

Jawna zgoda na opisany zakres TASK-0884: pełna kopia, scalenie i buildy,
migracje0144/0145 na game_predictor, instalacja/import/aktywacja jednego modelu
Mumii, restart głównych usług i pierwszy upload100.
Dawne zgody0140–0143 nie obejmowały tych nowych migracji.
Implementacja i przygotowanie preview nie wymagają kolejnego zatwierdzenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0884 — wykonanie wdrożenia według zaakceptowanego planu | gpt-6.1-sol | high | Migracja, checkpoint równoległej pracy i przełączanie usług wymagają kontroli rzeczywistych wejść oraz recovery. | Niezależny gpt-6.1-sol/high |
