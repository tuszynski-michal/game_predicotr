Zbieram fakty z repozytorium do audytu planu: wymagania ręcznej selekcji, wspólny rdzeń, Reviewer operator-local, numerację tasków i stan gałęzi na D.

**Werdykt: REVISE.** Kierunek planu dobry (Electron, rdzeń współdzielony, dane u odbiorcy, zero zmian API). Plan nie przechodzi bramki `PLAN_STANDARD.md`: brak sekcji „Stan obecny” ze sprawdzonymi ścieżkami i symbolami, brak jawnych decyzji, brak reguł błędów, brak mapy wymaganie-task-test. Dwie decyzje produktowe są ukryte i blokują TASK-0976/0978. Poniżej fakty, uwagi i podział P0/P1.

## Fakty sprawdzone w repo (D, czubek v1.7.316)

- Numery TASK-0975–0979 i D-545 wolne na wszystkich gałęziach lokalnych, `origin/*` i `c/*`. Ostatnia decyzja: D-544.
- Checkout C stoi na v1.7.312 i jest nieużywany (`CURRENT_STATE.md`, TASK-0956). Plan słusznie celuje w `D:\game_predicotr`. Prace tylko w osobnym worktree klonu D.
- `packages/manual-image-selection-core/src/index.ts` ma całą czystą logikę do reużycia: `resolveManualSelectionShortcut` (Enter/F akceptacja, Tab pominięcie, A i Ctrl+Z cofnięcie, strzałki, skok), `rangeForStart`, `isManualSelectionRangeTerminal`, `naturalCompare`, `createManualSelectionState`/`nextManualSelectionState`/`previousManualSelectionState`, `reconcileManualSelectionStateWithOutputManifest`, `manualPreviewWindow`, `fitManualImageToViewport`, porty `ManualSelectionSourcePort`/`OutputPort`/`SessionPort`. Plan powinien je wymienić zamiast ogólnego „wykorzystuje rdzeń”.
- Pod jedną nazwą `manual-image-selection-output-v1.json` istnieją **dwa różne formaty**: rdzeniowy (`gameId`, `sessionKey`, `items`; czyta Admin `manual-image-selection-fsa-adapter.ts`, repair `manual-selection-repair-storage.ts` i ranker workera, schema 1) oraz operator-local Reviewera (`storageMode: 'operator_local'`, `sessionId`, `batchId`, `decisions`; `apps/reviewer/src/features/manual-selection/operator-local-selection-output.ts`). Admin nie czyta wariantu operator-local.
- Twardy kontrakt dla właściciela to nazwy plików `seq_<start>-<end>.jpg` (`domain/image_geometry_v2.py`, `api/image_imports.py`). Manifest służy wznowieniu, repair i rankerowi.
- Checksum manifestu źródła (`buildRemoteSourceManifestV1`) obejmuje `sizeBytes` i `lastModifiedMs` każdego pliku. Kopia folderu na inny komputer zmienia mtime i unieważnia checksum.
- Semantyki Admina i Reviewera różnią się: Admin ma asynchroniczną kolejkę do 100 wyborów i edytor zakresu 1–9 plansz; Reviewer szereguje interakcje, zapis jest potwierdzony po JPEG i decyzji, edytor zakresu wymaga dokładnie 9. Plan przyjmuje semantykę Reviewera, ale nie mówi tego wprost.
- Gałąź `c/codex/manual-selection-queue` (v0.10.336–338, niescalona) zmienia tylko Admin (wyłącza Enter, blokuje podwójną akceptację). Nowa aplikacja nie dziedziczy tych zmian.
- `scripts/generate_code_map.py` ma listę `AREAS` na sztywno. Nowy workspace wymaga nowego obszaru, inaczej `code-map:check` go nie pokryje.
- `scripts/check_current_state_window.py` wymaga nagłówka `TASK-NNNN` w `CURRENT_STATE.md` dla każdego pliku w `ai_docs/tasks/`. Pięć plików `todo` wymaga pięciu sekcji.
- Root `package.json` ma klucz `allowScripts` z jedynym wpisem `unrs-resolver`. Pakiet `electron` pobiera binarkę w skrypcie `postinstall`. Trzeba ustalić, jaka polityka skryptów instalacyjnych obowiązuje i czy `npm install` całego monorepo ma pobierać Electron każdemu.
- Node lokalnie 24.21, `engines` `<25`, TypeScript ~6.0.3, React 19.2.3. Brak Electrona w repo.

