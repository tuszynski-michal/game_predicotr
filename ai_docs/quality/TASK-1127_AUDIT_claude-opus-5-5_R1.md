Historyczny raport R1. P1-1 zamknięte w raporcie R2 `TASK-1127_AUDIT_claude-opus-5-5.md`; P2 rozliczone w Outcome.

# Audyt TASK-1127 — Manifest wymiany źródeł

Werdykt: REVISE

- Audytor: claude-opus-5-5 / high
- Wykonawca: gpt-6-astra / high
- Zakres: B1 i ręczne miejsca integracji, HEAD `5b260fc2` (v1.7.522), data 2026-11-03
- Runda: 1

Przegląd był statyczny i tylko do odczytu. Nie zmieniłem żadnego pliku, nie uruchomiłem testów ani usług.

## Streszczenie

B1 w większości spełnia kontrakt. Manifest jest zapisywany przed jakimkolwiek wycofaniem. Token obejmuje cały dokument, a nie liczniki. Ponowienie dokładnej komendy zwraca pierwotną odpowiedź, zanim nastąpi sprawdzenie dryfu. Batch, wpisy, aliasy i potwierdzenie zapisują się w jednej transakcji. DELETE w nowym trybie odmawia, a zapytania planned nie uruchamiają odzyskiwania artefaktów. RLS jest wymuszone (FORCE) na tabelach i partycjach. Klucz idempotencji w UI zapisuje się w localStorage przed wysłaniem żądania.

Blokuje jedna luka P1 w łańcuchu dowodu jakości. Występuje na przejściu ze starych ocen do nowego rejestru: późniejsza ocena pending/skipped może skasować starą rozstrzygniętą ocenę.

## Znaleziska

### P0
Brak.

### P1

**P1-1. Późniejsza ocena pending/skipped kasuje starą rozstrzygniętą ocenę**
- `domain/source_replacement.py:41-57`
- `storage/symbol_readability.py:479-510`
- `storage/source_replacement_decisions.py:27-32`

`label()` nadpisuje `symbol_readability_items.state` w miejscu. Nowy rejestr zapisuje tylko nowy stan, bez stanu poprzedniego. `qualification()` sięga po stare oceny, gdy w rejestrze nie ma rozstrzygającej oceny dla bieżących pikseli. Liczy wtedy tylko te stare wiersze, które *teraz* mają stan readable/unreadable.

Przykład:
1. Przed rejestrem przebieg R1 ma ocenę readable, a R2 unreadable. To konflikt, więc działa blokada.
2. Operator zmienia ocenę R1 na `skipped`.
3. W rejestrze jest tylko `skipped`, a stary wiersz R1 wypada z porównania.
4. Zostaje sama ocena unreadable. Blokada znika, a pole staje się powodem wymiany.

**Skutek:** pole, które człowiek uznał za czytelne, trafia do planu jako powód wymiany. Narusza to dwie zasady kontraktu: pending/skipped nie kasuje rozstrzygnięcia, a konflikt daje blokadę i wymaga świeżej oceny. Poprzedniego stanu nie da się potem odtworzyć. Warunek: `ReadabilityLabelRequest` dopuszcza `skipped`/`pending`. Wskazuje na to CHECK w tabeli rejestru, ale schematu żądania nie czytałem.

**Poprawka:** przy pierwszym wpisie do rejestru dla danej pary pole/przebieg zapisać w wierszu poprzedni stan i rewizję, gdy stara pozycja była już oceniona (np. pola `prior_state` i `prior_revision`). W ścieżce starych ocen `qualification()` powinna liczyć ten poprzedni stan zamiast nadpisanego. Bez tej informacji wynikiem ma być `SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS`. Potrzebny jest test jednostkowy i test PG.

### P2

**P2-1. Puste ciało żądania daje 500 zamiast 422** (`main.py:988-997`)

Zależność wywołuje `await request.json()` przed walidacją ciała przez FastAPI. Legacy DELETE `/board-sources` lub preview bez ciała kończy się `JSONDecodeError`, czyli 500. Wcześniej taki błąd wracał jako 422.

**Poprawka:** łapać `ValueError` i przyjmować `replacement_request=False`, żeby odzyskiwanie się wykonało, a walidację zostawić FastAPI.

