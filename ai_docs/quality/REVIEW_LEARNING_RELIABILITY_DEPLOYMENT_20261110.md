---
title: Wdrożenie wydajności weryfikacji i gotowości uczenia
status: active
last_updated: 2026-11-10
---

# Wdrożenie TASK-1177–1178

Operator zaakceptował merge, push i restart potrzebnych usług w tym czacie.
Fast-forward main/origin do `bd99b5320419b1adbf58e790cfbfca1afa2374b5`
(v1.7.597) zawiera oba taski i wcześniejszy TASK-1179. Kolizje numerów
v1.7.594–595 z równoległej gałęzi zachowano bez przepisywania historii.
Konflikty dotyczyły tylko dwóch dokumentów stanu; pełne sekcje obu prac
zachowano, a okno ograniczono do dziesięciu wpisów. Migracja niepotrzebna;
preflight potwierdził zgodność głowy startowej i grafu Alembic.

Po zakończeniu preflightu 777 A2 (2201/2201) zatrzymano API, Admina i general
worker. Zapis stopped przekroczył początkowe 10s; po potwierdzeniu braku
procesów zakończono go osobno i dopiero wtedy uruchomiono jedną nową instancję.
API PID34400/port8000 zdrowe; Admin PID18772/port3000 HTTP200; general
PID13680/worker13856, budżet7. Reviewer pozostał uruchomiony bez zmian.

## Kontrole po synchronizacji

- 67 testów logiki/API PASS; 87 interakcji Admina PASS, w tym uczenie,
  odświeżanie i regresja podglądu importu TASK-1179.
- 8 testów rzeczywistych zapisów PostgreSQL PASS: zbiorcza akceptacja,
  liczniki, brak zdublowanych zdarzeń przy replay, konkurencyjny zapis,
  READ COMMITTED/REPEATABLE READ i krótkie blokady ownership/game/catalog.
- Admin production build/typecheck i SDK build PASS. docs:check PASS.
- Dwa wcześniejsze audyty terminalowe Opus5.5 mają PASS. Synchronizacja
  nie zmieniła audytowanego kodu backendu ani testu pełnego przepływu.

Ponowienie pełnego testu v4 nie otrzymało nowego PASS: pierwszą próbę
przerwał limit braku wyjścia, drugą limit115s. Druga doszła do prawdziwego
freeze i powiązania treningu/oceny w103s, lecz nie ukończyła cold replay
i końcowych asercji. Wcześniejszy PASS112.34s pozostaje dowodem sprzed
synchronizacji, nie jest przedstawiany jako nowy pomiar. Obie własne bazy
testowe usunięto po potwierdzeniu ich OID, journalu własności i0 połączeń;
nie przerywano sesji operatora. Ograniczony proces pierwszych unitów też
przerwano bez wyniku; normalny proces Windows zaliczył67 testów.

## Działająca aplikacja — tylko odczyty

- Mumie A2 `/grid-correction-learning/ready?recommendTrainingMode=true`:
  HTTP200, `canStart=true`, brak blokad,57.719s.195 zdjęć/362 ludzkie etykiety,
  TRAIN276 (201 użytych,75 nowych), VALIDATION53, REGRESSION21.
  Bufory63 zdjęcia/12 etykiet zachowane. Zalecane grid-only, ponieważ150
  zdjęć TRAIN jest częściowych. To gotowość danych, nie wynik treningu.
- Podgląd kohorty symboli HTTP200 w32.578s:4866 próbek,602 źródła,
  brak ostrzeżeń, brak missingAsset. Nie zamrażano kohorty operatora.
- Zachowana wcześniejsza operacja `07a5cbc4-f84b-491b-8683-f3f8939f8bcb`:
  completed,487/487 applied,0 konfliktów/failed/pending; GET0.062s.
  Nie tworzono nowych ocen człowieka ani nowej partii zatwierdzania.
  Wydajność nowej dużej partii operatora nie została tu zmierzona.

W logu API widać niezwiązany błąd serializacji istniejących jobów
`workflow=symbol_readability` jako AndroidBuildJobPayload. Ten kod nie był
zmieniany przez oba taski; nie naprawiano go przy wdrożeniu. Health oraz
wskazane odczyty Mumie A2 działają. Nie deklarujemy całego quality ani
wszystkich ekranów aplikacji jako PASS.

Nie uruchamiano treningu/GPU, nie zmieniano defaultu ani wag, nie
zatwierdzano arbitralnych symboli. Surowe logi, preflighty i odpowiedzi API:
`D:/game_predicotr/artifacts/review-learning-deployment-20261110/`.
Przed usunięciem scalonego worktree zachować jego artefakty i odpiąć trzy
junctiony bez usuwania ich celów. Pozostałe gałęzie zostają nietknięte.
