---
title: TASK-0654 — Dokumentacja „Przybliżonej wygranej” i odbiór na żywych danych
status: in_progress
---

# TASK-0654 — Dokumentacja i odbiór

## Status

`in_progress` — dokumentacja ukończona; odbiór na żywych danych wstrzymany
do osobnej, jawnej zgody użytkownika na uruchomienie lokalnego API i Admina.

**Uwaga o numeracji:** szósty i ostatni task planu sesji `2026-09-24`
„Przybliżona wygrana” w „Wyszukaj plansze”.
[TASK-0649](completed/0649-board-search-result-limit-input.md)–
[TASK-0653](completed/0653-approximate-win-admin-ui.md) ukończone.

**Kolizja numeracji D-445:** plan tej serii i wcześniejsze pliki tasków
(`0649`–`0653`) odwoływały się do zbiorczej decyzji jako „D-445”. W
międzyczasie inna, równoległa sesja zajęła ten numer własną decyzją
(reweryfikacja siatek 777). Właściwy, ostateczny wpis dla tej serii to
**D-446** w `DECISION_LOG.md`.

## Goal

Udokumentować w `ai_docs/` finalny, użyty w produkcji kontrakt „Przybliżonej
wygranej” (a nie roboczy stan decyzji D1–D6 z planu) i, po osobnej zgodzie,
potwierdzić działanie na żywych danych gry 777.

## Dependencies / entry conditions

TASK-0649–0653 ukończone i zacommitowane.

## Recommended execution

Sonnet 5, reasoning `medium` — praca dokumentacyjna bez zmiany kodu; brak
dodatkowego review.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- `ai_docs/requirements/ADMIN_APP.md`: nowy akapit o „Liczbie wyników” jako
  niezależnym parametrze oraz nowa sekcja „Przybliżona wygrana” (zakres,
  kategoryzacja, podsumowanie, zachowanie rozwijanej sekcji, brak cache
  serwerowego).
- `ai_docs/architecture/API_CONTRACT.md`: nowa sekcja „Przybliżona wygrana
  (kalkulator zakresu)” — pełny kontrakt endpointu, pola odpowiedzi, kody
  błędów.
- `ai_docs/requirements/ALGORITHMS.md`: nowa sekcja `## D. Przybliżona
  wygrana w Adminie` — zakres, kategoryzacja, pełny dowód, że naliczenie z
  widocznego prefiksu jest bezpiecznym dolnym ograniczeniem (właściwość
  `payout-v3-unknown-prefix-stop`, nie osobny algorytm).
- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-446 zbierający całą serię
  (0649–0653) w jedną decyzję referencyjną, z notatką o kolizji numeru D-445.
- `ai_docs/process/CURRENT_STATE.md`: wpis podsumowujący ukończenie planu.

## Out of scope

- Jakakolwiek zmiana kodu — ten task jest wyłącznie dokumentacyjny.
- Odbiór na żywych danych bez osobnej, jawnej zgody użytkownika na
  uruchomienie lokalnego API i Admina (patrz Outcome → Not completed).
- Naprawa pre-existing problemów zgłoszonych w poprzednich taskach
  (`test_payout_store.py`, `prettier --check` na `admin-api-client`).

## Acceptance criteria

- [x] `ADMIN_APP.md`, `API_CONTRACT.md`, `ALGORITHMS.md` opisują zachowanie
  faktycznie zaimplementowane w TASK-0649–0653, nie roboczy stan planu.
- [x] `DECISION_LOG.md` ma jeden referencyjny wpis (D-446) dla całej serii,
  z jawnym wyjaśnieniem kolizji numeru D-445.
- [x] `CURRENT_STATE.md` odzwierciedla ukończenie planu (6/6, z zastrzeżeniem
  wstrzymanego odbioru).
- [ ] Odbiór read-only na żywych danych gry 777 — **wstrzymany do zgody
  użytkownika**, patrz Outcome → Not completed.

