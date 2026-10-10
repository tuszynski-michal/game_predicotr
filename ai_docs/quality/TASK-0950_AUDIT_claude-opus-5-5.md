# Audyt TASK-0950 — Management pending modal recovery

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning medium
Wykonawca: Codex (model i reasoning niepodane w briefie)
Zakres: HEAD...e8ab35778cdaef53655d9a1d5dd1eb6c547972c1 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików i nie uruchamiał testów.

## Streszczenie

Sprawdziłem przeniesienie błędu i przycisku „Ponów ten sam zapis” do okien edycji i usuwania, blokadę pól oraz zachowanie oczekującej operacji po zamknięciu okna. Funkcja `run` (`management-workspace.tsx:430-513`) dalej zapisuje i ponawia dokładnie tę samą operację. Odrzucenia 4xx (poza 401/403/429) czyszczą oczekującą operację, a strażnik `accessRef` blokuje zapis po końcu dostępu. Nie znalazłem błędów P0 ani P1. Główne ryzyko to luka w testach scenariusza końca sesji przy otwartym oknie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `apps/reviewer/test-interactions/management-panel.test.mjs:1208-1330`: nowe testy nie sprawdzają, że po utracie dostępu przy otwartym oknie przycisk ponowienia jest nieaktywny. Dotyczy to obu okien: edycji (`management-workspace.tsx:1062`) i usuwania (`management-workspace.tsx:1098`). Kod jest poprawny: `!accessAllowed` oraz strażnik w `run:431`. Jednak kryterium „ended access cannot launch another write” sprawdzają tylko starsze testy, w których przycisk ponowienia był poza oknem. Propozycja: w pętli testów dodać wariant z odpowiedzią 401 albo z `accessAllowed=false` po błędzie 502. Test powinien sprawdzać, że `Ponów ten sam zapis` i `Zapisz`/`Potwierdź usunięcie` w oknie są `disabled`, a liczba mutacji się nie zmienia.
- [P2-2] `ai_docs/tasks/0950-management-pending-modal-recovery.md`: Outcome wciąż podaje „Lint/typecheck pending”, a pola kryteriów akceptacji są niezaznaczone. W sekcji Expected files jest `apps/admin/test-interactions/management.test.mjs`, ale ten plik się nie zmienił; pokrycie zapewnia wspólny komponent i testy Reviewera. Propozycja: przed commitem wpisać potwierdzone wyniki lint/typecheck, zaznaczyć kryteria i dopisać, że testy Admina przeszły bez zmian (13/13). Można też uzasadnić, dlaczego regresji nie dodano po stronie Admina.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Błąd edycji z komunikatem i aktywnym ponowieniem w oknie | spełnione | `management-structure-modal.tsx:87,192-196`; `management-workspace.tsx:1060-1065`; test `management-panel.test.mjs:1270-1281` |
| Zamknięcie i ponowne zamontowanie zachowują UUID i treść; udane ponowienie odblokowuje edycję i usuwanie | spełnione | `management-workspace.tsx:1073-1076` (zamknięcie nie czyści `pending`), `:472-475`; test `:1286-1323` (`deepEqual` treści, przyciski aktywne) |
| Błąd usuwania z komunikatem i ponowieniem w oknie potwierdzenia | spełnione | `management-workspace.tsx:1091,1096-1105`; testy w pętli dla punktu i maszyny |
| Odrzucenie walidacyjne zostawia edytowalne pola i komunikat | spełnione | `management-workspace.tsx:452-460`; `management-structure-modal.tsx:102`; test `:1332-1374` |
| Trwający zapis i koniec dostępu blokują nowy zapis | spełnione (kod), częściowo przetestowane | `management-workspace.tsx:431,675,1062,1098`; pola zablokowane przy `saving || retryAvailable`; zob. P2-1 |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- `apps/reviewer/test-interactions/management-panel.test.mjs`: błąd 502 w oknie edycji lub usuwania, potem 401 przy ponowieniu albo utrata dostępu. Asercje: ponowienie i zapis w oknie są nieaktywne, liczba mutacji się nie zmienia, oczekująca operacja zostaje w sessionStorage. Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przeczytałem diff z briefu, `management-workspace.tsx` (linie 85-164, 425-684, 800-830, 1040-1119) i listę testów w pliku testów Reviewera. Nie uruchamiałem żadnych testów; wyniki 13/19/11 PASS oraz lint i typecheck PASS przyjąłem od operatora. Poza zakresem pozostały plan layoutu, przywracanie zarchiwizowanych encji i przyczyna zgłoszenia operatora. Nie sprawdziłem wizualnie zachowania okna ani obsługi klawisza Escape w komponencie okna.

## Zamknięcie uwag przez wykonawcę

P2-1: dodano cztery warianty testów okien edycji/usuwania punktu/maszyny po zakończeniu dostępu. Potwierdzają nieaktywne ponowienie/zapis, brak nowej mutacji oraz zachowanie oczekującego żądania.

P2-2: Outcome uzupełnia wyniki lint/typecheck i kryteria. Testy Admina pozostały bez zmian; nowe scenariusze przechodzą przez rzeczywisty współdzielony komponent i adapter publiczny.

Uwagi otwarte: brak. Zamknięcie wykonawcy nie stanowi ponownego audytu.