**P2-2. Legacy cleanup na źródle z planu kończy się surowym błędem bazy** (`0174_source_replacement.py:107, 172-180`)

Klucze obce RESTRICT z `source_replacement_entries/sources` są zgodne z kontraktem. Legacy preview nie pokazuje jednak tej zależności, więc legacy DELETE źródła objętego planem kończy się surowym naruszeniem klucza obcego. Rollback i przywracanie artefaktów działają. Nie sprawdzałem, jak ten błąd jest mapowany na odpowiedź HTTP.

**Poprawka:** dodać kodowaną blokadę w istniejącym legacy preview/delete (bez drugiego grafu usuwania) oraz test.

**P2-3. Każdy błąd wymiany źródeł dostaje 409** (`main.py:2510-2516`)

409 dotyczy także `SOURCE_REPLACEMENT_NOT_FOUND` i `SCOPE_LIMIT`. Semantycznie poprawne byłoby 404/422. UI i tak czyści zapis przy każdym 4xx, więc to nie blokuje.

## Pokrycie kryteriów

| Kryterium | Stan |
|---|---|
| Dokładne sourceIds, cała historia plansz, numerów i rewizji, bez dziewiątek, zakres 1..2 | OK `storage:98-183` |
| Aliasy tylko w tej samej grze, z tym samym SHA i zakresem; niejednoznaczność, obce canonical i pending (w tym geometria) blokują | OK `storage:112-221` |
| Preview z mode na istniejącym endpoincie, POST/GET/export, DELETE odmawia | OK `cleanup.py:116-251` |
| Planned bez odzyskiwania artefaktów, bez zmiany current/canonical | OK `main.py:985-1002` |
| Token całego dokumentu, expectedRevision 0, replay przed dryfem, jedna transakcja | OK `storage:378-474` |
| Brak rezerwacji i wycofanych wierszy w B1 | OK |
| Rejestr: ordinal pod blokadą EXCLUSIVE, unique, atomowy, bez FK do pola | OK `decisions:26-44`, `0174:157-169` |
| Chronologia rejestru i stare oceny | **P1-1** |
| Zmiana pikseli nie dziedziczy oceny | OK (filtr tożsamości wycinka) |
| 0174: RLS FORCE, partycje, indeksy, FK aliasów i slotów, manifest v21 | OK `0174:79-245` |
| UI: checkboxy, preview, jawny zapis, lista, eksport | OK |
| UI: localStorage przed siecią, retry, 4xx, uszkodzony zapis | OK `panel.tsx:103-217` |
| Wrapper rozróżnia nowy tryb od legacy | OK `index.ts:4609-4645` |

## Listy zamknięte i otwarte

**Zamknięte:** replay i idempotencja, dryf preview, aliasy i krótki zakres, obce pending i canonical, nienaruszalność rejestru (trigger), brak odzyskiwania dla planned, reload i uszkodzony zapis w UI, rozdzielenie unii schematów (`ApiModel` ma `extra="forbid"`).

**Otwarte:** P1-1 oraz P2-1 do P2-3.

## Proponowane testy

1. Unit + PG dla P1-1: stare R1 readable i R2 unreadable, potem w rejestrze R1 `skipped`. Oczekiwana blokada albo readable z poprzedniego stanu, w żadnym razie powód unreadable.
2. HTTP: legacy DELETE i preview bez ciała powinny dać 422, nie 500.
3. PG: legacy DELETE źródła z zapisanego planu powinien dać kodowany błąd, rollback i nienaruszone artefakty.

## Zakres przeglądu i ograniczenia

Wykorzystałem 15 z 16 dozwolonych wywołań. Czytałem cały kod domeny, storage, 0174 i pliku decisions, panel, wskazane fragmenty `cleanup.py`, `main.py`, `index.ts` i `symbol_readability.py`. Z testów i schematów przejrzałem tylko nazwy i konfigurację (grep).

Nie czytałem: treści testów, migracji 0173 i manifestu v21, `AGENTS.md` (limit wywołań), schematów żądań wymiany źródeł ani kolumny `image_sequence_canonical.source_image_id`. Kolumnę przyjmuję jako istniejącą na podstawie zgłoszonego PASS testów PG.

Zgłoszonej weryfikacji wykonawcy nie sprawdzałem. Kodu upstream grid correction nie audytowałem.
