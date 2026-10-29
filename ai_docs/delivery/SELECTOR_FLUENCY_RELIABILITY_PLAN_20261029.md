---
title: Płynność i niezawodny wybór zdjęć w Selektorze Windows
status: accepted
last_updated: 2026-10-29
---

# Selektor Windows — płynny podgląd i niezawodne F

## Status, zakres zgody i koszt

Rewizja 3. Operator 2026-10-29 zaakceptował cały plan TASK-1104–1107,
wykonanie kolejno, koszt 3–5 godzin, testy i gotowy ZIP Windows. Operator
zrezygnował ze wszystkich audytów Claude implementacji, tak jak wcześniej
z audytu TASK-1103. To rezygnacja, bez werdyktu PASS. Nie uruchamiamy prób
ponownego audytu. Zgoda nie obejmuje merge/push, usług, danych oryginalnych
ani zmian ochrony Windows. Zadania zamykamy osobno. Numery TASK-1104–1107
ponownie sprawdzono we wszystkich lokalnych gałęziach: wolne.

## Stan obecny: fakty, hipotezy i ograniczenia diagnozy

Baza: `main` / `1c9c13fd72503b8bbc06584a81f6f3a7945fb3c0`, aplikacja 1.0.3.
Dokumenty powstają na `codex/selector-reliability-plan`. Dwa wcześniejsze
usunięcia w `artifacts/v7-main-panel-entry-20261007/` i obcy worktree są
poza zakresem. Nie uruchamiano API, Admina, usług ani benchmarków.

Potwierdzone w kodzie:

| Obszar | Dowód | Skutek / zakres pewności |
|---|---|---|
| Ciche odrzucanie F | `renderer/App.tsx`: `keyboard`, `canAccept`, `execute`, `busyRef` | Podczas operacji lub dekodowania F nie trafia do native i nie zostaje zachowane. Odtworzone w izolowanej próbie komponentu z kontrolowaną odpowiedzią IPC. |
| Nawigacja czeka na zapis | `project/project-store.ts`: `execute` → `prepare` → `applyJournal` | Strzałka przechodzi przez journal, ledgery, heady, manifest i lease. Renderer czeka na zakończenie i blokuje następne polecenia. |
| Manifest zawiera kursor | `manifest/operator-local.ts`: `projectManifest` | `currentIndex` i `updatedAt` zmieniają się podczas nawigacji. Samo wyłączenie zapisu manifestu naruszyłoby obecny kontrakt. |
| Duża odpowiedź IPC | `native/project-controller.ts`: `snapshot` i `execute`; `contracts.ts`: `DesktopWorkspace` | Każda operacja buduje mapę całego źródła i zwraca `source.images`. Koszt zależy od liczby zdjęć, mimo zmiany jednej pozycji. |
| Podwójna ścieżka podglądu | `renderer/image-viewer.tsx`: `ImageViewer`; `main.ts`: protokół `selector-photo` | Detached `Image` jest dekodowany, potem JSX tworzy drugi `<img>` z tym samym URL; protokół ustawia `no-store`. Jest ryzyko ponownego odczytu/dekodowania. Faktyczną liczbę żądań trzeba zmierzyć testem, nie zakładać identycznego zachowania każdego Chromium. |
| Prefetch konkuruje z bieżącym zdjęciem | `ImageViewer`: pętla `manualPreviewWindow` | Do siedmiu obrazów jest uruchamianych bez priorytetu dla aktualnego. Rozmiar pamięci zależy od pikseli, nie wielkości pliku JPEG. |
| Integralność ma koszt | `ProjectStore.sourceChecksum`, `copyJpeg`, `verifyOutput` | Nowy accept odczytuje źródło do SHA przed journalem, ponownie przed kopią i podczas kopiowania. To istniejąca ochrona; ten plan jej nie usuwa. |

Próba z poprzedniej analizy: F podczas niezakończonej nawigacji wysłało tylko
`navigate`; F przed decode nie wysłało polecenia; F przy gotowym zdjęciu
wysłało jeden `accept`. Test używał atrap React/IPC, więc nie dowodzi zachowania
na komputerze odbiorcy. Istniejący test skrótów `desktop decision repeats…`
przeszedł. Pełnych testów aplikacji ani pomiarów FPS/latencji nie wykonano.

Hipoteza: połączenie oczekiwania na dysk, serializacji indeksu i pracy przy
JPEG-ach wyjaśnia przycięcia. Nie ustalono udziału CPU, dysku, antywirusa,
rozdzielczości zdjęć ani konfiguracji komputera odbiorcy. Nie deklarujemy
antywirusa przyczyną zgłoszenia i nie obiecujemy braku opóźnień na każdym dysku.