## Technical notes

Dokumentacja opisuje wyłącznie zachowanie już pokryte testami
(jednostkowymi, integracyjnym PostgreSQL) w TASK-0650–0653. Nie wprowadza
nowych zobowiązań ani decyzji produktowych ponad to, co zostało
zaimplementowane — w szczególności limit `10 000` spinów jest udokumentowany
jako oszacowanie bez pomiaru (zgodnie z D-446 i TASK-0652's Technical notes),
nie jako zmierzony, gwarantowany próg wydajności.

## Expected files

- Istniejące: `ADMIN_APP.md`, `API_CONTRACT.md`, `ALGORITHMS.md`,
  `DECISION_LOG.md`, `CURRENT_STATE.md`.
- Nowe: brak plików kodu.

## Test cases

Nie dotyczy — task wyłącznie dokumentacyjny, bez zmiany kodu. Cała
implementacja jest już pokryta testami z TASK-0649–0653 (patrz ich pliki w
`ai_docs/tasks/completed/`).

## Verification

Nie dotyczy uruchamiania testów (brak zmiany kodu). Weryfikacja polega na
przeczytaniu zaktualizowanych dokumentów i porównaniu ich z faktycznym
kodem/testami z TASK-0649–0653.

## Risks / open questions

- **Odbiór na żywych danych nie został wykonany** — wymaga osobnej, jawnej
  zgody użytkownika na uruchomienie `npm run api:dev` i `npm run admin:dev`
  przeciw realnej, lokalnej bazie danych (gra 777). Do czasu tej zgody plan
  pozostaje w pełni zaimplementowany i przetestowany automatycznie, ale bez
  ręcznego potwierdzenia na żywym UI.
- Limit `spinCount ≤ 10 000` (D5 z planu) nie jest oparty na pomiarze
  rzeczywistego czasu odpowiedzi — do weryfikacji przy pierwszym realnym
  użyciu na dużym zakresie.

## Outcome

### Changed

- [ADMIN_APP.md](../requirements/ADMIN_APP.md): akapit o „Liczbie wyników”
  + nowa sekcja „Przybliżona wygrana”.
- [API_CONTRACT.md](../architecture/API_CONTRACT.md): nowa sekcja
  „Przybliżona wygrana (kalkulator zakresu)”.
- [ALGORITHMS.md](../requirements/ALGORITHMS.md): nowa sekcja `## D.
  Przybliżona wygrana w Adminie` z pełnym dowodem dolnego ograniczenia.
- [DECISION_LOG.md](DECISION_LOG.md): nowy wpis D-446.
- [CURRENT_STATE.md](CURRENT_STATE.md): wpis podsumowujący ukończenie planu
  (6/6, z zastrzeżeniem wstrzymanego odbioru).

### Verification results

- Nie dotyczy (brak zmiany kodu). Cała implementacja zweryfikowana testami
  w poszczególnych taskach TASK-0649–0653 (patrz ich pliki `Outcome`).

### Not completed

- **Odbiór na żywych danych gry 777** (uruchomienie lokalnego API i Admina,
  ręczne sprawdzenie ekranu „Przybliżona wygrana” na realnych danych) —
  celowo nie wykonany w tej sesji. Wymaga osobnej, jawnej zgody użytkownika
  zgodnie z zasadami bezpieczeństwa tej sesji (uruchamianie długożyjących
  procesów lokalnych i przeglądanie realnych danych administracyjnych).

### Documentation updates

- Patrz „Changed” powyżej — to jest ten task.

### Recommended next task

- Brak kolejnego zaplanowanego taska w tej serii. Po zgodzie użytkownika:
  odbiór na żywych danych gry 777 (uruchomienie `npm run api:dev` +
  `npm run admin:dev`, przejście do „Wyszukaj plansze” → „Przybliżona
  wygrana”, sprawdzenie realnego payoutu i braku zapisów).
