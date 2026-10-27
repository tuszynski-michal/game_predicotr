---
title: Architecture decision log — index
status: active
last_updated: 2026-10-23
---

# Decision Log

Indeks **30 najnowszych** decyzji. Pełne wpisy (kontekst, alternatywy,
konsekwencje) leżą w [decisions/DECISION_LOG_2026.md](decisions/DECISION_LOG_2026.md)
z nagłówkami `## D-NNN — …` (kotwice `#d-nnn-…`); starsze wiersze indeksu są w
[decisions/DECISION_INDEX_ARCHIVE.md](decisions/DECISION_INDEX_ARCHIVE.md).
Hierarchia źródeł prawdy (`AGENTS.md`) odnosi się do pełnych wpisów; indeks to
tylko ich skrót.

Reguły:

- Obowiązkowy odczyt startowy to ten plik. Starszej decyzji szukaj
  wyszukiwaniem, nie lekturą archiwum:
  `rg -n "<słowo|D-NNN>" ai_docs/process/DECISION_LOG.md ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`,
  a pełny wpis otwieraj przez kotwicę, gdy `Relevant docs` taska go wskazuje
  albo gdy trzeba ocenić sprzeczność.
- Nowa decyzja: pełny wpis na początku `decisions/DECISION_LOG_2026.md` i wiersz
  na górze tabeli poniżej; wiersze ponad 30 przenieś bez zmian na początek
  tabeli w `decisions/DECISION_INDEX_ARCHIVE.md`. Spójność i budżet (30 wierszy,
  12 000 B) sprawdza `npm run docs:check`.
- Numery D-416..D-429 oraz D-548 występują w dwóch torach (kolizja numeracji;
  D-548 to panel udostępniania `main` i doszkalanie V3 z gałęzi
  `codex/v3-grid-fine-tuning`); wiersze rozróżnia tytuł i kotwica.

## Indeks