## Uwagi do planu

**P0, blokują akceptację:**

1. **Decyzja o manifeście w `wybrane`.** Plan nie określa, który z dwóch formatów zapisuje folder wynikowy. Rekomendacja: wariant operator-local Reviewera, bajt w bajt ten sam writer co dziś u odbiorcy; właściciel nie widzi różnicy. Rdzeniowy wariant `items` tylko jeśli właściciel chce repair i rankera na tych wynikach. Zapisać jako D-545 razem z nową aplikacją i formatem projektu.
2. **Semantyka selekcji.** Zapisać wprost: semantyka Reviewera (szeregowanie, zakres zmieniany po trwałym zapisie, edytor `Od`/`Do` dokładnie 9 plansz, skok 1–20, fullscreen, zoom 100–3000%, `Restart selekcji` tylko po walidacji checksum). Ślad uczenia (`trace-v1`) poza zakresem albo P1.
3. **Zerowy dotyk Admina i Reviewera w P0.** Plan dopuszcza „wydzielanie wspólnych elementów interfejsu”. Komponent podglądu leży w `apps/admin` i `apps/reviewer`, nie w pakiecie; wydzielenie dotyka obu konsumentów i wymaga testów regresji. Rekomendacja: P0 importuje tylko `manual-image-selection-core`, podgląd pisze od nowa w aplikacji; wydzielenie wspólnego pakietu to osobny task P1.
4. **Przejęcie sesji (TASK-0978) i mtime.** Przy przeniesieniu źródła na inny komputer checksum manifestu źródła nie zgodzi się przez `lastModifiedMs`. Potrzebna reguła zgodności stopniowanej: identyczny checksum = przejęcie automatyczne; różnica tylko w mtime przy zgodnych ścieżkach, rozmiarach i SHA-256 wszystkich zaakceptowanych JPEG-ów = przejęcie po jawnym potwierdzeniu; inna lista plików lub checksum = blokada. Bez tej reguły task jest niewykonalny w głównym scenariuszu.
5. **Zależność TASK-0979 od TASK-0978.** Wydanie nie powinno czekać na przejęcie starych sesji. Odbiorca zaczyna nowe partie w nowej aplikacji, a bieżącą kończy w Reviewerze. Zależność: 0979 po 0977.
6. **Trwałość bez konkretów.** Dopisać: zapis stanu przez plik tymczasowy, `fsync`, `rename` nad poprzednią wersją; dziennik operacji z fazami `jpeg_written`, `decision_committed`; przy starcie rozliczenie dziennika przed odblokowaniem UI. Blokada drugiej instancji: `app.requestSingleInstanceLock()` nie wystarcza (druga maszyna, folder synchronizowany). Potrzebny plik blokady w folderze projektu z PID, nazwą hosta i heartbeatem oraz zasadą przejęcia stale lock. Ostrzeżenie w aplikacji i instrukcji: folder projektu poza katalogiem synchronizowanym Proton Drive; do chmury idzie tylko gotowy `wybrane`.
7. **Serwowanie zdjęć i bezpieczeństwo Electrona.** Dopisać do TASK-0975: `contextIsolation`, `sandbox`, bez `nodeIntegration`, CSP, blokada nawigacji i nowych okien; zdjęcia przez własny protokół (`protocol.handle`) strumieniujący bajty wyłącznie spod zarejestrowanego korzenia źródła, nie przez IPC jako base64; każda operacja IPC sprawdza containment ścieżki w korzeniu źródła lub projektu i odrzuca `..` oraz reparse pointy. To odpowiednik reguły R-002 z architektury zdalnej.
8. **Paczka bez podpisu.** ZIP z niepodpisanym exe pobrany z Proton Drive dostaje Mark-of-the-Web; SmartScreen zablokuje start, Defender może oznaczyć plik. Plan musi to rozstrzygnąć: brak podpisu świadomie plus instrukcja „Odblokuj” i „Uruchom mimo to” w TASK-0979, albo certyfikat jako osobna decyzja kosztowa. Dopisać też `ELECTRON_MIRROR`/politykę skryptów instalacyjnych i wpływ na `npm install` oraz bramkę `quality` (`npm test --workspaces` obejmie nowy workspace).

