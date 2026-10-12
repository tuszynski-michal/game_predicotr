---
title: Finalny pilot0.1.3 i dowody kompletnej rundy
status: done
last_updated: 2026-10-12
---

# TASK-0987 — Finalny pilot0.1.3 i dowody kompletnej rundy

## Status

`done`

## Goal

Dostarczyć sprawdzony ZIP0.1.3 z pełną instrukcją, pomiarem15k i gotowym przekazaniem do odbioru operatora.

## Context

Pełny audyt Claude rundy2 ma PASS i otwarte P2/P3. Operator polecił wykonać
całą finalizację, zatwierdził3–5 h oraz pomiar15000. Odbiór fizyczny na końcu.

## Dependencies / entry conditions

TASK-0986 done; wszystkie984–986 zweryfikowane; artefakty0.1.0/0.1.2 zachowane.

## Recommended execution

`gpt-6.1-sol / medium`. Konfiguracja zgodna z tabelą planu finalizacji.
Eskaluj przy naruszeniu własności danych, idempotencji lub zgodności migracji.
Końcowy audyt operatora warunkowo `claude-sonnet-5-5 / medium`;
D-545 odracza audyt do końca, bez gate CLI/per-task. Nie zastępuj Claude
niejawnie.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545, D-546
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md — TASK-0987
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — sekcja desktop
- ai_docs/architecture/CODE_MAP.md — selector
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md

## Scope

Wersja0.1.3; własne fixture15000, kontrolowany baseline/final pomiar; actual ZIP update0.1.0 i0.1.2 do0.1.3; wszystkie sześć scenariuszy obu kierunków, restart procesu i migrated history; SHA/provenance.

## Out of scope

API/Admin/Reviewer/baza, upload/linki/Proton, usługi operatora, podpis,
instalator, push/merge oraz fizyczny odbiór0979. Bez danych użytkownika.

## Acceptance criteria

- [x] Pełny desktop test/lint/typecheck/format, core/zgodność gdy właściwe, docs/code-map/diff PASS z zapisanymi komendami i timeoutami.
- [x] ZIP0.1.3 i asar mają zgodne SHA/build-info/sourceCommit; runtime bez źródeł/monorepo; historyczne ZIP-y bez zmian.
- [x] Sześć finalnych smoke oraz rzeczywiste update0.1.0/0.1.2→0.1.3 na kopiach przechodzą; oba kierunki/source reselect/legacy/recovery/relaunch bez utraty pracy.
- [x] Pomiar15000 podaje rzeczywiste p50/p95 i pozostałe koszty; brak zapisu inventory/receipt history na krok, brak dodatkowych warm worker spawns.
- [x] Instrukcja wskazuje źródłową decisions[].imagePath przy manualnym odtworzeniu JPEG i kontrolę SHA; dokumentacja wskazuje aktualną paczkę i wszystkie rundy.
- [x] Raport domyka uwagi implementacyjne albo jasno wykazuje blokujący przypadek; fizyczny0979 i końcowy audyt operatora nie są udawane.

## Technical notes

Wersja0.1.3; własne fixture15000, kontrolowany baseline/final pomiar; actual ZIP update0.1.0 i0.1.2 do0.1.3; wszystkie sześć scenariuszy obu kierunków, restart procesu i migrated history; SHA/provenance. Zdjęcia źródłowe tylko do odczytu. Nie resetuj projektu po braku
folderu. Obce dane/niezgodne checksumy blokują zapis. Numeracja i porządek
zdjęć zachowują reguły core; wyniki są operator-local v2.

## Expected files

Ścieżki runtime względem `apps/selector-desktop/src`, skrypty/testy względem
workspace'u, o ile podano inaczej. package.json/lockfile; scripts/release/smoke; instrukcja operatora, acceptance/handoff, plany, TRACEABILITY, CURRENT_STATE, task0979. Nowe proponowane scripts/measure-selector.mjs i quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md.

## Test cases

Własny bounded fixture15k; true processes/updates; ZIP contents; fault log retained; original fixture bytes/mtime; source and output relink; user receipt checklist.

## Verification

