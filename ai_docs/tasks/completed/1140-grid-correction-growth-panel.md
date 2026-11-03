---
title: Czytelny panel przyrostu korekt i aktualności oceny
status: done
last_updated: 2026-11-03
---

# TASK-1140 — Czytelny panel przyrostu korekt i aktualności oceny

## Status

`done`

## Goal

Panel pokazuje backendowy przyrost TRAIN i chronione kontrole oraz umożliwia jawne sprawdzenie aktualności zakończonej oceny przed zastosowaniem modelu.

## Context

Zatwierdzone korekty nie są równoznaczne z przykładami TRAIN. Historyczny PASS może wymagać odnowienia dowodu po nowych notices. Obecny podstawowy panel nie prowadzi przez tę czynność.

## Dependencies / entry conditions

- Zaakceptowany `GRID_CORRECTION_GROWTH_PLAN_20261103.md`, cały zakres i dodatkowy koszt 1–2 godzin zatwierdzone przez operatora.
- TASK-1139 dostarcza addytywne `progressCounts` w ready/preview, wygenerowane typy i wrapper.
- TASK-1138 pozostaje chronioną regresją: niezależne odczyty, `allSettled`, blokada podwójnego refresh i czas ostatniego udanego odczytu.
- Wykonawca UI nie zmienia backendu/kontraktu. Lead prowadzi wspólne CURRENT_STATE, DOC_INDEX, audyt i zamknięcie.

## Recommended execution

`gpt-6.1-sol` / `high`, zgodnie z zaakceptowanym planem. Obowiązkowy niezależny audyt Claude Code `claude-opus-5-5` / `high` przed commitem, prowadzony przez leada. Sprzeczność kontraktu lub otwarte P0/P1 blokują zamknięcie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md`
- `ai_docs/requirements/ADMIN_APP.md` — uczenie z zapisanych korekt.
- `ai_docs/architecture/VISION_LAB.md` — explicit apply i pipeline korekt.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/quality/TASK-1140_AUDIT_claude-opus-5-5.md` — pełny raport R1 i jedna runda poprawek.

## Scope

- Odczyt backendowych liczników: zatwierdzone ogółem, dostępne do TRAIN, etykiety w zamrożonych zestawach TRAIN oraz nowe etykiety, kontrole, nieopisane rezerwy, bufory i wyłączenia z przyczynami. Zapis w zestawie nie potwierdza zakończenia treningu.
- Wyraźne rozdzielenie gotowości następnego treningu i historycznego wyniku.
- Wyjaśnienie, że nieopisane rezerwy nie stanowią liczbowego pomiaru jakości; wskazanie korekty zarezerwowanych zdjęć albo nowego importu.
- Przycisk „Sprawdź aktualność oceny”, wyłącznie jawny POST istniejącego `verifyGridModelEvaluationCurrentness`, następnie GET wybranej oceny i podglądu zastosowania.
- Loading, ochrona podwójnego kliknięcia, błędy/retry, odrzucenie spóźnionej odpowiedzi po zmianie gry, przebiegu, odczytu lub unmount.
- Nowy apply pozostaje fail closed podczas sprawdzania i po niepotwierdzonej odpowiedzi; checkbox nie omija backendu. Resume częściowego zastosowania i dokładny replay zapisanego polecenia nadal docierają do autorytatywnej walidacji backendu.
- Testy interakcji z fake API, scoped lint/typecheck i Admin build.

## Out of scope

- Migracje, realny trening, publikacja, zastosowanie, zmiany defaultu i przypisań, operacyjne POST, start/stop/restart usług, merge/push.
- Obietnica użycia każdej korekty w TRAIN i pomiar jakości nieopisanych zdjęć.

## Acceptance criteria

- [x] Liczniki pochodzą bezpośrednio z backendu i nie mieszają rezerwy z użytymi kontrolami.
- [x] Wzrost TRAIN i nowe/użyte dane są czytelne; chroniona kontrola nie zwiększa TRAIN.
- [x] Otwarcie i zmiana wyboru wykonują wyłącznie GET.
- [x] Stale → jawne sprawdzenie → odczyt oceny i nowego podglądu; zmieniona etykieta nadal blokuje zastosowanie.
- [x] Loading/double click, błędy/retry, utrata odpowiedzi i spóźnione odpowiedzi są objęte testami.
- [x] Regresje TASK-1138 oraz scoped lint/typecheck/build PASS.
- [x] Dokumentacja zachowania, mapa kodu, docs:check i niezależny audyt zakończone przed commitem leada.

