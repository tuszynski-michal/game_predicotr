# Audyt TASK-0969 - Sekcja „Ostatnie korekty” w Reviewerze

Werdykt: REVISE
Audytor: Codex, etykieta briefu: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, medium
Zakres: HEAD...cbf0d588803f20ccfc2a732b7350b2c5c4ff3ff0 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 3

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Poprawiono rozpoznawanie nieznanego wyniku operacji przy rzeczywistym zachowaniu klienta API. Testy obejmują odrzucony `fetch`, odpowiedź 503, ponowienie z identycznym żądaniem oraz odtworzony sukces. Pozostaje wyścig odpowiedzi podglądu po zamknięciu i ponownym otwarciu tej samej korekty, który może uniemożliwić ponowienie operacji.

## Znaleziska

### P0

- [P0-2] `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:176` — Odpowiedź podglądu jest przypisywana do modala wyłącznie na podstawie `boardGeometryRevisionId`. Operator może otworzyć podgląd, anulować go podczas pobierania i ponownie otworzyć tę samą korektę. Opóźniona odpowiedź pierwszego żądania nadpisze wtedy podgląd drugiego otwarcia. Jeżeli drugie otwarcie zdążyło już wysłać cofnięcie z nieznanym wynikiem, późniejszy błąd pierwszego podglądu ustawi `preview=null` i `previewError`, blokując przycisk ponowienia (`:338`). Późniejszy sukces ze starszymi tokenami może zamiast tego zmienić CAS kolejnej próby przy zachowanym kluczu idempotencji (`:206`). Należy powiązać odpowiedź podglądu z konkretnym otwarciem modala, np. przechwyconym `idempotencyKey`, i ignorować odpowiedzi poprzednich otwarć. Dodać test odwróconej kolejności odpowiedzi.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Lista korekt i blokada niedozwolonego cofnięcia | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:115` |
| Podgląd skutków przed potwierdzeniem | spełnione | `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:319`; wyścig odpowiedzi opisuje P0-2 |
| Jedno żądanie przy podwójnym kliknięciu, z CAS | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:135` |
| Bezpieczne ponowienie po utracie odpowiedzi | niespełnione | Podstawowy scenariusz pokrywa test `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:233`; P0-2 narusza go przy ponownym otwarciu modala |
| Konflikt 409 pokazuje komunikat i odświeża listę | spełnione | `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:211` |
| Sukces odświeża kolejkę i historię | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:675` |
| Zapis korekty odświeża historię | spełnione | `apps/reviewer/test-interactions/board-geometry-correction.test.mjs:660` |
| Zielone `typecheck`, `lint`, `test` i `build` | niezweryfikowane | Wyniki zadeklarowane w Outcome; audyt nie uruchamiał kontroli. Ostatnia aktualizacja wyników nie wymienia ponownego builda |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1** — Rozróżniono potwierdzoną odmowę 4xx od nieznanego wyniku; test używa rzeczywistego klienta z atrapą `fetch` (`apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:221`, `apps/reviewer/test-interactions/geometry-correction-history.test.mjs:233`).
- **P1-1** — Testy pełnego workspace sprawdzają odświeżanie historii po zapisie oraz kolejki po cofnięciu (`apps/reviewer/test-interactions/board-geometry-correction.test.mjs:660`, `:675`).
- **P2-1** — Dodano zarządzanie fokusem, obsługę klawiatury modala i blokadę skrótów edytora (`apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx:105`, `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx:869`).

Otwarte: **P0-2**.

## Proponowane testy

- W `apps/reviewer/test-interactions/geometry-correction-history.test.mjs` sterować dwoma oczekującymi żądaniami podglądu tej samej korekty. Zamknąć pierwsze otwarcie, otworzyć drugie, zwrócić drugi podgląd i zasymulować utratę odpowiedzi cofnięcia. Następnie zakończyć pierwszy podgląd błędem albo innymi tokenami. Ponowienie musi pozostać dostępne i wysłać identyczny klucz oraz CAS.
- W tym samym pliku dodać odpowiedź z nieparsowalnym JSON po cofnięciu i sprawdzić zachowanie klucza oraz treści żądania.

Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Sprawdzono brief, wcześniejsze raporty, komponent historii, integrację workspace, zmiany skrótów i stylów, testy oraz wrapper i transport klienta API. Uwzględniono wymagania i fragment planu. `git diff --check` nie zgłosił błędów.

Nie uruchamiano testów, builda, usług ani operacji na danych. Wyniki wykonawcy nie zostały niezależnie potwierdzone. Wygląd i zachowanie w przeglądarce pozostają niezweryfikowane.

Task pozostaje `in_progress`. Dokumentacja zamknięcia, regeneracja mapy kodu oraz zapis wersji i hasha commita pozostają po stronie wykonawcy lub leada.