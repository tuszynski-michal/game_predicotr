---
title: Kompaktowe punkty i maszyny z nawigacją w głąb
status: done
last_updated: 2026-10-09
---

# TASK-0941 — Kompaktowe punkty i maszyny z nawigacją w głąb

## Status

`done`

## Goal

Umożliwić szybką nawigację punkt → maszyna z małymi kafelkami i atomowymi modalami bez utraty szkicu.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

TASK-0940 zakończony, audyt i commit zapisane. Przed kodowaniem przeczytać ten task oraz sekcje produktu/nawigacji planu.

## Recommended execution

gpt-6-sol / medium. Nie rozszerzać zmian domyślnego search/share. Największe ryzyko: popstate/dirty guard i własny refresh unieważniający preview. Layout oceniany na fixture, produkcyjne przeglądarki i dane operatora poza testem.
Wymagany niezależny ręczny review claude-opus-5-5 / medium przed commitem. Konfiguracja musi
odpowiadać końcowej tabeli planu; niedostępność albo zmiana ryzyka wymagają jawnej
aktualizacji, bez ukrytej zamiany modelu.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0941 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Siatka punktów i maszyn max320px, cztery kolumny od pierwszego kafelka; Home/back i brak wszystkich poziomów naraz.
- Cały tile klikalny, sibling edit/delete icons, widoczne zaznaczenie i touch44.
- Modal punktu/maszyny; atomowa nazwa+gry, preview/confirm/delete i zachowanie formularza po błędzie.
- URL mpPoint/mpMachine/mpGame/mpStake, ostatnia gra pernamespace/machine, scrollpertab, refresh snapshot i pending recovery.
- Dirty guards wszystkich wyjść, pauza własnego autorefresh przy delete; lokalny panel linków collapsed; legacy archived collapsed.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [x] Jeden tile nie rozciąga się; kontener1000/750/500 używa4/3/2kolumn, mniejszy1; brak horizontal scroll przy390px.
- [x] Home i Cofnij do punktów działają, wybrana maszyna/stawka oznaczone; ikony nie wybierają kafelka.
- [x] Modal zapisuje name+games jednym request; error/CAS zachowuje draft i wymaga świeżego preview.
- [x] Reload/URL/popstate odtwarzają najbliższy poprawny poziom, mpStake nie otwiera editor, parent params zachowane.
- [x] Pending scope i stara sesja nie są przenoszone na innego aktora; recovery bez autoretry.
- [x] Focus/back/writes/notfound/conflict odświeżają snapshot; usunięcie w innym oknie nie zostawia fałszywego aktywnego celu.
- [x] Dirty draft chroniony na Home/back/popstate/game/modalclose; legacy archived usuwalne, archiwizacja niewidoczna.
- [x] Admin i Reviewer używają tego samego UI; link controls tylko lokalnie.

## Technical notes

Handoff z audytu TASK-0940 (P2-2): formularz musi wywołać machine
`update-preview` dla końcowej komendy przed usunięciem istniejącego przypisania,
także legacy `attached=false`. Nie wyznaczaj zakresu wyłącznie z aktualnie
widocznych/aktywnych gier. Po potwierdzeniu przekaż token z tym samym UUID,
body i rewizją. Do zamknięcia tego taska stary formularz nie obsługuje tokenu
i odpięcie zwraca 409; nie omijaj tej ochrony backendu.

Obowiązuje sekcja „Nawigacja i ochrona szkicu” planu. Lokalny namespace i publiczny session UUID są odrębne. Wybrane mpStake oznacza tile, nie jest serializacją szkicu. Controls edit/delete to rodzeństwo pełnego button, nie nested HTML. Reload pending nie ponawia mutacji automatycznie. Restore zakresu służy odzyskiwaniu, nie zastępuje wyboru URL innymi danymi bez guardu. Nie kopiować wrapperów do nowych niezależnych implementacji.

## Expected files

- Istniejące: packages/board-search-ui/src/management/management-workspace.tsx, management.css — hierarchy/layout/modals.
- Istniejące: management-operation.ts, management-client.ts, management-game-workspace.tsx — pending commands, preview ports, refresh pause.
- Istniejące: apps/admin/src/features/management/management-workspace.tsx, management-share-panel.tsx; apps/reviewer/src/features/management/management-gate.tsx — cienkie integracje.
- Nowe, proponowane: packages/board-search-ui/src/management/management-navigation.ts i management-structure-modal.tsx — czysta URL/state logika i modal.
- Testy istniejących management interaction/geometry suites w board-search-ui/Admin/Reviewer.