| Nr | Tytuł | Status | Data | Jedno zdanie |
|---|---|---|---|---|
| [D-573](decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach) | Wyszukiwanie po kolejnych układach | accepted | 2026-10-24 | 1–4 spiny, ranking cykliczny, historia v2, wygrane od końca; od 2026-10-27 wzory przed szukaniem i podgląd +10 zdjęć. |
| [D-572](decisions/DECISION_LOG_2026.md#d-572--nazwa-folderu-wynikowego-selektora) | Nazwa folderu wynikowego selektora | accepted | 2026-10-23 | Nowe partie: gra aktualizacja pierwsza-ostatnia; stary outputRoot i nazwy JPEG bez zmian; zastępuje regułę folderu D-571. |
| [D-571](decisions/DECISION_LOG_2026.md#d-571--trwały-katalog-gier-i-aktualizacja-partii-selektora) | Trwały katalog gier i aktualizacja partii selektora | accepted | 2026-10-23 | Katalog niezależny od historii; aktualizacja a+cyfry lub z_a+cyfry w etykietach, bez zmiany nazw eksportu. |
| [D-570](decisions/DECISION_LOG_2026.md#d-570--nierozpoznane-pozycje-jako-wildcard-w-wyszukiwaniu-777a2) | Nierozpoznane pozycje jako wildcard w wyszukiwaniu 777a2 | accepted | 2026-10-23 | Tylko 777a2: brak dowodu daje punkt, nadal unknown; czerwony licznik w wynikach, bez zmiany wypłat. |
| [D-568](decisions/DECISION_LOG_2026.md#d-568--zachowanie-wygranych-sprzed-rozwinięcia-super-symbolu) | Zachowanie wygranych sprzed rozwinięcia super symbolu | accepted | 2026-10-21 | Większa wypłata per (linia, symbol), sztuki raz; próg rozwinięcia i bazowa plansza uruchamiająca bez zmian. |
| [D-567](decisions/DECISION_LOG_2026.md#d-567--edytowalny-kierunek-i-granica-500000-w-selektorze-windows) | Edytowalny kierunek i granica 500000 w selektorze Windows | accepted | 2026-10-21 | Jeden wybór folderu, wspólne kompaktowe przyciski, limit nowych zakresów i trwała zmiana kierunku dalszej numeracji. |
| [D-566](decisions/DECISION_LOG_2026.md#d-566--kolejka-masowej-weryfikacji-symboli) | Kolejka masowej weryfikacji symboli | accepted | 2026-10-19 | Wyjątek od D-551 pozwala kolejkować bulk za bulk; wykonanie pozostaje pojedyncze, konflikty z innymi typami bez zmian. |
| [D-565](decisions/DECISION_LOG_2026.md#d-565--tymczasowa-baza-wypłat-i-stawki-mumii) | Tymczasowa baza wypłat i stawki Mumii | accepted | 2026-10-19 | Tabela Mumii dotyczy 10 kredytów (1 zł); wyszukiwarka ma stawki 1/2/5/10/20 zł jako tymczasowy wyjątek w kodzie dla jednej gry, bez przeliczania historii. |
| [D-564](decisions/DECISION_LOG_2026.md#d-564--super-symbol-serii-definiowany-także-przez-odbiorcę-linku-udostępniania) | Super symbol serii definiowany także przez odbiorcę linku udostępniania | accepted | 2026-10-18 | Odbiorca linku otwiera serię z każdego znacznika supergry i definiuje super symbol przez cztery trasy publiczne z aktorem sesji; `seriesId` w markerach udostępnienia, panel zarządzania bez zmian. |
| [D-563](decisions/DECISION_LOG_2026.md#d-563--przycinanie-i-usuwanie-oryginałów-importów-oczekujących-na-przegląd) | Przycinanie i usuwanie oryginałów importów oczekujących na przegląd | accepted | 2026-10-18 | Import `completed` albo `waiting_for_review` kwalifikuje oryginał; aktywne, przerwane i anulowane importy wykluczają (`IMPORT_NOT_SETTLED`). |
| [D-562](decisions/DECISION_LOG_2026.md#d-562--przycięty-wariant-zarządzanego-oryginału) | Przycięty wariant zarządzanego oryginału | accepted | 2026-10-17 | Bezstratny crop JPEG z atestem obok pliku zastępuje usunięty oryginał; współrzędne i zatwierdzenia bez zmian, odczyt poza kadrem kończy się błędem. |
| [D-561](decisions/DECISION_LOG_2026.md#d-561--parity-eksportu-onnx-względna-do-wielkości-wyjścia) | Parity eksportu ONNX względna do wielkości wyjścia | accepted | 2026-10-16 | Różnica torch/ONNX dzielona przez max(1, moduł wyjścia torch): współrzędne w pikselach nie padają na szumie fp32, wyjścia jednostkowe bez zmian. |
| [D-560](decisions/DECISION_LOG_2026.md#d-560--wspólny-kandydat-geometrii-v3-kilku-gier) | Wspólny kandydat geometrii V3 kilku gier | accepted | 2026-10-16 | Jedna baza na TRAIN kilku gier z równą wagą gier i nagrań, przypięty plan bez aliasów kontrolnych, ocena na wszystkich kohortach treningu. |
| [D-559](decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów) | Ocena kandydata geometrii V3 per gra i most aktualności dowodów | accepted | 2026-10-16 | Raport v2 z miarami bazy i kandydata per gra, PASS tylko bez regresji w każdej grze, proof per gra z licznikiem notices blokuje nieaktualną publikację. |
| [D-558](decisions/DECISION_LOG_2026.md#d-558--trwały-trening-geometrii-v3-w-osobnym-lane-z-procesem-gpu) | Trwały trening geometrii V3 w osobnym lane z procesem GPU | accepted | 2026-10-16 | Lane i slot `grid_training`, nadzorca z bazą i trener GPU bez bazy, wznowienie po kroku, kandydat `not_evaluated` bez duplikatu. |
| [D-557](decisions/DECISION_LOG_2026.md#d-557--presety-treningu-geometrii-v3-dzierżawa-gpu-i-dopuszczenie-runu) | Presety treningu geometrii V3, dzierżawa GPU i dopuszczenie runu | accepted | 2026-10-16 | Wersjonowane presety z odciskiem, koszt kohorty, jedna dzierżawa GPU aplikacji, budżet bez odnowienia przy wznowieniu i smoke 50 kroków/120 s treningu. |
| [D-556](decisions/DECISION_LOG_2026.md#d-556--niezmienne-kohorty-geometrii-v3-i-aktualność-dowodów) | Niezmienne kohorty geometrii V3 i aktualność dowodów | accepted | 2026-10-16 | Exact human labels i24nodes, bounded snapshot/use/currentness; zachowana historia, nowe użycie usuniętego źródła zablokowane decyzją operatora. |
| [D-555](decisions/DECISION_LOG_2026.md#d-555--pomiar-jakości-v3-i-jawne-zatwierdzenie-niezmienionej-geometrii) | Pomiar jakości V3 i jawne zatwierdzenie niezmienionej geometrii | accepted | 2026-10-16 | Frozen baseline i9 pozycji, separate canonical approval bez recropu, symbols manual-only i forward permissions. |
| [D-554](decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3) | Nagrania i ochrona danych kontrolnych geometrii V3 | accepted | 2026-10-15 | Geometry-only aliasy i role nagrań, prywatne capability, dependent-only invalidation; bez operator runs. |
| [D-553](decisions/DECISION_LOG_2026.md#d-553--diagnostyka-pokrycia-v3-i-izolowany-odczyt-liczników) | Diagnostyka pokrycia V3 i izolowany odczyt liczników | accepted | 2026-10-14 | Opt-in spójny odczyt READ ONLY/RLS oraz odrzucony slot jako przyczyna braku; bez zmian danych. |
| [D-552](decisions/DECISION_LOG_2026.md#d-552--baza-i-wznowienie-planu-doszkalania-v3) | Baza i wznowienie planu doszkalania V3 | accepted | 2026-10-14 | Baza planu to main v1.7.360 / 171e23799ebdbee4ed4590a53376bf870c6741c2; worktree D:\game_predicotr\worktrees\v3-grid-fine-tuning, branch codex/v3-grid-fine-tuning. |
| [D-551](decisions/DECISION_LOG_2026.md#d-551--propozycje-dla-błędnej-siatki-v3) | Propozycje dla błędnej siatki V3 | accepted | 2026-10-14 | W zgodzie z D-462/D-543 ponowne rozpoznanie zgłoszonej Złej siatki tworzy trwałą propozycję i zdarzenia bez zmiany cropów lub zgłoszenia. |
| [D-550](decisions/DECISION_LOG_2026.md#d-550--akceptacja-silnika-v3-i-statusowy-backfill) | Akceptacja silnika V3 i statusowy backfill | accepted | 2026-10-14 | Doprecyzowanie D-484/D-541 zachowuje późniejsze wyjątki V3. |
| [D-549](decisions/DECISION_LOG_2026.md#d-549--wspólna-geometria-v3-i-domyślna-wersja) | Wspólna geometria V3 i domyślna wersja | accepted | 2026-10-14 | Rozszerzenie D-527 obejmuje wspólną geometrię i katalog; od TASK-1012 nowe preflighty V3 wybierają przypiętą wersję z assignment, a nie formatu. Serwerowy dowód oceny i invalidation nie przełączają assignment; stale blokuje nowe komendy. Nowa gra ma atomową rezerwację/transfer, fork-lineage i własny cold-start symboli. |
| [D-548](decisions/DECISION_LOG_2026.md#d-548--doszkalanie-geometrii-z-ręcznych-korekt-v3) | Doszkalanie geometrii z ręcznych korekt V3 | accepted | 2026-10-14 | Odrębny zakres D-480 dopuszcza aktualne geometrie zatwierdzone przez człowieka do TRAIN. |
| [D-548](decisions/DECISION_LOG_2026.md#d-548--panel-wyszukiwarki-wielu-gier-przez-link-bez-kodu) | Panel wyszukiwarki wielu gier przez link bez kodu | accepted | 2026-10-13 | Immutable chosen games, full search/corrections, capability link max 72h, shared tunnel; audit omitted and migration/main integration/cleanup explicitly approved 2026-10-16. |
| [D-547](decisions/DECISION_LOG_2026.md#d-547--selektor-windows-bez-limitu-zdjęć-i-wydanie-100) | Selektor Windows bez limitu zdjęć i wydanie 1.0.0 | accepted | 2026-10-13 | Brak limitu liczby zdjęć, stabilny układ i fullscreen, odbiór decyzją operatora, main oraz zachowanie artefaktów przed usunięciem worktree. |
| [D-546](decisions/DECISION_LOG_2026.md#d-546--finalizacja-i-zgodny-kompaktowy-zapis-selektora-windows) | Finalizacja i zgodny kompaktowy zapis selektora Windows | accepted | 2026-10-12 | Pełna runda0984–0987, brak resetu, mirrored ledger/head2/journal3 z migracją, wszystkie receipty, kontrolowany pomiar15000 i ZIP0.1.3; odbiór na końcu. |
| [D-545](decisions/DECISION_LOG_2026.md#d-545--lokalny-selektor-zdjęć-windows-dla-odbiorcy) | Lokalny selektor zdjęć Windows dla odbiorcy | accepted | 2026-10-11 | Electron ZIP, dane i projekt u odbiorcy, operator-local v2; pięć tasków wraz z0978 uruchomione przez operatora, audyt Claude na końcu i osobny odbiór urządzenia. |
| [D-544](decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) | Nowe gry 777 importują przez V3 z profilem `grid_profile_777_v2` | accepted | 2026-10-11 | każdy profil silnika siatek importuje przez ścieżkę neural z własnym modelem (777 v2 z laboratorium), V1.1 zostaje tylko dla starej 777 (rozszerza D-521). |
