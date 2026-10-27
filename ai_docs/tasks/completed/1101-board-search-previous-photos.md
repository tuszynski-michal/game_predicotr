---
title: Nawigacja po piętnastu zdjęciach w obie strony
status: done
last_updated: 2026-10-27
---

# TASK-1101 — Nawigacja po piętnastu zdjęciach w obie strony

## Status

`done`

## Goal

Po znalezieniu układu można obejrzeć do piętnastu zdjęć przed początkiem i piętnastu zdjęć po końcu dopasowania, lokalnie i przez oba widoki udostępniania.

## Context

Operator rozszerza dotychczasowy podgląd dopasowania i dziesięciu późniejszych zdjęć. Doprecyzował zakres do piętnastu zdjęć w obie strony, także po pojedynczym wzorze. Nowy zakres dla dopasowania 240–243 wynosi 225–258. Początkowy podgląd nadal wskazuje 240; ranking i kotwica wygranych pozostają niezależne od przeglądania. Osobno zatwierdził przebudowę i restart API, Admina i Reviewera. Stwierdzono, że Reviewer produkcyjny i build Admina pochodzą z 25 października, sprzed poprzednich poprawek UI.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Ograniczona zmiana istniejącej nawigacji i regresji interakcji. Dodatkowy audyt niewymagany; eskalacja przy konieczności zmiany API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — podgląd zdjęć wyszukiwania.
- `ai_docs/architecture/API_CONTRACT.md` — istniejący GET szczegółów i kadru.
- `ai_docs/architecture/CODE_MAP.md`

## Scope

- „Poprzedni układ” odczytuje wcześniejsze zdjęcia po numerze pierwszej planszy dopasowania, do piętnastu kroków wstecz.
- Granica numeru 1, bez zawijania i bez przeskakiwania braków, jak dla dodatkowych zdjęć w przód.
- Osobny stan podglądu, cache na czas wybranego wyniku, blokada podwójnych żądań i odrzucanie spóźnionych odpowiedzi.
- Rozszerzenie dotychczasowych dziesięciu zdjęć w przód do piętnastu; zachowanie rankingu, wygranych i korekty oglądanej planszy.
- Zatwierdzona przebudowa i restart API, Admina i Reviewera; worker i tunel bez zmian. Kontrola pojedynczego układu na działającym widoku.

## Out of scope

Zmiany API, migracje, dane operatora, merge i push. Dotychczasowa zgoda na integrację obejmowała wcześniejsze taski, nie to nowe rozszerzenie. Zgłoszenie powtarzającego się timeoutu podlega osobnej diagnozie backendu.

## Acceptance criteria

- [x] Dla dopasowania 240–243 można przejść od 240 do 225 i dalej w przód do 258, bez przekraczania granic.
- [x] Dla początku 6 cofanie kończy się na 1 i nigdy nie odczytuje 0.
- [x] Admin, link gry i panel korzystają z tej samej nawigacji; wcześniejsze zdjęcia otwierają własne szczegóły/korektę.
- [x] Błąd zachowuje zdjęcie i pozwala ponowić ten sam numer; późna odpowiedź nie zmienia innego dopasowania.
- [x] Nawigacja nie zmienia wygranych ani rankingu; powrót po odczytanych zdjęciach nie wysyła kolejnych GET.
- [x] Testy interakcji, lint, formatowanie, typecheck, docs i mapa kodu przechodzą.

## Technical notes

Indeks 0 nadal oznacza pierwszą planszę dopasowania. Minimalny indeks to `-min(15, firstSequenceNumber - 1)`. Ujemne indeksy odczytują `firstSequenceNumber + index`, a indeksy za dopasowaniem korzystają z numeru jego ostatniej planszy. Cache szczegółów jest mapą po indeksie podglądu; istniejące plansze dopasowania pochodzą z API i zachowują cykliczną kolejność. Każdy odczyt następuje po kliknięciu, nie pobieramy całego zakresu z góry. Błędy wskazują właściwy przycisk ponowienia. Licznik obejmuje cały dozwolony zakres, a opis odróżnia zdjęcia przed i po dopasowaniu.

## Expected files

