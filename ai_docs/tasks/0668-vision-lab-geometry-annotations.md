---
title: TASK-0668 — T03 — edytor i zbiór geometrii
status: in_progress
last_updated: 2026-09-27
---

# TASK-0668 — T03 — edytor i zbiór geometrii

## Status

`in_progress` — D-456 zatwierdza T03k i pilota całymi grami bez pomiaru.
Pełny protokół rodzin/pomiaru pozostaje odroczony. Historycznie: anotacje
i przegląd operatora wykonane; D-453 rozstrzyga użycie
historycznych zdjęć 777 w modelu geometrii. Pozostają techniczne mapowanie
źródeł do rodzin, kontrola konfliktów oraz zamrożony podział. Mechanizmy
T03e/T03f są wdrożone i odebrane; T03g zachował zapisy w rozszerzonym zbiorze,
a T03h zastosował kwalifikację geometrii. T04/T05 nie rozpoczęto; nie uruchamiać ich przed
spełnieniem bramek danych; od D-456 wystarczy odebrany T03k dla pilota.

## T03k — podział całymi grami i zamrożenie pilota D-456

### Status / Goal / Context / Dependencies

`done`. Umożliwić jawny, ograniczony pilot 5 × 3 na istniejących
akceptacjach bez udawania verified rodzin lub pomiaru czasu. D-456 accepted,
T03j done v1.7.26, mapa i siedem unresolved zapisane v1.7.27. Stan wejściowy
rev267/SHA f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae.
Przed apply ponowna kontrola; obcy zapis blokuje zamiast nadpisania.

### Recommended execution / Relevant docs

`gpt-6-sol` / `medium`, osobny audyt `gpt-6-astra` / `medium`. To zmiana
spójnego pionu splitu i operacja danych, nie trening. P0–P2 po dwóch cyklach
blokują. AGENTS, PLAN_STANDARD/TASK_TEMPLATE/DoD, wymagania/architektura labu,
plan etapu B, D-453–456 i VISION_LAB_SOURCE_MAPPING_20260927.md.

### Scope / Technical notes

- Nowa wartość SplitRequest.geometry_policy:
  `lab-geometry-whole-game-pilot-v1`; opcjonalne nowe game_partitions=None,
  mapa game_id na development/validation/final_test/unseen_game.
  None usuwane przed fingerprintem requestu dla zgodności starych receipts.
  game_partitions poza pilotem odrzucone; brak mapy w pilocie odrzucony.
- Pilot wymaga purpose geometry, jawnej niepustej unikalnej znanej kohorty,
  pustych measurement_source_ids i difficulties. Klucze mapy dokładnie
  pokrywają gry całego katalogu; co najmniej jedna gra development i dokładnie
  jedna validation/final_test/unseen_game, unseen zgodne z unseen_game_id.
  Każda z czterech partycji ma co najmniej jeden pełny wybrany target;
  pusta partycja to PILOT_GAME_PARTITIONS_INVALID.
  Nie nadaje się roli źródła ani akceptacji na podstawie przypisania gry.
- Wszystkie wybrane źródła muszą mieć aktualny photo_accepted, własną
  skuteczną kwalifikację gdy niedata i pełne ręczne targety wyłącznie 5 × 3.
  Wąski wyjątek niewybranego historycznego kontekstu 777 identyczny z D-455.
  Role/kwalifikację kontekstu kontroluje się w komponentach dotykających
  kohorty jak w T03j; kontrola przecinania partycji obejmuje cały katalog.
  Błędne wybrane źródło odrzuca cały pilot, bez cichego pomniejszania kohorty.
- build_components nadal obejmuje wszystkie źródła i wszystkie istniejące
  SHA/families/related. Każdy komponent całego katalogu musi należeć do jednej
  partycji wynikającej z game_partitions, także gdy nie ma targetów. Znany
  konflikt przecinający partycje odrzuca cały freeze. Nie tworzyć verified.
  Konserwatywne związanie wszystkich źródeł tej samej gry realizuje mapa,
  nie zapis nowych pozornych FamilyDecision.
- FrozenSplit zapisuje nową politykę, game_partitions, kohortę, assignments
  tylko targetów, NOT_IN_GEOMETRY_COHORT dla kontekstu, pusty measurement,
  pełne leakage_components/fingerprints oraz target/qualification/annotation
  fingerprints. Fingerprint wiąże cały protokół i mapę. Stare hashe i polityki
  bez nowych elementów. Odczyt sprawdza pełny graf/fingerprints, mapę i własne
  kwalifikacje targetów; nie robi fałszywego stale od unresolved lub kontekstu.
  Mutacje nadal konserwatywnie ustawiają stale, bez ponownego freeze.
- Czystą gałąź pilota wydzielić do proponowanego whole_game_split.py,
  wykorzystując istniejące mechanizmy. Błędy domenowe atomowe HTTP409,
  nieznana wartość schematu 422. Stabilne błędy PILOT_GAME_PARTITIONS_REQUIRED,
  PILOT_GAME_PARTITIONS_INVALID, PILOT_MEASUREMENT_NOT_SUPPORTED,
  PILOT_CROSS_PARTITION_COMPONENT, PILOT_FULL_GEOMETRY_REQUIRED,
  PILOT_TOPOLOGY_NOT_SUPPORTED; dotychczasowe błędy kohorty/kwalifikacji
  zachować tam, gdzie pasują. API/OpenAPI/generated/wrapper/request test.
- Operacja po audycie kodu i exact requestu: aktualny katalog/state, backup,
  dry-run, jeden istniejący AnnotationStore.mutate (CAS267), kolejny odczyt
  i identyczny retry w nowym procesie. Tylko split + rewizja/event/receipt;
  geometrie, review, rodziny, kwalifikacje i timingi bez zmian. Backup nie
  oznacza nadpisywania źródła podczas testu odtworzenia: restore do nowego
  katalogu. Raport i checksummed manifest pilota poza repo w danych labu.
- Manifest zawiera snapshot_id, split fingerprint, policy, game_partitions,
  source_id/SHA/relative path i jawne targety board_index/revision/nodes/SHA
  oraz przydziały. Nie dodaje nowych etykiet. Walidator T04 ma czytać
  zamrożony stan i sprawdzać zgodność; trening tylko development, strojenie
  tylko validation. Bez czytania targetów final_test/unseen do strojenia.
  Koperta manifestu używa istniejącego formatu {payload, sha256=digest(payload)}.
  Payload zachowuje format `vision-lab-whole-game-pilot-manifest-v1` propozycji,
  status zmienia na `frozen`, split_fingerprint na rzeczywisty hash; pozostałe
  pola i 180 targetów zgodne z zaudytowaną propozycją. Manifest ID to digest
  payloadu, plik `manifests/<manifest_id>.json` w danych labu, create-only,
  identyczny retry sprawdza bajty/checksumę. snapshot_manifest_id i katalogowy
  snapshot_id są różnymi identyfikatorami, nie zamieniać ich. Kontrola całych
  targetów służy integralności; do modelu podaje się tylko development/validation.

### Expected files

Istniejące vision_lab/annotation_contracts.py, annotations.py, splits.py,
geometry_qualification.py, pakiet vision-lab-api-client i testy HTTP/request.
Nowe proponowane vision_lab/whole_game_split.py i test_vision_lab_whole_game_split.py.
Raport jakości VISION_LAB_WHOLE_GAME_PILOT_20260927.md. Root odpowiada za
task/current/plan/decision; wykonawca kodu za wymagania i architekturę.

### Acceptance / Test cases / Verification

- [x] Pełny pion pilota i 63/180 targetów z przydziałem D-456; żadnych nowych zgód.
- [x] Testy: unresolved dopuszczone tylko pilotem; brak/pomylona mapa,
  measurement, zła topologia, błędna zgoda/kwalifikacja odrzucone atomowo.
- [x] Konflikt między grami przez SHA lub przechodni nieanotowany alias
  odrzucony; zmiana grafu/metadanych/kwalifikacji daje stale; stare polityki,
  receipts i None zachowane; nowy proces, backup/restore oraz retry PASS.
- [x] Pytest nowych i sąsiednich regresji, Ruff/format/mypy modułów,
  TypeScript klienta/labu, OpenAPI generate/check, klient request test PASS.
  Każda komenda ograniczona do 120 s; bez pełnego benchmarku.
- [x] Audyt kodu i exact operacji bez P0–P2; apply/odczyt/retry PASS;
  osobny commit, Outcome i CURRENT_STATE. T03k domyka tylko bramkę pilota.

### Out of scope / Risks / Outcome

Bez verified rodzin, etykiet symboli, wyników 3 × 3, oceny oszczędności czasu,
strojenia na final_test/unseen, treningu w tym podzadaniu, push i aktywacji.
90 siatek treningowych to mały zbiór; wynik może być słaby. Brak poprawy
nie upoważnia do zmiany holdoutów. Testy powyżej są planowane, nie wykonane.
Implementacja zamrożona do audytu. Wykonawca Sol medium: 82 testy backendu
PASS (nowy pilot 5 + v2/receipt 8: 42,94 s; cohort 24: 68,54 s;
qualification/annotations/review 45: 56,25 s), klient 8/8 PASS. Ruff check,
format 20 plików, mypy 16 modułów, TypeScript klienta/labu, OpenAPI generate/
check/generated i git diff check PASS. Początkowy błąd fixture testu,
import-order i dwie adnotacje typów poprawione bez osłabienia kontraktu.
Kontrakt, exact request, końcowy kod i dry-run/manifest przeszły audyt Astra
medium bez P0–P2; niezależnie 13 backend + 8 client PASS. Wykonano jeden
freeze CAS267 do rewizji268. Split:
`3ebcc3a401a17295c5509cbe5d1f59886fa7a87588427c6bed671665dbe63572`.
Manifest `1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0`
opublikowany create-only pod LAB/manifests. Nowy proces replay, odczyt oraz
restore backupu do nowego katalogu PASS. Pozostały payload identyczny, stare
store niezmienione; split_stale=false. SHA aktywnego stanu:
`084bc39de16502de46f6237cbc2fb453a9dc00665ab20d1319301f44f6efa314`.
Końcowy niezależny audyt operacji Astra medium PASS bez P0–P2: odtworzenie
całego payloadu z backupu i jednego requestu, obie kopie i manifest zgodne.
Brak instalacji GPU, treningu, zmian UI i aktywacji. Kryteria T03k spełnione;
pełny protokół rodzin/pomiaru T03 pozostaje odroczony zgodnie z D-456.
Osobny commit `v1.7.28` / `84f523ea8a26a45ce419dfc65cd64d73fdaf0cba`.
Staged check/stat/list i show/stat/status PASS; obce zmiany zachowane. Po commicie
następny task T04; rodzic TASK-0668 pozostaje aktywny dla odroczonego zakresu.

## T03i — odzyskanie metadanych selekcji z Kosza

### Status / Goal / Context

`done`. Użytkownik jawnie zezwolił na przeszukanie Kosza i odzyskanie
projektowych metadanych. Celem jest bezpieczna kopia znalezionych eksportów
oraz wskazanie ich pokrycia, bez żądania ponownego przygotowania zdjęć.

### Dependencies / Recommended execution / Relevant docs

Zgoda operatora, istniejący katalog laboratorium, odczyt T03h oraz dokumenty
w Relevant docs tego taska. Wykonawca `gpt-6-sol` / `medium`; osobny audyt
`gpt-6-astra` / `medium`. Konflikt ścieżki, SHA lub nierozwiązane P0–P2 po
dwóch cyklach zatrzymują operację. Brakujące pliki raportować, nie odtwarzać
metadanych z domysłów.

### Scope / Technical notes / Expected files

- Read-only przeszukanie Kosza znalazło osiem JSON w katalogach Blazing,
  Gang i Reels oraz jeden JSON wewnątrz usuniętego katalogu 777. Sprawdzono
  375 wpisów najwyższego poziomu i oba usunięte katalogi, 65 katalogów /
  70914 plików; bez błędów, pozostałej kolejki i pominiętych reparse points.
- Kopie tylko tych dziewięciu `manual-image-selection-output-v1.json`,
  w odrębnych podkatalogach nowego `recovered_metadata` pod katalogiem labu.
  Zachować nazwę oryginału, ścieżkę z Kosza, pierwotną lokalizację, datę
  usunięcia, rozmiar i SHA-256 w raporcie. Nie wykonywać restore/move/delete.
- Walidować brak dowiązań i położenie celu; istniejący identyczny plik jest
  idempotentnym retry, inna zawartość konfliktem. Nie nadpisywać.
- Parse JSON i porównanie nazw/hash z obecnymi zdjęciami są tylko analizą
  dowodów. Dopasowana nazwa nie oznacza identycznych pikseli ani nagrania.
- Zmiany repo: ten task, CURRENT_STATE, plan oraz nowy raport
  `ai_docs/quality/VISION_LAB_RECOVERED_METADATA_20260927.md`.

### Out of scope / Acceptance criteria / Verification

Bez odzyskiwania zdjęć/filmów, zmian Kosza, snapshotów, kwalifikacji, rodzin,
zgód, splitu, usług i treningu. Bez zmian API/UI i kodu produkcyjnego.

- [x] Dziewięć kopii poprawnych JSON ma SHA i rozmiar identyczne ze źródłem.
- [x] Niezależny nowy proces potwierdza kopie i zachowanie źródeł w Koszu.
- [x] Raport rozróżnia pliki, trafienia nazw, powiązania SHA i niewiadome.
- [x] Niezależny audyt, diff check, osobny commit i zapis wyniku.

Weryfikacja operacyjna: ograniczone czasowo odczyty JSON, Get-FileHash i
Test-Path, świeży proces. Testy aplikacji/lint/typecheck nie dotyczą tej
operacji danych; nie zmienia ona kodu. Nadrzędny T03 pozostaje blocked.

### Outcome T03i

