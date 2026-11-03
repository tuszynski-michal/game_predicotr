---
title: Audyt TASK-1140, runda 2
status: active
last_updated: 2026-11-03
---

# Audyt TASK-1140 — Czytelny panel przyrostu korekt i aktualności oceny

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: drzewo R1 fcd4d62ea356e52b965017dffa239303e1a6b3b2...drzewo R2 0604c78893cd03fdbafae53fa5beb5542c6f0541 (zmiany niezacommitowane na HEAD 3562ab1a), data 2026-11-03
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem jedną rundę poprawek po R1 na podstawie dokładnego diffu z `artifacts/audits/TASK-1140_R2_FOCUSED.md` i odczytu bieżących linii zmienionych plików. Oba P1 są zamknięte. `evidenceBlocked` blokuje teraz tylko nowe zastosowanie. Wznowienie i replay dokładnie zapisanego polecenia trafiają do backendu, a testy używają rzeczywistego `evaluationId` z oceną `stale`. P2-1 i P2-2 też są zamknięte. P2-3 dotyczy granicy commitów dokumentacji, zostaje otwarte i należy do prowadzącego. W samych poprawkach nie znalazłem nowych P0 ani P1.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-3] `ai_docs/architecture/VISION_LAB.md:62–84` — Bez zmian względem R1. Plik nadal zawiera w jednym diffie sekcje TASK-1139 (D-582, `grid_correction_progress.py`) i blok TASK-1140. Skutek: przy commicie można pomieszać hunki dwóch tasków. Propozycja: przy osobnych commitach prowadzący zachowuje granicę bloku TASK-1140 (od „TASK-1140: readiness renders” do „old optimistic response cannot restore a stale preview or its confirmation.”) i sprawdza ją przez `git diff --cached`. To akceptowane ryzyko po stronie prowadzącego i nie blokuje werdyktu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Liczniki z backendu, bez mieszania rezerwy z kontrolami | spełnione | `grid-correction-learning-panel.tsx` (`LearningProgress`, wiersz „W zapisanych zestawach TRAIN”); test kontroli poza kolejką z rezerwą 0 i wyłączeniem 1/0 (`grid-correction-learning-panel.test.mjs` ok. `:389–452`); etykieta `GRID_CORRECTION_CONTROL_NOT_PENDING` w `grid-model-state.ts` |
| Wzrost TRAIN i nowe/użyte dane czytelne; kontrola nie zwiększa TRAIN | spełnione | Bez zmian logiki względem R1; zmieniona etykieta i objaśnienie zamrożonych zestawów TRAIN; test wzrostu z `assertOnlyReads` |
| Otwarcie i zmiana wyboru wyłącznie GET | spełnione | `grid-correction-learning-panel.test.mjs:20–40` (jawna allowlista bez `previewGridCorrectionLearning`); asercje po zmianie wyboru `:717`, `:826` |
| Stale → jawne sprawdzenie → odczyt oceny i nowego podglądu; zmieniona etykieta blokuje | spełnione | `grid-correction-learning-panel.tsx:279–282` (verify tylko dla `completed` z raportem i bez błędu odczytu); `grid-correction-apply-panel.tsx:225–242, 296` (nowe apply nadal blokowane) |
| Loading/double click, błędy/retry, utrata i spóźnione odpowiedzi w testach | spełnione | `grid-correction-learning-panel.tsx:267–270` (loading kończy się w `finally` dla bieżącej generacji, błąd z instrukcją ponowienia); test `grid-correction-learning-panel.test.mjs:497` |
| Regresje TASK-1138 oraz scoped lint/typecheck/build PASS | niezweryfikowane przez audytora | Wynik deklarowany przez wykonawcę: 40/40, 74/74, ESLint 0/0, tsc PASS, build PASS (`TASK-1140_R2_FOCUSED.md:50–54`); testów nie uruchamiałem |
| Dokumentacja, mapa kodu, docs:check i niezależny audyt przed commitem | częściowo; reszta należy do prowadzącego | ADMIN_APP i blok TASK-1140 w VISION_LAB zaktualizowane spójnie z poprawką; mapa, `docs:check`, `code-map:check` i commit są poza zakresem tej rundy, ich brak nie jest błędem |

