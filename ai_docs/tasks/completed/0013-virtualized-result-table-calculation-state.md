---
title: TASK-0013 Virtualized result table and calculation state
status: completed
last_updated: 2026-07-24
---

# TASK-0013 — Virtualized result table and calculation state

## Goal

Pokazać wszystkie dodatnie lokalne maksima Target na dole ekranu w jednej
pionowej liście wirtualizowanej, zachować pełny przepływ Layout → Target oraz
domknąć M1.5 i bramkę G5.

## Context

TASK-0012 zwraca gotowy `ForecastResult` wraz z uporządkowanym
`positiveLocalPeaks`. Obecny ekran używa zwykłego `ScrollView`, dlatego nie
może bezpiecznie zawierać długiej pionowej listy. Zaakceptowany baseline
techniczny wskazuje wbudowany `FlatList`; dodatkowa biblioteka wymagałaby
pomiaru przewagi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0005-target-engine-golden-tests.md`
- `ai_docs/tasks/completed/0012-full-cycle-target-integration.md`

## Scope

- zastąpienie głównego pionowego `ScrollView` jednym `FlatList`,
- Layout, Selection, matching i podsumowanie Target jako `ListHeaderComponent`,
- `positiveLocalPeaks` jako jedyne dane wirtualizowanych wierszy,
- tabela umieszczona po wszystkich polach wejściowych i podsumowaniu,
- sześć wymaganych wartości każdego szczytu: spin, `sequence_number`, payout
  spinu, payout skumulowany, koszt skumulowany i wynik netto,
- układ wiersza mieszczący się na szerokości telefonu bez przewijania całej
  strony w poziomie,
- jawny pusty stan, gdy nie ma dodatnich lokalnych maksimów,
- stabilne klucze i jawna konfiguracja okna renderowania,
- zachowanie loading, error, Retry, Undo, Reset i zmiany gry,
- testy późniejszego niższego szczytu, plateau, zera i długiej listy,
- domknięcie bramki G5.

## Out of scope

- zmiana czystego Target engine lub definicji lokalnego maksimum,
- nowa biblioteka listy bez dowodu przewagi nad `FlatList`,
- poziomy arkusz danych,
- eksport, filtrowanie lub sortowanie wyników przez użytkownika,
- benchmark 500 000 layoutów na urządzeniu,
- release APK i odbiór na Pixel 10 Pro XL oraz Galaxy S21 Ultra.

## Acceptance criteria

- [x] Główny ekran używa jednej pionowej listy wirtualizowanej.
- [x] Nie ma pionowego `FlatList` zagnieżdżonego w zwykłym `ScrollView`.
- [x] Sekcje wejściowe i podsumowanie są nagłówkiem tej samej listy.
- [x] Tabela znajduje się na dole przepływu ekranu.
- [x] Każdy wiersz pokazuje wszystkie sześć wymaganych wartości.
- [x] Wiersze mają dostępne etykiety i nie przekazują wyniku tylko kolorem.
- [x] Klucz wiersza jest stabilny i domenowy.
- [x] Wiersze zachowują rosnącą kolejność `spinNumber`.
- [x] Zero i wartości ujemne nie tworzą wiersza.
- [x] Późniejszy niższy szczyt jest widoczny.
- [x] Plateau wskazuje pierwszy spin.
- [x] Brak dodatnich szczytów ma jawny empty state.
- [x] Długi wynik nie renderuje wszystkich wierszy jednocześnie.
- [x] Loading i error nie pokazują starych wierszy.
- [x] Undo, Reset i zmiana gry usuwają wiersze Target.
- [x] Duplicate nigdy nie pokazuje tabeli Target.
- [x] UI nie wymaga poziomego przewijania całej strony.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] Bramka G5 oraz dokumentacja M1.5 są zaktualizowane.

## Technical notes

- `FlatList<ForecastPeak>` otrzymuje bezpośrednio zamrożone
  `positiveLocalPeaks`; UI nie sortuje ani nie przelicza domeny.
- Klucz łączy `spinNumber` i `sequenceNumber`, które są jednoznaczne w jednym
  forecastcie.
- `initialNumToRender`, `maxToRenderPerBatch` i `windowSize` są jawne, a test
  długiej listy sprawdza ograniczenie liczby zamontowanych wierszy.
- Wiersz używa responsywnej siatki etykieta/wartość zamiast poziomej tabeli,
  dzięki czemu wszystkie kolumny pozostają czytelne na wąskim ekranie.
- Testy komponentowe są dowodem bramki G5 w repozytorium; płynność na
  fizycznych urządzeniach pozostaje obowiązkowym odbiorem M1.6.

## Expected files

- `apps/mobile/src/features/target/target-peak-row.tsx`
- `apps/mobile/src/features/target/target-results-header.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- testy tabeli i aktualizacja testów przepływu
- dokumentacja procesu i planu M1

## Verification

```powershell
npm run quality
git diff --check
```

## Risks / open questions

- `FlatList` może wymagać strojenia po teście na fizycznych urządzeniach.
  Zmiana na FlashList pozostaje dozwolona dopiero po takim pomiarze.
- Liczba dodatnich szczytów dla danych docelowych nie jest jeszcze znana, ale
  nie zmienia kontraktu ani konieczności wirtualizacji.

## Outcome

Ukończono 2026-07-24.

- Główny pionowy `ScrollView` został zastąpiony jednym `FlatList`; GameHeader,
  Layout, Selection, matching, Target i diagnostics są jego nagłówkiem.
- `positiveLocalPeaks` są jedynymi danymi listy i zachowują domenową kolejność
  bez dodatkowego sortowania w UI.
- Każdy wiersz pokazuje spin, layout, payout spinu, payout i koszt skumulowany
  oraz wynik netto, wraz z pełną etykietą dostępności.
- Dodano jawny empty state dla pełnego cyklu bez dodatnich lokalnych maksimów.
- Lista używa stabilnego klucza `spinNumber:sequenceNumber`, okna `5`,
  `initialNumToRender = 8`, `maxToRenderPerBatch = 8` i odcinania elementów
  poza ekranem.
- Test 100 lokalnych maksimów potwierdza, że nie wszystkie wiersze są
  montowane jednocześnie.
- Test UI golden M1 ocenia `999` spinów od spin 0 = `99`, pokazuje szczyt
  `190` na spinie `1` i późniejszy niższy `180` na spinie `12`; payout `10`
  na spinie `13` tworzy plateau, ale nie drugi wiersz.
- Zero i ujemne wyniki nie są wierszami, a Reset, Undo, zmiana gry, loading,
  error i duplicate nie zachowują starej tabeli.
- `npm run quality` przeszedł: format, lint, PowerShell syntax, TypeScript,
  mypy, `62` testy mobile, `22` shared TypeScript, `52` Python oraz walidacje
  snapshotu i fixture.
- `git diff --check` przeszedł bez błędów.
- Płynność na Pixel 10 Pro XL i Galaxy S21 Ultra oraz ewentualne dalsze
  strojenie `FlatList` pozostają w TASK-0014.