Odzyskano dziewięć kopii (737005 bajtów), w tym dwa puste eksporty Blazing.
Preview, copy i świeży verify PASS: identyczne SHA/rozmiary i poprawny JSON,
źródła w Koszu zachowane. Nazwami objęto 121 z 473 nowych JPG: Blazing 27/27,
Gang 35/35, Reels 54/54 i 777 5/32. Żaden z tych bieżących cropów nie ma SHA
oryginału wskazanego w eksporcie. To przesłanka pochodzenia, nie dowód pikseli
ani niezależności nagrań. Z wcześniejszym Treasure znane pokrycie nazw 157/473;
316 niepokrytych: 27 zdjęć 777, 225 Mumii, 64 Treasure. Nie ponawiać prośby
o ponowne rysowanie 180 zachowanych siatek. Store rev260/SHA ad7c3d82… bez zmian.
Raport: VISION_LAB_RECOVERED_METADATA_20260927.md. Nie zmieniono kodu, API,
usług, snapshotów, anotacji, kwalifikacji, rodzin ani splitu; brak treningu.
Testy aplikacji/lint/typecheck nie dotyczą tej operacji. Niezależny audyt
Astra medium PASS bez P0–P2: dziewięć kopii, oryginalne ścieżki/daty z $I,
121 trafień nazw bez zgodnych SHA obrazów oraz oba niezmienione store.
Trwały manifest `recovered_metadata/recovery-manifest-20260927.json`:
74899 B, SHA `954cadcfc97e71cf8636a0b0d6f3dafaa72192c299ff79a0b84d9412e71f38a2`.
Skorygowano nieścisłość opisu daty Shell; surowe wartości odpowiadają UTC,
nie lokalnej strefie. Odbiór obejmuje kontrolę nowego procesu i brak nadpisań.
Commit T03i: `v1.7.25` / `6db4f895719695ab6cdfd6a1f3ad9300f64be013`.
Staged check/stat/list i show/stat/status PASS; obce zmiany zachowane.
Porównanie z DoD: kontrola kopii, nowego procesu, zachowania źródeł oraz
rozróżnienia dowodów spełniona. Nadrzędny task pozostaje blocked; dalszy krok
to osobna analiza dowodów pochodzenia, nie automatyczne uruchomienie treningu.

## T03j — nowa polityka kwalifikacji targetów 777

### Status / Goal / Context / Dependencies

`done`. Usunięto zatwierdzoną przez operatora nadmiarową bramkę: niewybrane
historyczne zdjęcia 777 nie muszą uzyskać zgód treningowych, aby wybrane
zatwierdzone zdjęcia mogły się uczyć. D-455 przyjęte; T03f/h odebrane.
Nie oznacza to rozstrzygnięcia rodzin ani zgody na dodatkowe targety.

### Recommended execution / Relevant docs

`gpt-6-sol` / `medium`, niezależny `gpt-6-astra` / `medium` według planu.
AGENTS, PLAN_STANDARD, TASK_TEMPLATE, wymagania/architektura labu i D-453–455.
Brak modelu lub P0–P2 po dwóch cyklach blokuje odbiór.

### Scope / Technical notes / Errors

- Proponowane pole `SplitRequest.geometry_policy`, opcjonalne Literal
  `lab-geometry-cohort-777-targets-v2` lub None. None usuwane z request_data
  przed fingerprintem; stare receipts obu purpose i kohort pozostają ważne.
- Wybór v2 wymaga purpose geometry i jawnej niepustej kohorty; błędny wybór
  kończy stabilnym ValueError/istniejącym 409, zły enum pozostaje 422.
- FrozenSplit v2 zapisuje tę wersję i komplet obecnych fingerprintów.
  Default/None nadal tworzy poprzednią politykę bez nowych danych hashujących.
- Wyjątek dotyczy wyłącznie źródła POZA kohortą: source_kind folder,
  game_name dokładnie 777, pierwszy segment filename dokładnie 777,
  role comparison_only. To nie jest test podciągu nazwy. DB, V2, inne role
  i comparison_only pozostają pod dotychczasowymi bramkami.
- Wybrane niedata zawsze wymagają skutecznej własnej kwalifikacji; nie wolno
  jej kopiować. Cały komponent nadal verified, pełny graf SHA/families/related,
  kontrola gry/unseen i pomiaru bez zmian. Kontekst nie ma assignments/targetów.
- `_view` rozgałęzia skuteczność kwalifikacji według wersji frozen splitu.
  V1 zachowuje kontrolę wszystkich członków; v2 używa tego samego wąskiego
  wyjątku co freeze. Zmiana grafu lub pełnych fingerprintów nadal daje stale;
  sam stały brak kwalifikacji wyłączonego kontekstu nie daje stale w v2.
- Mutacje, backup, CAS, receipts i retry nadal należą do AnnotationStore.
  Błąd nie zapisuje częściowej zmiany. Realne dane/mapowanie i trening poza
  zmianą kodu T03j; wznowiona analiza T03 może działać równolegle read-only.

### Expected files

Istniejące `vision_lab/annotation_contracts.py::SplitRequest/FrozenSplit`,
`splits.py::freeze_splits`, `annotations.py::mutate/_view`, ewentualny wspólny
predykat w `geometry_qualification.py`, pod
`services/worker/src/game_predictor_worker/`. Testy w
`services/worker/tests/test_vision_lab_geometry_cohort.py`, kwalifikacji,
anotacji i API. OpenAPI i generated types, wrapper `src/index.ts` oraz
`test/request.test.mjs` w `packages/vision-lab-api-client`. Bez nowego UI.
Root aktualizuje plan/task/current/decision log, wykonawca właściwe wymagania
i architekturę; nie dotykać obcych zmian.

### Acceptance / Test cases / Verification

- [x] V2 dopuszcza targety 777 z niekwalifikowanym kontekstem; nie tworzy zgód.
- [x] V1/None/legacy oraz stare receipts zachowują poprzednie zachowanie.
- [x] Brak własnej kwalifikacji targetu, nieweryfikowana rodzina, DB/V2/inne
  comparison, most przez niewybrany alias, unseen i konflikty pomiaru blokują.
- [x] Nowy proces i backup/restore: v2 bez fałszywego stale, zmiany źródeł,
  rodziny lub kwalifikacji targetów dają stale, v1 pozostaje rygorystyczne.
- [x] Spójny pion API/OpenAPI/client i test requestu; testy backendu,
  Ruff/format/mypy zmienionych modułów, TypeScript klienta, generated check.
- [x] Niezależny audyt bez P0–P2; Outcome/CURRENT_STATE uzupełnione,
  osobny commit v1.7.26 wykonany (pełny hash w Outcome).

Sprawdzone komendy: pytest plików testowych wyżej, root
`npm run vision-lab:openapi:generate` i `npm run vision-lab:openapi:check`;
pozostałe komendy jakości z package.json i konfiguracji repo. Wszystkie
skończone komendy mają timeout do 120 s, bez benchmarków. Wykonane wyniki
w Outcome, nie traktować tej listy jako zaliczonych testów.

### Outcome T03j

Implementacja i niezależny audyt zakończone. Sol medium:
7 nowych regresji PASS (22,09 s), 69 pozostałych regresji PASS (113,98 s),
łącznie 76 testów backendu; 7 testów klienta PASS (0,37 s). Ruff check/format,
mypy 15 modułów, TypeScript klienta i laboratorium, OpenAPI generate/check,
generated check oraz diff check PASS. Każda komenda miała limit do 120 s.
Istniejące ostrzeżenia Starlette/AnyIO bez błędów testów. Astra medium:
niezależne 31 testów backendu i 7 klienta PASS; audyt kodu bez P0–P2.
Pierwszy audyt klienta zatrzymało ograniczenie sandboxa
`uv_os_get_passwd ENOMEM`; zatwierdzone ponowienie poza sandboxem PASS.

Zmieniono opcjonalny kontrakt istniejącego API, backend, wygenerowany klient,
wrapper i test żądania; wymagania i architektura odzwierciedlają D-455.
Nie zmieniono UI, danych, kwalifikacji ani starych receipts. Brak realnego
freeze i treningu. Po odbiorze ponowić dry-run mapy z nową jawnie wybraną
polityką; nie omijać pozostałych bramek T03. Wszystkie kryteria T03j pokryto
testami i audytem; bez pełnego builda repo ani wdrożenia. Cały TASK-0668
pozostaje aktywny, więc nie przenosi się go do completed razem z podzadaniem.
Commit T03j: `v1.7.26` / `867da1167362f32ae6ff3e623fa976c57c261c1c`.
Staged check/stat/list oraz show/stat/status PASS; obce zmiany zachowane.

## Goal

Zatwierdzać warstwowe anotacje geometrii z trwałymi rewizjami i zamrożonymi podziałami.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

STOP A; wybór gry niewidzianej zapisany przed pierwszym treningiem; zatwierdzony budżet B. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `medium`; osobny audyt `gpt-6-astra`, reasoning `medium`. Trwałość decyzji oraz brak przecieku rodzin źródeł wymagają kontroli rewizji i podziałów. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T03 — edytor i zbiór geometrii)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447, D-450, D-453)

## Scope

Edycja narożników i pełnych węzłów, rewizje, backup/restore, kwalifikacja
geometrii historycznego 777 według D-453, pochodzenie 777 V2, split rodzin
i duplikatów; pomiar pierwszych 10 zdjęć na grę i prognoza pracy.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Brak przecieku rodzin; restart i odtworzenie backupu; narożniki nie udają pełnej siatki; nierozstrzygnięte 777 V2 wykluczone.
- [x] Historyczne zdjęcia 777 kwalifikowane do geometrii zgodnie z D-453:
  nowe ręczne siatki labu, zachowane pochodzenie i ważne zgody niezmienionych
  źródeł, bez targetów v1.1, zmiany istniejących snapshotów i automatycznej
  kwalifikacji symboli; techniczne wdrożenie sprawdzone przed treningiem.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Wznowienie operacyjne po deklaracji Treasure (2026-09-27): zlecony wykonawca
gpt-6-sol / medium przygotowuje pełną mapę źródeł i odczytowy dry-run podziału
istniejącym `splits.py::freeze_splits` na kopii stanu. Oddzielić dowody SHA,
eksporty selekcji/cropów, konkretną deklarację operatora i nierozstrzygnięte
kandydatury. Brak JSON nie jest samodzielnym blokerem zadeklarowanego katalogu.
Wszystkie powiązania obejmują katalog, nie tylko 63 akceptowane zdjęcia.
Nie tworzyć verified z samej nazwy; nie dobierać fikcyjnych trudności lub
niezależnych rodzin pod wymagania pomiaru. Nie przenosić zatwierdzeń na nowe
obrazy. Realne zapisy dopiero po audycie dokładnej propozycji, bez osłabiania
bramek w celu uzyskania zielonego wyniku. Konflikt wymaga konkretnego raportu.
Nowy raport: `ai_docs/quality/VISION_LAB_SOURCE_MAPPING_20260927.md`;
requesty i wyniki diagnostyczne w `artifacts/vision-lab`. Zmiany dokumentacji
task/current/plan prowadzi root. Kod produkcyjny i API/UI poza tym krokiem.
Kryteria: pełne pokrycie mapą (także jawne unresolved), brak podziału znanych
powiązań, dokładne komunikaty istniejących bramek, zachowane SHA obu store,
niezależny audyt Astra medium. Następnie zapis rodzin/splitu tylko jeśli
rzeczywiste dowody i wymagania wystarczają; T04 wymaga ukończonego T03.

Decyzja użytkownika z 2026-09-27 (D-453): historyczne zdjęcia 777 mają wejść
do modelu geometrii, aby obsługiwał przyszłe podobne zdjęcia. Referencją są
nowe ręczne siatki zatwierdzone w labie, nie dawne geometrie v1.1. Nie ma
już otwartej decyzji produktowej o użyciu 777. Obecne role i immutable
snapshoty nie zostały zmienione. T03e wdrożył jawną kwalifikację z zachowaniem
historycznego pochodzenia, ważnych zgód niezmienionych źródeł oraz bramek
symboli. Realne apply wykonał T03h; mapowanie rodzin i split pozostają do wykonania.
Tryb legacy `vision_lab/splits.py::freeze_splits` odrzuca grupy z `role != data`
jako `COMPARISON_OR_777_PROVENANCE_UNRESOLVED`. T03e dodaje odrębny jawny
purpose geometry i kwalifikację D-453, bez zmiany pochodzenia ani wyłączenia
kontroli przecieku. Realna kwalifikacja nie zastępuje zamrożenia splitu.

Deklaracja operatora: materiał pozostałych pięciu gier w
`C:\Users\tuszy\Documents\game_predictor_traning_set` pochodzi z innych
zakresów/folderów nagrań niż zdjęcia wskazane do dotychczasowych siatek;
operator ocenia zdjęcia jako odległe brzegi nagrań, oddzielone kilkoma
katalogami. Nie jest to wniosek z samych nazw. Nie ponawiamy ogólnego pytania
o pochodzenie: kolejną kontrolą jest techniczne mapowanie źródło–rodzina
i konflikty z dotychczasowym zbiorem. Brzegi tego samego filmu pozostają
w jednej rodzinie; różne foldery nie są automatycznie niezależnymi filmami.

Wyjątek doprecyzowany przez operatora 2026-09-27: nowe Treasure
`seq_23590–23913` (36 zdjęć, metadata `sourceDirectoryName=tresure23600`)
najprawdopodobniej pochodzi z tego samego filmu co dawne zdjęcia
`tresure zd/tresure23600__tresure23600_002634.jpg` oraz
`tresure zd/tresure23600__tresure23600_010010.jpg`. Traktować cały wskazany
nowy zakres i dawne źródła tresure23600 jako jedną grupę ochrony przed
przeciekiem, bez dzielenia jej między train/validation/test. Przesłanki stanowią
metadane oraz ostrożna deklaracja operatora, nie niezależne potwierdzenie
tożsamości filmu. Nie przenosić geometrii na nowe piksele ani nie oznaczać
tej deklaracji jako pełnej weryfikacji pozostałych rodzin. Brak potrzeby
ponawiania tego pytania lub rysowania niezmienionych siatek. Następnym krokiem
pozostaje techniczne mapowanie i kontrola pozostałych powiązań.

Doprecyzowanie operatora 2026-09-27: konkretne katalogi Treasure to
`D:\tresure zd\tresure23600` dla 36 nowych zdjęć `seq_23590–23913` oraz
`D:\tresure zd\tresure427100` dla pozostałych 64 zdjęć `seq_429661–430236`.
Operator jawnie poprawił wcześniejsze `439***` na `429***`; w drugiej grupie
38 nazw zaczyna się od 429 i 26 od 430. Odczyt potwierdził istnienie obu
katalogów i te zakresy w 100 zdjęciach folderu treningowego; brak `seq_439*`.
Traktować jako deklarację katalogu pochodzenia, nie niezależne potwierdzenie
tożsamości pikseli ani rozłączności filmów. Nie wymagać drugiego eksportu
wyłącznie po to, by ponownie pytać o już zadeklarowany katalog. Przed freeze
nadal powiązać z dawnymi źródłami i sprawdzić konflikty, bez przenoszenia
geometrii lub akceptacji na nowe piksele.

