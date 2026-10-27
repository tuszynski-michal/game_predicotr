---
title: Wprowadzanie układów przed szukaniem i nawigacja zdjęć
status: done
last_updated: 2026-10-27
---

# TASK-1098 — Wprowadzanie układów przed szukaniem i nawigacja zdjęć

## Status

`done`

## Goal

Przygotowanie do czterech układów przed jednym wyszukaniem oraz przegląd zdjęć dopasowania i dziesięciu kolejnych zdjęć w lokalnym Adminie i obu powierzchniach udostępniania.

## Context

Operator 2026-10-27 zmienia wcześniejszą regułę dodawania wzoru dopiero po udanym wyszukiwaniu. Potwierdził dziesięć dodatkowych zdjęć po dopasowanym ciągu. Nawigacja po rankingu pozostaje osobną operacją.

## Dependencies / entry conditions

Istniejące GET szczegółów i checksumowanego kadru obsługują dowolny numer planszy lokalnie i przez oba proxy. Zmiana nie wymaga API ani migracji. Robocza gałąź od main; zastane usunięcia artifacts i obcy worktree pozostają poza taskiem.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Ograniczona zmiana wspólnego UI z testami interakcji. Osobny audyt krzyżowy nie jest wymagany dla tego niezależnego taska; eskalacja przy konieczności zmiany kontraktu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — wyszukiwanie i udostępnianie.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — współdzielony widok i proxy.
- `ai_docs/architecture/API_CONTRACT.md` — ciągi i GET szczegółów/kadru.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach`
- `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` — poprzednie zachowanie, zmienione niniejszym zleceniem.

## Scope

- Dodawanie poprawnie wypełnionych wzorów przed pierwszym wyszukaniem, limit czterech bez zmian.
- Oddzielny podgląd od pierwszego zdjęcia dopasowania do dziesiątego zdjęcia po końcu ciągu, przyciski Następny układ i Poprzedni układ.
- Powrót do pierwszego zdjęcia; reset podglądu po zmianie wyniku lub odświeżeniu wyszukiwania.
- Zachowanie rankingu, kotwicy wygranych i kontekstu korekty wskazanej planszy.
- Lokalne wyszukiwanie, link gry i panel udostępniania używają wspólnej implementacji. Panel zarządzania zachowuje poprzedni workflow.

## Out of scope

Migracje, zmiany API, restarty, publikacja, push i merge.

## Acceptance criteria

- [x] Cztery wzory można wpisać bez żądania wyszukiwania, po czym wysłać jeden POST.
- [x] Dla dopasowania 240–243 podgląd obejmuje 240–253; wstecz tylko do 240.
- [x] Jeden wzór również pozwala obejrzeć dziesięć kolejnych zdjęć.
- [x] Nawigacja zdjęć nie zmienia dopasowania ani wygranych; nowy wynik zaczyna od pierwszego zdjęcia.
- [x] Odczyt brakującej planszy lub błąd nie przeskakuje numeru, zachowuje poprzedni podgląd i umożliwia ponowienie.
- [x] Spóźniona odpowiedź nie zmienia innego wyniku; nie ma automatycznego pobierania wszystkich zdjęć.
- [x] Testy wspólnego komponentu, lint, formatowanie, typecheck, docs:check i mapa kodu przechodzą.

## Technical notes

Dodawanie wymaga poprawnego prefiksu bez pustych luk, ostatniego badża, gotowej hydratacji i braku trwającego wyszukiwania/obliczenia. Przycisk edytora otrzymuje nazwę Dodaj układ, aby odróżnić go od nawigacji zdjęć. Podgląd używa istniejących boards w odpowiedzi w kolejności API (w tym cyklicznych ciągów). Dodatkowe zdjęcia odczytuje kolejno po numerze ostatniej planszy, bez zawijania ani przeskakiwania braków. Przy braku następnej planszy pozostaje poprzednie zdjęcie z komunikatem. Dodatkowe zdjęcia nie mają oceny dopasowania. Zapisany wybór rankingu pozostaje niezależny; po ponownym otwarciu podgląd zaczyna od pierwszej planszy dopasowania.

## Expected files

- `packages/board-search-ui/src/use-board-search-sequence.ts` — canNext.
- `packages/board-search-ui/src/board-search-workspace.tsx` — etykieta i włączenie podglądu.
- `packages/board-search-ui/src/board-search-results.tsx` — podgląd i otwarcie wskazanej planszy.
- Nowy: `packages/board-search-ui/src/board-search-photo-navigation.tsx` — ograniczona nawigacja zdjęć.
- `packages/board-search-ui/src/board-search.css` — odstępy i układ przycisków na małym ekranie.
- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs` — regresje interakcji.
- Wymagania, D-573, adnotacja poprzedniego planu, mapa kodu, CURRENT_STATE i ten task.

