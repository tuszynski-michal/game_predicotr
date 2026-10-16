---
title: Architecture decision log — index
status: active
last_updated: 2026-10-16
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
- Numery D-416..D-429 występują w dwóch torach (kolizja numeracji); wiersze
  rozróżnia tytuł i kotwica.

## Indeks

| Nr | Tytuł | Status | Data | Jedno zdanie |
|---|---|---|---|---|
| [D-547](decisions/DECISION_LOG_2026.md#d-547--selektor-windows-bez-limitu-zdjęć-i-wydanie-100) | Selektor Windows bez limitu zdjęć i wydanie 1.0.0 | accepted | 2026-10-13 | Brak limitu liczby zdjęć, stabilny układ i fullscreen, odbiór decyzją operatora, main oraz zachowanie artefaktów przed usunięciem worktree. |
| [D-546](decisions/DECISION_LOG_2026.md#d-546--finalizacja-i-zgodny-kompaktowy-zapis-selektora-windows) | Finalizacja i zgodny kompaktowy zapis selektora Windows | accepted | 2026-10-12 | Pełna runda0984–0987, brak resetu, mirrored ledger/head2/journal3 z migracją, wszystkie receipty, kontrolowany pomiar15000 i ZIP0.1.3; odbiór na końcu. |
| [D-545](decisions/DECISION_LOG_2026.md#d-545--lokalny-selektor-zdjęć-windows-dla-odbiorcy) | Lokalny selektor zdjęć Windows dla odbiorcy | accepted | 2026-10-11 | Electron ZIP, dane i projekt u odbiorcy, operator-local v2; pięć tasków wraz z0978 uruchomione przez operatora, audyt Claude na końcu i osobny odbiór urządzenia. |
| [D-544](decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) | Nowe gry 777 importują przez V3 z profilem `grid_profile_777_v2` | accepted | 2026-10-11 | każdy profil silnika siatek importuje przez ścieżkę neural z własnym modelem (777 v2 z laboratorium), V1.1 zostaje tylko dla starej 777 (rozszerza D-521). |
| [D-543](decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) | Odrzucanie przyciętych plansz po imporcie i przejęcie sekwencji przez zdjęcie zastępcze | accepted | 2026-10-10 | odrzucony slot lub plansza czeka na zamiennik; nowe zdjęcie przejmuje tylko sekwencje odrzucone albo bez właściciela, żywa pozycja `pending` innego zdjęcia zostaje (zmienia D-238). |
| [D-542](decisions/DECISION_LOG_2026.md#d-542--cofnięcie-ostatniej-ręcznej-korekty-cięcia-siatki) | Cofnięcie ostatniej ręcznej korekty cięcia siatki | accepted | 2026-10-10 | tylko najnowsza korekta planszy, fail-closed, migawka audytu przy usuwaniu wierszy slotu (zmienia D-462), migracja `0154`. |
| [D-541](decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) | Lokalny Reviewer pracuje w zakresie gry i pokazuje realne braki geometrii zdjęć | accepted | 2026-10-10 | lokalny Reviewer ma zakładki „Do korekty” i „Braki zdjęć” (realne braki D-484), „Siatka niepotwierdzona” zostaje licznikiem w Adminie, UI wyjątków bramki usunięte z Admina. |
| [D-540](decisions/DECISION_LOG_2026.md#d-540--przeniesienie-aplikacji-i-bazy-na-dysk-d) | Przeniesienie aplikacji i bazy na dysk D | accepted | 2026-10-10 | aplikacja z D, baza z obrazem dysku Docker Desktop, kopie i bramki przełączenia według planu DISK_D. |
| [D-539](decisions/DECISION_LOG_2026.md#d-539--wybór-maszyny-na-widoku-punktu) | Wybór maszyny na widoku punktu | accepted | 2026-10-09 | Punkt otwiera widok; maszyna pozostaje podświetlonym wyborem na tej samej liście. |
| [D-538](decisions/DECISION_LOG_2026.md#d-538--minimalistyczny-panel-administracyjny-i-jawne-usuwanie-zakresu) | Minimalistyczny Panel Administracyjny i jawne usuwanie zakresu | accepted | 2026-10-09 | Hierarchical compact navigation, explicit bound-preview scope deletion, restored saves; import of panel D-536. |
| [D-537](decisions/DECISION_LOG_2026.md#d-537--wypłata-planszy-w-serii-supergry-wynik-prowizoryczny-i-koszt-per-pozycja) | Wypłata planszy w serii supergry, wynik prowizoryczny i koszt per pozycja | accepted | 2026-10-09 | plansza na pozycji objętej opublikowaną serią supergry jako jej spin jest liczona oceną planszy serii… |
| [D-536](decisions/DECISION_LOG_2026.md#d-536--serie-supergry-manifest-v6-licznik-wejścia-i-generacje) | Serie supergry: manifest v6, licznik wejścia i generacje | accepted | 2026-10-09 | serie supergry są danymi pochodnymi wyprowadzanymi z komórek pociętych plansz z przypisanym symbolem… |
| [D-535](decisions/DECISION_LOG_2026.md#d-535--gra-mumie-wild-symbol-uruchamiający-supergrę-i-rodzaj-supergry-wild-super-spins) | Gra Mumie: Wild, symbol uruchamiający supergrę i rodzaj supergry „Wild super spins” | accepted | 2026-10-08 | dotychczasowy „Joker” nazywa się w UI i dokumentach „Wild” (kolumna symbols.is_wildcard zostaje). |
| [D-534](decisions/DECISION_LOG_2026.md#d-534--image-import-resumption-uses-the-hard-reserve-not-the-gc-target) | Image import resumption uses the hard reserve, not the GC target | accepted | 2026-10-07 | source ingestion and in-flight image pipeline checks use the configured hard reserve in every job stage,… |
| [D-533](decisions/DECISION_LOG_2026.md#d-533--pointsmachines-panel-with-durable-stake-saves-and-whole-panel-links) | Points/machines panel with durable stake saves and whole-panel links | accepted | 2026-10-07 | add Panel Administracyjny with points (name/city/street), named machines and editable active-game assignments. |
| [D-532](decisions/DECISION_LOG_2026.md#d-532--integrate-the-complete-v7-code-into-the-main-vision-lab-branch) | Integrate the complete V7 code into the main vision lab branch | accepted | 2026-10-07 | transplant the V7 product and tests from calibration HEAD b087ad08b62992c54f5e26191e6408d287b64273 onto… |
| [D-531](decisions/DECISION_LOG_2026.md#d-531--main-admin-offers-a-local-entry-to-the-approved-v7-test-panel) | Main Admin offers a local entry to the approved V7 test panel | accepted | 2026-10-07 | when main V7 remains blocked and selection is enabled, offer ordinary local navigation to the separate V7… |
| [D-530](decisions/DECISION_LOG_2026.md#d-530--managed-image-operations-retain-five-gib-after-estimation) | managed image operations retain five GiB after estimation | accepted | 2026-10-07 | the default hard reserve for managed image writes is 5 GiB, measured after the existing conservative… |
| [D-529](decisions/DECISION_LOG_2026.md#d-529--metadata-overview-precedes-exact-training-cohort-preparation) | metadata overview precedes exact training cohort preparation | accepted | 2026-10-07 | page entry reads current-owner logical symbol approvals and registry metadata through the existing… |
| [D-528](decisions/DECISION_LOG_2026.md#d-528--one-explicit-save-and-approve-action-in-symbol-verification) | one explicit save-and-approve action in symbol verification | accepted | 2026-10-07 | replace the separate approve and apply-change buttons with Symbol do zatwierdzenia and Zapisz i zatwierdź. |
| [D-527](decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) | shared model families and published game creation catalog | accepted | 2026-10-07 | a model family is independent of a game record. |
| [D-526](decisions/DECISION_LOG_2026.md#d-526--neural-proposals-are-not-mandatory-correction-shared-laboratory-direction) | neural proposals are not mandatory correction; shared Laboratory direction | accepted | 2026-10-07 | neural review source counts describe unapproved proposals, not rejected geometry or mandatory manual work. |
| [D-525](decisions/DECISION_LOG_2026.md#d-525--grid-diagnostics-belong-to-correction-not-import) | grid diagnostics belong to correction, not import | accepted | 2026-10-07 | move the existing whole-image grid diagnostics out of Import plansz into Korekta cięcia siatki, alongside… |
| [D-524](decisions/DECISION_LOG_2026.md#d-524--show-the-actual-neural-import-and-retire-old-ui-choices) | show the actual neural import and retire old UI choices | accepted | 2026-10-06 | Mumie's existing game profile identifies V3 in Admin. |
| [D-523](decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification) | operational neural crops and recoverable symbol verification | accepted | 2026-10-06 | new neural imports pin neural-auto-crop-v1. A bound full structurally valid 24-node lattice can produce… |
| [D-522](decisions/DECISION_LOG_2026.md#d-522--current-manual-neural-slot-approval-permits-its-own-symbol-save) | current manual neural slot approval permits its own symbol save | accepted | 2026-10-06 | a bound neural slot retaining its proposal checksum and exact 24-node lattice, saved as manual_v1 with the… |
| [D-521](decisions/DECISION_LOG_2026.md#d-521--explicit-mumie-rgb-and-neural-folder-pilot) | explicit Mumie RGB and neural folder pilot | accepted | 2026-10-06 | selection of the recommended earlier RGB and request to connect the engine to main-app folder uploads,… |
| [D-520](decisions/DECISION_LOG_2026.md#d-520--rgb-v2-jako-źródło-nowej-wersji-predykcji-oczekujących-komórek) | RGB v2 jako źródło nowej wersji predykcji oczekujących komórek | accepted | 2026-10-05 | oczekujące komórki z przypisaniem od modelu dostają symbol wybrany metodą RGB v2 z D-494 (argmax zamrożonej… |
| [D-506](decisions/DECISION_LOG_2026.md#d-506--explicit-larger-local-rgb-experiment) | explicit larger local RGB experiment | accepted | 2026-10-06 | autonomous larger-training instruction and accepted TASK-0871–0873 plan. |
| [D-505](decisions/DECISION_LOG_2026.md#d-505--explicitly-authorized-isolated-ai-symbol-experiment) | explicitly authorized isolated AI symbol experiment | accepted | 2026-10-06 | request to continue training autonomously and use internal AI to inspect graphics. |