Wznowienie po przeglądzie: ostatni odczyt wykazał 63 zaakceptowane zdjęcia,
180 pełnych geometrii i brak zapisanych rodzin/splitu; liczności wymagają
ponownego odczytu. Użytkownik potwierdza geometrię, nie poprawność symboli.
Nowe bieżące sprawdzenie: SHA i rewizje akceptacji, węzły i granice źródła,
liczności per gra/topologia, exact duplicates i stan dowodów rodzin.
Wynik nie może udawać wizualnej walidacji ani potwierdzać niezależności
po samych nazwach. Planowana kontrola nie zapisuje decyzji, nie zamraża
splitu i nie zmienia roli 777. Raport:
`ai_docs/quality/VISION_LAB_STAGE_B_DATA_PREFLIGHT.md` (nowy).
Sprawdzone moduły: `catalog.py::Catalog`, `annotations.py::read_checked`,
`photo_review.py::photo_accepted`, `geometry.py::cell_quads`,
`splits.py::freeze_splits` w `services/worker/src/game_predictor_worker/vision_lab`.
Komendy diagnostyczne ograniczone do istniejącego zbioru, timeout do 120 s.
Odczyt nie zastępuje mapowania deklarowanego pochodzenia do konkretnych
źródeł i rodzin; nierozstrzygnięty konflikt jest raportowany jako blokada,
bez osłabiania istniejących testów.

Etap B uruchomiony jawnie przez użytkownika 2026-09-26. Na wejściu jest
snapshot plikowy T02 (1180 wystąpień, 1160 SHA), bez ręcznych anotacji.
Prefiksy rodzin są kandydatami, nie potwierdzonym pochodzeniem. Budowa
edytora i mechanizmów splitu jest możliwa; zamrożenie rzeczywistych danych
oraz trening wymagają potwierdzonego pochodzenia i decyzji człowieka.
Nie wolno zastąpić tych decyzji automatycznym zatwierdzaniem baseline.
Kandydat niewidzianej gry `gang zd` pozostaje warunkowy do kontroli rodzin
i pokrycia topologii. Pomiar czasu anotacji musi być rzeczywisty, nie
oszacowany z czasu działania agenta.

Doprecyzowanie użytkownika: foldery mają różne konwencje numeracji,
prefiksy nie mają wspólnego standardu, a różne nazwy mogą przedstawiać ten
sam układ plansz. SHA-256 wykrywa tylko identyczne bajty, nie wszystkie
takie powtórzenia. Relacje powiązanych źródeł/pochodnych muszą być jawnie
grupowane wraz z duplikatami SHA; brak dopasowania nie potwierdza
niezależności. Nie wolno automatycznie zamrozić splitu według nazw.

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/api/src/game_predictor_api/domain/board_topology.py::BoardTopology`, `apps/vision-lab/src/app/page.tsx::Page`. Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/annotations.py::approve_geometry`, `.../splits.py::freeze_splits`, `apps/vision-lab/src/components/geometry-editor.tsx::GeometryEditor`, `services/worker/tests/test_vision_lab_annotations.py`.

## Test cases

- Rewizja cropa unieważnia approval; dwa zdjęcia jednej rodziny zawsze w jednym splicie; backup po restarcie zachowuje decyzje; interpolacja nie jest referencją.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_annotations.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## T03e — kwalifikacja geometrii historycznego 777

Status `done` (podzadanie; nadrzędny T03 nadal blocked). Zależność D-453, wznowienie B przez użytkownika;
wykonawca `gpt-6-sol` / `medium`, niezależny audyt `gpt-6-astra` / `medium`.
Cel: jawnie dopuścić pełne ręczne geometrie historycznego 777 do geometry-only
splitu, bez zmiany ról snapshotu ani uprawnień do uczenia symboli.

### Kontrakt wykonawczy

- Nowe `GeometryQualificationRequest(Mutation)` i binding źródła: source_id,
  source_sha256, expected_board_revisions. Request zawiera dokładny game_id,
  wersję `historical-777-lab-geometry-v1`, referencję `D-453` i niepustą,
  ograniczoną listę unikalnych bindings. Zakres zawsze geometry. Sprawdzić
  dokładną tożsamość historycznego folderu 777 w katalogu, nie substring
  nazwy albo samo comparison_only. Źródła DB bez dowodu tej tożsamości
  pozostają poza pierwszym wariantem; V2 nie jest promowane.
- Nowe `StoredGeometryQualification` wiąże binding, game_id, politykę,
  autora, czas i rewizję decyzji. `AnnotationState.geometry_qualifications`
  ma domyślnie pustą mapę. Stare payloady nadal się odczytują bez zapisu.
- `AnnotationStore.mutate`: snapshot/CAS, istnienie i unikalność źródeł,
  jawna tożsamość gry/rola comparison_only, zgodne SHA i mapa rewizji,
  photo_accepted, co najmniej jeden pełny obecny target z węzłami human.
  Wszystkie bindings walidowane przed jednym atomowym zapisem; błąd dowolnego
  elementu nie kwalifikuje części batcha. Receipt/retry działa jak istniejące
  mutacje; zmieniony payload przy tym samym request_id daje konflikt.
- Proponowany `geometry_qualification.py` jest właścicielem wspólnej
  walidacji skuteczności decyzji. Nie zapisuje anotacji, photo review ani
  rodzin. Nie wymaga ukończonych rodzin do samej kwalifikacji; freeze nadal
  bezwarunkowo wymaga poprawnego pochodzenia i wszystkich dotychczasowych bramek.
- `SplitRequest` rozróżnia dotychczasowy tryb (domyślny przy pominięciu nowego
  pola) i jawny purpose geometry. Tylko geometry może użyć kwalifikacji D-453.
  Nowy `FrozenSplit` zachowuje purpose i wersję polityki, fingerprints
  kwalifikacji oraz osobną mapę pełnych obecnych ręcznych targetów. Szkice,
  lokalizacje i predykcje nie stają się targetami. Brak targetów wyklucza
  źródło. Stare fingerprints i assignments nie są przeliczane przy odczycie.
- Edycja geometrii, odrzucenie/utrata akceptacji albo zmiana rodzin nadal
  daje stale. Ponowna kwalifikacja jest nowym requestem z bieżącymi bindings;
  nie zmienia istniejącego zamrożonego podziału. Odczyt wykrywa także utratę
  skuteczności kwalifikacji. Nie otwierać nowego toru symboli ani zmieniać
  Source.training_eligible, ról i metadanych katalogu.
- Proponowany `qualify_geometry.py`: request z pliku JSON, domyślny preview
  przez read_checked bez tworzenia katalogu/.lock; apply przez ten sam
  AnnotationStore. Odczyt i walidacja bez mutacji, błąd z konkretnym powodem;
  apply ponawia walidację pod lockiem. Retry po utracie odpowiedzi i nowy
  proces zwracają tę samą utrwaloną decyzję, nie drugą rewizję.
- `rebase_annotations.py` ma jawny fail-closed dla niepustych kwalifikacji
  i ich historii; nie pomija referencji. Obsługa ich przenoszenia poza T03e.
  Backup/restore do nowego katalogu zachowuje cały payload.
- Istniejące API/OpenAPI, klient generowany, wrapper i test odczytu stanu
  aktualizowane spójnie. Brak nowej trasy i UI. Nowy request kwalifikacji
  dostępny wyłącznie przez CLI, istniejący transport nie przyjmuje go niejawnie.

### Pliki i weryfikacja

Istniejące moduły w services/worker/src/game_predictor_worker/vision_lab:
annotation_contracts.py, annotations.py, splits.py, rebase_annotations.py;
nowe geometry_qualification.py i qualify_geometry.py. Nowe testy kwalifikacji
oraz istniejące test_vision_lab_annotations.py, test_vision_lab_photo_review.py
i test_vision_lab_rebase.py (nazwy potwierdzone w repo).
Kontrakt: packages/vision-lab-api-client/openapi/openapi.json, wygenerowane
typy, wrapper i testy klienta. Root prowadzi CURRENT_STATE i commit.

Przypadki: poprawne 777 z zachowaniem SHA/role/anotacji; inna gra, inne
comparison_only, V2, złe SHA/mapa, brak akceptacji, brak full/human, duplikaty
bindings i częściowo błędny batch odrzucone. CAS/race, konflikt request_id,
restart i utracona odpowiedź, backup/restore, edycja/reject po freeze,
niezweryfikowane rodziny, rebase fail-closed, stare payloady i brak pola
purpose zachowują zachowanie. API i klient potwierdzają additive odpowiedź.

Najpierw focused pytest (limit 120 s), potem Ruff format/check, mypy lab,
testy klienta/typecheck oraz `npm run vision-lab:openapi:check` z package.json.
Generowanie: `npm run vision-lab:openapi:generate`. Każda komenda skończona
ma limit; testy są planowane, nie wykonane. Po audycie porównać DoD punktowo.
Kryterium ukończenia T03e nie obejmuje zamrożenia realnego splitu ani treningu.
Aliasy Reels/cohort i import nowych zdjęć to osobny następny pion T03.

### Outcome T03e

- Zrealizowano wersjonowany geometry-only request/binding i atomowy batch
  w AnnotationStore z CAS, receipts, historią, backupem oraz wspólną walidacją.
  CLI preview nie tworzy .lock; apply powtarza walidację pod istniejącą blokadą.
  Dokładne folderowe 777/game_id/SHA/mapa, pełny human target i photoacceptance
  są wymagane. Nie zmieniono roli, anotacji, photo reviews ani uprawnień symboli.
- Jawny geometry split zapisuje wersję, qualification fingerprints i osobne
  full/present/human target fingerprints; topologie liczone tylko z targetów.
  Legacy split/receipts zachowane, odczyt nie przelicza dawnych fingerprintów.
  Edycja/reject/rodziny/kwalifikacja dają stale; reaccept nie usuwa stale.
  Rebase jawnie odrzuca kwalifikacje także obecne wyłącznie w historii.
- Focused backend końcowo 54/54 PASS (41,29 s): kwalifikacja, anotacje,
  photo review i rebase. Obejmuje atomic batch/race, błędne bindings,
  nowe procesy po utracie odpowiedzi, legacy receipt retry, backup/restore,
  rebase fail-closed, brak side effects preview, stale i pokrycie topologii.
  Poprzedni przebieg 52/52 PASS zawierał podzbiór tych regresji.
- Ruff format/check PASS; mypy lab 15 modułów PASS; OpenAPI/generated check
  PASS; klient 5/5 PASS; TypeScript klienta i UI PASS, także po eksportach
  wrappera. API GET zwraca kwalifikacje; POST /annotations odrzuca nowy
  request (CLI-only). Bez nowych tras/UI. git diff --check PASS.
- Root wykonał wyłącznie realny preview rewizji 259: 11 zaakceptowanych
  zdjęć 777 / 30 pełnych siatek, status ready. Fingerprint requestu
  `fa81cb9623e84d1a9ec15907d65ff55db763a133878bb70e5ef11edbcb94c72b`.
  SHA state przed/po identyczny (`22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586`).
  Artefakty: artifacts/vision-lab/t03e-777-qualification-request-rev259.json
  i t03e-777-qualification-preview-rev259.json. Nie wykonano apply.
- Wymagania, architektura, plan i instrukcja operatora opisują mechanizm
  oraz obowiązek import/rebase przed realną kwalifikacją. Bez realnego
  importu, apply, freeze, usług, treningu, buildu UI lub pełnych testów repo.
  Aliasy/cohort Reels i bramki danych całego T03 pozostają osobnym krokiem.
- Porównanie z kontraktem T03e: jawność i izolacja D-453, atomowość,
  trwałość/retry, aktualność kwalifikacji, targety, legacy compatibility,
  rebase fail-closed oraz spójny odczyt API potwierdzone powyższymi testami.
  Niezależny audyt Astra medium PASS, bez P0–P2; audytor powtórzył backend
  qualification/photo review 36/36 PASS (27,42 s) i klient 5/5 PASS.
  T03e spełnia powyższe DoD; nadrzędny T03 pozostaje blocked na danych,
  więc plik pozostaje aktywny. Commit T03e: `v1.7.21` /
  `6ae971dfc1bd9e97b563a7774594fac59f3f441d`. Hash dopisany po commicie;
  staged check/stat/list oraz show/stat/status PASS. Obce hunki poza commitem.

## T03f — jawna kohorta targetów geometrii

### Status, cel i warunki wejścia

Status `done` — kontrakt i końcowy kod odebrane przez niezależny audyt
Astra medium, bez P0–P2. Zależność: odebrany T03e, wznowienie etapu B.
Cel: wybrane zaakceptowane źródło może być targetem bez zatwierdzania jego
nieanotowanego aliasu; pełny graf pochodzenia nadal zapobiega przeciekowi.
Potwierdzona przyczyna: freeze_splits grupuje cały Catalog, ale wymaga zgód
każdego członka, także aliasu poza planowaną kohortą. Dotyczy to pięciu
zaakceptowanych zdjęć Reels; liczność nie jest stałą implementacji.
Brak rodzin lub decyzji danych nie blokuje izolowanych testów mechanizmu,
ale nadal blokuje rzeczywisty freeze i T04/T05.

### Recommended execution / Relevant docs

`gpt-6-sol` / `medium`; niezależny audyt `gpt-6-astra` / `medium`.
Ryzyko obejmuje przeciek przez niewybrane źródła, zachowanie starych receipts
i oddzielenie członkostwa od targetów. Nierozwiązane P0–P2 po dwóch cyklach
lub sprzeczność kontraktów zatrzymują wykonanie. Modele dostępne w sesji.
Relevant docs: dokumenty nadrzędnego T03, PLAN_STANDARD, TASK_TEMPLATE,
sekcje T03e/T03f planu; nie wczytywać niezwiązanych archiwów.

### Scope i Technical notes

- SplitRequest otrzymuje opcjonalne `geometry_source_ids: list[str] | None`
  z domyślnym None i limitem 10000. None zachowuje dokładne zachowanie
  legacy i geometry T03e. Jawna kohorta wymaga purpose geometry, niepustej
  listy unikalnych, znanych source_id. Nie wybiera źródeł według nazw,
  akceptacji ani pierwszego wystąpienia SHA automatycznie.
- Request zachowuje kolejność podaną przez klienta do receipt fingerprintu.
  Przy None usuwać nowe pole z request_data przed fingerprintem/historią;
  zachować istniejące usuwanie purpose legacy. Dzięki temu stare receipts
  obu trybów działają bez przepisywania. Zmieniona lista/kolejność przy tym
  samym request_id daje REQUEST_ID_CONFLICT; nowe ID nie omija CAS ani
  SPLIT_ALREADY_FROZEN. Dokładny retry po utracie odpowiedzi działa po restarcie.
