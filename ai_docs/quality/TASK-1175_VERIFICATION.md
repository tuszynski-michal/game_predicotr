---
title: TASK-1175 — Pełne pola bez marginesu8%
status: verified_with_baseline_limit
last_updated: 2026-11-09
---

# TASK-1175 — Weryfikacja

## Zmiana

Nowe aktywne snapshoty przypinają `cropPolicyVersion=full-cell-v2` (0%).
Historyczny brak pola zachowuje hash i8% (LAB0%). Wagi, klasy, rozmiary,
interpolacja i RGB nie zmieniają się. Serwer oferuje politykę NOWEJ korekty,
klient wiąże nią podgląd/podpowiedzi/zapis/przyjęcie propozycji i szkic.
Nie opisuje tym polem dawnych wycinków. Nowy manifest wiąże również efektywny
snapshot predykcji; source job pozostaje niezmieniony.

Poprawny pin joba nie pożycza konfiguracji przypadkowego sąsiedniego renderu.
Niekompletny historyczny pin runtime zachowuje dawny reader; jeśli istnieje
zweryfikowany snapshot klasyfikatora, jego padding wygrywa z marginesem sąsiada.
Nie daje to nowego dowodu jakości.
Nowe null pola nie zmieniają serializowanych dawnych komend ani propozycji.

## Wykonane kontrole

- **198 PASS**, API/domena/worker,99.92s: nowa polityka, golden fingerprint
  sprzed zmiany, nieznane/tampered piny, zgodność rendererów, CAS,15 wycinków,
  klasyfikacja i brak przeniesienia starego dowodu automatu. Jedno ostrzeżenie
  FutureWarning z zewnętrznego torch/copyreg, bez wpływu na wynik.
  Po uzupełnieniu kompatybilności starszego runtime także focused46 PASS,
  obejmujące wszystkie32 testy repozytorium i14 testów nowej polityki.
- **PG1 PASS**,52.54s: pełne migracje jednorazowej bazy `*_test`, produkcyjny
  preview/geometry-symbol-preview/save. Stare8% i nowe0% z identycznej siatki;
  zmienione piksele wszystkich15 pól, stary job pin/render i zdarzenia ludzkich
  zatwierdzeń identyczne. Nowe piksele wracają do pending. Nieznana polityka422,
  ten sam klucz z inną polityką409. Ponowienie z NOWEGO interpretera i silnika
  API zwraca tę samą rewizję, created=false. Kontrola PID dowodzi nowego procesu.
- Reviewer: **44 PASS** stan/kontrakt, **40 PASS** interakcje, a po wzmocnieniu
  oferty0 w teście przyjęcia propozycji również focused1 PASS. Stare wywołania
  bez oferty zachowują dawny payload; nowa oferta trafia do wszystkich etapów.
- Klient: **160 PASS**, w tym request0% preview/symbols/manual-resolution.
  OpenAPI wygenerowane, `check:generated` PASS.
- Reviewer typecheck i produkcyjny build PASS; scoped ESLint PASS. Build
  ostrzega o dwóch lockfile w zagnieżdżonym worktree, bez błędu kompilacji.
- Ruff format/check PASS; `docs:check`/`code-map:check` PASS,
  startup43589B,11/11 budżetów. Mapa została zregenerowana.

Logi lokalne: `artifacts/t1175-suite-final.log`, `t1175-pg-cold.log`,
`t1175-reviewer-state.log`, `t1175-interactions-final.log`,
`t1175-proposal-policy-interaction.log`, `t1175-client-final.log`,
`t1175-reviewer-types.log`, `t1175-web-lint-final.log`, `t1175-build.log`,
`t1175-generated-check.log`.

## Ograniczenie mypy — bez zastępczego PASS

Kontrola16 zmienionych modułów źródłowych zgłasza jeden **zastany** błąd:
`storage/virtual_grid_geometry_repository.py:2925`, przypisanie tuple do
zmiennej wywnioskowanej jako SQLAlchemy Row w niezmienionym `_current_row`.
Nie tłumimy go i nie zmieniamy globalnej konfiguracji. Pełny gate mypy nie ma PASS.

Porównanie: źródło z HEAD1181797c, ta sama kontrola `--follow-imports=silent`,
odrębny plik w artifacts; tylko dwa importy względne zapisano absolutnie, aby
zachować oryginalne wiązanie pakietu. Rezultat: ten sam jedyny assignment error
na dawnej linii2901. Wcześniejsze pomocnicze próby miały dodatkowo dwa błędy
relokacji importów; dopiero `t1175-mypy-baseline-final.log` jest wynikiem porównania.
AST `_current_row` jest sprawdzany jako identyczny z HEAD. Dowody:
`artifacts/t1175-mypy-final.log`, `t1175-mypy-baseline-final.log`,
`t1175-type-baseline-proof.json`. Niezwiązana poprawka pozostaje poza commitem,
zgodnie z regułą istniejących regresji. Brak nowych błędów w16 modułach.