## Listy zamknięte i otwarte

Zamknięte:

- **P1-1:** `send()` zwraca wcześniej tylko dla `command.kind === 'apply' && evidenceBlocked`. Replay przechodzi wyłącznie wtedy, gdy polecenie dokładnie odpowiada zarówno `pending`, jak i komendzie w localStorage. W przeciwnym razie panel pokazuje jawny komunikat zamiast cichego no-op (`grid-correction-apply-panel.tsx:225–242`).
  - „Wznów zastosowanie” używa `disabled={disabled}` bez `evidenceBlocked` (`:529`).
  - Checkboxy i „Zastosuj wersję” używają `newApplyDisabled` (`:296`).
  - Panel wyjaśnia blokadę (`:314`).
  - Nowe apply nie obejdzie tej ścieżki, bo przy `pending !== null` przycisk jest wyłączony, a bez `pending` warunek dokładnego dopasowania nie jest spełniony.
- **P1-2:** testy wznowienia i replay działają teraz na `evaluatedRun` z oceną `stale`. Sprawdzają aktywne „Wznów zastosowanie” i „Ponów zapisane polecenie zastosowania”, identyczny payload startu i dalszą blokadę „Zastosuj wersję” (`grid-correction-learning-panel.test.mjs:1414`, `:1471`).
- **P2-1:** `READ_ONLY_METHODS` i `assertOnlyReads` zastąpiły regex prefiksów (`grid-correction-learning-panel.test.mjs:20–40`). Asercje dodano także po zmianie wyboru (`:717`, `:826`).
- **P2-2:** `open()` ma `try/catch/finally`. `evaluationReading` jest zdejmowane dla bieżącej generacji, `evaluationReadError` przechowuje instrukcję ponowienia przez „Odśwież stan uczenia” i dalej blokuje verify oraz nowe apply (`grid-correction-learning-panel.tsx:267–270`, `:900`, `:933`). Pusta lista przebiegów zeruje stan odczytu. Pokrywa to test `:497`.

Otwarte: P2-3 (u prowadzącego, akceptowane ryzyko).

## Proponowane testy

- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: przypadek negatywny strażnika replay. Przy `evidenceBlocked` i komendzie w localStorage różnej od `pending` (np. podmienionej po remount) panel nie wywołuje `startGridCorrectionApply` i pokazuje komunikat „Nowe zastosowanie wymaga aktualnej oceny”. Komenda: `npx tsx --tsconfig apps/admin/tsconfig.growth-local.json --test apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`. Test jest opcjonalny: tej ścieżki nie da się wywołać z UI bez ręcznej zmiany localStorage, a backend i tak waliduje polecenie.

## Zakres przeglądu i ograniczenia

Przeczytałem:

- brief R2 z pełnym diffem R1→R2;
- bieżące numery linii kluczowych zmian w `grid-correction-apply-panel.tsx`, `grid-correction-learning-panel.tsx` i `grid-correction-learning-panel.test.mjs`;
- wnioski z R1 o backendowym `resume()` (`grid_correction_apply.py:384–421`), które uzasadniają przepuszczanie wznowienia.

Nie robiłem szerokiego audytu od nowa i nie oceniałem sekcji TASK-1139 w VISION_LAB. Nie uruchamiałem testów, lintu, typecheck ani builda. Wyniki 40/40, 74/74, ESLint, tsc i builda pochodzą od wykonawcy i nie mam na nie własnego dowodu.

Zmiana fixture starego testu TASK-1138 (ocena z `status: 'completed'` i `report: null` zamiast obiektu bez statusu) jest uzasadniona nowym wczesnym returnem w `LearningReport` (`grid-correction-learning-panel.tsx:1084`) i urealnia dane. Nie traktuję jej jako osłabienia regresji.

Zamknięcie taska, mapa kodu, `docs:check`, `code-map:check` i commit należą do prowadzącego.
