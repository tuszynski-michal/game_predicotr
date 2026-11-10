---
title: TASK-1176 — Bieżąca weryfikacja domknięcia symboli
status: accepted
last_updated: 2026-11-10
---

# TASK-1176 — Stan wykonania

Poniżej zachowano historyczny odbiór kodu przed integracją. Wdrożenie i pełna
partia zakończyły się 2026-11-10; wynik operacyjny znajduje się na końcu raportu.
Nowe niekwalifikowane piny oznaczają cel ręcznej weryfikacji symboli, bez
zmiany kwalifikacji modelu. Zapis wykorzystuje istniejący automatic=True,
renderer full-cell-v2 i klasyfikator źródłowego snapshotu, bez human approval.
Stare piny pozostają czytane według swoich wersji i blokad.

## Historia i aktualny stan

Pierwszy etap zatrzymano na limicie15min. Operator następnie jawnie wycofał
limit i zatwierdził dokończenie oraz konkretny pakiet do Anthropic.
Wyniki poniżej zastępują wcześniejsze częściowe podsumowania.
44 testy historycznych pinów/backendu PASS;2 błędy starych Mock scalars/mappings
odtworzono także na main (`artifacts/t1176-baseline.log` w głównym checkout).
Nie naprawiano tych niezwiązanych fixture dla zielonego wyniku.
6219 operatorowych plansz pozostaje niezmienione; wdrożenie nie nastąpiło.

Opus R1: REVISE, P0-1/P1-1; raport i receipt zachowane. Jedna runda poprawek
i skupiony R2 zakończone. R2: PASS,0 otwartych P0/P1, zgodne SHA pakietu
9f8e4077… i receipt. Główny model potwierdzony przez CLI: claude-opus-5-5;
high jest parametrem żądanym, bez osobnego potwierdzenia backendu.
Zachowano oba raporty. P2-5/P2-6 jawnie przyjęte w Outcome taska.

## Odbiór po wznowieniu

Implementacja wykorzystuje ten sam produkcyjny renderer i klasyfikator.
Nowy cel `v3-symbol-review-v1` przypina pinv4 i
`neural-symbol-review-v1`. Brak kalibracji nie blokuje przygotowania danych
do ludzkiej weryfikacji. `FIT_OUTLIERS` pozostaje ostrzeżeniem;
`FIT_FAILED`, wadliwe piksele, topologia, źródło i własność nadal blokują.
Zapis nie tworzy human approval, nie kwalifikuje automatu i nie zmienia wag.
Nowe importy i reinferencja wybierają politykę z pinu: v4→review, v3→kalibracja.
Para review z inną wersją pinu jest odrzucana przed zapisem. Historyczne
joby i przygotowane wcześniej operacje nie zmieniają wersji polityki.

Wyniki końcowej implementacji przed audytem:

- 117 testów API/workera PASS po poprawkach R1, `artifacts/unit.log` (16,32s).
- 3 testy PostgreSQL PASS, `artifacts/pg.log` (32,19s): rzeczywiste adaptery
  importu i zapis, renderer, komórki pending, 0%, brak human approval, dokładny
  odczyt pinu do ponowienia, istniejące deferred przez LocalJobWorker oraz
  replay w nowym interpreterze i widoczność30 pending przez produkcyjne
  zapytanie weryfikacji symboli. Trzeci test zachowuje zakwalifikowany pinv3,
  politykęv4 i kontrolę dowodów kalibracji w rzeczywistym checkpoincie.
  Baza testowa została usunięta przez fixture.
  Wynik inferencji geometrii w fixture jest kontrolowany; to test integracji,
  nie pomiar jakości modelu.
- 163 testy klienta i build SDK PASS (`artifacts/sdk.log`), typecheck SDK PASS
  (`artifacts/types.log`). Wrapper zachowuje nową politykę, bez nowego endpointu.
- OpenAPI i wygenerowany klient odzwierciedlają nowe tokeny.
- Ruff format/check PASS, `artifacts/format.log`, `artifacts/lint.log`.
- `docs:check` PASS (43474/45000B startup, 16122B okno), `code-map:check` PASS.
- Scoped mypy: 10 zmienionych modułów, jeden wcześniej znany błąd przypisania
  typu w `_current_row`, `virtual_grid_geometry_repository.py:2927`.
  Ten sam zastany błąd opisuje odbiór TASK-1175; nie osłabiano konfiguracji.
  Odczyty torch pominięte wyłącznie w lokalnym configu kontrolnym, globalny
  pyproject bez zmian. Nie jest to pełny gate projektu.