Z worktree D:\game_predicotr\worktrees\offline-photo-selector. Najpierw pion,
potem pełny desktop. Każdy krok ma timeout; brak wyniku60s wymaga kontroli
zgodnie z AGENTS, buildy kontrolowane mają znany limit120s.

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run code-map:check
```

Powyższe skrypty są sprawdzone. Nowe testy używają istniejącego runnera Node
lub jawnie dodanego skryptu; ich komendy/wyniki dopisz w Outcome. Odbiór
zadania wymaga wszystkich właściwych kryteriów, nie tylko zielonego testu.

## Risks / open questions

Fizyczny odbiór0979 i końcowy review operatora następują po implementacji.
Nie certyfikuj zaniku zasilania ani dowolnego sprzętu. Format disk2 jest
jednokierunkową zgodną migracją do nowej aplikacji; stara musi odmówić zapisu.

## Outcome

### Changed

Wersja aplikacji 0.1.3 i lockfile bez zmiany zależności. Dwa nowe skrypty
odtwarzają zatwierdzony pomiar 15 000 JPEG na baseline i nowym runtime.
Update smoke sprawdza oba rzeczywiste starsze EXE na migrowanej kopii i
niezmienione SHA/size/mtime wszystkich plików projektu/wyniku. Czeka na
gotowość renderera po native commit, zamiast wysyłać klawisz podczas zapisu.

Commit kodu/przygotowania wydania: v1.7.337 /
`0b1ab3302df2119efb2519661e2f82b8bdf545df`. Build wykonano z czystego worktree.
Runtime src i rdzeń są identyczne z mierzoną rewizją v1.7.336. Następny
commit zamyka dokumentację/dowody i patch harnessu; nie zmienia ZIP-a.

Finalny ZIP: `apps/selector-desktop/out/releases/pilot-0.1.3-0b1ab330/Selektor zdjec-win32-x64-0.1.3.zip`,
149410942 B. ZIP SHA-256 `cfb078b5f86a57cd781d99210ff699849485031a1ac173b6acb1861c1a145761`;
app.asar `23e0fa358455e6796fa01fd6951e695a6d6b9e9312730c86ec3382a8bad0e3a2`.
dirty=false, applicationSourceDirty=false; builtAt2026-10-12T15:33:25.902Z,
releasedAt2026-10-12T15:33:52.292Z. Trzy pliki zachowanej kopii ZIP/SHA/metadata
zgodne bajtowo z make. Obie stare paczki i oba raporty Claude bez zmiany SHA.

### Verification results

Pełny desktop262/262 PASS (110,837 s, limit120 s), core110/110 PASS
(2,132 s,60 s), zgodność operator-local Reviewera16/16 PASS (0,160 s,60 s).
Desktop lint/typecheck PASS (60 s), format nowych skryptów PASS (30 s).
Runtime nie zmieniał się po pełnym teście, więc nie powtarzano całego zestawu.
Mapy zregenerowane; code-map:check, docs:check i git diff --check PASS.

Release i pięć wariantów rzeczywistego finalnego ZIP-a:
smoke:release:start, smoke:release, smoke:release:shortcuts,
smoke:release:legacy, smoke:release:ux PASS, każdy z limitem120 s.
Smokes potwierdzają oba kierunki, historię/reselect źródła, skróty/granicę,
legacy, restart, kopie/relink, utratę locka, scroll oraz deferred relaunch.
Actual update0.1.0→0.1.3 i0.1.2→0.1.3 PASS; ostateczny harness sprawdzony
w obu ścieżkach. Wszystkie decyzje/kursor/JPEG zachowane, nowa decyzja
przeżywa kolejny proces. Starsze EXE zwracają UNSUPPORTED_PROJECT_SCHEMA;
projekt/wynik pozostają bez zmiany SHA/size/mtime. Oryginały testowe nietknięte.
Po finalnych smokes liczba procesów Selektor-zdjec wyniosła0.

Pierwszy update0.1.0 FAIL przez cztery uszkodzone literały UTF-8 w nowych
locatorach, log smoke-update-z7d7tO. Po naprawie kolejny FAIL przy Tab,
log smoke-update-xPk6Mz. Jeden bounded actual probe0.1.0 dowiód: native
accepted=1 przed React busy=false, DOM jeszcze Wybrane0/zapis w toku.
Harness czeka teraz na imageReady, zgodny DOM/save-state i aktywny przycisk
pominięcia. Wszystkie asercje pozostały. Nie uznajemy pierwszych FAIL za PASS,
nie przypisujemy tej przyczyny automatycznie dawnym błędom audytu.
Pierwszy Prettier wskazał measure-selector.mjs; poprawiono formatowanie.

Kontrolowany pomiar15000: NAV p50/p95 95,08/106,66 ms zamiast918,79/979,36;
accept124,49/143,81 zamiast976,16/1024,35. Sto operacji każdej wersji,
pełna retencja100 receiptów/retry po nowym procesie,24 zachowane prefixy
ledgeru, zero dodatkowych warm worker spawns. Cztery immutable pliki i
wszystkie15000 oryginalnych SHA/size/mtime bez zmian. Current create21,277 s;
open pięciu świeżych procesów p50/p95 10,523/10,637 s. Szczegółowe komendy,
sprzęt, pozostałe koszty i ograniczenia w dwóch raportach jakości.

Porównanie punkt po punkcie: sześć kryteriów akceptacji ma dowody w raporcie
finalizacji, pomiarze, testach i finalnym artefakcie. Nie rozszerzono zakresu
poza D-546; D-545 odracza formalny audyt na koniec przez operatora.

### Not completed

Końcowy audyt krzyżowy Claude i fizyczny odbiór TASK-0979 wykonuje operator.
Brak lokalnego CLI Claude nie jest niejawnie zastąpiony review Codex.
Nie wykonano dystrybucji, podpisu, instalatora, push/merge, usług ani zmian
danych operatora/API/Admina/Reviewera/OpenAPI/bazy. Brak certyfikacji zaniku
zasilania lub dowolnego sprzętu. Własne fixture pomiaru zachowano do audytu.
Pomiar na JPEG8×8 nie obejmuje realnego dekodowania, tysięcy zaakceptowanych
decyzji ani transportu IPC. Manifest/open/retencja zachowują jawne koszty.

### Documentation updates

Raport finalizacji i pomiar, nowy pełny brief Claude, instrukcja brakującego
JPEG ze źródłowej imagePath i SHA; README, wymagania, architektura,
TRACEABILITY, cztery plany, handoff, acceptance i aktywny0979 wskazują
bieżący ZIP0.1.3. CURRENT_STATE przenosi task do done i zachowuje10 wpisów;
starsze paczki i raporty pozostają historyczne. Funkcja nie jest oznaczona
jako zaliczony fizyczny pilotaż lub wdrożenie głównej aplikacji.

### Recommended next task

Fizyczny odbiór TASK-0979 przez operatora i jego końcowy audyt.
