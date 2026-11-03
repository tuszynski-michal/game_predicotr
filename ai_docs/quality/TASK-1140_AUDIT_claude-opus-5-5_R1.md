---
title: Audyt TASK-1140
status: active
last_updated: 2026-11-03
---

# Audyt TASK-1140 — Czytelny panel przyrostu korekt i aktualności oceny

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...3562ab1a868ae26cb2c36bf453197c1790561015 oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przeczytałem zmiany w panelu uczenia, panelu zastosowania, etykietach przyczyn, nowych testach interakcji oraz fragmentach ADMIN_APP i VISION_LAB. Porównałem je z kontraktem klienta i z backendem `grid_model_evaluation.py` oraz `grid_correction_apply.py`. Liczniki pochodzą z backendu i są dobrze rozdzielone. Jawne sprawdzenie aktualności ma poprawny synchroniczny guard, generacje odpowiedzi i działa fail closed. Główny problem jest gdzie indziej: nowa flaga `evidenceBlocked` blokuje w `send()` każde polecenie panelu zastosowania. Obejmuje to wznowienie częściowo wykonanego zastosowania oraz idempotentne ponowienie zapisanego polecenia, czego backend celowo nie wiąże z aktualnością oceny. W rzeczywistym przebiegu z oceną jest to regresja, a obecne testy jej nie wykrywają.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx:224` (także `:276` i `:501`) — Warunek `if (locked.current || evidenceBlocked) return;` obejmuje wszystkie rodzaje `Command`, a nie tylko nowe `apply`.
  - Ten sam `disabled` blokuje przycisk „Wznów zastosowanie” (`:501`).
  - Przycisk „Ponów zapisane polecenie zastosowania” (`:305–312`) ma tylko `disabled={busy}`, więc pozostaje aktywny, ale kliknięcie nic nie robi i nie pokazuje komunikatu.
  - Backend `resume()` (`services/api/src/game_predictor_api/application/grid_correction_apply.py:384–421`) nie sprawdza aktualności oceny. Celowo kończy przebieg z zachowanymi receiptami (`:424–428`). Ponowienie startu z tym samym `idempotencyKey` także nie powinno zależeć od lokalnej blokady.
  - Skutek: operacja przerwana po publikacji, ale przed przypisaniem gry, utknie w UI, gdy dowód oceny stanie się `stale`. Jeśli przyczyną jest zmieniona etykieta (`GRID_COHORT_LABEL_STALE`), dowód tego raportu nigdy nie wróci do `current`, więc wznowienie z panelu staje się trwale niemożliwe. Przebieg po utracie odpowiedzi też nie da się ponowić, a operator nie wie dlaczego.
  - Poprawka: stosować `evidenceBlocked` tylko do nowego `kind: 'apply'` bez zapisanego `pending`, czyli do przycisku „Zastosuj wersję” i checkboxów zakresu. Wznowienie i replay zapisanego polecenia mają pozostać zależne od backendu.

- [P1-2] `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:1247–1272` i `:1274–1304` — Istniejące testy wznowienia i ponowienia zastosowania używają fixture `run` z `evaluationId: null` (`:51`). W tym układzie `evidenceBlocked` zawsze daje `false`. Rzeczywisty przebieg PASS z możliwym zastosowaniem zawsze ma `evaluationId`, bo backend `_evidence` go wymaga (`grid_correction_apply.py:71–76`).
  - Skutek: nowa zmiana zachowania wznowienia nie jest objęta żadnym testem. Regresja z P1-1 przechodzi 34/34.
  - Poprawka: dodać wariant z `evaluatedRun` i oceną `stale`. Test ma pokazać, że „Wznów zastosowanie” i „Ponów zapisane polecenie zastosowania” wywołują odpowiednio `resumeGridCorrectionApply` i `startGridCorrectionApply`, a „Zastosuj wersję” pozostaje zablokowane.

### P2

- [P2-1] `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:1009` — Kryterium „wyłącznie GET” sprawdza tylko nazwy metod regexem `/^(get|list|preview)/`. Ten regex przepuszcza także `previewGridCorrectionLearning`, który jest POST z body (`packages/admin-api-client/src/index.ts:1600–1608`).
  - Testy zmiany wyboru przebiegu (`:1184–1245` i `:1288–1352`) w ogóle nie sprawdzają braku wywołań innych niż GET po przełączeniu.
  - Skutek: przypadkowy automatyczny POST podglądu przy otwarciu albo zmianie wyboru przeszedłby niezauważony.
  - Poprawka: zawęzić dozwoloną listę do jawnie nazwanych metod GET (`previewGridCorrectionApply` zamiast prefiksu `preview`). Dodać tę asercję także po zmianie wyboru.

- [P2-2] `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:220–269` — `open()` ustawia `evaluationReading(true)`, ale nie zdejmuje go, gdy GET przebiegu albo oceny zakończy się błędem (rzucony wyjątek przed `:262`/`:267`).
  - Skutek: przycisk „Sprawdź aktualność oceny” pozostaje wyłączony, a zastosowanie zablokowane aż do ręcznego „Odśwież stan uczenia”. Panel nie wyjaśnia, dlaczego przycisk jest nieaktywny. Działa to fail closed, więc ryzyko jest akceptowalne.
  - Poprawka do rozważenia: komunikat przy przycisku wskazujący odświeżenie stanu. Można też zostawić stan „czytanie” i tylko opisać ścieżkę ponowienia.

- [P2-3] `ai_docs/architecture/VISION_LAB.md:75–103` — Niezacommitowany diff tego pliku zawiera także sekcje TASK-1139: „Incremental correction split (D-582, TASK-1139)” i opis `grid_correction_progress.py`.
  - Skutek: ryzyko, że commit TASK-1140 zabierze hunki należące do TASK-1139 albo odwrotnie.
  - Poprawka: lead commituje TASK-1139 osobno przed TASK-1140, zgodnie z granicą hunka opisaną w `ai_docs/quality/TASK-1140_VERIFICATION.md`. Przed commitem trzeba to sprawdzić przez `git diff --cached`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Liczniki z backendu, bez mieszania rezerwy z kontrolami | spełnione | `grid-correction-learning-panel.tsx:973–1041` (wiersze bezpośrednio z `progressCounts`), test `grid-correction-learning-panel.test.mjs:925–982` |
| Wzrost TRAIN i nowe/użyte dane czytelne; kontrola nie zwiększa TRAIN | spełnione | `grid-correction-learning-panel.tsx:980–990`, test `grid-correction-learning-panel.test.mjs:959–977` |
| Otwarcie i zmiana wyboru wyłącznie GET | spełnione w kodzie; testy słabe (P2-1) | `grid-correction-learning-panel.tsx:220–270`, `grid-correction-apply-panel.tsx:195–210`; test `:1009` |
| Stale → jawne sprawdzenie → odczyt oceny i nowego podglądu; zmieniona etykieta blokuje | spełnione | `grid-correction-learning-panel.tsx:272–351`, `grid-correction-apply-panel.tsx:121–122, 148`; testy `:984–1114` |
| Loading/double click, błędy/retry, utrata i spóźnione odpowiedzi w testach | spełnione | testy `:1116–1488`; guard `grid-correction-learning-panel.tsx:273–280, 286–289` |
| Regresje TASK-1138 oraz scoped lint/typecheck/build PASS | niezweryfikowane | Wynik deklarowany przez wykonawcę (34/34, 68/68, ESLint, tsc, build); testów nie uruchamiałem. Istniejące testy wznowienia nie obejmują przypadku z P1-1/P1-2. |
| Dokumentacja, mapa kodu, docs:check i niezależny audyt przed commitem | niespełnione (otwarte u leada) | Checkbox niezaznaczony w pliku taska; ADMIN_APP i VISION_LAB uzupełnione; mapa kodu i `docs:check` niewykonane |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3.

## Proponowane testy

- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: przebieg `evaluatedRun` z oceną `stale` i częściowym zastosowaniem `failed`. Test sprawdza, że „Wznów zastosowanie” wysyła `resumeGridCorrectionApply`, a „Zastosuj wersję” pozostaje zablokowane. Komenda: `npx tsx --tsconfig apps/admin/tsconfig.growth-local.json --test apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`.
- Ten sam plik: utracona odpowiedź `startGridCorrectionApply` przy `evaluatedRun`, potem ocena `stale` po remount. „Ponów zapisane polecenie zastosowania” wysyła identyczne polecenie z tym samym `idempotencyKey`.
- Ten sam plik: po zmianie wyboru przebiegu wszystkie wywołania należą do jawnej listy metod GET (bez prefiksu `preview`).
- Ten sam plik: błąd GET oceny w `open()` utrzymuje blokadę i pokazuje ścieżkę ponowienia przez odświeżenie.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief audytu z pełnym diffem;
- `grid-correction-learning-panel.tsx` w części `Learning` (linie 60–480), nowy blok aktualności, propsy przekazywane do zastosowania i `LearningProgress`;
- cały `grid-correction-apply-panel.tsx`;
- wygenerowane typy `GridCorrectionLearningProgressCounts`, `GridModelEvaluationCurrentness` i `GridModelEvaluationCurrentnessResult`;
- wrapper klienta dla `previewGridCorrectionApply`, `previewGridCorrectionLearning` i `verifyGridModelEvaluationCurrentness`;
- w backendzie `verify_currentness` i widok oceny z pustym `currentness` dla niezakończonej oceny (`grid_model_evaluation.py`) oraz `_evidence` i `resume` (`grid_correction_apply.py`);
- istniejące testy wznowienia i ponowienia zastosowania.

Nie uruchamiałem testów, lintu, typecheck ani builda. Wyniki 34/34, 68/68 oraz PASS dla ESLint, tsc i builda podaje wykonawca, nie sprawdzałem ich. Nie sprawdzałem `docs:check`, `code-map:check`, CURRENT_STATE ani DOC_INDEX, bo należą do leada. Nie oceniałem kontraktu TASK-1139 poza typami potrzebnymi UI. Nie sprawdziłem w działającej aplikacji, czy częściowe zastosowanie z nieaktualnym dowodem faktycznie występuje operacyjnie. P1-1 wynika z porównania kodu UI z backendową ścieżką `resume`.
