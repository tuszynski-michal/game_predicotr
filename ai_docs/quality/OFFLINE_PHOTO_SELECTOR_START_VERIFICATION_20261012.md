---
title: Selector source-first UX verification
status: ready_for_review
last_updated: 2026-10-12
---

# TASK-0983 — Dowody startu i wznowienia

To raport wykonawcy, nie niezależny audyt ani odbiór odbiorcy. Operator
zatwierdził zakres i1–2 h. Wykonano source-first start, etykietę gry,
dropdown historii i auto-resume. D:\Mumie\123 tworzy D:\Mumie\123 wybrane
oraz D:\Mumie\123 selekcja. Kierunek dotyczy numeracji, nie porządku zdjęć.

## Kod i dokumentacja

- Worktree: D:\game_predicotr\worktrees\offline-photo-selector;
  branch codex/offline-photo-selector.
- Source commit v1.7.328 /9ade6a8596cd316d214cf25339eae40e8789be9f.
- Uzupełnienie historii po relink: v1.7.329 /c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f.
- Baza przyrostu: c32fa802597ecaeb3d9ad0b4d15466a730e6bb70 (v1.7.327).
- Task: `ai_docs/tasks/completed/0983-selector-desktop-source-first-start.md`;
  plan: `ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_START_PLAN_20261012.md`.
- Typowane begin/create, opaque token, tożsamość source/project pod lockiem
  przed recovery. Metadane gameName opcjonalne w ProjectState1, bez zmian
  manifestu operator-local. Cache historii10 wpisów jest pomocniczy.
- Ponowny picker po anulowaniu zachowuje formularz/token. Historia po
  relink źródła aktualizuje sourceRoot; jego kolejny wybór wznawia projekt.

## Faktycznie wykonana weryfikacja

122 unikalne testy PASS: start/resume10, project48, UI4, legacy25,
legacy-recovery26, foundation7, release2. Lint, typecheck i format PASS.
Docs/mapy sprawdzono; końcowe sprawdzenie po zamknięciu taska zapisane w Outcome.
Każda skończona kontrola miała jawny limit120 s lub niższy.

Start/resume obejmuje oba kierunki, accept/skip/range/undo/navigate,
nową instancję, utratę cache, dokładne bajty JPEG, view cache, stare projekty,
anulowanie, zły token, obcy folder, niejednoznaczność, niezgodny source/id,
junction i przerwany create. Zapamiętanie gry przechodzi recovery journalu;
niezgodny source jest odrzucany bez przepisania obcego journalu.

Wszystkie sześć finalnych smoke scenariuszy PASS:

| Komenda workspace (wrapper120 s) | Rzeczywisty dowód |
|---|---|
| smoke:release:start | Formularz po jednym pickerze, gry w dropdownie, oba kierunki po nowym procesie; source relink i ponowny wybór przeniesionego folderu. |
| smoke:release | Enter/Tab, undo, repeat/doubleclick, fullscreen/zoom/scroll, restart procesu, kopia projektu i wyników, niezmieniony oryginał fixture. |
| smoke:release:shortcuts | Malejący F, granica19–20, zły JPEG i opaque IPC; przeniesione źródło bez resetu. |
| smoke:release:legacy | Preview/import, anulowanie, token, nienaruszone stare pliki i wznowienie przez nową historię. |
| smoke:release:ux | Debounce/flush, trwałe decyzje/widok, zamknięcie prawdziwego procesu po LOCK_LOST i zachowana obca blokada. |
| smoke:update | Rzeczywiste ZIP-y0.1.0→0.1.2: kopia projektu zachowuje kursor, decyzje i SHA JPEG; nowy wybór przetrwał proces; oryginał fixture SHA/size/mtime bez zmian. |

Formularz i historię obejrzano na screenshotach rzeczywistego EXE.
Pierwszy smoke ujawnił brak jednoznacznego aria-label kierunku; uzupełniono
UI. Asercję fault testu dostosowano do istniejącego opakowania WRITE_FAILED
z dowodem osiągnięcia prepare:after. Nie osłabiono kontroli plików ani semantyki.

## Finalna paczka

- Wersja0.1.2, Win11 x64 ZIP: `apps/selector-desktop/out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip`.
- Rozmiar: 149402003 bajtów.
- ZIP SHA-256: `9426704949dd8ab7d16f9d9743e2254257805a8ed1cc5dce38eecd2c37442e27`.
- app.asar SHA-256: `0e2c2bf2894bd519ceea96e957e564dbe02f54d0963f3d381085396815c323c0`.
- SourceCommit: `c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f`.
- dirty=false; applicationSourceDirty=false.
- builtAt: 2026-10-12T12:13:30.073Z; releasedAt: 2026-10-12T12:13:58.018Z (UTC).
- Obok znajdują się .sha256 i .release.json. Suma stabilnej kopii jest zgodna.

Pierwszy build0.1.2-9ade6a85 zachowano jako historyczny, przed uzupełnieniem
relink. Nie jest finalną paczką. Sumy wcześniejszych0.1.0/0.1.1 i pierwotnego
raportu Claude REVISE ponownie sprawdzone i niezmienione.

## Granice odbioru

Końcowy audyt wykonuje operator według jego polecenia dla selektora.
Oryginalnego raportu REVISE nie zastąpiono własnym PASS. Fizyczny odbiór0979,
restart Windows odbiorcy, podpis i droga dystrybucji pozostają pending.
Pełne SHA przy open i koszt pełnej historii/inventory nadal mają wcześniejsze
ograniczenia. History cache jest pomocniczy; projekty custom poza nim otwiera
się jawnie. Brak folderu nigdy nie resetuje selekcji. Bez usług głównej
aplikacji, danych operatora, chmury, benchmarków, push i merge.