## Test cases

- 1/4/40 kafelków oraz40punktów do40maszyn — geometria bez autoexpand pojedynczego tile.
- Enter/Space na tile, edit/delete click, touch44 → poprawna akcja bez double navigation.
- Niepoprawny/missing URL scope i delete w drugim oknie → valid ancestor replaceState.
- Błąd atomowego save/preview expired → modal zachowuje wpisany formularz.
- Dirty draft + każda droga wyjścia/popstate → guard; cancel pozostawia wybrany scope.
- Public session change/recovery UUID → stara operacja nie przechodzi do nowej sesji.

## Verification

Katalog: root oddzielnego worktree. Każdą poniższą skończoną komendę wykonaj
z wymuszonym timeoutem 120s w runnerze; provisioning check:30s. PG wyłącznie
disposable DB, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 tylko w procesie testowym.
Brak venv/node_modules worktree wymaga izolowanego środowiska; nie buduj dist
ani aplikacji w głównym checkout operatora. Testy poniżej są planowane,
nie zostały jeszcze uruchomione. Najpierw pion, potem lint/typecheck/scoped
format, dopiero regresje/build. Znany build >120s poprzedź komunikatem.

```powershell
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test:geometry --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/board-search-ui
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Brak audytu zatrzymuje następny task.

## Risks / open questions

Nie rozszerzać zmian domyślnego search/share. Największe ryzyko: popstate/dirty guard i własny refresh unieważniający preview. Layout oceniany na fixture, produkcyjne przeglądarki i dane operatora poza testem.

## Outcome

### Changed

- Wspólny panel pokazuje jeden poziom na raz: punkty, maszyny punktu albo gry i stawki maszyny. Kafelki mają stałe progi 4/3/2/1 kolumn i limit 320 px, pełny przycisk wyboru oraz osobne przyciski edycji i usunięcia. Archiwalne rekordy są dostępne w zwiniętych sekcjach wyłącznie do usunięcia.
- Formularze punktu i maszyny są modalne. Maszyna zapisuje nazwę i końcową listę gier jednym żądaniem. Odpięcie istniejącego wiersza, także legacy `attached=false`, zawsze poprzedza `update-preview`; żądanie zapisu zachowuje UUID, body, rewizję i token podglądu. Błąd lub konflikt pozostawia wpisany formularz. Punkt i maszyna używają podglądu liczników oraz potwierdzonego usunięcia.
- Prezentację formularza wydzielono do planowanego `management-structure-modal.tsx`; logika operacji pozostaje we wspólnym workspace. Nie dodano kopii wyszukiwarki ani obliczeń stawek.
- Parametry `mpPoint/mpMachine/mpGame/mpStake` zachowują inne parametry adresu. Niepoprawny zakres wraca do najbliższego poprawnego rodzica. Ostatnia gra jest lokalna dla namespace i maszyny, scroll dla poziomu pozostaje w pamięci karty. Oczekująca operacja ma pierwszeństwo przy odzyskiwaniu; reload nie ponawia zapisu samoczynnie. Home, back, popstate, zmiana gry i zamknięcie modala chronią szkic. Powrót na listę, focus, zapis i konflikt pobierają świeży snapshot. Refresh stawek jest pauzowany podczas podglądu/usuwania.
- Popstate zewnętrznego katalogu Admina sygnalizuje odmowę przejścia, aby jeden brudny szkic wyświetlał jeden dialog potwierdzenia. Lokalne linki pozostają zwinięte w nagłówku; Reviewer używa tego samego wspólnego komponentu.

### Verification results

- `@game-predictor/board-search-ui test:interactions`: 51/51 PASS; nowy test czystej nawigacji URL: 2/2 PASS.
- `@game-predictor/admin test:geometry`: 171/171 PASS przed dodaniem ostatniego testu modala; późniejszy scoped management/cards po wydzieleniu modala: 26/26 PASS. Zmieniono oczekiwania wyłącznie dla świadomie zastąpionych kontroli archive i poprzedniego układu; dodano atomową komendę modala, legacy `attached=false`, 409 z zachowaniem formularza, delete preview, exact UUID po utracie odpowiedzi oraz odmowę Home/popstate/modal close przy brudnym szkicu.
- `@game-predictor/reviewer` management-panel interaction: 14/14 PASS po przejściu testu na modal atomowy i nową hierarchię. Testy komponentu w obu aplikacjach korzystają ze wspólnego UI.
- Typecheck `board-search-ui`, Admin i Reviewer: PASS. Scoped ESLint zmienionych modułów board-search-ui: PASS. Pełny lint Admin i Reviewer: exit0, odpowiednio pięć i jedno wcześniejsze ostrzeżenie poza panelem. Prettier zmienionych plików UI/testów: PASS.

### Not completed at initial handoff (historical)

- Niezależny ręczny audyt `claude-opus-5-5 / medium`, ewentualna jedna runda poprawek, commit `v1.7.274` i przeniesienie taska do completed czekają na raport audytora. Nie wykonywano działań na danych operatora, migracji produkcyjnej ani lifecycle API/Admin.
- Fizyczny odbiór układu na ekranach 390/1440/1920 px i danych operatora należy do TASK-0943; obecne testy potwierdzają kontrakt interakcji i reguły CSS, nie pomiar przeglądarki produkcyjnej.

### Documentation updates

- Odbiór przeglądarkowy0943 wykrył nadpisanie limitu320px oraz potwierdził
  potrzebę umieszczenia ikon w górnym rogu i objęcia ich/nawigacji obecnym
  stylem przycisków. Korekty wspólnego CSS wykonano przy0942. Odroczony audyt
  i commit0941 mają uwzględnić tę poprawkę fundamentu UI:
  `artifacts/audits/TASK-0941_STAGE/acceptance-correction.patch` i
  `closure-files.zip`; pierwotny snapshot pozostaje zachowany. Nie jest to
  raport Claude ani formalne zamknięcie taska.
- `CURRENT_STATE.md` opisuje stan implementacji, dowody testowe i nadal wymaganą bramkę audytu. Wymagania i architektura D-536 już definiują wprowadzone zachowanie.
- Po zakończeniu kontroli skill claude-audit wygenerował
  `artifacts/audits/TASK-0941_BRIEF_claude.md` (106776 bajtów, 104 KB),
  Base HEAD `0625512d4a37072f1d6d44f3f85ef225e7db1835`, właściwy worktree,
  ograniczone ścieżki taska i model claude-opus-5-5. Wymagany reasoning medium
  wynika z tabeli planu i Recommended execution. Tryb DryRun nie uruchomił
  audytora. Raport docelowy: `ai_docs/quality/TASK-0941_AUDIT_claude-opus-5-5.md`.
  Instalacja Claude Code w Desktop istnieje, lecz CLI poza sandboxem nadal
  zgłasza brak logowania; poświadczeń nie odczytano ani nie kopiowano.

### Poprawki po audycie (2026-10-09, jedna ograniczona runda)

- Audyt `claude-opus-5-5 / medium` zakończył się werdyktem `REVISE` w `ai_docs/quality/TASK-0941_AUDIT_claude-opus-5-5.md`. P1-1 naprawiono: modal zachowuje początkową `baseRevision` i szkic, a odświeżenie sygnalizuje nowszy stan; zapis nadal używa starej rewizji, więc 409 nie nadpisuje cudzej zmiany i pozostawia formularz. P1-2 naprawiono: zewnętrzny guard Admina otrzymuje łączny stan szkicu gry i modala. Odmowa zmiany workspace albo popstate wyświetla jedno potwierdzenie i zachowuje modal. P1-3 naprawiono: odzyskanie zakresu następuje raz na UUID i namespace, po walidacji i guardzie; Home/focus nie otwierają go ponownie, oczekująca operacja struktury w tej samej maszynie zachowuje prawidłową grę i stawkę, a zmiana publicznej sesji usuwa poprzedni szkic modala. P1-4: dodano regresje izolacji namespace, zmiany sesji, usunięcia maszyny/punktu w drugim oknie oraz wyboru `mpStake` bez otwarcia edytora. Końcowy odbiór przeglądarkowy leada PASS (10/10 przypadków) objął 1/4/40 kafelków, 40 maszyn/200 gier, progi kontenera 1000/750/500/320 px dające 4/3/2/1 kolumn, limit320 px, touch44 oraz położenie i szerokość modali.
- P2-1 zaakceptowano jako jawne ryzyko: modal wyjaśnia, że legacy `attached=false` pozostaje zaznaczone dla ochrony historii; zapis może ponownie przypisać aktywną grę, a nieaktywną trzeba jawnie odpiąć po podglądzie i potwierdzeniu usunięcia historii. Zmiana kontraktu backendu wymaga osobnego taska. P2-2 naprawiono: aktywne odłączone przypisanie pojawia się raz z etykietą „odłączona”. P2-3 naprawiono: zewnętrzny popstate obsługuje zewnętrzny guard, a znacznik anulowania wygasa po zdarzeniu. P2-4 naprawiono: zmienione pliki sformatowano, testy i lint przechodzą. P2-5 naprawiono po pomiarze przeglądarkowym: `container-type` na całym workspace zmieniał containing block dla `position: fixed`. Kontener przeniesiono na wrapper list, a modal pozostał jego rodzeństwem; limit320 px dotyczy tylko kafelków. Powtórny pomiar 10/10 PASS. W diagnostyce 1440 px pozorny offset 7,5 px względem `innerWidth` wynikał z pionowego scrollbara; modal jest wycentrowany względem `documentElement.clientWidth`. P2-6 naprawiono po audycie fokusowym: przywrócono układ etykiety i motyw pola nazwy w modalu (padding, obramowanie, zaokrąglenie, tło); szybki pomiar stylu wykona lead. P2-7 zaakceptowano: odmowa guardu świadomie nie przywraca automatycznie zakresu tej samej operacji w późniejszym odświeżeniu, ale zachowuje lokalizację i przycisk „Ponów ten sam zapis”.
- Niezależny audyt fokusowy `claude-opus-5-5 / medium`, runda 2, zakończył się `PASS` (`ai_docs/quality/TASK-0941_AUDIT_claude-opus-5-5_ROUND_2.md`), bez P0/P1. Pozostałe P2-1/P2-7 zaakceptowano powyżej; P2-6 naprawiono bez kolejnej rundy audytu.
- Weryfikacja poprawek: skoncentrowane suite interakcji Admin 39/39 PASS; Reviewer geometry 41/41 PASS według leada; Chromium 10/10 PASS, w tym progi 4/3/2/1 i modal w dostępnej szerokości viewportu. Typecheck wspólnego UI PASS; ESLint dwóch zmienionych komponentów wspólnych oraz dwóch plików testowych Admin PASS; Prettier zastosowano do tych plików; `git diff --check` dla ścieżek poprawki PASS. Wykonawca nie uruchamiał API/Admin, nie zmieniał danych operatora, nie wykonywał push, merge ani commita.

### Recommended next task

- Operator 2026-10-09 jawnie pozwolił przygotować kod i testy TASK-0942–0943
  przed audytem0941. Stan0941 zachowano w
  `artifacts/audits/TASK-0941_STAGE/files.zip` wraz z manifestem i patchem.
  Audyt, rozwiązanie uwag, osobny commit i done pozostają odroczone;
  bez nich plan nie może być zamknięty ani scalony.


### Końcowe zamknięcie (2026-10-09)

- Fokusowy audyt Claude `claude-opus-5-5 / medium`, runda2: PASS; wszystkie
  P1-1–P1-4 zamknięte. Oryginalny REVISE i niezależny PASS zachowano w ai_docs/quality.
- R2 P2-6: przywrócono motyw pola modala. P2-1 zaakceptowane: zachowanie legacy
  jest jawnie opisane przed zapisem, a usunięcie historii wymaga powiązanego preview
  i potwierdzenia. P2-7 zaakceptowane: odmowa odzyskania brudnego szkicu nie może
  później nadpisać nawigacji operatora; identyczne ponowienie pozostaje dostępne.
- Końcowe dowody: Admin interakcje39/39, Reviewer geometry41/41, Chromium10/10 PASS;
  kontenery1000/750/500/320 dają4/3/2/1 kolumny, max320px, touch44px,
  wycentrowane modale z motywem i brak poziomego przewijania. Buildy obu aplikacji PASS.
  Fixture nie zastępuje odbioru urządzeń/live ingress ani migracji danych operatora.
- Wersja commita: v1.7.274. Pełny hash zostanie zapisany od razu po commicie
  w Outcome i CURRENT_STATE razem z dokumentacją kolejnego taska.
- Nowe AGENTS wymaga okna done i mapy: nadmiarowe wpisy done archiwizujemy bez zmiany
  treści; mapy dla dokładnego indeksu powstają aktualnym generatorem z main tylko
  do odczytu. Baza gałęzi poprzedza narzędzia TASK-0938/0939. `npm run docs:check`
  zwraca Missing script; nie deklarujemy PASS ani nie włączamy niezwiązanej migracji procesu.

### Commit

v1.7.274 — 993ddc763f3946453ea391c1a82ba6288052f866. Osobny commit potwierdzony przez git log/show; zapis dołączany do dokumentacji następnego taska.