## Cel i proponowane reguły produktu

Widoczne zdjęcie ma reagować na nawigację bez oczekiwania na zakończenie
poprzedniej transakcji. Każde osobne F/Enter ma zakończyć się jednym trwałym
wyborem, widocznym oczekiwaniem albo jawnym komunikatem odrzucenia. Nigdy nie
wolno zapisać innego zdjęcia lub zakresu niż przypięte do tego naciśnięcia.

Poniższe reguły zaakceptował operator 2026-10-29. Właścicielami zachowania
są wymagania i architektura ręcznej selekcji; decyzja D-574 uzupełnia D-546/D-547
w zakresie interakcji i zamykania, bez zmiany trwałego formatu.

1. Rozdzielamy `displayedImageId` (bieżący zamiar użytkownika) od kursora
   potwierdzonego przez `ProjectStore`. Podgląd może wyprzedzać dysk, licznik
   wybranych i następny zakres nigdy nie wyprzedzają commita.
2. Jedna operacja native może trwać. Dodatkowo wolno przechować najwyżej jeden
   ostatni niewysłany cel nawigacji i jeden zamiar accept. Pośrednie cele
   strzałek można połączyć przed wysłaniem. Nie pomijamy żadnego wysłanego
   zapisu, żadnego wyboru ani receiptów. Powtarzanie strzałek jest dozwolone.
3. F przypina `{projectId, sourceId, imageId, rangeStart, direction,
   sequenceUpperBound}` oraz jeden `operationId`. Nie przypinamy numeru rewizji
   sprzed nawigacji jako oczekiwanej rewizji accept, ponieważ sama nawigacja
   zwiększa rewizję. Po zakończeniu wymaganej nawigacji porównujemy domenowy
   kontekst i aktualną rewizję, zanim wyślemy accept.
4. Gdy JPEG nie jest gotowy lub trwa nawigacja, F czeka na **ten sam** cel.
   Widoczny stan „Oczekuje na zapis” pojawia się od razu. Na czas tego zamiaru
   dalsza nawigacja, skip, undo, zakres i zmiana projektu są blokowane.
   Przycisk „Anuluj oczekiwanie” kasuje zamiar tylko przed wysłaniem accept.
   Gdy native już dostał accept, nie udajemy jego anulowania.
5. Po zakończeniu nawigacji do przypiętego celu i udanym decode wysyłamy accept
   dokładnie raz. `event.repeat` nigdy nie tworzy wyboru; kolejne F podczas
   oczekiwania/zapisu pokazuje ten sam stan, nie dopisuje kolejnego wyboru.
6. Timeout oczekiwania na nawigację/decode: 10 s. Niewysłany accept zostaje
   anulowany z informacją „Nie zapisano — podgląd nie jest gotowy. Spróbuj
   ponownie”. Timeout nie anuluje ani nie uznaje za zakończoną trwającej
   operacji native. Po wysłaniu accept wynik nie ma sztucznego limitu sukcesu:
   dłuższy zapis pokazuje trwającą pracę; błąd uruchamia obecne recovery.
7. Błąd decode, zmiana źródła, konflikt kontekstu lub utrata locka kasują
   niewysłany zamiar. Operacje native kończą się dotychczasowymi kodami błędów.
   Nie zamieniamy błędu w sukces i nie odblokowujemy kolejki przy nieznanym
   wyniku operacji. F w formularzu/input/select/button zachowuje obecne zasady.
8. Po utracie odpowiedzi accept interfejs blokuje nowe mutacje i próbuje
   snapshot. Jeśli ten sam projekt nadal działa, ponowienie używa **tego
   samego** `operationId` i identycznego polecenia; najwyżej jedna automatyczna
   próba, potem jawne wznowienie. Awaria snapshot również pozostawia widoczny
   błąd i blokadę, bez nieobsłużonego odrzucenia Promise.
9. Po sukcesie zachowujemy zachowanie desktopu potwierdzone
   `smoke-shortcuts.mjs`: następny zakres i następne zdjęcie o jedną pozycję,
   niezależnie od skoku strzałek. Nie przenosimy tu innej semantyki Reviewera.
10. Przy zamknięciu projektu/aplikacji kończymy wysłaną operację i utrwalamy
    ostatni cel nawigacji. Niewysłany accept wymaga jawnego anulowania albo
    dokończenia. Crash przed utrwaleniem podglądu może wrócić do ostatniego
    trwałego kursora; nie wolno zgłaszać tego jako utraty zatwierdzonego wyboru.
    Zamknięcie okna musi mieć typowany handshake main→renderer→main przed
    istniejącym `controller.close`: main ustawia closing, renderer wstrzymuje
    nowe wejście i rozlicza powyższy ogon, a main zwalnia lock dopiero po
    zgodnym potwierdzeniu. Timeout handshake 10 s nie wymusza zamknięcia;
    pozostawia okno z błędem i możliwością ponowienia. Wymuszone zakończenie
    procesu przez system jest scenariuszem crash/recovery, nie tym handshake.

