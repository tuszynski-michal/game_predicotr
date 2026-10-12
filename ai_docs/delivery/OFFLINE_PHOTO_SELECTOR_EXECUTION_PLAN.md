---
title: Lokalny selektor zdjęć Windows
status: accepted
last_updated: 2026-10-11
---

# Lokalny selektor zdjęć Windows — plan po audycie Codex

## Stan obecny i cel

Obecny Reviewer wykonuje selekcję na komputerze odbiorcy, ale dostęp do
interfejsu zależy od hosta i tunelu. Postęp znajduje się w IndexedDB oraz
manifeście wynikowym. Nowa aplikacja ma uniezależnić pracę od tych usług.

Sprawdzone punkty odniesienia na bazie v1.7.316:

- `packages/manual-image-selection-core/src/index.ts`: `resolveManualSelectionShortcut`,
  `rangeForStart`, `naturalCompare`, `manualPreviewWindow`,
  `fitManualImageToViewport`, reguły stanu selekcji i porty Source/Output/Session.
- `apps/reviewer/src/features/manual-selection/operator-local-selection-output.ts`:
  `OperatorLocalOutputManifestV1`, `OperatorLocalOutputManifestV2`,
  `verifyOperatorLocalOutputDirectory`, `resumeOperatorLocalBatch`.
- `apps/reviewer/src/features/manual-selection/remote-manual-selection-workspace.tsx`:
  `RemoteManualSelectionWorkspace`, szeregowanie zapisów i zachowanie UI.
- `scripts/generate_code_map.py`: stała `AREAS`; nowy workspace wymaga
  jawnego obszaru. Root `package.json` obejmuje workspace'y przez `apps/*`.

**Cel:** odbiorca uruchamia aplikację Windows z ZIP, wybiera lokalne zdjęcia
i kontynuuje pracę po restarcie. Zdjęcia oraz wyniki pozostają u niego.
Proton Drive obsługuje poza aplikacją.

## Akceptacja i zakres uruchomiony

Operator zaakceptował plan i polecił jego implementację 2026-10-11.
Oddzielnie zatwierdził przewidywany koszt 3–6 godzin pracy z testami,
pakowaniem i audytami, bez wiarygodnego szacunku procentu pakietu.

- Pierwotne pierwsze wydanie obejmowało **0975 → 0976 → 0977 → 0979**.
  Końcowy zakres pilotażu obejmuje także zgodne przejęcie starej sesji0978.
- Operator uruchomił również TASK-0978 poleceniem wykonania pięciu zadań.
  Kolejność implementacji: 0975 → 0976 → 0977 → 0979 → 0978.
- Pierwsze przekazanie to pilotaż bez podpisu na konkretnym komputerze.
- Dane i wyniki zostają u odbiorcy; upload, linki oraz integracja Proton Drive
  nie należą do tego zakresu.
- Zgoda nie obejmuje push, merge, uruchamiania usług głównej aplikacji,
  instalacji/logowania CLI audytora ani odbioru na cudzym komputerze.

Operator następnie polecił rozpoczęcie wszystkich pięciu tasków i odroczył
audyt do końca całej implementacji. Jest to jawny wyjątek od audytu przed
każdym commitem i potwierdzenia CLI przed startem. Agent nie uruchamia audytów
ani nie zastępuje audytora. Operator wykonuje końcowy przegląd. Odbiór drugiego
komputera pozostaje osobną bramką 0979; nie zatrzymuje implementacji 0978.

## Decyzje architektoniczne

### Aplikacja i granice zmian

- Electron, React i TypeScript; Electron Forge tworzy ZIP dla Windows 11 x64.
- Nowy workspace `apps/selector-desktop`, osobny worktree klonu na D,
  gałąź `codex/offline-photo-selector`.
- Aplikacja korzysta z istniejącego rdzenia, ale ma własny interfejs.
  Pierwsze wydanie nie zmienia komponentów Admina ani Reviewera.
- Brak zmian API, OpenAPI, PostgreSQL, migracji i usług głównej aplikacji.
- Nowe interfejsy to typowane polecenia lokalne oraz wersjonowany format
  projektu. Transport IPC nie przyjmuje dowolnych ścieżek od renderera.
- Zależności są przypięte w lockfile. Instalacja całego monorepo pobiera też
  Electron; dokumentacja i odbiór 0975 mają uwzględnić ten wpływ.
  Wolno dopuścić wyłącznie skrypty konkretnych niezbędnych pakietów,
  bez globalnego wyłączenia kontroli i bez niestandardowego ELECTRON_MIRROR.

### Projekty, wyniki i zgodność

