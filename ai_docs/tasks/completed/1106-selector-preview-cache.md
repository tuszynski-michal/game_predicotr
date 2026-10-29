---
title: Priorytet bieżącego zdjęcia i jeden obiekt podglądu
status: done
last_updated: 2026-10-29
---

# TASK-1106 — Priorytet bieżącego zdjęcia i jeden obiekt podglądu

## Status

`done`

## Goal

Jeden odczyt protokołu na cache miss i ten sam HTMLImageElement w cache oraz widoku, z kontrolowanym prefetch.

## Dependencies / entry conditions

TASK-1104 i TASK-1105 ukończone; HEAD baef7026, v1.7.499. Operator zatwierdził cały plan i koszt 3–5 h, testy i ZIP, bez merge/push. Audyty pominięte decyzją operatora.

## Recommended execution

`gpt-6.1-sol`, `medium`; ograniczony cache bitmap i cykl życia DOM. Naruszenie aktualności plików wymaga ponownej analizy na high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md` — reguły intencji, preview i TASK-1106.

## Scope

Aktywny JPEG przed sąsiadami, jeden obiekt DOM, maksymalnie ±3/7 entries, jeden decode prefetch i estymowany budżet 128 MiB. Wspólny sourceLookup z TASK-1105. Obsługa decode error, późnych odpowiedzi i zmiany źródła. Regresje zoom, scroll i fullscreen.

## Out of scope

Cache HTTP, zmiany JPEG, oryginałów, kontroli SourceRegistry/SHA, trwałych formatów, usług i ustawień ochrony. TASK-1107, merge i push. Trzy wcześniej wykazane timeouty native-checks pozostają poza zakresem.

## Acceptance criteria

- [x] Bieżący JPEG dekodowany przed prefetch; maksymalnie jeden decode prefetch.
- [x] Maksymalnie siedem entries w oknie ±3 i 128 MiB estymowanych bitmap; aktywny JPEG jest jedynym wyjątkiem.
- [x] Ten sam HTMLImageElement w cache i hoście; jeden request na miss, zero nowych requestów na decoded hit.
- [x] Późny decode, błędy i zmiana źródła nie ustawiają ready niewłaściwego JPEG-a.
- [x] Zachowane SourceRegistry/no-store/SHA oraz zoom, scroll, fullscreen i SelectionIntents.
- [x] Testy jednostkowe, prawdziwy Electron z licznikiem protokołu, lint/typecheck/build, fluency/shortcuts i docs/mapa.

## Technical notes

Klucz sourceId/imageId. Prefetch dopiero po gotowości aktywnego, najbliższe zdjęcia pierwsze. Po poznaniu wymiarów usuwanie najdalszych nieaktywnych bitmap. Nieznane wymiary mogą chwilowo przekroczyć budżet; aktywny większy od budżetu wyłącza prefetch. Limit dotyczy cache, bez gwarancji RSS. Zmiana bootstrapu źródła i unmount zwalniają elementy i referencje. Brak pytań blokujących; implementacja zgodna z zaakceptowanym planem.

## Expected files

Istniejące: `apps/selector-desktop/src/renderer/image-viewer.tsx` (ImageViewer), `src/renderer/style.css`, `scripts/smoke-fluency.mjs`. Nowe: `src/renderer/preview-cache.ts` (PreviewCache), `test/preview-cache.test.mjs`. Dokumentacja wymagań/architektury, plan, mapa i stan.

## Test cases

Miss/hit i tożsamość elementu, aktywny przed prefetch, max jeden prefetch, błędy, szybkie ±, wyparcie, duży JPEG, source replacement, close; rzeczywisty protokół i zoom/scroll/fullscreen.

## Verification

Celowane testy node, lint, typecheck, selector:build, smoke-fluency --local, smoke-shortcuts --local, docs:check i code-map:check. Każde polecenie z timeoutem ≤120 s.

## Risks / open questions

Jednorazowy decode nieznanego wymiaru może przekroczyć estymatę. Chromium nie gwarantuje synchronicznego zwolnienia RSS. Odbiór fizycznego Windows i komputera operatora pozostaje osobny.

## Outcome

Commit: v1.7.500 / `a081e9213717bb5af7c0930bc8a9721633059323`.

### Changed

- `PreviewCache` utrzymuje rzeczywiste HTMLImageElement, parę sourceId/imageId i wspólny sourceLookup. Host widoku otrzymuje ten sam element; hit nie wywołuje src ani decode ponownie.
- Aktywny JPEG ma pierwszeństwo, sąsiedzi są dekodowani szeregowo po gotowości aktywnego. Okno ±3/7 entries, estymata bitmap 128 MiB, wyjątek aktywnego i natychmiastowe usuwanie nadmiaru po poznaniu wymiarów. Duży sąsiad nie powoduje pętli decode/evict.
- Generacja celu, tożsamość entry i unieważnienie bootstrapu chronią późne odpowiedzi oraz nowe źródło z tymi samymi imageId. Unmount usuwa DOM/src/cache. Błąd aktywnego JPEG-a nadal trafia do SelectionIntents.
- Zoom, obie osie scrolla i fullscreen używają tego samego elementu DOM. Protokół no-store, SourceRegistry i pełne SHA accept pozostały bez zmian.

### Verification results

Wszystkie polecenia kontrolowane, timeout ≤120 s:

- `node --experimental-strip-types --test test/preview-cache.test.mjs`: **7/7 PASS** (priorytet, serial prefetch, tożsamość/hit, ±3, wyparcie, duży aktywny/sąsiad, błędy, spóźniony decode, source replacement, szybka zmiana celu, clear).
- `test/selection-intents.test.mjs`: **18/18 PASS** w celowanym wywołaniu wraz z cache/workspace. Dwa testy native workspace w tym ograniczonym środowisku zgłosiły `NATIVE_CHECK_FAILED`; ponowienie ich poza ograniczeniem poniżej zaliczone.
- `node --experimental-strip-types --test --test-concurrency=1 test/workspace-updates.test.mjs test/renderer-contracts.test.mjs`: **10/10 PASS**, z rzeczywistymi kontrolami Windows.
- `node --experimental-strip-types --test --test-name-pattern "^(recursive JPEG|junctions are rejected|a directory replaced)" test/foundation.test.mjs`: **3/3 PASS**; odczyt opaque id, zmieniony JPEG, źródło/descendant junction po indeksowaniu.
- Lint selektora, typecheck i build: **PASS**. Formatowanie zmienionych plików: **PASS**.
- `node scripts/smoke-fluency.mjs --local`: **PASS** w nowym procesie Electron. `session.defaultSession.webRequest.onCompleted` liczy faktyczne selector-photo requests, bez modyfikacji handlera bezpieczeństwa. photo1/photo2 dokładnie po jednym żądaniu po 1→2→1; porównanie ścisłej tożsamości obiektu z decode i img w DOM. Zoom 100–3000%, obie osie scrolla i native fullscreen PASS. IPC/fallback, pinned F, decode cancellation, utrata odpowiedzi, crash/reopen z SHA/manifestem, błędny JPEG oraz close/timeout/retry PASS.
- Smoke przystosowano do braku ponownego decode hitów: bariery wymagają jawnego wyparcia zdjęcia. Fixture ma 8 małych JPEG-ów, z photo6 uszkodzonym; zdjęcie1 800×600 jak w istniejącym smoke-packaged umożliwia sprawdzenie scrolla. Wcześniejszy test zakładał, że uszkodzony plik jest ostatni (ArrowRight ograniczany do końca); po rozszerzeniu fixture poprawiono nawigację według odzyskanego ordinalu.
- `node scripts/smoke-shortcuts.mjs --local`: **PASS**, w tym obie numeracje, skróty, błędny JPEG i natywny relink po restarcie. Pierwsze wykonanie zaliczyło asercje, ale teardown trafił w `SHUTDOWN_PENDING`: snapshot native kończył się przed wyzerowaniem busy adaptera relink. Dodano oczekiwanie na odblokowanie przycisku Zamknij projekt, następnie smoke przeszedł. Własne procesy testowe zakończone; bez zmiany produktu i limitów.
- `npm run docs:check`, `npm run code-map:check`: **PASS** po zamknięciu taska.

### Not completed

- Audyt Claude pominięty jawną decyzją operatora 2026-10-29; bez niezależnego werdyktu PASS.
- Pełny zestaw selektora, pomiary odbiorcze i ZIP należą do TASK-1107. Nie uruchamiano benchmarków, usług, merge/push ani operacji na oryginałach.
- Fizyczny restart Windows i odbiór na innym komputerze pozostają pending. Limit 128 MiB jest estymatą cache, bez gwarancji szczytowego RAM ani synchronicznego zwolnienia RSS.
- Dwa wcześniejsze usunięcia artefaktów i obcy worktree zachowane poza commitem. Trzech znanych timeoutów native-checks nie uruchamiano ani nie zmieniano.

### Documentation updates

Wymagania i architektura podglądu, zaakceptowany plan (status), mapa kodu i CURRENT_STATE. Wszystkie sześć kryteriów akceptacji oraz właściwe punkty Definition of Done spełnione; bez API/migracji i nowych zależności runtime.

### Recommended next task

TASK-1107 — dowody płynności, diagnostyka i sprawdzona paczka; nie rozpoczęto w tym tasku.