## Architektura i granice optymalizacji

### Sterowanie interakcją

Proponowany czysty moduł `renderer/selection-intents.ts` opisze stany
`idle`, `navigating`, `waiting_to_accept`, `accepting`, `recovering`, `error`.
To nowe nazwy wewnętrzne UI, nie format projektu. Efekty IPC i dekodowanie
pozostają w adapterze React. Widoczny kursor zmienia się najwyżej raz na klatkę
przez `requestAnimationFrame`; delta następnego klawisza liczy się od ostatniego
zamiaru, nie od opóźnionego snapshotu. Spóźnione odpowiedzi nie cofają podglądu.
Przy zmianie celu od razu unieważniamy gotowość starego imageId i usuwamy stary
JPEG z hosta, dopóki nie można pokazać nowego; placeholder wskazuje nazwę
docelowego zdjęcia. F w takim stanie oznacza proponowaną jawną regułę czekania
na ten cel, nigdy zapis obrazu pozostawionego z poprzedniej pozycji.
Po F usuwamy niewysłany cel nawigacji inny niż przypięty i czekamy na zakończenie
już wysłanej operacji, następnie doprowadzamy trwały kursor do celu F.

Nie budujemy kolejki JPEG-ów ani nie przenosimy trwałych decyzji do RAM.
Oczekujący zamiar zajmuje O(1) metadanych i nie zawiera Blob/Buffer obrazu.
Enter i przycisk wyboru korzystają z tej samej maszyny stanów co F.

### Małe odpowiedzi native i stabilny indeks

`ProjectController.snapshot()` oraz create/open/resume/relink zachowają pełny
bootstrap. Proponowany `DesktopWorkspaceUpdate` zawiera skalary workspace,
`sourceId` i `acceptedImageIds`, ale **bez `source.images`**. Tylko `execute`
zwraca update. Zmiana przechodzi jednym pionem: `contracts.ts`, controller,
`main.ts`, `preload.ts`, adapter renderera i test rzeczywistego IPC.
Nie ma API HTTP ani zmian OpenAPI.

Renderer przyjmuje update tylko przy zgodnych `projectId`, `sourceId` oraz
monotonicznej rewizji. Nieznane źródło lub luka uniemożliwiająca odtworzenie
stanu wymagają pełnego snapshotu; do czasu zgodnego bootstrapu accept jest
zablokowany. Wyjście z projektu unieważnia wcześniejsze odpowiedzi.
Mapa imageId/path/ordinal jest budowana raz na instancję zweryfikowanego
SourceIndex w native i rendererze; wymiana/relink źródła ją unieważnia.
Nie skanujemy N źródeł ani nie kopiujemy N metadanych przy zwykłej nawigacji.
Lista acceptedImageIds pozostaje O(D); to jawny koszt, bez ukrytej obietnicy O(1).
Pełny bootstrap pozostaje O(N+D), pamięć indeksu O(N).

### Jeden zdekodowany obiekt na zdjęcie podglądu

`ImageViewer` będzie miał dedykowany pusty host DOM, do którego dołączany jest
ten sam `HTMLImageElement`, który został pobrany/dekodowany i jest w cache.
React zarządza hostem i etykietami; nie tworzy drugiego `<img>` z URL.
Obiekt migruje między cache a hostem zamiast pobierać zdjęcie drugi raz.
Aktualne zdjęcie ma pierwszeństwo przed prefetch. Prefetch jest uruchamiany
po gotowości bieżącego zdjęcia, najwyżej jeden dodatkowy decode naraz.

Okno pozostaje maksymalnie ±3. Dodajemy budżet 128 MiB szacowanych bitmap
(`naturalWidth * naturalHeight * 4`): usuwamy najdalsze nieaktywne elementy,
zanim uruchomimy kolejny prefetch. Bieżące zdjęcie jest jedynym wyjątkiem
od budżetu; pojedynczy duży JPEG może go przekroczyć, wtedy prefetch jest
wyłączony. To szacunek zasobu cache, nie twardy limit całego procesu Chromium.
Jednorazowy decode nieznanego wymiaru może chwilowo przekroczyć budżet;
po poznaniu wymiarów natychmiast usuwamy nadmiar. Nie deklarujemy limitu
szczytowego RAM. Szybka zmiana projektu zwalnia DOM i referencje do cache;
spóźniony decode nie może zaznaczyć innego imageId jako gotowego.