## Istniejące zestawy PostgreSQL — wymagane przez R1

`test_grid_reinference_postgres.py`: wykonano wszystkie23 przypadki w czterech
rozłącznych grupach i skupionym ponowieniu poprawionego fixture deferred.
Końcowo21 PASS,2 zastane FAIL. Logi `artifacts/pg-reinf{,2,3,4}.log` oraz
`artifacts/pg-reinf-deferred.log`. Zakres obejmuje też rollback/retry,
manual sibling, anulowanie, historyczne źródło i kolejki. Nie nazywamy całego
modułu zielonym; dwa pozostałe problemy leżą poza kierowaniem symboli:

- cleanup_reset: reset usuwa review przed zależnymi cell rows (23503).
  Odtworzony na niezmienionym main94c5bc6d przez rzeczywisty CleanupService,
  z importem starej politykiv2/8%: `artifacts/baseline-reset.log` (1 test PASS
  potwierdzający oczekiwany błąd), `artifacts/baseline-reset-FK.json`.
- superseded_preview: stary fixture przypina manifestv19 przy wymaganymv22.
  Ten sam FAIL na main: `artifacts/baseline-reinference-focused.log`.

Baseline main potwierdził również zastaną TypeError atrapy recognize
(`artifacts/baseline-reinference-accepted.log`) oraz niemożliwy fixture
deferred_stats (pełny v2 binding przy brakującej detekcji). Dostosowano tylko
atrapy i faktyczny pin historycznego importu, zachowując asercje ochrony
człowieka, statystyk, kolejności i trwałości. Deferred końcowo PASS.

`test_grid_geometry_proposals_postgres.py`:13 FAIL na gałęzi (63,93s)
i dokładnie te same13 FAIL na main (80,31s), przed wejściem w workflow:
stary budżet tabel fixture nie kończy provisioning po rozszerzeniu schematu.
Logi `artifacts/pg-proposals.log`, `artifacts/baseline-proposals.log`.
Nie zmieniano niezwiązanego fixture ani produkcyjnego provisioning/resetu.

Pierwsza szeroka próba baseline reinferencji osiągnęła limit120s, bez
pełnego wyniku. Po odczycie stanu własnego procesu usunięto dokładnie
zarejestrowaną, nieaktywną bazę testową; dalsze próby były ograniczone.
Dwie awarie teardown podczas niezaliczonych prób również posprzątano po
sprawdzeniu OID i braku połączeń, istniejącym mechanizmem receipts.
Końcowe scenariusze mają cleanup receipts z databaseRemaining=0.
Żadna baza ani usługa operatora nie została zmieniona.

## Rzeczywiste dane — tylko odczyt

- Zamrożony manifest691 zdjęć: 6219/6219 propozycji spełnia techniczne warunki
  nowej polityki review. Bez blokad struktury, zakresów i widoczności.
  `artifacts/batch-preview.json`. To nie jest ocena poprawności symboli,
  aktualnej własności ani dopuszczenie automatu; są ponownie sprawdzane przy zapisie.
- Jedno istniejące zdjęcie, source `4d381d15-63fc-4cc3-90f6-f3acefd4d053`,
  od sekwencji146440: `_prepare_source` z produkcyjnym rendererem i rzeczywistym
  `spatial-symbol-cnn-onnx-v1` dało135 predykcji z9 plansz i padding0%.
  Jawna transakcja READ ONLY. Bez zapisu geometrii, klas lub ocen.
  `artifacts/real-classifier-preview.json`; wynik nie jest human ground truth.

## Warunki wdrożenia — zapis sprzed integracji