- Graf nadal obejmuje cały Catalog: SHA, family_id i przechodnie relacje
  source_ids/related_source_ids. Dla komponentu selected oznacza przecięcie
  z jawną kohortą. Brak selected wyłącza komponent z losowania i liczby grup.
  Wyodrębnić wspólny czysty helper budowania komponentów z obecnej funkcji
  freeze_splits bez zmiany deterministycznej kolejności starego algorytmu.
- Na CAŁYM komponencie dotykającym kohorty obowiązują dotychczasowe bramki
  role/D-453 oraz families.provenance=verified. Nieanotowany alias data
  może być członkiem, ale inne comparison_only i nierozstrzygnięte V2 nadal
  blokują; kwalifikacja D-453 nie rozszerza się na aliasy. Nie zapisujemy
  żadnych rodzin, kwalifikacji lub zatwierdzeń w toku freeze.
- Tylko selected musi posiadać location approval, photo_accepted i pełny
  present/human target. Błąd dowolnego selected wyklucza wszystkie selected
  tego komponentu; pozostałe poprawne komponenty mogą wejść do wyniku,
  jeżeli wszystkie bramki całego splitu są spełnione. Losowany jest komponent,
  lecz assignments, measurement i wszystkie mapy targetów/anotacji/kwalifikacji
  zawierają wyłącznie wybrane źródła. Alias nie dziedziczy zgody ani targetu.
- Każde źródło poza jawną kohortą dostaje NOT_IN_GEOMETRY_COHORT w exclusions.
  Wybrane źródła wykluczone przez bramkę dostają jej istniejący konkretny powód.
  Brak wymaganych pełnych targetów: FULL_HUMAN_GEOMETRY_TARGET_REQUIRED.
  Wybór źródła nie jest deklaracją niezależności lub potwierdzeniem rodziny.
- FrozenSplit dla jawnej kohorty ma policy_version
  `lab-geometry-cohort-split-v1`, posortowane geometry_source_ids oraz
  leakage_components: mapę reprezentant → posortowani członkowie dla
  WSZYSTKICH komponentów katalogu, również niedotykających kohorty.
  leakage_component_fingerprints wiąże dla każdego komponentu pełne Source,
  StoredFamily albo jawny brak decyzji oraz StoredGeometryQualification
  każdego członka niedata (jawny null przy braku), w kolejności source_id. Reprezentant
  to najmniejsze source_id jak w obecnym union. Obie mapy i kohorta wchodzą
  do nadrzędnego fingerprintu splitu wraz z dotychczasowymi danymi.
  Nowe pola mają None/{}/{} dla odczytu starych danych; nie dopisywać ich do
  danych hashowanych przy freeze bez kohorty. Stare fingerprints bez zmian.
- Kontrola unseen używa gier CAŁEGO komponentu. Niewybrany most do unseen
  nie omija UNSEEN_GAME_RELATED_TO_DEVELOPMENT. Pokrycie topologii wyłącznie
  z wybranych pełnych human targetów, zgodnie z T03e. Nadal wymagane unseen
  i co najmniej trzy niezależne komponenty development.
- Measurement wymaga niepustych, unikalnych ID należących do kohorty
  i przechodzących kwalifikację. Komponent dotykający measurement przenosi
  wszystkie swoje selected do measurement, nigdy części do development.
  Wymagane difficulties dla WSZYSTKICH członków komponentu, jedna trudność
  i jedna gra oraz dwie niezależne grupy na stratum; baseline/hybrid przypisuje
  się grupie. Te metadane nie zatwierdzają niewybranych aliasów.
- Walidacja kształtu/kombinacji celu, nieznanych/duplikowanych ID i measurement
  poza kohortą kończy całą operację bez stanu/receiptu/history; czytelne nowe
  powody GEOMETRY_COHORT_PURPOSE_REQUIRED, GEOMETRY_COHORT_EMPTY,
  GEOMETRY_COHORT_DUPLICATE_SOURCE, GEOMETRY_COHORT_SOURCE_NOT_FOUND,
  MEASUREMENT_OUTSIDE_GEOMETRY_COHORT, MEASUREMENT_DUPLICATE_SOURCE.
  Błędy domenowe istniejącego /splits zwracają 409, błędy schematu 422.
  Korekta wymaga poprawnego requestu; brak ukrytego częściowego zapisu.
- Istniejący AnnotationStore jest jedynym właścicielem atomowego zapisu
  pod lock/CAS. _view nadal sprawdza photoacceptance wyłącznie assignments;
  dla nowej wersji dodatkowo porównuje pełne komponenty/fingerprints z
  aktualnym stanem, oznaczając stale przy zmianie bez przepisywania splitu.
  Ponadto sprawdza qualification_effective WSZYSTKICH członków niedata
  komponentów zakwalifikowanych do assignments, także niewybranych mostów.
  Utrata ich akceptacji jest stale nawet bez zmiany Source/rodziny/kwalifikacji.
  Stały brak kwalifikacji w całkowicie wykluczonej grupie nie daje stale;
  mapy targetów i ich qualification fingerprints pozostają selected-only.
  Pozostawić konserwatywne stale po mutacji geometrii/review/rodziny/kwalifikacji
  także poza kohortą. Nie kasować stale po reaccept, retry lub przywróceniu
  poprzedniej relacji. Backup/restore/new process zachowują wszystkie pola.
  Rebase z istniejącym splitem nadal jest zablokowany.
- Addytywny kontrakt istniejącego POST /splits oraz odpowiedzi AnnotationState:
  backend, OpenAPI, generated client, wrapper freezeAnnotations i test requestu
  aktualizowane razem. Nie powstaje nowy endpoint/UI ani magazyn decyzji.

### Expected files

Istniejące w services/worker/src/game_predictor_worker/vision_lab:
annotation_contracts.py (SplitRequest/FrozenSplit), annotations.py (mutate/_view),
splits.py (freeze_splits i proponowane build_components/component_fingerprints).
Istniejące test_vision_lab_annotations.py, test_vision_lab_geometry_qualification.py,
test_vision_lab_photo_review.py; nowy proponowany test_vision_lab_geometry_cohort.py.
Kontrakt packages/vision-lab-api-client/openapi/openapi.json, src/generated,
src/index.ts, test/request.test.mjs. Dokumenty wymagań/architektury/guide
VISION_LAB oraz task/plan aktualizowane przy implementacji. Root: CURRENT_STATE,
DECISION_LOG, realne operacje i commit.

### Acceptance criteria / Test cases

- [x] Zaakceptowany Reels + nieanotowany alias SHA: z kohortą jedno assignment,
  alias wyłącznie w pełnym komponencie; bez kohorty stare wykluczenie.
- [x] Niezweryfikowany alias, niedozwolona rola lub V2 blokują selected;
  żadna rodzina, kwalifikacja, anotacja lub photo review nie jest dopisywana.
- [x] Przechodni most przez niewybrane źródła scala grupę; niewybrany członek
  unseen powoduje konflikt; liczby grup nie rosną od liczby aliasów.
- [x] Measurement spoza kohorty/duplikaty/stratum/difficulty/unseen/pokrycie
  topologii są fail-closed; komponent nigdy nie dzieli measurement/development.
- [x] Puste, nieznane i duplikowane ID oraz legacy+kohorta odrzucone; brak
  pełnego targetu wyklucza komponent, bez częściowego zapisu operacji.
- [x] Pełny graf/fingerprints wszystkich komponentów są zamrożone, a targety
  obejmują wyłącznie kohortę. Odczyt i mutation wykrywają stale, także zmianę
  niewybranego aliasu/rodziny; assignments/fingerprint pozostają niezmienne.
- [x] Utrata/zmiana kwalifikacji lub reject niewybranego 777 w zakwalifikowanym
  komponencie daje stale mimo niezmienionego grafu Source/rodzin; stała
  niekwalifikowana grupa całkowicie wykluczona nie unieważnia wyniku.
- [x] Nowy proces, utracona odpowiedź/retry, race/CAS i backup/restore PASS;
  oba historyczne rodzaje receiptów oraz stare fingerprints zachowane.
- [x] API/generated/wrapper przesyłają dokładną kohortę i odczytują pełne mapy;
  UI typecheck i dotychczasowy workflow bez kohorty zachowane.

### Verification, granice i Outcome

Procedura weryfikacji (wyniki wykonania poniżej): focused pytest wraz z annotations,
geometry_qualification i photo_review; małe izolowane fixture, limit 120 s
na proces jak w Verification nadrzędnego taska. Następnie Ruff format/check,
mypy --follow-imports=silent modułów labu, npm run vision-lab:openapi:generate,
npm run vision-lab:openapi:check, test i typecheck workspace
@game-predictor/vision-lab-api-client oraz typecheck @game-predictor/vision-lab.
Każdy skończony proces z jawnym timeoutem do 120 s; zero benchmarków.
Zaliczenie: wszystkie kryteria, spójny kontrakt i niezależny audyt bez P0–P2.
Zakres wyłączony: realne freeze/import/rebase/apply, automatyczne rodziny,
kopiowanie zgód, zmiany ról, symbole, migracje DB, nowe UI i trening T04/T05.
Kohorta sama nie dowodzi niezależności i nie zamyka T03. Następny krok po
odbiorze narzędzia: odczytowy preview konkretnej kohorty i pozostałych bramek.
### Outcome T03f — odebrane

- Jawna kohorta działa przez istniejący /splits i AnnotationStore. Pełny graf
  SHA/rodzin/relacji obejmuje wszystkie źródła. Role i verified są sprawdzane
  dla wszystkich członków, zgody i targety tylko dla wybranych. Alias nie
  otrzymuje targetu, akceptacji ani assignmentu. Brak kohorty zachowuje legacy
  i T03e, łącznie z kolejnością algorytmu, fingerprintami i receipts.
- Nowa wersja zamraża całą mapę komponentów, pełne metadane źródeł/rodzin
  i kwalifikacji niedata. Odczyt sprawdza również skuteczność kwalifikacji
  niewybranego członka użytej grupy; trwały brak kwalifikacji w całkowicie
  wykluczonej grupie nie unieważnia splitu. Stale nie zmienia przydziałów.
- Backend pierwszy fokus: **64/64 PASS** (70,48 s), cohort + qualification
  + annotations + photo_review. Rozszerzony cohort: **24/24 PASS** (43,41 s),
  czyli łącznie 69 różnych przypadków tych czterech plików. Dodatkowo
  **11/11 PASS** (11,28 s): dwa powtórzone legacy/geometry retry na starych
  payloadach bez trzech nowych pól oraz dziewięć regresji rebase. Razem
  78 różnych przypadków backendu, bez pełnego uruchomienia repozytorium.
- Ruff check i format PASS (17 plików format), mypy lab --follow-imports=silent
  PASS (15 modułów). Klient **6/6 PASS**, TypeScript klienta i lab UI PASS.
  OpenAPI wygenerowane, OpenAPI/generated check PASS. Wrapper zachowuje
  dokładną kolejność requestu; jego test przesyła kohortę i odczytuje wszystkie
  mapy. Bez ręcznie rozbieżnych typów, nowego endpointu ani UI.
- DoD punktowo: alias bez zgód, role/provenance, przechodni most/unseen,
  liczba niezależnych grup i pomiar całego komponentu, selected-only topology,
  nieprawidłowe requesty/HTTP409/422, pełny graf/fingerprints i stale, kwalifikacja
  niewybranego 777, nowy proces/retry/race/backup oraz zgodny klient mają
  izolowane regresje. Niezależny audyt Astra medium PASS bez P0–P2;
  audytor osobno wykonał cohort 24/24 (41,96 s) i klient 6/6 (0,18 s).
- Wymagania, architektura, guide i plan opisują wdrożony zakres. Nie wykonano
  rzeczywistego freeze/import/rebase/apply, zmian ról lub zgód, restartu usług,
  treningu, pełnego buildu ani pełnych testów repo. Testy nie potwierdzają
  niezależności realnych nagrań; T03/T04/T05 zachowują wcześniejsze bramki.
- Pierwszy start Pythona został zablokowany przez sandbox (exit101), właściwe
  testy uruchomiono z zatwierdzoną eskalacją. Jedno dodatkowe wywołanie pytest
  miało błąd cytowania filtra PowerShell (exit4, bez testów); poprawiono samo
  wywołanie. Żaden test ani bramka nie zostały osłabione. Zastane ostrzeżenie
  Starlette/AnyIO pozostaje poza zakresem.
  Końcowy git diff --check PASS. Commit T03f: `v1.7.22` /
  `d179e8fd46366aa90a06b1187fe2980fd28cfb76`; staged check/stat/list oraz
  show/stat/status PASS, obce zmiany poza commitem.
  Podzadanie done; nadrzędny plik pozostaje aktywny/blocked do odbioru danych T03.

## T03g — addytywny import i zachowanie zapisów

Status `done`. Cel: dołączyć 473 zdjęcia bez utraty 993 źródeł, 180 siatek
i 63 akceptacji. Wykonanie `gpt-6-sol` / `medium`, niezależny audyt
`gpt-6-astra` / `medium` przed operacją oraz po jej wykonaniu. Warunki wejścia:
niezmieniony stan rewizji 259, brak rodzin/splitu/kwalifikacji, zgodne referencje.
Relevant docs: wymagania i architektura VISION_LAB, D-453, T03c/T03e,
PLAN_STANDARD/TASK_TEMPLATE. Plan zapisany przed wykonaniem:
`artifacts/vision-lab/t03-additive-import-proposed-plan.md`; helper operacyjny
korzysta z istniejących snapshot.import_folder i rebase_annotations.

Scope: jawne mapowanie sześciu nazw gier, nowe ścieżki partii, kontrola wszystkich
SHA, backup, raport pochodzenia i kopie sidecarów, nowy immutable snapshot,
preview i apply do nowego store. Brak usuwania, nadpisania starych danych,
przenoszenia zgód na inne piksele, zmian ról, rodzin, splitu lub treningu.
Nie przełączać działających usług. Każda różnica ID/SHA/metadanych referencji,
stanu, backupu albo przypiętych digestów zatrzymuje operację bez obchodzenia
guardów. Retry akceptuje tylko dokładnie ten sam opublikowany wynik.

Kryteria odbioru i wykonane kontrole: wszystkie stare wpisy manifestu identyczne;
1466 wystąpień / 1440 SHA / 6 gier; cały payload równy poza snapshot_id;
180 pełnych siatek, 63 aktualne akceptacje i 259 history/receipts zachowane;
brak nowych zatwierdzeń; backup identyczny; nowy proces daje already_applied.
Przed apply brak writera na 8102, po operacji brak osieroconego helpera.
Limity pojedynczego helpera 60 s, brak benchmarków i zmian kodu aplikacji.