Kontrole `SourceRegistry.openImage`, brak cache HTTP (`no-store`), traversal,
reparse pointów i mtime pozostają. Nie zastępujemy aktualności pliku długim
cache HTTP. Nowy projekt z takim samym imageId nie dziedziczy starej bitmapy:
klucz cache to para sourceId/imageId. Zoom, obie osie scrolla i fullscreen
zachowują obecny kontrakt i dostają regresję.

### Dysk i bezpieczeństwo

Nie zmieniamy formatów head2/journal3/ledgerów/manifestu v2, retencji receiptów,
fsync, kolejności commita ani kontroli SHA/lock/lease. Nie usuwamy zapisu
manifestu z wysłanych nawigacji. Redukujemy liczbę **niewysłanych** pośrednich
celów nawigacji i pracę UI/IPC/preview. Przebudowa trwałego zapisu i redukcja
odczytów SHA wymagają osobnego dowodu, planu i zgody; nie są obejściem tutaj.

## Zadania w kolejności wykonania

### TASK-1103 — Plan i rozliczenie rezygnacji z audytu (bieżący zakres)

- **Goal:** dostarczyć kompletny plan oraz udokumentować próby dostępu Claude
  i jawną rezygnację operatora z audytu tego planu.
- **Dependencies:** AGENTS.md, PLAN_STANDARD.md i TASK_TEMPLATE.md przeczytane;
  diagnoza i granice zgody opisane powyżej.
- **Scope:** niniejszy plan, plik `tasks/completed/1103-selector-fluency-plan.md`, katalog
  dokumentów, CURRENT_STATE i zapis diagnostyczny. Bez kodu aplikacji.
- **Acceptance:** zapis rezygnacji operatora z audytu zamiast niezależnego
  raportu; docs:check PASS; zakres implementacji i koszt przedstawione do
  akceptacji. Nie ma znalezisk audytora, bo nie wykonał on przeglądu.
  Nie nazywamy samoprzeglądu audytem Claude ani nie deklarujemy PASS audytu.
- **Verification:** porównanie planu z wymaganiami, architekturą, mapą kodu,
  rzeczywistymi skryptami i szablonem taska; `npm run docs:check` (120 s).
- **Outcome:** w pliku taska i odnośnikach z sekcji audytu poniżej.

### TASK-1104 — Płynna nawigacja i niezawodne F

- **Status:** done; `tasks/completed/1104-selector-selection-intents.md`, v1.7.496.
- **Goal:** usunąć ciche gubienie F i zależność odświeżania podglądu od dysku,
  bez zmiany numeracji i momentu trwałego potwierdzenia.
- **Dependencies:** zaakceptowany plan i koszt; zapis proponowanych reguł UI
  w wymaganiach/architekturze oraz odpowiedniej nowej decyzji, jeśli konieczna.
- **Recommended execution:** `gpt-6.1-sol`, `high`; stan asynchroniczny i ryzyko
  przypisania złego JPEG-a wymagają analizy przejść. Audyt `claude-fable-5-1`,
  `high`; eskalacja przy niejednoznacznym celu F lub recovery.
- **Relevant docs:** AGENTS.md, wymagania i architektura ręcznej selekcji,
  D-545/546/547 (linki niżej), niniejsze reguły produktu i sterowania.
- **Expected files:** istniejące `renderer/App.tsx` (`run`, `execute`, keyboard),
  `renderer/desktop-shortcuts.ts`, `scripts/smoke-shortcuts.mjs`,
  `test/renderer-contracts.test.mjs`, `main.ts`, `preload.ts`, `contracts.ts`
  i `native/desktop-lifecycle.ts` (typowany handshake zamykania z walidacją
  nadawcy i projektu); proponowane `renderer/selection-intents.ts`,
  `test/selection-intents.test.mjs` i `scripts/smoke-fluency.mjs`.
- **Technical notes:** stan widoczny i trwały zgodnie z regułami 1–10; native
  zachowuje pojedynczy writer i dotychczasowy `ExecuteRequest`/operationId.
  Kontrolowane opóźnienie odpowiedzi w teście nie może opóźniać ani modyfikować
  prawdziwych danych operatora. Zmiany `run` nie maskują błędu snapshot.
- **Acceptance criteria:** każdy nowy F jest rozliczony; najwyżej jeden zamiar
  accept, jeden writer i jeden niewysłany cel; podczas opóźnionego native
  podgląd cached reaguje niezależnie; nie zmienia się zakres przed commitem.