**P1, ulepszenia:**

- Plik logu diagnostycznego z rotacją w folderze projektu i przycisk „Otwórz folder logów”. Tanie, kluczowe dla zdalnego wsparcia odbiorcy. Można wciągnąć do P0 w TASK-0975.
- Skala: założyć do 15 000 JPEG na partię (jak architektura zdalna), indeks w pamięci, okno podglądu ±3, bez miniatur. Zapisać w planie jako założenie.
- Testy awarii TASK-0976 jako czysty moduł Node (`node --test`) z wstrzykiwanymi punktami awarii adaptera plików, bez Electrona. E2E Electrona (Playwright) dopiero P1.
- Nazewnictwo: dziś odbiorca ma `<źródło> wybrane` obok źródła. Plan daje `<źródło> selekcja\wybrane`. Zachować nazwę `wybrane` bez zmian, decyzja o lokalizacji jawna.
- Dokumentacja wymagana przez proces, dziś pominięta: nowa sekcja w `requirements/MANUAL_IMAGE_SELECTION.md` i `architecture/MANUAL_IMAGE_SELECTION.md`, wpis D-545, obszar w `generate_code_map.py`, pozycja w `ai_docs/README.md`, sekcje w `CURRENT_STATE.md`, wpis w `TRACEABILITY.md`.
- Usunąć z treści planu akapit o trybie planowania i blokadzie edycji; to stan sesji, nie plan. Literówka „Zależżność”.
- Model table: zgodna ze standardem i z regułą rodzin (Codex wykonuje, Claude audytuje). Dla TASK-0976 rozważyć audyt `high`: utrata decyzji odbiorcy to utrata danych dowodowych.

## Podział na taski P0 / P1

**P0: odbiorca dostaje działające narzędzie do nowych partii.**

| Task | Zakres po korekcie | Zależność |
|---|---|---|
| TASK-0975 | Workspace `apps/selector-desktop`, Electron Forge ZIP, hardening, własny protokół zdjęć, typowany kontrakt IPC z containment, log diagnostyczny, polityka skryptów instalacyjnych, obszar w mapie kodu, D-545 | plan zaakceptowany |
| TASK-0976 | Projekt: format wersjonowany, dziennik operacji, kopia stanu, atomowy zapis, plik blokady, odzyskiwanie, manifest operator-local w `wybrane`; testy awarii w czystym Node | 0975 |
| TASK-0977 | Pełny UI w semantyce Reviewera, tylko import z `manual-image-selection-core`, zero zmian w Adminie i Reviewerze, ekran „Kontynuuj”, „Otwórz folder wynikowy” | 0976 |
| TASK-0979 | Wydanie: wersja, SHA-256 ZIP, instrukcja z SmartScreen i zasadą „projekt poza synchronizacją”, aktualizacja przez rozpakowanie, odbiór na drugim komputerze | 0977 |

**P1: po pierwszym wydaniu.**

| Task | Zakres | Zależność |
|---|---|---|
| TASK-0978 | Przejęcie sesji operator-local v1/v2 z regułą zgodności stopniowanej (mtime), podgląd, jawne przejęcie, bez zmiany oryginału | 0977, wydanie 0979 |
| TASK-0980 (nowy, opcjonalny) | Wspólny pakiet podglądu dla Admina, Reviewera i desktopu z testami regresji obu konsumentów | 0977, decyzja operatora |
| Kandydaci bez numeru | E2E Electrona, eksport śladu uczenia w formacie `items`, podpis kodu, autoaktualizacja | 0979 |

Nie zapisałem plików i nie uruchamiałem testów. Następny krok po Twojej akceptacji uwag: poprawiony plan plus pięć tasków w worktree klonu D, numeracja 0975–0979 i D-545 sprawdzone ponownie tuż przed zapisem.