## Test cases

Cztery wzory przed wyszukiwaniem; błędny/pusty wzór; 4+10 zdjęć i powrót; pojedynczy wzór; cykliczne dopasowanie; zmiana rankingu podczas GET; błąd i ręczne ponowienie; korekta wcześniejszego/dodatkowego zdjęcia; niezmieniona kotwica wygranych; konsument bez sekwencji.

## Verification

Komendy z katalogu repozytorium, każda z limitem 120 s:

```powershell
npm run test:interactions --workspace @game-predictor/board-search-ui
npm test --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/board-search-ui
npm run docs:check
npm run code-map:check
```

## Risks / open questions

Nie wykonujemy fizycznego odbioru Androida ani restartów usług operatora. Dodatkowe zdjęcia wymagają istniejących dokumentów wyszukiwania i dostępnych reguł szczegółów; brak lub nieaktualny dokument daje jawny błąd.

## Outcome

Commit: v1.7.484 (hash dopisuje kolejny commit).

### Changed

- Do czterech poprawnych wzorów przed pierwszym wyszukiwaniem; niewysłane wzory pozostają po ponownym zamontowaniu widoku we wszystkich trzech scope'ach.
- Podgląd pierwszej planszy dopasowania, wszystkich kolejnych plansz ciągu i dziesięciu dodatkowych zdjęć. Powrót do pierwszego zdjęcia, lokalny cache tylko na czas przeglądu wyniku, pojedynczy odczyt na krok i ochrona przed spóźnioną odpowiedzią.
- Osobne przyciski edytora, zdjęć i rankingu; wskazane zdjęcie otwiera własną korektę. Wygrane zachowują koniec dopasowania.
- Początkowy test ujawnił regresję zamykania modalu po odświeżeniu; reset ograniczono do komponentu podglądu. Test regresyjny pozostaje bez osłabiania asercji.

### Verification results

- Wspólny UI: 127/127 interakcji (finalny przebieg po sprawdzeniu ponownego montowania), 108/108 testów logiki.
- Adapter linku i oba proxy: 38/38 istniejących testów.
- Lint pakietu oraz końcowy lint zmienionych plików, Prettier zmienionych plików, typecheck wspólnego UI, Admina i Reviewera: PASS.
- `npm run docs:check`: PASS; mapa kodu zregenerowana i sprawdzona przed commitem.
- Kryteria akceptacji sprawdzono punkt po punkcie. Testy nowych procesów, ponownego montowania i odtwarzania localStorage potwierdzają trwałość kodu i niewysłanych wzorów.

### Not completed

- Bez odbioru na fizycznym Androidzie, działającym linku operatora i bez buildów aplikacji; nie uruchamiano ani nie restartowano usług.
- Bez merge i push. Zastane usunięcia artefaktów i obcy worktree pozostają poza commitem.
- Audyt krzyżowy niewymagany w wierszu TASK-1098; nie powtarzano audytów zakończonych zadań 1091/1092.

### Documentation updates

- Wymagania Admina, doprecyzowanie D-573 i jego indeks, poprzedni plan z jawną zmianą operatora, mapy kodu i CURRENT_STATE.

### Recommended next task

- Operator zgłosił istniejący `BOARD_SEARCH_SEQUENCE_TIMEOUT`; dalsza poprawka limitu czasu będzie osobnym TASK-1099, bez zmiany rankingu w tym commicie.