- **Test cases:** strzałka→F przed odpowiedzią, F przed decode, szybkie zmiany
  kierunku/skoku, stale odpowiedzi, przytrzymanie F, podwójne F, klik/Enter,
  uszkodzony JPEG, timeout oczekiwania, zmiana projektu i zakresu, anulowanie
  przed/po dispatch, błąd oraz utrata odpowiedzi, jeden operationId po retry,
  crash po commicie przed odpowiedzią i wznowienie w nowym procesie, zamknięcie
  z niewysłanym celem i oczekującym F. Poprzedni zaakceptowany JPEG nigdy nie
  jest ponownie wybrany dla następnego zakresu.
- **Verification:** test modułu intencji i renderer-contracts (120 s), lint i
  typecheck (każde 120 s), `selector:build` (120 s), nowy smoke na lokalnym
  buildzie (120 s), istniejący smoke shortcuts (120 s). Audyt pominięty decyzją operatora 2026-10-29.
- **Out of scope / risks:** nie tworzymy masowej kolejki wyborów i nie
  przyspieszamy dysku przez pominięcie trwałości. Zimny JPEG nadal wymaga decode.

### TASK-1105 — Mała aktualizacja workspace przez IPC

- **Status:** done; `tasks/completed/1105-selector-workspace-updates.md`, v1.7.498.
- **Goal:** zwykły execute nie przesyła pełnego N zdjęć i nie buduje ponownie
  indeksu w warstwie controller/renderer. Istniejące liniowe odczyty inventory
  wewnątrz ProjectStore i projectManifest nie są objęte obietnicą O(1).
- **Dependencies:** TASK-1104 i zaakceptowany kontrakt update z sekcji architektury.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; skończony pion kontraktu;
  audyt `claude-fable-5-1`, `medium`. Eskalacja do high przy zmianie recovery.
- **Relevant docs:** kontrakt i reguły intencji tego planu, architektura selekcji.
- **Expected files:** `src/contracts.ts` (`SelectorBridge`, nowy
  `DesktopWorkspaceUpdate`), `native/project-controller.ts` (`snapshot`,
  `execute`, `refreshSource`), `main.ts`, `preload.ts`, `renderer/App.tsx`,
  `test/native-checks.test.mjs`, `test/start-resume.test.mjs`; proponowany
  `test/workspace-updates.test.mjs`. Istniejące testy korzystające z wyniku
  controller.execute trzeba jawnie przenieść na nowy kontrakt.
- **Acceptance criteria:** bootstrap pełny, execute bez source.images; sourceId
  zgodne; odrzucenie starej odpowiedzi po zmianie projektu; indeks imageId/path/
  ordinal odtwarzany tylko przy zmianie SourceIndex; pełny snapshot jest fallback.
- **Test cases:** execute round trip przez prawdziwe preload/IPC; nawigacja,
  accept, undo, range, błąd i retry; brak inventory/receiptów/źródłowych ścieżek
  absolutnych w delta; niezgodne sourceId i projectId, starsza rewizja, relink,
  puste źródło, close/reopen i dwie instancje renderera z różnym bootstrapem.
  W teście rozmiar/kształt update nie zależy od N zdjęć przy stałym D decyzji;
  użyć małych istniejących fixture'ów, bez testów obciążeniowych.
- **Verification:** celowane testy kontraktu/controller (120 s na polecenie),
  lint/typecheck i build (120 s każde), smoke TASK-1104 po przebudowie;
  aktualizacja mapy kodu, niezależny audyt i commit.
- **Out of scope / risks:** acceptedImageIds nadal ma koszt O(D). Nie zmieniamy
  API HTTP, modeli bazy ani publicznego kontraktu Reviewera.

### TASK-1106 — Priorytet bieżącego zdjęcia i jeden obiekt podglądu

- **Status:** accepted; plik taska materializowany przy rozpoczęciu.
- **Goal:** jeden odczyt protokołu na cache miss podglądu i brak drugiego
  `<img>` dla tego samego cache entry; kontrolowana praca prefetch.
- **Dependencies:** TASK-1104–1105; reguły preview i pamięci z tego planu.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; ograniczona zmiana widoku,
  audyt `claude-fable-5-1`, `medium`; eskalacja przy naruszeniu aktualności plików.
- **Relevant docs:** architektura selekcji, reguły preview i intencji tego planu.
- **Expected files:** `renderer/image-viewer.tsx` (`ImageViewer`), istniejący
  arkusz `renderer/style.css`; proponowany
  `renderer/preview-cache.ts` i `test/preview-cache.test.mjs`;
  rozszerzenie `scripts/smoke-fluency.mjs`. `main.ts` tylko gdy konieczny
  obserwowalny licznik testowy; bez osłabiania protokołu i bezpieczeństwa.