- Użytkownik wybiera źródło oraz lokalizację projektu. Domyślne katalogi
  obok źródła: `<źródło> selekcja` oraz `<źródło> wybrane`.
- Projekt działa na lokalnym dysku, poza synchronizacją i udziałami
  sieciowymi. Gotowy wynik można ręcznie przekazać przez Proton Drive.
- Źródło jest tylko do odczytu. Wyniki zachowują oryginalne bajty JPEG oraz
  nazwy `seq_<start>-<end>.jpg`.
- Folder wynikowy zapisuje wariant **operator-local schema v2** pod nazwą
  `manual-image-selection-output-v1.json`, z semantyką pól Reviewera.
  Nie jest to rdzeniowy wariant `items`. Repair i trace uczenia są wyłączone.
- Projekt jest źródłem prawdy dla decyzji. Manifest wynikowy stanowi jego
  zgodną projekcję. Rozbieżność wymaga recovery; obce dane blokują zapis.
- Projekt ma stabilny lokalny identyfikator. Historyczne nazwy sessionId i
  batchId w kompatybilnym manifeście nie oznaczają sesji sieciowej.

### Interfejs i numeracja

- Ekran startowy: Nowy projekt, Otwórz projekt, Kontynuuj.
  Lista ostatnich projektów jest cache'em; cały postęp jest w projekcie.
- Pomocniczy cache widoku w userData według projectId przechowuje krok
  nawigacji, zoom i scroll. Jest zapisywany atomowo i rozliczany przy
  zamknięciu. Brak/uszkodzenie tego cache'u zmienia wyłącznie widok;
  projekt nadal określa decyzje, zdjęcie, zakres i kierunek.
- Semantyka Reviewera: zapis szeregowy, licznik po trwałym commitcie,
  Enter/F, Tab, A/Ctrl+Z, strzałki i brak powtórnej akceptacji tego samego
  źródła bez cofnięcia. Kierunek numeracji nie zmienia porządku źródła.
- Zweryfikowany Reviewer: Enter i F akceptują i przesuwają zdjęcie o jeden,
  niezależnie od kroku nawigacji; Tab pomija zakres, pozostawiając zdjęcie.
  Na końcu listy kursor pozostaje na ostatnim zdjęciu.
- `rangeForStart` daje standardowo dziewięć plansz i krótszy zakres przy
  końcowej granicy sesji. Edytor nie dopuszcza dowolnej długości 1–9.
- Skoki z rdzenia: 1–10, 15, 20. Zoom 100–3000%, fullscreen, obie osie
  przewijania i okno podglądów ±3, bez miniaturek.
- Otwórz folder wynikowy otwiera lokalny folder. Restart wymaga preview,
  potwierdzenia i walidacji własności/checksum; brak katalogu nie resetuje.

### Trwałość, błędy i blokady

- Stan jest wersjonowany, z ostatnią poprawną kopią. Zapis: temp w tym samym
  katalogu, synchronizacja, podmiana. Nie usuwamy poprzedniej wersji przed
  powodzeniem podmiany. Testujemy zachowanie Windows, nie tylko memory store.
- Przed zmianą JPEG-a utrwalamy zamiar. Dziennik rozróżnia przygotowanie,
  zapis JPEG-a i zatwierdzenie decyzji. Recovery rozlicza go przed mutacjami.
- Powtórzenie identycznej operacji odtwarza wynik; ten sam identyfikator
  z innymi argumentami powoduje konflikt. Kursor zapisuje ścieżkę względną.
- Plik blokady powstaje atomowo i zawiera identyfikator właściciela, hosta
  oraz procesu. Sam przeterminowany heartbeat nie uprawnia do przejęcia.
  Martwy proces tego samego hosta można przejąć po sprawdzeniu tożsamości;
  nieznany właściciel blokuje zapis. requestSingleInstanceLock nie zastępuje
  blokady projektu i nie chroni folderu synchronizowanego między komputerami.
- Transakcja dodatkowo bierze atomową przejściową blokadę folderu wynikowego,
  aby dwa różne projekty nie przypisały tego samego outputu. Własność/proces
  są sprawdzane jak w blokadzie projektu; nieznany lub aktywny właściciel
  blokuje zapis. Blokada znika przed potwierdzeniem. Finalny wynik zawiera
  wyłącznie JPEG-i i manifest; po awarii najpierw rozlicza się blokadę i journal.
- Brak miejsca/błąd zapisu: zatrzymanie nowych decyzji, wcześniejsze commity
  pozostają, dziennik nie znika. Komunikat opisuje etap i jawne wznowienie.