## Technical notes

Istniejący `GridCorrectionLearningClient` rozszerzyć o metodę aktualności. Nie tworzyć lokalnych odpowiedników typów backendu. Gotowość używa `progressCounts` nullable; brak danych daje jawny komunikat, nigdy zmyślone zero. Wszystkie kategorie pokazują zdjęcia i plansze, rezerwa bez etykiet ma zero plansz. Ocena jest przypięta do wybranego learning/evaluation/report. Weryfikacja ma osobny synchronizowany guard i generację; każde nowsze otwarcie/odświeżenie unieważnia odpowiedzi. Nowy podgląd resetuje zgodę człowieka. Weryfikacja sama nie publikuje i nie stosuje modelu.

## Expected files

- `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx` — Learning, LearningReport, liczniki i jawna weryfikacja.
- `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx` — Apply: odświeżenie i blokada starego podglądu.
- `apps/admin/src/features/model-quality/grid-model-state.ts` — polskie przyczyny ochrony i buforów.
- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs` — scenariusze liczników i aktualności.
- `ai_docs/requirements/ADMIN_APP.md` i `ai_docs/architecture/VISION_LAB.md` — krótkie fragmenty właścicielskie.

## Test cases

- TRAIN rośnie po nowej korekcie; użyte kontrole i rezerwa bez etykiet pozostają osobne.
- Stale PASS nie udaje aktualnego dowodu; weryfikacja odczytuje ocenę i podgląd.
- Błąd/utrata odpowiedzi nie pozostawia lokalnego sukcesu; jawne ponowienie jest możliwe.
- Zmieniona/wycofana etykieta zwraca blocker mimo checkboxa.
- Podwójne kliknięcie wysyła jeden POST; stara gra/przebieg/odczyt i unmount nie przyjmują odpowiedzi.
- Wejście wykonuje wyłącznie GET, nie rozpoczyna treningu, publikacji ani apply.
- Dotychczasowe testy TASK-1138 pozostają PASS.

## Verification

Polecenia z katalogu `D:\game_predicotr\worktrees\grid-correction-growth`, każde pod kontrolą `subprocess.run(..., timeout=120)`:

```powershell
npx tsx --tsconfig apps/admin/tsconfig.growth-local.json --test apps/admin/test-interactions/grid-correction-learning-panel.test.mjs
Push-Location apps/admin
npx eslint src/features/model-quality/grid-correction-learning-panel.tsx src/features/model-quality/grid-correction-apply-panel.tsx src/features/model-quality/grid-model-state.ts test-interactions/grid-correction-learning-panel.test.mjs
npx tsc --noEmit -p tsconfig.growth-local.json
Pop-Location
npm run build --workspace @game-predictor/admin
```

Lokalny wariant tsconfig i przygotowanie builda opisuje raport `ai_docs/quality/TASK-1140_VERIFICATION.md`; nie jest to trwała konfiguracja produktu. Lead regeneruje mapę i wykonuje `npm run docs:check`, `npm run code-map:check`, audyt oraz zamknięcie taska. Wyniki poniżej odróżniają testy wykonane od zaplanowanych.

## Risks / open questions

- Kontrakt liczników TASK-1139 jest dostępny i przechodzi scoped typecheck; lead zatwierdza go osobnym audytem i commitem przed UI.
- Brak bezpiecznych danych może wymagać nowego importu; panel nie obiecuje odblokowania każdej korekty.

## Outcome

Commit: v1.7.538 (hash dopisuje kolejny commit).

### Changed

- Sekcja danych do następnego uczenia renderuje `progressCounts` z backendu, bez lokalnego rekonstruowania podziału i sumowania nakładających się kategorii zdjęć. Oddziela nowe/użyte etykiety TRAIN, kontrole, nieopisane rezerwy, bufory i wyłączenia z polskimi przyczynami.
- Zakończona ocena ma jawne sprawdzenie aktualności z loading, synchronizowanym guardem, obsługą błędów i generacjami odpowiedzi. Po POST następuje GET przypiętej oceny i nowego podglądu; sprawdzenie nie uruchamia treningu, publikacji ani zastosowania.
- Nowe zastosowanie pozostaje zablokowane podczas sprawdzania i po utracie odpowiedzi, także do zakończenia późniejszego autorytatywnego GET. Scope/generacja podglądu odrzucają stare optymistyczne odpowiedzi i resetują zgodę człowieka.
- Dodano 18 scenariuszy interakcji, obejmujących wzrost TRAIN, chronione kontrole/rezerwy, zmianę etykiety, loading/double click, utratę odpowiedzi/reload, błędy GET i stare odpowiedzi POST/GET/preview. Wzmocniono wcześniejsze testy resume/replay rzeczywistą oceną stale i evaluationId.
- Jedyna runda poprawek po audycie R1 REVISE: P1-1/P1-2 — evidenceBlocked chroni wyłącznie nowy apply; resume oraz identyczne zapisane polecenie są wysyłane do backendu. P2-1 — jawna allowlista metod GET także po zmianie wyboru. P2-2 — zakończenie loading po błędzie odczytu i czytelna instrukcja ponowienia. P2-3 — granicę dokumentacji zachowuje lead przy osobnych commitach.
- Dodatkowe uwagi leada: verify wymaga statusu completed i rzeczywistego raportu; etykieta licznika wskazuje zamrożone zestawy TRAIN, nie ukończone użycie GPU. Kategorie mogą się nakładać; bufory obejmują też nieopisane zdjęcia. GRID_CORRECTION_CONTROL_NOT_PENDING ma polską etykietę i test rezerwy zero / wyłączenia 1 zdjęcia bez plansz.

### Verification results

- Końcowy odczyt hashy potwierdził identyczność pięciu plików UI/testu/wymagań i bloku architektury z drzewem zaudytowanym w R2. Po złożeniu nad osobnym commitem TASK-1139: ponownie 74/74 interakcje PASS, lokalny TypeScript PASS, docs:check i code-map:check PASS. Mapa zregenerowana.
- P2-3 rozliczone: commit TASK-1139 nie zawiera plików apps/admin ani bloku TASK-1140 w VISION_LAB. Commit TASK-1140 obejmuje wyłącznie panel i własną dokumentację, mapę oraz wymagane metadane hasha poprzedniego taska; granicę sprawdza staged diff.

- Opus 5.5/high: focused R2 PASS; P1-1/P1-2/P2-1/P2-2 zamknięte. Raport końcowy `ai_docs/quality/TASK-1140_AUDIT_claude-opus-5-5.md`, pierwszy raport zachowany jako `_R1.md`. P2-3 rozlicza prowadzący przez oddzielne commity i kontrolę staged hunków.

- Po rundzie poprawek R1: panel 40/40 testów interakcji PASS, w tym 22 wcześniejsze regresje. Szerszy zakres 4 plików interakcji model-quality: 74/74 PASS. Wcześniejsze wyniki 34/34 i 68/68 nie pokrywały regresji resume/replay ujawnionej przez audyt; naprawiono ją i uzupełniono testy.
- Scoped ESLint trzech modułów i testu: PASS, 0 błędów i 0 ostrzeżeń. Format Prettier PASS.
- Scoped TypeScript Admina i produkcyjny build Admina: PASS. Użyto tymczasowych aliasów do klienta w worktree; oryginalny tsconfig przywrócono. Lead przeniósł początkowy patch z głównego checkoutu przed weryfikacją; wszystkie kontrole wykonano w izolowanym worktree bez sterowania działającymi usługami.
- Wszystkie komendy miały timeout 120 s. Szczegóły i rozróżnienie lokalnych aliasów od konfiguracji produktu: `ai_docs/quality/TASK-1140_VERIFICATION.md`.

### Not completed

- Audyt R2 PASS po jednej rundzie poprawek; końcowe kontrole mapy, dokumentacji i wspólnego pionu PASS. Wdrożenie pozostaje osobnym krokiem.
- Bez operacyjnego treningu, zastosowania, migracji, restartu usług i merge/push; nie wykonywano żadnego operacyjnego POST. Testy używają fake API.

### Documentation updates

- ADMIN_APP opisuje liczniki przyrostu, ograniczenia rezerw i jawne sprawdzenie aktualności.
- VISION_LAB opisuje backendowe źródło liczników, guard/generacje i tożsamość odświeżanego preview.
- Raport `ai_docs/quality/TASK-1140_VERIFICATION.md`; lista audytu `artifacts/task1140-audit-paths.txt`. CURRENT_STATE i DOC_INDEX należą do leada.

### Recommended next task

- Odbiór całego planu przez leada, bez operacyjnego treningu i zastosowania.