- **Acceptance criteria:** aktywny JPEG dekodowany przed sąsiadami; najwyżej
  siedem cache entries i jeden decode prefetch; budżet bitmap/wyjątek aktywnego
  zdjęcia opisane wyżej; ten sam obiekt DOM trafia do widoku; zero nowych żądań
  JPEG przy nawigacji do zdekodowanego cache hit w niezmienionym źródle.
- **Test cases:** cache miss/hit z licznikiem faktycznych żądań protokołu,
  szybkie ± i zmiana projektu podczas decode, błąd JPEG i odczytu, jeden bardzo
  duży obraz, wyparcie cache, zamknięcie, zoom 100–3000%, scroll/fullscreen,
  relink i ponowne otwarcie zmienionego pliku. Błąd nie ustawia ready dla
  niewłaściwego id; wybór nadal używa pełnej świeżej kontroli SHA.
- **Verification:** test cache (120 s), lint/typecheck/build (120 s każde),
  smoke fluency i shortcuts (120 s każde), aktualizacja mapy kodu, audyt i commit.
- **Out of scope / risks:** brak miniaturek na dysku, zmiany JPEG, cropów,
  cache HTTP i znoszenia kontroli SourceRegistry. Dekodowanie bardzo dużego
  obrazu nadal zużywa RAM/CPU; zwolnienie pamięci przez Chromium nie jest
  synchroniczną gwarancją zwolnienia RSS procesu.

### TASK-1107 — Dowody płynności, diagnostyka i sprawdzona paczka

- **Status:** accepted; plik taska materializowany przy rozpoczęciu.
- **Goal:** pokazać brak zgubionych wyborów w realnym Electronie, zakres
  poprawy na istniejących zdjęciach i zgodne wznowienie z finalnego ZIP.
- **Dependencies:** TASK-1104–1106 po testach/audytach/commitach; osobna zgoda
  kosztowa na wydanie; dobór niezmienianych zdjęć do ograniczonego odbioru.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; audyt dowodów i wydania
  `claude-fable-5-1`, `high`; nie utożsamiać pomiaru z gwarancją dla odbiorcy.
- **Relevant docs:** niniejszy plan, `guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`,
  `quality/SELECTOR_OUTPUT_FOLDER_1_0_3_20261023.md` (wcześniejszy kontrakt wydania).
- **Expected files:** `native/diagnostic-log.ts` (`DiagnosticMetadata`),
  `main.ts` (handle), `scripts/smoke-fluency.mjs`, `scripts/smoke-release.mjs`
  (nowa jawna flaga smoke), package.json i lockfile przy podbiciu wersji,
  instrukcja operatora, nowy raport jakości i artefakty nowego wydania.
- **Technical notes:** pomiar czasu wejście→zmiana widoku, decode, IPC,
  native write i potwierdzenie, liczba żądań JPEG i wielkość payloadu.
  Timingi są agregowane w ograniczonej pamięci i zapisywane po serii/na żądanie;
  brak fsync/logowania każdego scrolla/klawisza i brak ścieżek zdjęć w logu.
  Diagnostyka nie zmienia sukcesu/błędu operacji. Raport poda wersję, komputer,
  dysk, ochronę, liczbę/wymiary JPEG, cold/warm, medianę i p95, maksimum oraz
  liczbę próbek. Minimum 30 nawigacji i 10 wyborów na kopiach z istniejącej
  małej partii to odbiór, nie test obciążeniowy; bez generowania dużego korpusu.
- **Acceptance criteria:** przy sztucznie opóźnionej odpowiedzi IPC o 500 ms
  cache hit jest wyświetlany przed jej zwolnieniem; po zaakceptowaniu zakresu
  każdy JPEG/manifest/licznik zgadza się po nowym procesie; zero zagubionych
  F i zero błędnych imageId/range w scenariuszach kontrolowanych.
  Cel lokalnego warm preview: p95 ≤ 50 ms wejście→paint na opisanej maszynie,
  bez obietnicy czasu zapisu zależnego od dysku. Przekroczenie celu wymaga
  analizy śladu i decyzji operatora, nie ukrycia próbek lub rozszerzenia zakresu.
- **Test cases:** finalny rozpakowany ZIP, szybka sekwencja strzałki/F/Enter,
  obie numeracje, skoki 1/20, zakres końcowy 500000, uszkodzony plik, konflikt
  wyniku, utrata odpowiedzi, crash/wznowienie, stary projekt z wydania 1.0.3.