Audyt i odbiór kodu zakończone. Operator polecił dokończyć całość z audytami
i wyraził zgodę na wszystko poza scaleniem, o które mamy zapytać na końcu.
Restart API/general workera i przetworzenie partii są zatem zatwierdzone
w bieżącym zadaniu; pozostają zależne od osobnej zgody na merge/push.
Po niej uruchomić nową, przypiętą operację
reinferencji dla deferred tylko importu `bf601495-df47-45e4-ae5d-8b98176fb46f`.
Bez migracji schematu. Stary import/retry zachowuje starą politykę, więc nie
należy go przepisywać. Użyć nowej operacji istniejącego API: przygotowanie,
manifest, freeze, pilot, a następnie zatwierdzony szeroki zakres.
Ręcznie zmienione pozycje pozostają chronione. Docelowe symbole są pending,
oceniane przez istniejącą weryfikację (także „Zła siatka” i „Nieczytelne”).
Nowe stagingi przechodzą przez tę samą politykę w nowym procesie importu;
test żądania start/replay potwierdza token, pełne pola i brak duplikatu joba.
Nie deklarujemy ukończonego przetworzenia6219 przed odbiorem wdrożenia.

Logi i pakiety audytów przed usunięciem worktree są zachowywane w głównym
checkout, `artifacts/symbol-review-routing-20261109/` (ścieżki powyżej
wskazują pliki wewnątrz tej kopii, jeżeli worktree już nie istnieje).


## Odbiór wdrożenia — 2026-11-10

Operator jawnie zaakceptował merge/push, cleanup, restart potrzebnych usług
i przetworzenie6219. Fast-forward v1.7.591–592 do main oraz push origin
zakończone; kod wdrożenia: `6da65caa38e948f8815c4d83a13a935e55ce65b6`.
Gałąź codex/symbol-review-routing i jej worktree usunięte po odpięciu
junction, z zachowaniem wspólnych zależności oraz pozostałych worktrees.
Migracja nie była potrzebna (head0183). API i general worker z7 wątkami
uruchomione z main; Admin/Reviewer bez zbędnego restartu, HTTP200.
Reviewer pozostał lokalny. Domyślny model i MumieA2 nadal3ed60010/rev2;
nie uruchamiano treningu ani nie kwalifikowano automatu.

Istniejące API przygotowania/freeze/start wykonało dwa przypięte przebiegi
z selektorem deferred tylko importu bf601495-df47-45e4-ae5d-8b98176fb46f:

- Pilot d0a0a019-0647-41b3-bc07-b2e91f27fa58:100 zdjęć,900 plansz,
  13500 symboli; completed, wyłącznie automatic_written.
- Szerszy041bb1a9-1a80-4cff-bb10-90436f0dd64f:591 zdjęć,5319 plansz,
  79785 symboli; completed, wyłącznie automatic_written. Przypięty raport
  pilota oraz jawne broadScopeConfirmed; żadnej zmiany starego pinu importu.

Końcowy odczyt w nowym procesie i produkcyjne API potwierdzają:

- 691 zdjęć,6219 unikalnych numerów plansz,93285 komórek pending/model/full.
- Wszystkie93285 aktualnych specyfikacji renderowania mają paddingFraction0.0.
- 6219 dawnych deferred ma status resolved; zero nowych human approvals.
- API weryfikacji symboli zwraca allCount93285, pendingCount93285,
  approvedCount0. Podgląd rzeczywistego symbolu: HTTP200 image/webp.
- Zachowano1000 różnych zdjęć pierwotnej partii, bez duplikatów źródeł.
- Porównanie przed/po:788 wcześniejszych źródeł,293 ręcznie zatwierdzone
  plansze,1774 wcześniejsze rewizje źródłowe i295 rewizji plansz niezmienione.
- Powtórzenie identycznej komendy start zakończonego pilota zwraca ten sam
  operationId/jobId, raport i liczniki; bez nowego joba i komórek.
- API, Admin i lokalny Reviewer odpowiadają HTTP200; worker bez błędów.
  docs:check po integracji i po uzupełnieniu tego odbioru PASS.

To odbiór przepływu i dostępności propozycji, nie93285 ludzkich ocen jakości.
Złe siatki i nieczytelne symbole operator może oznaczać w istniejącej
weryfikacji symboli, bez wcześniejszego zatwierdzania każdej geometrii.

Dowody: root `artifacts/symbol-review-deployment-20261110/RESULT.json`,
`statistics-final.json`, `preservation-before.json`, `preservation-after.json`,
`pending-symbols-final.json`, `queue-counts-final.json`, `pilot-replay.json`,
`broader-latest.json` oraz komendy i odpowiedzi HTTP. Audyt kodu pozostaje
Opus R2 PASS; niniejszy dopisek opisuje operacje, bez zmian implementacji.