Outcome: wszystkie kryteria PASS, niezależny audyt Astra medium bez P0–P2.
Restart komputera nastąpił między importem i rebase; świeże odczyty potwierdziły
import. Rebase i retry potwierdzone w nowych procesach, bez kolejnego restartu OS.
Dokładne ścieżki/digests/logi: `ai_docs/quality/VISION_LAB_ADDITIVE_DATA_20260927.md`.
Guide wskazuje nowy snapshot/store. Bez usług, kwalifikacji, freeze i treningu.
Commit T03g: `v1.7.23` / `6e1879eeae85121f75e06ff987fc9f37affa4197`.
Staged check/stat/list i show/stat/status PASS. Następny krok: osobny T03h.

## T03h — zastosowanie jawnej kwalifikacji geometrii 777

Status `done`, kontrakt, preview i końcowe dane odebrane przez audyt Astra medium.
Cel: utrwalić wcześniej autoryzowaną decyzję D-453 dla dokładnych
11 zdjęć / 30 nowych ręcznych siatek 777 w nowym store. Wykonawca
`gpt-6-sol` / `medium`, niezależny audyt `gpt-6-astra` / `medium` przed apply
i po wyniku. Zależność: odebrany i osobno zapisany T03g; dotychczasowy preview
na nowym snapshot/store daje ready, rewizja 259. Relevant docs jak T03g oraz
kontrakt T03e i CLI qualify_geometry. Bez nowego kodu, API lub UI.

Wejście: snapshot/store 0cdc0770… (pełne ścieżki w raporcie T03g), SHA stanu
`ef5903646401fc95225542126e84a85e8d0991bebcbb177efbdb916606de0f01`, request
`artifacts/vision-lab/t03e-777-qualification-request-rev259.json`, fingerprint
`fa81cb9623e84d1a9ec15907d65ff55db763a133878bb70e5ef11edbcb94c72b`.
Request nie był zastosowany na starym store; nie zmieniać jego bindings,
autora ani rewizji. Rebase zachował źródła, więc nowy preview wiąże te same SHA.

Kolejność: kontrola braku writera, świeży preview, istniejący AnnotationStore.backup
i sprawdzenie kopii, kwalifikacja istniejącym CLI --apply pod CAS, nowy proces
preview/retry tego samego requestu. Każdy krok skończony do 60 s. Różnica SHA,
rewizji, źródła, requestu, kopii lub konflikt zatrzymuje apply bez nadpisania.
Po niepewnej odpowiedzi najpierw odczytać receipt; nie tworzyć nowego request_id.

Acceptance: rewizja 260, dokładnie 11 skutecznych kwalifikacji, jeden nowy
receipt/event; wszystkie anotacje, akceptacje, timingi i wcześniejsza historia
identyczne. Nowy proces rozpoznaje already_applied; ponowienie apply nie zwiększa
rewizji/historii. Stary store/snapshot i snapshot nowy bez zmian. Brak zmiany
comparison_only, rodzin, podziału, zgód symboli lub nowych zdjęć. Qualification
nie odblokowuje treningu bez pozostałych bramek. Rebase z kwalifikacjami pozostaje
zablokowany; nie usuwać decyzji, aby obchodzić tę granicę przy kolejnych importach.
### Outcome T03h — odebrane

- Wszystkie sześć kroków limit 60 s, exit 0, stderr pusty: świeży preview,
  istniejący backup z pełnym porównaniem, CLI apply, nowy proces preview,
  nowy proces identycznego apply retry oraz końcowe read_checked/Catalog.
- Rewizja 260, dokładnie 11 skutecznych kwalifikacji / 30 pełnych ręcznych
  targetów, jeden nowy receipt/event. Pozostały payload identyczny z backupem;
  180 anotacji, 63 aktualne akceptacje i 196 timingów bez zmian. Zero rodzin,
  brak splitu, żadnej zmiany ról lub symboli. Stary store i oba snapshoty nietknięte.
- Nowy proces preview zwraca already_applied; powtórny apply nie zmienia
  SHA/revision/history. Sam CLI zwraca applied również dla receipt replay,
  dlatego odbiór opiera się na porównaniu danych, nie samym tekście statusu.
- Backup ID `8377e75c24281af07136724f5db9ec70d312bd87a7d90f6893a29484431ef62f`;
  SHA stanu po: `ad7c3d8248d303696e701819d705e949be9df094c3e1c2e74e317e7ef8456f17`.
  Ścieżki, logi i digesty: VISION_LAB_ADDITIVE_DATA_20260927.md / T03h
  oraz artifacts/vision-lab/t03h-qualification-operation-outcome.md.
- Bez testów aplikacji dla samej operacji (kod niezmieniony), restore,
  restartu OS/usług, treningu, aktywacji, cleanupu i push. Trwałość sprawdzona
  w nowych procesach; brak osieroconych procesów i listenera 8102.
  DoD porównano punktowo z kontraktem powyżej. Końcowy niezależny audyt Astra
  medium PASS bez P0–P2: nowy proces potwierdził ścisłą różnicę payloadu,
  zgodność backupu, 11/30 skuteczność i already_applied bez zmiany SHA.
  Audytor dopasował diagnostykę do braku opcjonalnego pola w dawnym payloadzie;
  nie przepisywano danych ani nie osłabiano kontraktu. Commit T03h: `v1.7.24` /
  `1434f2135a1056760d5581f9ad180cfb1ccd1d6e`. Staged check/stat/list oraz
  show/stat/status PASS; obce zmiany zachowane. Hash dopisany po commicie.
  Podzadanie done, nadrzędny plik pozostaje aktywny.
  Nadrzędny T03 pozostaje blocked na rodzinach i podziale, nie na kwalifikacji 777.

## T03a — ergonomia edytora i bieżące cropy

Status: `done` (podzadanie; nadrzędny T03 nadal blocked na danych). Polecenie użytkownika 2026-09-26; wyłącznie laboratorium
3102. Wykonawca `gpt-6-sol` / `medium`, niezależny audyt `gpt-6-astra` / `medium`.
Duży edytor po lewej i zwarte cropy po prawej, automatyczny podgląd bieżących
węzłów po puszczeniu uchwytu. Kadr zdjęcia dopasowuje się do granic siatki
z 8% marginesem dopiero po puszczeniu; podczas gestu pozostaje zamrożony.
Zdjęcie nie jest rektyfikowane, współrzędne źródła i rewizje są zachowane.
Powrót do pełnego zdjęcia jest jawny; małe etykiety mają stabilny rozmiar
ekranowy i większy obszar chwytania. Początkowa propozycja obejmuje 70% zdjęcia.

Istniejący POST `/geometry` otrzymuje opcjonalne `preview_board` (kontrakt
Board); brak pola zachowuje baseline. Preview używa `cell_quads` i `crop_cell`,
zwraca istniejący GeometryResult i tylko nietrwałe assety. Błędna geometria
nie pokazuje starych cropów; nieobecność i brak węzłów nie uruchamiają żądania.
Frontend unieważnia trwające odpowiedzi przy każdej zmianie geometrii,
źródła, planszy i topologii; najnowsze żądanie jest jedynym przyjmowanym.
Podgląd nie zapisuje szkicu, decyzji, rewizji ani podziału.

Pliki: geometry-editor.tsx, nowy lib/editor-viewport.ts i lib/latest-preview.ts,
style.css, vision_lab/contracts.py, catalog.py, api.py, OpenAPI i generowany
klient/wrapper oraz testy UI, API i klienta. Dokumenty wymagań/architektury
i plan są aktualizowane; CURRENT_STATE prowadzi koordynator.

Kryteria/testy: mapowanie pointera po zoomie, nieruchomy kadr podczas drag,
dopasowanie po release, powrót do pełnego zdjęcia, obie topologie, zgodność
bajtów cropów z crop_cell, błędna/brak geometrii, odwrócona kolejność
odpowiedzi i zmiana źródła. Testy skoncentrowane → lint/typecheck → kontrola
OpenAPI/generowania → build i odbiór przeglądarkowy; każdy proces limit 120 s.
Nie obejmuje rzeczywistych zatwierdzeń ani odblokowania T04/T05.

### Outcome T03a

- Commit `v1.7.3` — `5db0a10bfa464526a6eb08dd6611cdafc9c262bf`.
  Hash uzupełniony po commicie, lokalnie do kolejnego commita.
- Wdrożono edytor/kadr, małe uchwyty z 44 px obszarem chwytania, sidebar
  cropów i automatyczny preview po release. Viewport nie zmienia geometrii.
  Stare odpowiedzi są unieważniane również na początku kolejnego drag.
- POST `/geometry` przyjmuje `preview_board`; cropper i walidacja pozostają
  wspólne z baseline, a brak pola zachowuje dotychczasowe zachowanie.
  Wygenerowano OpenAPI i klienta. Podgląd nie tworzy katalogu anotacji.
- Testy: UI 9/9, klient 4/4, backend API/anotacje 30/30. Po wzmocnieniu
  testu teksturowanym obrazem ponownie API 21/21; porównanie dokładnych
  bajtów JPEG croppera i odmienności wobec baseline dla obu topologii.
- ESLint, TypeScript obu pakietów, Ruff, formatowanie, OpenAPI i kontrola
  generowanego klienta zaliczone. Skoncentrowany mypy
  `--follow-imports=silent services/worker/src/game_predictor_worker/vision_lab`
  zaliczony (11 modułów). Domyślny mypy zgłosił 14 wcześniejszych błędów
  zależności `images` (brak importów `game_predictor_api.domain` i pochodny
  `no-any-return`); nie zmieniano ich w T03a.
- Koordynator potwierdził production build i odczyt przez 3102: 15/9 cropów,
  asset 200, rewizja anotacji nadal 0. Końcowy build dokładnego kodu
  po wydzieleniu helpera gestu także zaliczony; nowe procesy API i UI działają.
- Niezależny audyt Astra medium: PASS, brak otwartych P0–P2. Audytor
  uruchomił API 21/21 i końcowe helpery UI 4/4. Wykryte przerywanie gestu
  na numerze uchwytu naprawiono i potwierdzono czterema długimi gestami.
- Przeglądarka: pojedyncza plansza przybliżona po lewej i 15 aktualnych
  symboli po prawej, 3 × 3 z 9 cropami, powrót do pełnego zdjęcia,
  szerokość 390 px bez poziomego przepełnienia. Dowód lokalny:
  `artifacts/vision-lab/t03a-editor.png` (szkic, bez zatwierdzenia).
  Fizyczny Android niesprawdzony; stałość kadru w środku gestu potwierdzono
  kodem/testem, ponieważ narzędzie przeglądarkowe wykonuje drag atomowo.
- Kryteria podzadania zestawiono z implementacją i testami: fit/release,
  poprawne współrzędne źródła, kompaktowy layout, oba rozmiary siatki,
  zgodny cropper, obsługa braku/błędu geometrii i odrzucanie starych odpowiedzi
  zaliczone. Cały task pozostaje w aktywnych ze względu na bramkę danych.
- Audyt przeglądarkowy wykrył przerwanie długiego gestu z numeru uchwytu
  przez domyślny drag tekstu/obrazu. Dodano preventDefault przed capture,
  blokadę natywnego drag SVG i zaznaczania tekstu. Test regresji sprawdza
  kolejność preventDefault/capture; UI 9/9, lint i typecheck po poprawce
  zaliczone. Ponowny build/odbiór prowadzi koordynator i audytor.
- Nie zapisano zatwierdzeń ani pilota, nie uruchomiono T04/T05. Dane T03
  pozostają blokadą etapu B. Commit/hash dopisze koordynator po audycie.

## T03b — uproszczenie zatwierdzania i następna plansza

### Status i cel

`done` — implementacja odebrana testami i audytem kodu; ograniczenie browser QA opisano w Outcome.
Uprościć jawne zapisy operatora i rozpoczęcie kolejnej planszy na tym samym
zdjęciu. Wymaga ukończonego T03a, nie wymaga zakończenia pilota danych.
Relevant docs pozostają jak w T03 oraz sekcja T03b zaakceptowanego planu.

### Recommended execution

`gpt-6-sol` / `medium`; niezależny audyt `gpt-6-astra` / `medium`.
Ryzyko: zapis niewłaściwej pozycji, podwójna nawigacja po retry i niejawne
zatwierdzenie. Nierozwiązane P0–P2 po dwóch cyklach blokują odbiór.

### Scope i kontrakt

- Rozszerzenie zatwierdzone przed kodowaniem: miniatury pokazują osobno liczbę
  obecnych pełnych siatek, lokalizacji i szkiców. Filtry wszystkie / bez zapisów /
  rozpoczęte / z pełną siatką obejmują całą grę, przed paginacją. Pełna siatka
  oznacza przynajmniej jedną zapisaną obecną pełną geometrię, nie komplet zdjęcia
  ani kwalifikację do treningu. Wszystkie metadane pobierane partiami istniejącym API.
- Pozycje 1–9 oraz istniejące dalsze pozycje mają jawne statusy; wybór wczytuje
  dokładny zapis i jego topologię. Brak zapisu pozostaje pusty do jawnej propozycji
  (po automatycznym przejściu propozycja jest przygotowana bez zapisu).
  Przegląd pełnego zdjęcia pokazuje numerowane, klikalne obrysy zapisanych plansz.
- Jeden właściciel stanu anotacji odświeża galerię, geometrię i rodziny po zapisie
  oraz odczycie. Nawigacja, filtry i zmiana topologii porzucają niezapisane
  zmiany bez pytania (korekta T03d); niepotwierdzone żądanie blokuje nawigację do rozstrzygnięcia.
  Baza toastów jest współdzielona w packages/ui, bez importu z Admina.

- Ukryć pole osoby w edytorze geometrii; nowe decyzje mają `actor=operator`.
  Nie przepisywać autorów wcześniejszych rewizji ani panelu rodzin.
- Grupy przycisków wczytania/propozycji i trzech zapisów mają odstępy
  poziome/pionowe także po zawinięciu, z krótkim opisem znaczenia akcji.
- Usunąć checkbox sprawdzenia węzłów. Kliknięcie „Zatwierdź pełną siatkę”
  jest świadomym potwierdzeniem wszystkich granic: tylko ta akcja wysyła
  `reviewed_all_nodes=true`. Szkic, lokalizacja i preview nie zatwierdzają
  pełnej geometrii. Pozostają walidacja backendu oraz wymaganie pełnych węzłów.
- Po potwierdzonym sukcesie `approve_full` lub `approve_location` pozycji
  1–8 otworzyć następną pozycję na tym samym źródle, przywrócić cały kadr,
  unieważnić stary preview i stan gestu. Nie kopiować zatwierdzenia ani
  geometrii poprzedniej planszy jako zapisu nowej. Wczytać istniejący zapis
  następnej pozycji; dla braku zapisu przygotować niezatwierdzoną propozycję.
  Niezgodna topologia zapisu: komunikat, bez nadpisania lub konwersji.