- **Verification:** testy zmienionych pionów → lint/typecheck → pełny zestaw
  selektora w grupach z `--test-concurrency=1`, każda grupa ≤120 s; żadnego
  drugiego runnera, jeśli pierwszy jeszcze działa. Build ≤120 s; znane make
  ≤300 s po uprzedzeniu; SHA-256/metadata/asar i smoke finalnego ZIP ≤120 s
  na wariant. Zachować stare ZIP-y; nowa wersja dopiero z historii wydań.
- **Out of scope / risks:** brak gwarancji braku wszystkich przycięć na innym
  sprzęcie. Fizyczny restart Windows i odbiór na komputerze zgłaszającego mają
  osobny wynik `pending`, dopóki operator ich nie wykona.

## Antywirus: pomiar i granice

Nie projektujemy „niezależności od antywirusa”. Odczyt i zapis podlegają ochronie
Windows lub produktu odbiorcy. Optymalizacje ograniczają zbędne otwarcia
plików i ilość pracy aplikacji, ale nie omijają ochrony.

W TASK-1107 instrukcja zbiera nazwę i wersję antywirusa, rodzaj dysku oraz
lokalność folderów. Dla Defendera opisuje opcjonalne, wykonywane przez operatora
krótkie nagranie `New-MpPerformanceRecording` i analizę
`Get-MpPerformanceReport -Path <nagranie.etl> -TopFiles 10 -TopProcesses 10`.
Nagranie uruchamia operator z wymaganymi uprawnieniami, kończy po krótkiej
serii i nie przekracza 60 s; zanim powstanie komenda automatyczna, należy
sprawdzić parametry lokalnej wersji (`Get-Command ... -Syntax`) i dostępność
trybu z limitem czasu. Brak cmdletu/uprawnień daje „niezweryfikowane”, nie PASS.
Dla innego antywirusa potrzebna jest jego dokumentacja i konfiguracja odbiorcy.

Nie dodajemy wyjątków, nie wyłączamy ochrony, nie wykluczamy procesu ani całego
dysku. Podpis EXE nie jest obietnicą pomijania skanowania. Ewentualna zmiana
polityki ochrony wymaga osobnego pomiaru, oceny ryzyka i zgody operatora.