- Brak źródła/wyniku: ponowne wskazanie i weryfikacja, bez resetu.
  Checksuma/obcy plik: konflikt i blokada zależnej mutacji, bez nadpisania.
- Błąd programistyczny nie staje się wynikiem successful albo empty.

### Bezpieczeństwo, skala i wydanie

- contextIsolation, sandbox, nodeIntegration=false, restrykcyjne CSP,
  blokada nawigacji zewnętrznej i nowych okien, walidacja nadawcy IPC.
- Protokół zdjęć strumieniuje pliki spod zarejestrowanego korzenia.
  Identyfikatory indeksu zamiast ścieżek i base64. Natywna warstwa odrzuca
  wyjście poza korzenie, traversal i reparse pointy także przy zapisie.
- Założenie: do 15 000 JPEG na projekt; indeks metadanych w pamięci,
  bounded preview ±3, hashowanie/kopiowanie strumieniowe.
- Rotowane logi bez treści obrazów i z przyciskiem otwarcia folderu logów.
- ZIP pilotażowy może wywołać ostrzeżenie albo blokadę Windows. Blokada
  wstrzymuje odbiór; nie zalecamy wyłączania ochrony. Podpis to osobny zakres.

## TASK-0975 — Fundament aplikacji i pakowanie

Samodzielne okno, lokalny JPEG, Forge ZIP, typed IPC, własny protokół zdjęć,
hardening, logi, polityka instalacji oraz obszar generatora mapy kodu.
Wejście: zaakceptowany plan i zgoda operatora; audyt na końcu zakresu. Odbiór pakietu na drugim komputerze
jest końcową bramką 0979; 0975 sprawdza paczkę lokalnie i zapisuje ten limit.
Szczegóły: [task 0975](../tasks/completed/0975-selector-desktop-foundation.md).

## TASK-0976 — Projekt, manifest i odzyskiwanie

Po 0975: wersjonowany projekt, recovery, backup, journal, lock oraz writer
JPEG/manifest. Czyste testy Node z awariami przed/po każdym kroku i restartem
procesu. Szczegóły: [task 0976](../tasks/completed/0976-selector-desktop-durability.md).

## TASK-0977 — Interfejs pełnej selekcji

Po 0976: własny UI nowych projektów, skróty, zakresy, nawigacja, undo,
restart, wznowienie, logs/output folder. Bez refaktoru webowych konsumentów.
Szczegóły: [task 0977](../tasks/completed/0977-selector-desktop-selection-ui.md).

## TASK-0979 — Pilotaż i odbiór wydania

Po 0977, niezależnie od 0978: wersja i SHA-256 ZIP, instrukcja, aktualizacja,
backup, odbiór rzeczywistej drogi dystrybucji na komputerze odbiorcy.
Nie raportować pilotażu jako zaliczonego bez dowodów operatora.
Szczegóły: [task 0979](../tasks/0979-selector-desktop-release-acceptance.md).

## TASK-0978 — Przejęcie starej sesji

Po części implementacyjnej 0979; polecenie pięciu tasków uruchomiło 0978. Operator-local v1/v2, checksummy źródła
i wybranych plików, preview i nowy projekt bez modyfikacji oryginału.
Brak dowodów lub różna tożsamość źródła blokują migrację. V1 wymaga jawnej
konfiguracji. Historyczny końcowy malejący v1 o semantyce niezgodnej z v2
jest odrzucany; nie zmieniamy ukrycie flagi zakończenia. Historia z wielokrotną
akceptacją tego samego źródła również wymaga odrębnego rozszerzenia, mimo
że stary parser tolerował taki zapis; GUI i obecny desktop blokują powtórki. Stary output nie
zawiera pełnej listy metadanych źródła: nie wolno na podstawie samej innej
checksummy twierdzić, że różni się wyłącznie mtime. Taki scenariusz wymaga
osobnego rozszerzenia. Szczegóły: [task 0978](../tasks/completed/0978-selector-desktop-legacy-adoption.md).

## Dokumentacja, audyt planu i odbiór

Plan, taski, requirements/architecture, README, TRACEABILITY i CURRENT_STATE
opisują plan i zweryfikowaną implementację na osobnej gałęzi. Nie oznaczają
wdrożenia do głównej aplikacji ani zaliczonego fizycznego pilotażu. D-545
zapisuje zaakceptowaną architekturę. Każdy task ma osobny commit i Outcome; lead
dopisuje wersję i pełny hash w kolejnym commicie zgodnie z AGENTS.md.