- „Zapisz szkic” pozostaje na pozycji. Po zatwierdzeniu pozycji 9 zatrzymać
  automatyczną nawigację; nie przełączać zdjęcia. Komunikat „Zatwierdzono
  9 plansz” tylko jeśli stan potwierdza pełne zatwierdzenia pozycji 1–9;
  w pozostałych przypadkach podać faktyczną liczbę i brakujące pozycje.
  Dziewięć to koniec tego automatycznego przebiegu, nie limit domenowy.
- Błąd/konflikt/utrata odpowiedzi pozostawia bieżącą planszę i identyczny
  request do retry. Sukces retry przechodzi raz, względem pozycji zapisanej
  w request, nie ruchomego stanu UI; zablokować podwójny submit. Restart
  odczytuje trwałe zapisy i nie powtarza zatwierdzeń automatycznie.

### Expected files i testy

Doprecyzowanie T03b — komunikaty wyłącznie w toastach:

- Wszystkie powiadomienia ekranu laboratorium (galeria, edytor, rodziny,
  backup, preview, zapis, konflikt i błędy odczytu) trafiają do wspólnego
  stosu `position: fixed` w lewym dolnym rogu viewportu. Usunąć ich kopie
  z body; scroll ani przejście między planszami nie ukrywa komunikatu.
- Sukces: zielone tło, błąd: czerwone, ostrzeżenie: pomarańczowe.
  Informacje i postęp: neutralny wariant informacyjny, bez sugerowania sukcesu.
  Treść/ikona i dostępna nazwa opisują typ niezależnie od koloru.
- Czas wszystkich rodzajów: 4 s (korekta użytkownika 2026-09-27);
  odliczanie od pokazania, wstrzymane na hover/focus i w ukrytej karcie.
  Kliknięcie body zamyka; przycisk Kopiuj kopiuje samą wiadomość bez zamknięcia;
  przyciski akcji (np. ponów) nie mogą przypadkowo zamykać komunikatu.
- Kolejka nie nadpisuje niezauważonych błędów sukcesem; powtarzający się
  identyczny komunikat scala się z licznikiem. Nie tworzyć toastu na każdy
  pointermove; aktualizacja jednej operacji zastępuje jej postęp wynikiem.
  Timeout toastu nigdy nie resetuje stanu błędu, blokady ani pending request.
- Toast informuje o niepoprawnym polu i pozwala do niego przejść; pole może
  zachować aria-invalid/oznaczenie, ale nie osobny banner komunikatu w body.
  Etykiety, instrukcje, dane raportu i kontrolki nie są powiadomieniami
  i pozostają w układzie. Niedostępna sekcja zachowuje bezpieczny stan
  oraz kontrolkę retry; szczegółowy komunikat pojawia się w toaście.