Źródła Microsoft sprawdzone 2026-10-29:
[analizator i jego ograniczenia](https://learn.microsoft.com/en-us/defender-endpoint/performance-analyzer-reference),
[wyjątki i ograniczenia ochrony](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/virus-and-threat-protection-in-the-windows-security-app).

## Pokrycie wymagań i odbiór całości

| Wymaganie | Task | Test / dowód |
|---|---|---|
| F nie znika i wybiera właściwe zdjęcie/zakres | 1104, 1107 | deterministyczne opóźnienia, pinned intent, retry tego samego id, finalny ZIP |
| Płynne strzałki bez czekania na dysk | 1104, 1107 | ostatni zamiar w klatce, max jedna operacja, cached paint przed odpowiedzią |
| Brak kopiowania listy N zdjęć co klik | 1105 | payload/update, indeks raz na sourceId, test prawdziwego IPC |
| Mało odczytów i kontrolowany prefetch | 1106 | licznik protokołu, ten sam DOM, limity entries/decode i estymata bitmap |
| Bez utraty trwałości i starszych projektów | 1104–1107 | crash/nowy proces, receipty, zakresy, manifest i SHA JPEG |
| Antywirus bez obchodzenia ochrony | 1107 | instrukcja, pomiar odbiorcy lub jawne niezweryfikowane |
| Niezależne sprawdzenie | 1103–1107 | raport Claude, P0/P1 rozliczone przed commitami |

Polecenia istniejące, sprawdzone w package.json (z repo root):

```powershell
npm run test:ui --workspace @game-predictor/selector-desktop
npm run lint --workspace @game-predictor/selector-desktop
npm run typecheck --workspace @game-predictor/selector-desktop
npm run selector:build
npm run selector:make
npm run smoke:release:shortcuts --workspace @game-predictor/selector-desktop
npm run smoke:release:workflow --workspace @game-predictor/selector-desktop
npm run docs:check
npm run code-map:check
```

Każde skończone polecenie uruchamiać kontrolowanym procesem z timeoutem z opisu
taska, z zakończeniem wyłącznie własnego drzewa po przekroczeniu. Nowe testy
node: z `apps/selector-desktop`, `node --experimental-strip-types --test
test/<proponowany-plik>.test.mjs` (120 s); smoke fluency jest proponowanym,
jeszcze nieistniejącym skryptem. Testy planowane nie są wynikami wykonania.

Przed każdym taskiem odczytać jego plik i właściwe fragmenty planu. Taski
wykonywać kolejno; zamykać osobno przez skill task-close z Outcome, audytem
i commitem. Bez etapów polecenie jednego taska nie uruchamia następnych.
Merge/push i dystrybucja paczki wymagają osobnej zgody. Plan nie zmienia usług,
bazy, oryginałów zdjęć ani ustawień Windows. Brak nowej zależności runtime.

Relevant docs wspólne:

- `ai_docs/process/DEFINITION_OF_DONE.md`.
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`.
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`.
- [D-545](../process/decisions/DECISION_LOG_2026.md#d-545--lokalny-selektor-zdjęć-windows-dla-odbiorcy).
- [D-546](../process/decisions/DECISION_LOG_2026.md#d-546--finalizacja-i-zgodny-kompaktowy-zapis-selektora-windows).
- [D-547](../process/decisions/DECISION_LOG_2026.md#d-547--selektor-windows-bez-limitu-zdjęć-i-wydanie-100).

## Audyt planu i niewiadome

**Audyt TASK-1103 pominięty decyzją operatora 2026-10-29** („Kontynuuj bez
audytu”). Nie ma raportu ani werdyktu Claude. Nie deklarujemy niezależnego
PASS. Wykonawca przeprowadził jedynie własną kontrolę spójności dokumentów.

Sprawdzenie konta wykazało zgodny identyfikator konta CLI i aplikacji desktop,
subskrypcję Max i brak nadpisujących zmiennych konta/API w procesie oraz
ustawieniach użytkownika i projektu. Cache modeli wskazywał Fable 5.1.
Osobna krótka próba `claude-fable-5-1` zakończyła się kodem 1 i komunikatem
o wyłączeniu dostępu subskrypcji do Code przez organizację. Nie uzyskano
odpowiedzi modelu; samo znalezienie go na liście nie dowodzi dostępności.
Nie wpisywano poświadczeń, nie zmieniano konta ani polityki organizacji.
Zapis diagnostyczny i decyzja operatora:
[TASK-1103_CLAUDE_AUDIT_BLOCKER.md](../quality/TASK-1103_CLAUDE_AUDIT_BLOCKER.md).
Historyczny brief `artifacts/audits/TASK-1103_BRIEF_claude.md` nie jest raportem
i nie opisuje końcowej rewizji 2. Nie ponawiamy audytu po rezygnacji operatora.
Konfiguracje Codex poniżej są rekomendacjami z listy modeli narzędzia sesji;
nie są odczytem identyfikatora modelu aktualnej rozmowy ani zmianą modelu.
Aktualizacja 2026-10-29: operator jawnie zrezygnował również ze wszystkich
audytów implementacyjnych TASK-1104–1107. Historyczne propozycje audytów
w opisach tasków powyżej są zastąpione tą decyzją i końcową tabelą.

Niewiadome odbiorcze: wersja EXE u zgłaszającego, liczba i rozdzielczość JPEG,
SSD/HDD, produkt ochrony, miejsce źródła/projektu/wyniku oraz ślad opóźnienia.
Nie blokują opracowania planu; blokują stwierdzenie przyczyny na urządzeniu
odbiorcy i obietnicę konkretnego przyspieszenia. Przekroczenie kosztu, zmiana
formatu projektu lub niewykonalny cel p95 zatrzymują zależną pracę do decyzji.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1103 | gpt-6.1-sol | high | Plan obejmuje współbieżność UI, trwałość i granice ochrony. Rekomendacja dla wykonania planowania; nie identyfikacja modelu rozmowy. | Nie; operator 2026-10-29 zrezygnował z audytu planu po nieudanej próbie Fable. |
| TASK-1104 | gpt-6.1-sol | high | Maszyna intencji musi zachować tożsamość JPEG-a, zakres i idempotencję mimo opóźnień i crasha. | Nie; operator 2026-10-29 zrezygnował z audytów implementacji. |
| TASK-1105 | gpt-6.1-sol | medium | Skończony pion IPC i cache indeksu; przy zmianie recovery ponowna analiza na high. | Nie; operator 2026-10-29 zrezygnował z audytów implementacji. |
| TASK-1106 | gpt-6.1-sol | medium | Ograniczony cache bitmap i cykl życia DOM; przy naruszeniu aktualności plików eskalacja na high. | Nie; operator 2026-10-29 zrezygnował z audytów implementacji. |
| TASK-1107 | gpt-6.1-sol | medium | Odbiór, diagnostyka i weryfikacja istniejącego procesu wydania. | Nie; operator 2026-10-29 zrezygnował z audytów implementacji. |