## Granice dowodu i wdrożenie

Porównanie15 rzeczywistych produkcyjnych rastrów8/0 wykonano na kontrolowanym
obrazie fixture; contact sheets są w katalogu testu PG jako inset-8.png/full-0.png.
To dowód kontraktu renderowania, nie dowód jakości modelu na zdjęciach operatora.
Bez zatwierdzonych klas/obrysów nie deklarujemy lepszej klasyfikacji ani pełności
każdej grafiki. Margines0 nie naprawia źle wyznaczonej siatki. Stara kalibracja
nie kwalifikuje automatu0; nowa kalibracja klasyfikatora nie należy do taska.

Bez migracji, treningu, zmian defaultu, operatorowych zapisów, masowego recropu,
restartów, merge lub push. Historyczne pliki i zatwierdzenia są zachowane.
Przy wdrożeniu API/Reviewer i główny worker wymagają zgodnych wersji, zanim API
utworzy nowe piny0. Wymagają osobnej zgody. Samo wdrożenie nie przerabia starych
importów; istniejące plansze dostają0 przy dalszej jawnej korekcie.

## Jedna runda poprawek po Opus R1

Opus5.5 przez terminal, z żądanym high, R1: REVISE, P0-1 (publiczny payload
joba nie dopuszczał nowego tokenu). Dodano zamknięte opcjonalne pole do wspólnego
schematu zadań, bez null w dawnych odpowiedziach; OpenAPI i SDK zregenerowane.
Test odtworzył błąd extra_forbidden dla nowego pinu, stary wariant przechodził.
Po poprawce: cztery warianty browser import POST/replay/GET/list (legacy/full,
bootstrap/LAB) PASS. Sam zapis joba nie wystarczał — test sprawdza odpowiedź API.
Pełna próba obu plików import/jobs przekroczyła120s; nie ma wyniku PASS.
Nie pozostawiła własnego procesu. Zawężono weryfikację do czterech opisanych
przypadków importu oraz całego pliku jobs. Pierwsza izolowana próba TestClient
zawiesiła się; zakończono wyłącznie jej procesy i użyto zwykłego procesu testowego.
Log red pokazuje rzeczywisty błąd kontraktu, a nie wcześniejszy błąd katalogu temp.

Nowy moduł schematu: mypy1 PASS; wcześniejszy, opisany baseline mypy16 pozostaje.
Cały plik jobs:36 PASS i jeden zastany FAIL asercji zbioru JobType (pomija
GRID_CORRECTION_LEARNING i SYMBOL_READABILITY). Osobny nowy proces na czystych
plikach main41c784fd odtworzył dokładnie ten FAIL; poza zakresem, bez zmiany
asercji. Testy nowego pinu oba PASS. Klient po dodatkowym teście wrappera:
161 PASS; wygenerowany kontrakt, Reviewer TS, Ruff i docs/map PASS.
Logi dodatkowe: artifacts/t1175-fix-red.log, t1175-fix-import.log,
t1175-fix-jobs.log, t1175-fix-jobsbaseline.log, t1175-fix-types.log
i t1175-fix-client.log.

P2-1: pin modelu w reinferencji istniejących symboli nie określa ich nowych
pikseli; worker korzysta z manifestu każdego istniejącego cropu i wiąże go
checksumą rewizji. Pole i architektura opisują to jawnie, bez masowej zmiany8%.
P2-2: zachowano dawny fallback konfiguracji dla historycznych jobów całkowicie
bez pinu klasyfikatora. Może pochodzić z sąsiedniego manifestu0. To przyjęte
ograniczenie kompatybilności; nowe pełne piny nie pożyczają tej konfiguracji.

Skupiony audyt R2: **PASS**,0 P0/P1, zamknięte P0-1/P2-1; P2-2 przyjęte
ograniczenie kompatybilności. Raport i receipt:
ai_docs/quality/TASK-1175_AUDIT_claude-opus-5-5.md oraz .receipt.json.
SHA pakietu db6034a137b87f8aca30883777c2267c3c1e8bfc12988caff007f50eacd01648.
Terminal CLI potwierdził model główny claude-opus-5-5, high żądane (nie osobno
atestowane przez backend). Audyt statyczny nie zastępuje opisanych wykonań.
Kopie logów z SHA są również poza worktree w root
artifacts/full-field-correction-flow-20261109/checks i checks-r2.