- `packages/board-search-ui/src/board-search-photo-navigation.tsx` — nawigacja i cache.
- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs` — nowe granice i regresje.
- `ai_docs/requirements/ADMIN_APP.md` i dokumenty zamknięcia taska.

## Verification

Z katalogu repozytorium; każda skończona komenda z jawnym timeoutem do 120 s. Testy interakcji pakietu board-search-ui, ESLint zmienionych plików, Prettier, typecheck pakietu, regeneracja mapy kodu, `npm run docs:check` i `npm run code-map:check`. Zatwierdzone buildy i restarty; odbiór działającego widoku bez fizycznego telefonu.

## Outcome

Commit: v1.7.490 / `93f7697e1071290f23c2467e59c8394bf6fd32a4`.

### Changed

- Podgląd obejmuje piętnaście zdjęć przed początkiem i piętnaście zdjęć po końcu dopasowania, także po pojedynczym wzorze. Cofanie zatrzymuje się na numerze 1, bez zawijania. Indeks 0 nadal oznacza pierwszy wynik ciągu; cache szczegółów jest wspólny dla obu kierunków.
- Poprzedni i następny odczyt zachowują blokadę podwójnego żądania, obsługę braku/nieaktualnego dokumentu i odrzucanie odpowiedzi po zmianie dopasowania. Ponowienie błędu wskazuje właściwy przycisk.
- Operator osobno zatwierdził buildy i restart trzech usług. Zatrzymano zweryfikowane procesy Admina i Reviewera, przebudowano obie aplikacje, uruchomiono je produkcyjnie na dotychczasowych portach 3000 i 3001, następnie zrestartowano API z `--reload` na 8000. Worker i istniejący tunel nie były zatrzymywane. PID i logi zapisano w ignorowanym `.runtime/board-search-1101-services.json`.

### Verification results

- Finalne 132/132 testów interakcji PASS: oba limity, powrót przez cały zakres, cache obu kierunków, granica 1 w trzech scope'ach, błąd i ponowienie, spóźniony odczyt, korekta wcześniejszej planszy i stała kotwica wygranych.
- ESLint, Prettier i typecheck wspólnego pakietu PASS. Produkcyjne buildy Admina i Reviewera PASS, wraz z kontrolą TypeScript obu aplikacji. Mapa kodu zregenerowana bez zmiany treści; docs i code-map sprawdzone przed commitem.
- Odbiór na nowym działającym Adminie w osobnej karcie: jeden znany symbol, jeden wzór, 40 wyników; zdjęcie 223129, przejście do 223130 i cofnięcie do 223128. Ranking i kotwica wygranych nadal wskazują 223129. Dowód obrazu: ignorowany `.runtime/board-search-1101-single.png`.
- Po restarcie: Admin `/`, Reviewer `/board-search`, API `/openapi.json` oraz publiczne `/board-search` na istniejącym adresie tunelu zwróciły HTTP 200. Host tunelu i istniejące linki nie były zmieniane.
- Kryteria akceptacji i właściwe punkty Definition of Done sprawdzone punkt po punkcie; działanie potwierdzone po nowym buildzie i w nowych procesach.

### Not completed

- Powtarzający się timeout odtworzono niezależnie od UI na ostatnim zgłoszonym wzorze 777a2: dwa pełne układy, 470444 bajty SQL, plan kosztu 1202339.98. Odczyt z obecną polityką zakończył się `BOARD_SEARCH_SEQUENCE_TIMEOUT` po 66,109 s; próba bez JIT z limitem 12 s również została anulowana. Nie wprowadzono zmiany zapytania. Operator po ostrzeżeniu o koszcie 20–40 minut wybrał: „Dokończ tylko nawigację, buildy i restarty”. Optymalizacja i usunięcie timeoutu pozostają świadomie poza zakończonym zakresem.
- Bez odbioru uwierzytelnionego pełnego linku odbiorcy i fizycznego Androida; publiczny smoke potwierdza dostępność strony, a regresje wspólnego UI obejmują oba typy linków.
- Bez merge i push tej nowej zmiany. Zastane usunięcia artefaktów i obcy worktree poza commitem. Osobny audyt niewymagany.

### Documentation updates

- ADMIN_APP opisuje zakres ±15, granicę 1 i działanie pojedynczego wzoru. CURRENT_STATE i ten task rejestrują zgody na build/restart oraz odłożoną optymalizację zapytania.

### Recommended next task

- Akceptacja kodu nawigacji i osobna zgoda na integrację. Optymalizację wyszukiwania ciągów podejmować dopiero po nowej zgodzie operatora na ten odłożony zakres i koszt.