Operator przekazał [audyt Codex](../quality/OFFLINE_PHOTO_SELECTOR_PLAN_REVIEW_CODEX_20261011.md) z werdyktem REVISE. Uwagi uwzględniono:
konkretny manifest, semantyka Reviewera, brak refaktoru web UI, jawna
trwałość/security, początkowo odroczona migracja, osobny odbiór. Skorygowano twierdzenia
o zawsze dziewięciu planszach, dowodzie zmiany wyłącznie mtime i pewnej
blokadzie niepodpisanego EXE. Audyt Codex planu nie zastępuje końcowego audytu implementacji przez operatora. Wszystkie pięć części implementacyjnych przeszło testy zapisane w Outcome;
końcowy audyt i fizyczny odbiór0979 pozostają do wykonania przez operatora.

| Wymaganie | Task | Dowód odbioru |
|---|---|---|
| Start bez hosta/internetu | 0975, 0979 | Paczka na drugim komputerze |
| Zachowanie potwierdzonej pracy | 0976 | Awarie, recovery i nowy proces |
| Numeracja i podgląd | 0977 | Reguły, skróty i interakcje |
| Lokalne wyniki | 0976, 0979 | JPEG i manifest, brak uploadu |
| Granice dostępu | 0975, 0976 | Traversal, reparse i obce dane |
| Aktualizacja bez utraty pracy | 0979 | Aktualizacja, reboot i resume |
| Stare sesje | 0978 | Manifesty zgodne i konfliktowe |

Komendy istniejące: test/typecheck rdzenia, test/lint/typecheck Reviewera,
`npm run docs:check`, `npm run code-map:check`. Nowy workspace publikuje
test/lint/typecheck/build/package/make w 0975 i trafia do kontroli root.
Każdy krok ma jawny timeout; domyślnie do 120 s. Znany dłuższy build wymaga
uprzedniej informacji o czasie. Bez benchmarków, sztucznych wielkich korpusów,
restartu usług i operacji na zdjęciach użytkownika bez osobnego zlecenia.

Po wykonaniu taska porównać wszystkie kryteria, uruchomić właściwe testy,
zapisać osobny commit i aktualizację dokumentacji. Audyt całego zakresu
wykona operator po pięciu taskach. Fizyczny drugi komputer,
restart Windows i realna dystrybucja są bramkami operatora, których agent
nie zastępuje testem w swoim środowisku. Otwarte P0/P1 zatrzymują zakres.

## Aktualna finalizacja — 2026-10-12

Wszystkie rundy implementacji, w tym TASK-0984–0987, są wykonane na osobnej
gałęzi. Aktualna paczka to ZIP 0.1.3 z v1.7.337 /
`0b1ab3302df2119efb2519661e2f82b8bdf545df`.
[Plan finalizacji](OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md)
opisuje D-546, zgodną migrację i pełną retencję receiptów.
[Aktualne dowody](../quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md)
obejmują 262 testy desktopu, pięć wariantów finalnego release smoke,
rzeczywiste aktualizacje 0.1.0/0.1.2 do 0.1.3 i pomiar 15 000.
Wcześniejsze wyniki w tym planie są historyczne; nie nadpisano ich.
[Końcowy brief Claude](../quality/OFFLINE_PHOTO_SELECTOR_FINAL_CLAUDE_AUDIT_BRIEF_20261012.md)
jest gotowy do przekazania operatorowi. Audyt nowych zmian i fizyczny
odbiór TASK-0979 pozostają osobne; nie są zaliczone lokalnymi testami.

## Przypisanie modeli do zadań

Wykonawcy są dostępni. Audyt operatora odbywa się po całym zakresie; nie
jest bramką startu ani osobnego commita. Model Claude w tabeli jest zaleceniem
do tego przeglądu, nie zleceniem agentowi. TASK-0976 wymaga szczególnej oceny
trwałości. Niedostępnego modelu wykonawcy nie zastępujemy niejawnie.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0975 | gpt-6.1-sol | medium | Integracja, pakowanie, granice dostępu. | Operator na końcu; zalecany claude-sonnet-5-5 / medium |
| TASK-0976 | gpt-6.1-sol | high | Trwałość, recovery, idempotencja. | Operator na końcu; zalecany claude-sonnet-5-5 / high |
| TASK-0977 | gpt-6.1-sol | medium | Interfejs i semantyka selekcji. | Operator na końcu; zalecany claude-sonnet-5-5 / medium |
| TASK-0979 | gpt-6.1-sol | medium | Wydanie i odbiór użytkowy. | Operator na końcu; zalecany claude-sonnet-5-5 / medium |
| TASK-0978 | gpt-6.1-sol | high | Walidacja historycznych danych. | Operator na końcu; zalecany claude-sonnet-5-5 / medium |