- Istniejący wzorzec to lokalny toast w
  `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
  (stan SymbolReviewToast) i module CSS `.toast`; ma timeout 4 s i dwa
  warianty, nie jest gotowym wspólnym komponentem. Wydzielić/reużyć bazę
  bez zależności laboratorium od aplikacji Admin; nie kopiować kilku implementacji.
  Zmiana zachowania pozostałych ekranów dopiero w końcowym T14.
- Dodać regresje kolorów/semantyki, zamykania klik/klawiatura, zegara,
  hover/focus, kolejki/deduplikacji, widoczności po scrollu i zmianie planszy,
  konfliktu/retry po zniknięciu toastu, braku zdublowanych komunikatów w body.

Istniejące: `apps/vision-lab/src/components/geometry-editor.tsx::GeometryEditor`
(save/load), `src/app/style.css`, testy `apps/vision-lab/test/` i kontraktu
anotacji. Proponowany nowy czysty helper przejścia pozycji, jeśli potrzebny.
Bez zmian DB, treningu, portu 3001 i automatycznych decyzji za człowieka.

Kryteria odbioru/testy planowane: stały operator i brak pola/checkboxa;
pełna zgoda wyłącznie przez akcję; odstępy desktop/mobile; sukces 1→2,
szkic 1→1, 9→9; brak nadpisania istniejącej pozycji; mniej niż 9 plansz;
niezgodna topologia; błąd i konflikt bez przejścia; utrata odpowiedzi/retry
bez podwójnej nawigacji; restart zachowuje zapis i autora; regresje 5×3/3×3.
Najpierw testy UI/klienta i istniejące testy anotacji, następnie lint,
typecheck, build i browser. Każda skończona komenda z timeoutem do 120 s.

### Outcome T03b

Korekta zlecona 2026-09-27: wszystkie toasty 4 s zamiast dawnych120/180 s,
przycisk „Kopiuj” zamiast „Zamknij” kopiuje wyłącznie item.message i nie
zamyka powiadomienia. Potwierdzenie dopiero po sukcesie clipboard; odmowa/
brak clipboard pokazuje lokalny status bez alertu i dodatkowych toastów.
Pauzy hover/focus/ukryta karta, kolejka/deduplikacja, akcje i kliknięcie body
zamykające pozostają. Timeout nie zmienia pending/retry. Pliki: wspólne
toasts.tsx/toast-store.ts, regresje lab i dokumentacja. Kontrakt zastępuje
wcześniejsze czasy także w planowanym T14, bez uruchamiania T14. Testy:
fakeclock4s/pauzy/kolejka, clipboard success/fail, retry po timeout; następnie
lint/typecheck do120s. Wykonawca Sol medium/audyt Astra medium według T03b.

Wynik korekty: wspólna baza toastów ma4000ms dla każdego rodzaju i przycisk
Kopiuj z lokalnym statusem. Testy UI **29/29 PASS** (1,34 s), format,
ESLint (lab i oba pliki wspólne), typecheck oraz diffcheck PASS. Testy
potwierdzają dokładny timeout/pauzy/kolejkę, oryginalną treść clipboard,
brak sukcesu przed odpowiedzią, odmowę i brak clipboard, izolację kliknięcia
oraz skuteczne identyczne retry po wygaśnięciu toastu. Dane i usługi nietknięte.
Audyt Astra medium PASS bez P0–P2, niezależne testy20/20 (1,89s).
Build/restart wyłącznie UI PASS, HTTP200. Browser: Kopiuj pokazuje Skopiowano
po sukcesie, schowek zawiera dokładną treść, focus zachowuje toast,
po opuszczeniu przycisku toast znika. Odbiór
na osobnej karcie, bez anotowania danych; API bez restartu. DoD korekty
potwierdzone testami; fizyczny Android i restart komputera niebadane.
Commit `v1.7.11` / `9626f3b3172172b76038f7f53a8314b5eddc2595`.
Hash dopisany po commicie; kolejny patch v1.7.12 po kontroli historii.
T14 nie uruchomiono, nadrzędny T03 blocked.

- Wdrożono stałego operatora, pełną zgodę przez kliknięcie, odstępy i opisy,
  auto-przejście po potwierdzonym zapisie z idempotentnym retry, dokładne
  wczytanie istniejącej geometrii/topologii, statusy pozycji i klikalny przegląd.
- Galeria filtruje pełny katalog przed paginacją i rozdziela pełne siatki,
  lokalizacje i szkice. Wspólny stan anotacji aktualizuje wszystkich odbiorców;
  starsze odpowiedzi nie cofają rewizji. Zmiana tej samej planszy w innym
  odczycie wymaga jej ponownego sprawdzenia przed zapisem lokalnej edycji.
- Powiadomienia korzystają ze współdzielonej bazy packages/ui: kolejka,
  deduplikacja, obecnie czas4 s, pauza hover/focus/hidden, kopiowanie i akcje.
  Raport pomiarów pozostaje danymi. Timeout toastu nie resetuje pending request.
- Testy UI: helpery oraz rzeczywiste komponenty React z izolowanym transportem;
  double submit, utrata odpowiedzi po persist/retry, szkic i pozycja 9,
  dokładne zapisane cropy 3×3/5×3, dirty guard, odczyt po konflikcie,
  wspólna i monotoniczna rewizja, filtr obejmujący dalszą stronę katalogu,
  hover/focus/hidden, osobne akcje i zamknięcie toastu.
- Backend anotacji 9/9 i klient 4/4 potwierdzone przez koordynatora.
  Końcowe UI 22/22, lint aplikacji i wspólnej bazy, format, TypeScript
  i production build PASS, również po poprawce topologii.
- Audyt Astra medium: brak otwartych P0–P2; niezależne 13/13 testów
  workflow (8 React + 5 helperów). Naprawiono wyścig odczytu po konflikcie,
  deduplikację postępu toastów i rozjazd selektora zapisanej topologii.
- Nowy proces UI na 3102, HTTP 200 i katalog dostępny. Odczyt anotacji
  po restarcie UI identyczny: rewizja 20, cztery pełne geometrie na dwóch
  źródłach (3 i 1), historyczni autorzy zachowani. SHA-256 odpowiedzi:
  `4D665227F4AF308BBAA1F51A9252514F7DB669AB5A77821C1DC56D086E805AB3`.
- Końcowy browser QA i screenshot nie zostały wykonane: connector nie
  udostępnia żadnej przeglądarki, także po próbie open_in_codex. Nie użyto
  wcześniejszego zrzutu T03a jako dowodu nowego UI. Zachowania sprawdzają
  testy React; odbiór wizualny w rzeczywistej przeglądarce pozostaje ryzykiem.
- Zakres porównano z kryteriami T03b: wszystkie funkcje wdrożone, testy
  scenariuszy zapisu/retry/statusów/topologii/toastów zaliczone. Brak wyłącznie
  końcowego odbioru przeglądarkowego. Commit `v1.7.5` —
  `07f8e02f5270710e498315c30a48968fadc40441`. Hash dopisany po commicie,
  lokalnie do kolejnego commita; następny patch v1.7.6 po kontroli historii.
- Nie zmieniono API, DB ani danych użytkownika; testy nie zapisują rzeczywistych
  decyzji. T03 pozostaje blocked na pilocie, T04/T05/T14 nie uruchomiono.
  Fizyczny Android i restart komputera pozostają niesprawdzone.

## T03c — aktualizacja snapshotu z zachowaniem anotacji

Status `done`; użytkownik jawnie zlecił aktualizację zdjęć z folderu
`new_traning_set`, nie tylko odtworzenie starego katalogu. Wykonawca
`gpt-6-sol` / `medium`, audyt `gpt-6-astra` / `medium`.

Scope: istniejący importer tworzy nowy niezmienny snapshot. Nowy CLI
`vision_lab/rebase_annotations.py` domyślnie wykonuje tylko preflight;
`--apply` publikuje atomowo stan w nowym katalogu. Porównuje wszystkie
referencje bieżących anotacji, timingów i historii: identyczne id, SHA oraz
pełne metadane Catalog. Brak, zmiana albo rodziny/split (także w historii)
blokują przeniesienie. Zachowuje cały payload, receipts, historię, autorów,
rewizje i geometrię; zmienia wyłącznie state.snapshot_id. Osobny raport wiąże
digest wejścia/wyjścia oraz starego/nowego katalogu. Retry rozpoznaje dokładnie
ten sam wynik; nigdy nie nadpisuje istniejącego lub nowszego stanu celu.

Expected files: nowy moduł rebase_annotations.py, nowy
tests/test_vision_lab_rebase.py, guide VISION_LAB_LOCAL, wymagania i architektura
VISION_LAB oraz plan. API i schematy bez zmian. Root prowadzi CURRENT_STATE,
rzeczywisty import, zatrzymanie API na czas rebase, restart i commit.

Testy/DoD: zachowana pełna geometria i wszystkie metadane w nowym procesie;
zmienione anotowane zdjęcie blokuje, także referencja tylko historyczna;
rodziny/split blokują, istniejący cel/nowszy stan nie jest nadpisywany,
idempotentny retry i dry-run nie publikują zmian. Pytest, Ruff i mypy z
limitami 120 s, audyt przed operacją. Stary snapshot i anotacje pozostają.
777 zachowuje obecną rolę, bez treningu ani zmiany kwalifikacji w tym tasku.

### Outcome T03c

- Gotowy osobny CLI preflight/apply, bez zmian API. Referencje historii,
  timingów i anotacji zachowują komplet metadanych; nieznane formaty,
  rodziny/split i zmiany użytych źródeł blokują operację. Payload zachowany
  poza state.snapshot_id; osobny raport ma digests wejścia i wyjścia.
- Testy rebase 9/9 oraz istniejących anotacji 9/9: 18/18 PASS (16,68 s).
  Obejmują nowy proces, retry po utracie wyniku, nowszy cel, zapis źródłowy
  po preflight, konflikt późniejszego retry, historię, metadane i overlap.
  Ruff check i format PASS, mypy --follow-imports=silent PASS (1 moduł).
  Niezależny audytor potwierdził 9/9 (4,98 s), końcowy audyt PASS bez P0–P2.
  Koordynator wykonał preflight i apply przy zatrzymanym API.
- Guide wskazuje nowy snapshot/katalog anotacji
  `82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9`,
  procedurę preflight/apply/restart oraz zachowanie starego snapshotu.
- Wykonawca nie modyfikował danych użytkownika ani usług. Koordynator
  zaimportował 993 źródła i przeniósł aktualny stan: rewizja 46, 30 anotacji,
  46 zdarzeń historii. Cały payload zachowano poza state.snapshot_id;
  wejście `5ff8beaa258cc6f462fa1da3ae367fa542bde2a1502c8240ed25ac94f476860d`,
  wyjście `b480bcd288646b5a849c58a89e7531c72768610cf09c134ea6541f3384d468b7`.
  Stary katalog anotacji i snapshot pozostają nietknięte.
- Nowy proces API potwierdził przez proxy 3102 kompletny katalog zgodny
  z nowym snapshotem. SHA wszystkich 993 plików zgodne z new_traning_set;
  po jednym podglądzie każdej gry zgodnym bajtowo z encode aktualnego obrazu.
  Sprawdzone Blazing 1520×954, Gang 1520×1304, Mumie 1520×1054,
  Reels 1520×1004, Treasure 1520×1154; 777 pozostało bez zmian.
- DoD T03c: preflight/apply, zachowanie danych, retry/konflikty i atomowość
  sprawdzone testami; rzeczywisty katalog/anotacje i odczyt nowego procesu
  sprawdzone operacyjnie. Nie wykonywano browser QA, restartu komputera ani
  nowego UI builda (UI nie zmieniono). Commit T03c `v1.7.7` —
  `dd4aae3268439299da1a208f49361673c298cec4`. Hash dopisany po commicie;
  następny patch v1.7.8 po kontroli historii.
  Liczba zatwierdzeń jest odczytem operacyjnym, nie stałą fixture.
  Bez zmiany roli 777, splitu, treningu, push lub merge.

## T03d — przegląd zdjęcia i poprawki wybranych plansz

Status `done`; wykonawca `gpt-6-sol` / `medium`, niezależny audyt
`gpt-6-astra` / `medium`. Zlecony przez użytkownika pełny pion UI/API, zależy
od gotowych T03b/c. Relevant docs: niniejszy task, plan T03d, VISION_LAB
wymagania/architektura, D-450, Definition of Done.

Cel: pełne zdjęcie z numerowanymi zapisanymi siatkami, wyborem/cropami,
oznaczeniem wybranych pozycji do poprawy (opcjonalna uwaga), wycofaniem
błędnego oznaczenia i jawnym przyjęciem bieżącego zestawu geometrii zdjęcia.
Filtry: Do przeglądu (niezaakceptowane bez needs_correction), Do poprawy,
Zaakceptowane; osobny licznik pozycji wymagających poprawy/przeglądu.

Kontrakt: istniejący POST /annotations przyjmuje dodatkowo PhotoReviewRequest
z mark/withdraw/accept, source SHA i expected_board_revisions całego
zdjęcia. AnnotationState rozszerzony kompatybilnie o photo_reviews (domyślnie
pusty). Istniejące request_id/CAS/history/backup chronią wszystkie decyzje.
Accept wymaga co najmniej jednej full/present i braku needs_correction;
wiąże wszystkie bieżące rewizje, bez promowania draft/location. Mark czyści
akceptację. Zapis oznaczonej pozycji → needs_review, pozostaje na tej pozycji.
Accept domyka needs_review tylko gdy każda taka pozycja jest full/present;
szkic/lokalizacja blokuje akceptację poprawki. Nie wymaga osobnego resolve.
Withdraw wycofuje błędne zgłoszenie niezależnie od poprawki, bez akceptacji.

Split wymaga dotychczasowych warunków i aktualnej akceptacji zdjęcia. Edycja
lub otwarcie uwagi oznacza istniejący split stale bez zmiany jego przydziałów.
Rebase zachowuje nowe review/history z kontrolą wszystkich referencji; stare
dane domyślnie nieprzejrzane. UI blokuje review przy dirty geometrii i wszystkie
nawigacje przy pending; retry zachowuje identyczny request, konflikt wymaga
odczytu i ponownego sprawdzenia. Komunikaty wyłącznie toastami.

Pliki: annotation_contracts.py, annotations.py, api.py, splits.py,
rebase_annotations.py; nowy photo_review.py; OpenAPI/generowany klient/wrapper;
GeometryEditor, nowy PhotoReviewPanel, status/gallery; testy backend/request/UI;
dokumenty właścicielskie i guide. CURRENT_STATE/build/restart/commit: koordynator.

DoD/testy: stary payload bez zmian po odczycie; mark→edit→needs_review→
accept; wycofanie; niepusty full/present bez wymagania9; każda zmiana/dodanie
pozycji unieważnia, inne zdjęcie nie; stale versions/CAS, utrata odpowiedzi,
nowy proces i backup, rebase zachowuje review. API/OpenAPI/client spójne;
UI filtry/liczniki/dirty/pending/wybór/cropy i brak auto-next po naprawie.
Kolejność: testy skoncentrowane → lint/typecheck → OpenAPI/check → audit/build.
Skończone procesy limit120s. Bez zapisu realnych danych, roli777 i treningu.

### Outcome T03d

### Rozszerzenie T03d — szybki przegląd (done, 2026-09-27)

Cel: jedna sekcja pełnego zdjęcia ze wszystkimi zapisanymi siatkami, liniami
wewnętrznymi i numerami; dwa główne przyciski Zatwierdź/Odrzuć, po sukcesie
natychmiast następne. Wejście przy górze, tryb ukrywa galerię/rodziny/edytor;
zdjęcie contain ograniczone viewportem. Powrót, retry/odświeżenie przy błędzie
są technicznymi kontrolkami. Stabilna kolejka katalogu wybranej gry lub wszystkich:
źródła z full/present i statusem review, nie accepted/rejected/needs_correction.

Additive API: PhotoReviewRequest.action += reject, PhotoReview.rejected=false.
Reject sprawdza SHA/mapę/CAS i idempotencję, czyści accept, ustawia rejected,
nie zmienia geometrii ani nie tworzy issues. Mark/withdraw/edycja zachowują
rejected; dopiero jawny accept po zwykłych warunkach go usuwa. Status rejected
to Do poprawy, wykluczony ze splitu i kolejki. Stare payloady zgodne; zachowanie
historii/backup/rebase bez zmian. Backend API rozszerzenie zapowiedziane.

QuickReview wysyła dokładnie wyświetloną mapę i rewizję; zdjęcie musi zakończyć
load bez error. Ref-lock chroni doubleclick, pending blokuje wyjście i zachowuje
identyczne retry niezależnie od toastu. Stara odpowiedź nie przesuwa kursora ani
nie obniża wspólnej rewizji. Sukces przesuwa raz, restart kolejki pomija decyzje.
Konflikt wymaga jawnego odczytu/przejrzenia nowych wersji. Brak autoapprove.

Pliki: annotation_contracts.py/photo_review.py i testy lab; izolowane OpenAPI,
generated client/wrapper/request test; nowy QuickReview/helper, Page/style/status,
UI regresje i guide/req/arch/plan. Bez dotykania obcego toru partial boards,
DECISION_LOG/CURRENT_STATE, live danych i usług. Koordynator zapisuje decyzję,
build/restart/commit. Wykonawca gpt-6-sol medium/audyt gpt-6-astra medium T03d.
Testy: reject/accept/oldpayload/retry/restart/backup/rebase/split, kolejka,
load/error/stale/doubleclick/lostresponse/monotonic i istniejące workflow;
najpierw fokus, lint/typecheck, kontraktcheck, audyt. Komendy do120s.

Wynik implementacji szybkiego przeglądu (freeze): nowy QuickReview i helper
kolejki, viewportowy obraz ze wszystkimi zapisanymi siatkami/numerami oraz
wyłącznie dwa główne przyciski decyzji. Loadguard obejmuje widoczne SVG image;
drugie zdarzenie doubleclick jest ignorowane także po szybkim sukcesie/cache.
Odrzucenie trwałe bez zmiany geometrii/issues, odwracalne jawnym accept w
zwykłym panelu. Additive kontrakt laboratoryjny wygenerowano; dotychczasowy
typowany wrapper writePhotoReview obsługuje rozszerzoną unię bez duplikacji.

Kontrole: UI **34/34 PASS** (1,28 s; node --experimental-strip-types --test
apps/vision-lab/test/*.test.mjs); backend photo_review+rebase **20/20 PASS**
(17,86 s; pytest dwa odpowiadające pliki); client request **4/4 PASS** (tsx).
ESLint lab, format, app/client typecheck, Ruff, mypy13 modułów lab
--follow-imports=silent, izolowane OpenAPI --check, generated-client --check
i diffcheck PASS. Testy obejmują kolejność/gry/filtry, wszystkie obrysy,
image error/load, doubleclick, pending po4s, exactretry, niższą rewizję
odpowiedzi/GET, zmienioną geometrię receipt oraz restart/backup/rebase.
DoD względem powyższego zakresu potwierdzone: pełne zdjęcie/wszystkie siatki
i numery, dwie decyzje i następne po sukcesie, odrzucenie bez kasowania,
bezpieczne błędy/retry i trwałość po odczycie/restartach w izolowanych testach.
Niezależny audyt Astra medium PASS bez P0–P2, UI25/25 i backend11/11 PASS.
Produkcyjny build i nowe procesy API/UI PASS, HTTP200 na3102. Pierwszy krótki
readiness timeout podczas startu; po kontroli logów kolejny GET200 bez
duplikowania usług. Kopia bezpieczeństwa state.json wykonana przed restartem;
SHA256 przed/po identyczny3519739500F642069E99D2BEAFBB334FF7F5118E2F4426CF38E83D35F0692AD3.
Browser QA na osobnej karcie: kolejka63, wszystkie3 zapisane siatki pierwszego
zdjęcia, oba przyciski aktywne po załadowaniu; pełny widok1280×720 bez scrolla,
Powrót do edycji działa. Dowód artifacts/vision-lab/quick-review-qa.png.
Nie podejmowano decyzji na danych użytkownika. Restart OS/fizyczny mobile,
trening, kwalifikacja777 i obcy tor partial boards poza zakresem.
Commit `v1.7.13` / `8c7f63350b3b5ee15c96d2e84e88b034abdf3f82`.
Hash dopisany po commicie; następny patch v1.7.14 po kontroli historii.
Nadrzędny T03 nadal blocked, plik pozostaje aktywny do zakończenia
pozostałych bramek danych i splitu.

Korekta bez modalnych potwierdzeń, zlecona 2026-09-27: usunąć window.confirm
z nawigacji i jawnego reconcile oraz beforeunload. Nawigacja porzuca lokalne
niezapisane zmiany bez autosave/autoapproval; busy/pending nadal blokuje
nawigację w aplikacji, a CAS i retry bez zmian. Ten kontrakt zastępuje
wcześniejszy wymóg pytania o odrzucenie lokalnej edycji. Pliki: Page,
GeometryEditor, PhotoReviewPanel i test interakcji; dokumenty wymagań,
architektury, plan i guide. Testy UI/lint/typecheck limit120s. Brak pytań
blokujących i zmian API/danych; wykonanie/audyt według istniejącego T03d.

Wynik korekty bez dialogów: wszystkie wywołania confirm i rejestracja
beforeunload usunięte z lab UI. Testy **28/28 PASS** (0,89 s), format,
ESLint, typecheck i diffcheck PASS. Mock confirm rzuca przy każdym wywołaniu,
mock rejestracji zdarzeń odrzuca beforeunload. Regresje potwierdzają dirty
nawigację bez zapisów, jawne odczyty geometrii/review bez pytania oraz
zachowane blokady pending/busy i identyczne retry. API/backend bez zmian.
Audyt Astra medium PASS bez P0–P2; niezależne testy interakcji 13/13 PASS
(0,93 s). Produkcyjny build i nowy proces UI PASS, HTTP200 na3102.
Przeglądarka: niezapisana propozycja → pozycja2 bez dialogu; ponowna
niezapisana propozycja → reload bez dialogu. Testowano osobną kartę,
bez zapisów/akceptacji; API i dane pozostają nietknięte. DoD korekty
spełnione w tym zakresie; fizyczny Android i restart komputera niebadane.
Commit korekty `v1.7.10` / `729970227d1968ff34f752e65c57e1128c040b03`.
Hash dopisany po commicie; kolejny patch v1.7.11 po kontroli historii.
Nadrzędny T03 nadal blocked.

Korekta ergonomii zlecona 2026-09-27 po odbiorze: przegląd zapisanych plansz
na całym zdjęciu ma być domyślnie zwinięty przy wejściu na ekran, żeby
ograniczyć przewijanie. Zakres: usunięcie `open` z istniejącego `details`
w GeometryEditor i aktualizacja asercji interakcji; natywne ręczne rozwijanie
pozostaje bez nowego stanu/mechanizmu. Bez zmian API, danych i workflow.
Weryfikacja: testy interakcji UI **12/12 PASS** (0,83 s), ESLint i
typecheck PASS (limit120s). Usunięto wyłącznie `open`, istniejąca asercja
sprawdza brak wymuszonego otwarcia. Bez nowego mechanizmu wymagającego
osobnego testu remount; natywna kontrolka zachowuje ręczne rozwijanie.
Audyt korekty Astra medium PASS bez P0–P2; niezależne 12/12 testów (0,93 s).
Build i restart wyłącznie UI PASS, HTTP 200 na 3102. Przeglądarka potwierdza
open=false po wejściu i ręczne false→true→false przez nagłówek. API i dane
pozostały nietknięte; fizycznego Androida nie badano. Commit korekty `v1.7.9`
/ `f5680ba60b093c852389b234b34102e878ed564e`. Hash dopisany po commicie;
następny patch v1.7.10 po kontroli historii. CURRENT_STATE prowadzi koordynator.

Implementacja zamrożona do audytu 2026-09-27. Dodano trwały przegląd zdjęcia
w istniejącym kontrakcie `/annotations`, mapę wersji zapisanych pozycji i SHA
źródła, CAS oraz idempotentne ponowienie. `mark` nie zmienia geometrii,
poprawka przechodzi do `needs_review`, a osobne `accept` zamyka sprawdzone
poprawki i wiąże bieżący zestaw. `needs_correction` oraz korekta będąca tylko
szkicem/lokalizacją blokują akceptację. `withdraw` nie zatwierdza zdjęcia.
Zmiana geometrii unieważnia tylko akceptację tego zdjęcia. Stare rekordy
pozostają nieprzejrzane, z zachowaniem zatwierdzeń i historii. Stan przeglądu
jest objęty backupem, restartem i bezpiecznym rebase T03c.

UI ma rozwijany (po korekcie domyślnie zwinięty) widok całego zdjęcia z zapisanymi siatkami, numerami,
wyborem/cropami i tekstowymi oznaczeniami statusu; panel decyzji, filtry oraz
liczniki działają dla całej gry. Dirty/pending guards chronią edycję i retry.
Poprawiana oznaczona pozycja pozostaje wybrana; nieoznaczone pozycje zachowują
poprzedni auto-next także po wcześniejszym review i utracie odpowiedzi.
Akceptacja jest dodatkową bramką splitu; efektywny `split_stale` dawnych
splitów jest spójny dla GET, retry i nowych mutacji, bez zapisu przy odczycie.

Kontrole: backend annotations/review/rebase **25/25 PASS** (22,96 s), po
dodaniu regresji legacy splitu review **8/8 PASS** (9,27 s), czyli wszystkie
26 przypadków zakresu zaliczone. UI **27/27 PASS**, request client **4/4 PASS**;
Ruff, app ESLint, app/client typecheck, mypy zmienionych 13 modułów lab
(`--follow-imports=silent`), OpenAPI check, generated-client check oraz
`git diff --check` PASS. Pełne mypy z importami poza zakresem ujawniło
zastane błędy typów NumPy w `images/shape_geometry_v2/core.py` i
`images/contrast_frame_grid_v12.py` oraz zastane błędy w dwóch modułach API
`v7_label_geometry_calibration`, `images/qualified_manual_geometry.py`
i `images/page_geometry_preflight.py` (łącznie 27 błędów w 6 plikach);
nie zmieniano tych modułów. Ostrzeżenia
testów: istniejące Starlette/AnyIO, react-test-renderer i module type.

DoD i plan porównano punktowo: kontrakt, zachowanie statusów, izolowane
race/retry, restart/backup/rebase, wybór/cropy, filtry i ochrona edycji mają
implementację oraz regresje. Dokumenty wymagań, architektury, D-450 i guide
są zaktualizowane. Audyt Astra medium **PASS, bez P0–P2**, niezależne
review **8/8 PASS** (9,98 s). Koordynator dodatkowo potwierdził istniejące
API **21/21 PASS** (2,11 s), review **8/8 PASS** (13,10 s) i UI **27/27 PASS**.
Produkcyjny build i restart laboratorium PASS. Nowy proces API i proxy 3102
odczytują rewizję 93, 77 pełnych siatek na 27 zdjęciach. Kopia stanu
`artifacts/vision-lab/t03d-before-restart-revision-93.json` i plik po restarcie
mają identyczny SHA-256
`B5B13E5723F3FE5345E0BA730FD9BA967EB6894761E3A2D1D99142969A0AC45A`.
Odbiór przeglądarkowy read-only: filtry, pusty widok Do poprawy, numerowane
siatki, wybór pozycji 2/3 klawiaturą i 15 cropów. Oględziny w wąskim panelu
bez poziomego przepełnienia; fizyczny Android i restart komputera niebadane.
Commit T03d: `v1.7.8` / `067a0350d1f5569ffdafa4aa2cf60ae65168e2c9`.
Hash dopisany po commicie; następny patch v1.7.9 po kontroli historii.
Nadrzędny T03 pozostaje blocked.
Nie wykonano
zapisu na rzeczywistych danych, akceptacji zdjęć użytkownika, treningu ani
zmiany roli `777`; CURRENT_STATE i usługi należą do koordynatora.

## Outcome T03 (narzędzia i operacje)

### Mapa źródeł i częściowe utrwalenie rodzin (2026-09-27)

- Sol medium zmapował wszystkie 1466 źródeł oraz 365 JSON. Raport:
  `ai_docs/quality/VISION_LAB_SOURCE_MAPPING_20260927.md`. Dowody SHA,
  deklaracje katalogów i niepotwierdzona niezależność pozostają rozdzielone.
- Astra medium zatwierdził dokładne siedem requestów bez P0–P2. Po backupie
  utrwalono 436 źródeł w siedmiu rodzinach unresolved przez istniejący CAS:
  rewizja 260–267, dokładnie siedem eventów i receipts. Pozostały payload
  identyczny z backupem; zachowane 180 anotacji, 63 akceptacje, 11 kwalifikacji
  i 196 timingów. Nowy proces replay i kolejny odczyt PASS, bez zmiany SHA.
  Końcowy niezależny audyt Astra medium PASS bez P0–P2: odtworzony cały
  payload z backupu i siedmiu requestów, SHA obu store oraz kopii potwierdzone.
  Mapę i requesty skopiowano create-only do
  `game_predictor_vision_data/reports/t03-source-mapping-20260927`.
- Dry-run po T03j, na kopii rzeczywistej rewizji 267 i tej samej kohorcie 63,
  z polityką `lab-geometry-cohort-777-targets-v2`: nadal
  `VERIFIED_MEASUREMENT_SOURCES_REQUIRED`. Wszystkie 63 targetowe zdjęcia
  mają nierozstrzygnięte/brakujące pochodzenie komponentu, zero eligible.
  Oba warianty measurement sprawdzone bez mutacji; SHA przed i po:
  `f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae`.
- DoD tego kroku: pełne pokrycie mapą, brak nowych akceptacji, backup,
  idempotencja i kontrola restartu spełnione. Nie zamrożono splitu i nie
  uruchomiono T04/T05 ani treningu. T03 pozostaje blocked. Osobna propozycja
  pilotażu całymi grami 5×3 bez pomiaru czasu oczekuje decyzji operatora;
  nie zastępuje przyjętego protokołu samodzielnie. Operacyjny zapis postępu
  T03 ma osobny commit `v1.7.27` / `381ec8893895cc40ff76c456ff78c67496bbd30c`.
  Staged check/stat/list i show/stat/status PASS; obce zmiany zachowane.

### Deklaracja obu katalogów Treasure (2026-09-27)

- Zapisano pochodzenie obu nowych zakresów i jawną korektę literówki
  `439***` na `429***`. Odczyt katalogów i 100 nazw PASS; brak zmian danych.
- Uzupełniono Technical notes i CURRENT_STATE. Nie zmieniono planu, kodu,
  rodzin, splitu ani zgód; nie uruchomiono treningu. Testy aplikacji nie
  dotyczą zapisu deklaracji. To uzupełnienie trwającego T03, nie zamknięcie
  taska ani nowa kwalifikacja. Kolejny krok: powiązania i kontrola konfliktów.

### Doprecyzowanie pochodzenia Treasure (2026-09-27)

- Zapisano odpowiedź operatora i ostrożne wspólne grupowanie nowego zakresu
  23590–23913 z dawnym tresure23600. Nie uznano prawdopodobieństwa za dowód
  niezależnej weryfikacji ani za zgodę na przenoszenie siatek między cropami.
- Aktualizacja dotyczy wyłącznie Technical notes i CURRENT_STATE. Nie
  zmieniono danych laboratorium, rodzin, podziału, kodu ani kwalifikacji;
  trening nie został uruchomiony. Testy aplikacji nie są potrzebne dla
  samego zapisu deklaracji. Kontrola diff bez błędów whitespace; zapis jest
  uzupełnieniem trwającego T03, bez osobnego zamknięcia taska lub commita.
  T03 pozostaje aktywny/blocked na innych bramkach.

### Korekta polityki geometrii i deklaracja pochodzenia (2026-09-27)

- D-453 rozstrzyga użycie historycznych zdjęć 777 w uczeniu geometrii
  z nowych ręcznych siatek labu. Zaktualizowano wymagania, architekturę,
  plan i bieżący zakres T03; root prowadzi DECISION_LOG/CURRENT_STATE.
- Zapisano deklarację operatora o innych zakresach/folderach i odległych
  brzegach nagrań pięciu gier. Do wykonania pozostaje mapowanie rodzin
  i kontrola konfliktów, bez uznawania odległości/nazw za niezależność.
- Odczyt nowego folderu w poprzednim kroku: 473 JPG (777: 32, blazing: 27,
  gang: 35, mumie: 225, reels: 54, treasure: 100), wszystkie odczytywalne,
  bez identycznych SHA wewnątrz folderu. Nie porównano ich ze starym
  snapshotem: odczyt był niedostępny, a API 8102 odrzucało połączenie.
  Wynik nie dowodzi braku konfliktów między zbiorami ani niezależności rodzin.
- To zmiana dokumentacji, bez kodu, API, operacji na danych, zmiany ról,
  przenoszenia akceptacji, restartu usług lub treningu. Testów aplikacji
  nie uruchamiano. Do wdrożenia kwalifikacji potrzebna jest osobna analiza
  techniczna; T03 nadal `blocked`, T04/T05 nie rozpoczęto.
- Kontrola diff bez błędów whitespace; końcowa sekcja modeli i wszystkie
  przypisania planu zachowane. Zastany zapis hasha commita v1.7.18 zachowano.
- Niezależny audyt Astra medium PASS, bez P0–P2. Potwierdzono odczytem
  istniejącą bramkę runtime i zgodność sześciu dokumentów z D-453.
  Kryteria dokumentacyjnej korekty spełnione; pełne DoD T03 nadal wymaga
  kwalifikacji, rodzin i podziału. Commit korekty `v1.7.20` /
  `69c4594cea8bead9d941fce23236096a1c17f26c`. Hash dopisany po commicie;
  show/stat/status sprawdzone, obce hunki pozostawiono poza commitem.
- Historyczne wyniki poniżej opisują stan sprzed D-453. Ówczesna rola
  `comparison_only` nie jest aktualną decyzją o wykluczeniu geometrii 777.
  Bieżące otwarte bramki określają Status i Technical notes tego taska.

### Wznowienie — odczytowy preflight danych (2026-09-27)

- Zapisano rozdzielenie zgody na geometrię od zatwierdzenia symboli w planie,
  wymaganiach i D-450. Etap C pozostaje poza zakresem wznowienia B.
- Preflight Sol medium: rewizja 259, 63 aktualne akceptacje, 180 pełnych
  obecnych siatek 5 × 3, 4320 węzłów / 2700 komórek. Kontrole SHA, map
  rewizji, struktury i granic źródeł bez błędów. Nie jest to dodatkowa
  wizualna weryfikacja jakości ani potwierdzenie poprawności symboli.
- Stan dyskowy i oba API (8102/3102) zgodne; SHA state.json przed/po:
  `22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586`.
  Zero zmian anotacji, rodzin, roli źródeł, splitu lub usług.
- Blokada pozostaje: rodziny 0, brak podziału i dowodów niezależności.
  20 grup dokładnych duplikatów Reels, z czego 5 zawiera zaakceptowane
  zdjęcie i nieanotowany alias. Brak identycznych plików w samych 63
  wybranych zdjęciach nie dowodzi niezależności nagrań. Brak anotacji 3 × 3;
  nie można raportować wyuczonej jakości tej topologii.
- Raport: `ai_docs/quality/VISION_LAB_STAGE_B_DATA_PREFLIGHT.md`.
  Testy aplikacji/build nieuruchamiane: kod i kontrakty niezmienione.
  Audyt Astra medium potwierdził niezależnie liczności, akceptacje i SHA;
  poprawiono nadmierny wniosek o liczbie grup w alternatywie measurement.
  Kontrola diff bez błędów; bez zmian kodu produkcyjnego i bez jego nowych
  testów. Audyt końcowy bez P0–P2. Commit preflight: `v1.7.18` /
  `b3f6ead9dc9f2a11002dbf5ee322d7bcbc9562f9`. Hash dopisany po commicie;
  następny patch v1.7.19 po potwierdzeniu historii. T03 pozostaje
  aktywny/blocked; T04/T05 nie zostały uruchomione.

### Operacyjne przywrócenie ścieżki danych

Na jawne polecenie użytkownika przeniesiono odnaleziony snapshot oraz
`state.json` z `Documents/Nowy folder` do udokumentowanego
`Documents/game_predictor_vision_data`, bez nadpisania istniejących danych.
Przed przeniesieniem zatrzymano zweryfikowany proces API; kopię zapisów
zachowano w `recovery-backups/777-state-revision45/state.json`.
SHA-256 kopii i przeniesionego pliku jest identyczny:
`F0BF79E1BDB96F09140AED26C0F7BAFCA063D96A4C5C14BCD78F79E57DB9E490`.
Nowy proces API weryfikuje snapshot i odczytuje rewizję 45: 29 pełnych
siatek na 10 zdjęciach 777. Proxy 3102 potwierdza ten sam stan oraz HTTP 200
dla zdjęcia. Nie ustalono przyczyny wcześniejszej zmiany lokalizacji.
Nie zmieniono kodu ani geometrii, nie wykonano treningu ani browser QA.
Aktualizacja przyciętych zdjęć pozostałych gier nie jest częścią przeniesienia:
aktywny pozostaje odzyskany snapshot 1180 źródeł. Commit `v1.7.6` —
`95e0915f6175e3dc38509212460bbcc3b61b168d`. Hash dopisany po commicie;
kolejny patch v1.7.7 po kontroli historii.

Część narzędziowa odebrana 2026-09-26. Cały T03 i etap B nie są ukończone.

Commit części narzędziowej: `v1.7.2` —
`cea04bcf243e13a42b87669ced0d04ec8f6aa055`. Hash dopisany po commicie;
ten wpis pozostaje lokalnym uzupełnieniem do następnego commita.

### Changed

- Edytor narożników i 24/16 węzłów, osobne zatwierdzenia lokalizacji oraz
  pełnej siatki, pomiar aktywności i korekt. Wyniki AI pozostają propozycją.
- Atomowy magazyn rewizji z kontrolą konfliktu, idempotentnym retry,
  historią wynikowych decyzji i backup/restore do nowego katalogu.
- Grupowanie rodzin, pochodnych i duplikatów SHA; niezweryfikowane grupy
  wykluczone. Edycja oznacza podział jako `split_stale`, zachowuje jego
  przydziały i nie pozwala ponownie losować holdoutów.
- API, OpenAPI, wygenerowany klient, wrapper i testy żądań są spójne.

### Verification results

- Backend: 9 testów anotacji i 19 istniejącego laboratorium; UI 5/5,
  klient 3/3. Ruff/format, ESLint, TypeScript, mypy 11 modułów i kontrole
  OpenAPI/generowanego klienta zaliczone.
- Production build oraz restart obu usług zaliczone. Odbiór przeglądarkowy:
  24/16 węzłów, przesunięcie uchwytu, brak automatycznego approval,
  zachowanie wyboru rodziny między stronami. Nie zapisano decyzji na danych
  użytkownika; po restarcie rewizja 0, brak anotacji, rodzin i podziału.
- Niezależny audyt Astra medium: PASS kodu, bez otwartych P0–P2.
  Audytor niezależnie uruchomił wcześniejsze 7 testów anotacji; końcowe
  rozszerzone zestawy pochodzą od wykonawcy Sol medium.

### Not completed

- Aktualizacja po pilocie: zatwierdzenia geometrii i zdjęć zostały wykonane.
  Nadal wymagane potwierdzenie pochodzenia rodzin, ocena pomiaru pierwszych
  10 zdjęć/grę i prognozy pracy oraz zamrożenie
  splitu. Kryterium braku przecieku jest przetestowane mechanicznie, ale
  nieudowodnione dla rzeczywistych danych.
- 777 V2 pozostaje fail-closed: nie dostarczono dowodu pochodzenia i
  podobieństwa dopuszczającego dane. Historyczne 777 tylko porównawcze.
- Nie uruchomiono T04/T05, instalacji treningowych, treningu, aktywacji,
  pełnej kontroli repozytorium ani testu fizycznego Androida. Brak push/merge.

### Documentation updates

- CURRENT_STATE, instrukcja VISION_LAB_LOCAL i raport
  VISION_LAB_STAGE_B_ACCEPTANCE. Zadanie pozostaje aktywne, nie w completed.

### Recommended next task

- Preflight wykonanych anotacji i rozstrzygnięcie powiązań zdjęć.
  Dopiero po spełnieniu bramek T03 można uruchomić zależny T04.
  Odblokowanie samego kodowania T04 wcześniej wymaga zmiany zaakceptowanego
  planu; nie przyjęto jej samodzielnie.
