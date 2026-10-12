---
title: Lokalny selektor Windows — finalizacja i dowody pilota0.1.3
status: ready_for_review
last_updated: 2026-10-12
---

# Finalizacja selektora Windows — dowody wykonawcy

Zakres: TASK-0984–0987, D-546 i pełna runda zatwierdzona przez operatora.
Ten raport zapisuje wykonane kontrole. Nie jest końcowym audytem Claude ani
odbiórką na komputerze odbiorcy. TASK-0979 pozostaje osobną bramką fizyczną.

## Ukończone etapy i źródła

- TASK-0984: v1.7.334 /c52518a8ece7c79f88b31224d4d90a84f0779b4c; bezpieczna historia/foldery, repeat decyzji i zamykanie/relaunch.151 testów oraz actualfull/UX smoke PASS.
- TASK-0985: v1.7.335 /d82fbcb576ef138b8b6049102212b85f97d0a803; head2/journal3, mirrored immutable inventory/baseline, append-only receipts bez retencji.233 testy PASS. Wewnętrzny review Codex REVISE2P1 → jedna runda poprawek → ograniczony PASS. [Raport](TASK-0985_ENGINEERING_REVIEW_CODEX.md) zachowuje pierwotne znaleziska i rozróżnia przegląd od testów oraz Claude.
- TASK-0986: v1.7.336 /c43434c28d49597407072f9636c7c07d1c3622b8; ograniczony timeout retry, bezpieczne telemetry, failure logs i exactarchive provenance.53 focused testy PASS, actualstart obu kierunków PASS. Pierwsze błędy harnessu i ich poprawki są w Outcome, nie są ukryte.
- TASK-0987: przygotowanie/runtime v1.7.337 /`0b1ab3302df2119efb2519661e2f82b8bdf545df`; zamknięcie v1.7.338 /`525af074136910fd0744dfe0f2f71196d5d4fe17`. Finalny ZIP, pomiar i komplet dowodów poniżej. Późniejszy commit dokumentacyjny zapisuje hash zamknięcia; nie zmienia aplikacji.

## Kontrole kodu przed finalnym release

Z worktree `D:\game_predicotr\worktrees\offline-photo-selector`, Node24.21.0.
Każda komenda skończona ma jawny limit w run-bounded.mjs.

| Komenda | Limit | Wynik |
|---|---|---|
| npm run test --workspace @game-predictor/selector-desktop |120 s|262/262 PASS,110,837 s;0 skip; pełny runtime po0986 |
| npm run test --workspace @game-predictor/manual-image-selection-core |60 s|110/110 PASS,2,132 s |
| node --experimental-strip-types --test apps/reviewer/test/operator-local-selection-output.test.mjs |60 s|16/16 PASS,0,160 s; bez uruchamiania Reviewera |
| desktop lint/typecheck/Prettier |60/60/30 s|PASS, również nowe skrypty pomiaru i aktualizacji; pierwsza uwaga formatowania została poprawiona |
| npm run docs:check |60 s|PASS:543 decyzje/odnośniki,43 aktywne taski,10 done po zamknięciu0987 |
| npm run code-map:check |60 s|PASS, mapy aktualne |
| git diff --check |30 s|PASS po usunięciu pustej końcowej linii CURRENT_STATE; zapis archiwalnego taska pozostaje bez zmian |

Najbardziej istotne przypadki: każda faza upgrade/ledger/head, rzeczywisty
exit i nowy proces, ENOSPC/rename/partial suffix, dwa uszkodzone mirrory,
obcy lock/plik, dokładny stary receipt po undo/restart, migracja legacy1/2,
relink źródła/wyniku podczas pending operacji i pending upgrade, oba
kierunki/naturalny kursor oraz brak decyzji z auto-repeat.

## Diagnostyka sprawdzona na rzeczywistym EXE

TASK-0986 celowo przerwał smoke-start po uruchomieniu testowego EXE.
Oczekiwany exit1 zachował `artifacts/selector-smoke-diagnostics/smoke-start-fiYX0L`:
selector.log64B z application-start oraz failure.json z kontrolowaną
przyczyną, timeout close i wymuszonym zakończeniem tylko własnego PID.
Fixture nie istnieje po capture; liczba procesów Selektor-zdjec wyniosła0.
Nie jest to PASS pozytywnego scenariusza; to dowód ścieżki błędu. Dodatni
smoke-start po poprawce finalizera przeszedł osobno. Gdy capture nie działa,
regresja potwierdza pozostawienie własnej fixture. Logi nie zawierają obrazów;
reason ma limit1500 znaków i redaguje dane obrazów/base64/buffer.

## Kontrolowany pomiar 15 000 zdjęć

[Pełny raport](OFFLINE_PHOTO_SELECTOR_MEASUREMENT_20261012.md) oraz surowe
wyniki w `artifacts/selector-measurements/final-20261012/` opisują sprzęt,
percentyle, etapy zapisu i wszystkie ograniczenia. Baseline: c4181f7d.
Current: c43434c2. `git diff c43434c2 0b1ab330 -- apps/selector-desktop/src packages/manual-image-selection-core`
jest pusty; finalny runtime ZIP ma dokładnie te same źródła co pomiar.
Zmiana wersji, harnessu i dokumentacji nie zmieniła mierzonego runtime.

| Operacja | Baseline p50 / p95 ms | Current p50 / p95 ms |
|---|---:|---:|
| Nawigacja | 918,79 / 979,36 | 95,08 / 106,66 |
| Wybór | 976,16 / 1024,35 | 124,49 / 143,81 |
| Cofnięcie wyboru | 948,67 / 1039,96 | 104,10 / 115,07 |
| Pominięcie | 924,19 / 1022,63 | 94,12 / 100,81 |

Po 100 operacjach każdej wersji kolejny proces potwierdził wszystkie stare
potwierdzenia oraz ponowienie bez drugiej decyzji. Zero dodatkowych ciepłych
workerów, cztery immutable pliki bez zmiany SHA/mtime, 24 zgodne prefixy
ledgeru. Wszystkie 15 000 oryginalnych SHA, rozmiary i mtime pozostały bez zmian.
Nowy create trwał 21,277 s; pięć fresh-process open miało p50/p95 10,523/10,637 s.
To 8×8 JPEG po 639 B, lokalny D:, Windows 11 Home, Ryzen 7 170, 33,63 GB RAM.
Pomiar nie obejmuje renderowania ani wielkich zdjęć. Liczba decyzji wynosiła
co najwyżej jeden przed undo, historia 100 operacji. Pełny manifest, walidacja
otwarcia, retencja i metadane źródła mają nadal jawne koszty; nie wyciągamy
z tego gwarancji dla dowolnej partii lub sprzętu.

## Finalna paczka

Paczka: `apps/selector-desktop/out/releases/pilot-0.1.3-0b1ab330/Selektor zdjec-win32-x64-0.1.3.zip`.
Wersja 0.1.3, 149410942 bajty, source commit v1.7.337 /
`0b1ab3302df2119efb2519661e2f82b8bdf545df`; dirty=false,
applicationSourceDirty=false. BuiltAt 2026-10-12T15:33:25.902Z,
releasedAt 2026-10-12T15:33:52.292Z.

- ZIP SHA-256: `cfb078b5f86a57cd781d99210ff699849485031a1ac173b6acb1861c1a145761`.
- app.asar SHA-256: `23e0fa358455e6796fa01fd6951e695a6d6b9e9312730c86ec3382a8bad0e3a2`.

Release (limit 120 s) rozpakował świeży ZIP i zweryfikował siedem wpisów ASAR,
package.json oraz osadzony build-info z metadanymi. Brak źródeł, node_modules,
symlinków i unpacked. Trzy pliki zachowanej kopii ZIP/SHA/release.json są
bajtowo zgodne z make. Wersja paczki jest niezależna od wersji commitów.

## Testy rzeczywistego finalnego ZIP-a

Każdy wariant sprawdza SHA, rozpakowuje tę samą paczkę i uruchamia jej EXE.
Limit każdej poniższej komendy wynosi 120 s; własne profile i fixture.

| Skrypt npm | Wynik | Sprawdzone zachowanie |
|---|---|---|
| smoke:release:start | PASS | Jeden folder, etykieta gry, historia, reselect i nowy proces w obu kierunkach; przeniesione źródło |
| smoke:release | PASS | Selekcja, undo, repeat/double submit, fullscreen, zoom/scroll, kopia projektu/wyniku i relink, restart procesu |
| smoke:release:shortcuts | PASS | Malejąca numeracja, krótszy zakres końcowy, skok 20 i wybór +1, malformed JPEG, nieprzezroczyste IPC, relink |
| smoke:release:legacy | PASS | Preview, anulowanie, walidacja tokenu, import na kopii bez zmian oryginału i nowy proces |
| smoke:release:ux | PASS | Scroll burst i flush, utrata locka, obce bajty locka bez zmian, dwa EXE podczas close → jedno nowe okno |
| smoke:update 0.1.0 → 0.1.3 | PASS po poprawkach harnessu | Rzeczywiste różne ZIP-y, zachowane decyzje/kursor/JPEG, relink kopii wyniku, kontynuacja i kolejny proces, odmowa starszego readera |
| smoke:update 0.1.2 → 0.1.3 | PASS, również ostateczny harness | Rzeczywiste różne ZIP-y, zachowane decyzje/kursor/JPEG, relink kopii wyniku, kontynuacja i kolejny proces, odmowa starszego readera |

Pierwszy update 0.1.0 zakończył się błędem polskiej etykiety w harnessie,
przed migracją. Log zachowano w `artifacts/selector-smoke-diagnostics/smoke-update-z7d7tO`.
Poprawiono cztery uszkodzone literały UTF-8; runtime i ZIP nie zmieniły się.
Kolejny przebieg zatrzymał się na oczekiwaniu pominięcia po Tab w starej
aplikacji; log `smoke-update-xPk6Mz` zachowano. Rzeczywisty ograniczony probe
0.1.0 potwierdził przyczynę: snapshot natywny już pokazywał accepted=1,
gdy React nadal miał busy=true, DOM „Wybrane: 0” i „Trwały zapis w toku…”.
Tab trafił do BODY, ale został prawidłowo odrzucony podczas zapisu. Harness
czeka teraz na obraz, DOM „Wybrane: 1”, zakończenie zapisu i aktywny przycisk
pominięcia. Nie osłabiono żadnej asercji. Finalny pełny update obu wersji
PASS; wszystkie historyczne porażki zachowano. Nie przypisujemy tej
udowodnionej przyczyny do każdego niewyjaśnionego błędu historycznego audytu.

Aktualizacja otwiera rzeczywisty starszy EXE po publikacji obu heads2.
0.1.0 i 0.1.2 zwracają `UNSUPPORTED_PROJECT_SCHEMA`; wszystkie pliki
migrowanego projektu i wyniku zachowują SHA, rozmiar i mtime, bez wyjątków.
Oryginalne fixture pozostają bez zmian. Po końcowych kontrolach nie ma
procesów Selektor-zdjec. Logi porażek pozostają poza usuniętymi fixture.

Z root wykonano pięć wariantów npm smoke:release oraz smoke:update; drugi
update używał `-- --old-archive=out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip`.
Pełne polecenia:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:start --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:shortcuts --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:ux --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:update --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:update --workspace @game-predictor/selector-desktop -- "--old-archive=out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip"
```

W sesji użyto równoważnych `scripts/run-bounded.mjs 120 npm run ...`
z katalogu desktop. Jedno uruchomienie każdego scenariusza naraz.

## Odpowiedzi na wszystkie uwagi rundy 2

Poniższe statusy są oceną wykonawcy opartą na kodzie i testach, a nie
niezależnym werdyktem Claude. Oryginalnego raportu audytora nie zmieniano.

| Uwaga | Wynik implementacji | Dowód |
|---|---|---|
| P2-A: martwa historia | Naprawione | Jawny brak projektu, ścieżka, Nowa partia po potwierdzeniu, tylko cache, deduplikacja i preferencja najnowszego wpisu; testy start-resume |
| P2-B: pełny inwentarz/historia na krok | Naprawiona przyczyna zapisu; jawne pozostałe koszty | D-546, head2/journal3, immutable sidecars, mirrory append-only, brak retencji; 82 testy compact i pomiar 15 000 |
| P2-C: auto-repeat decyzji | Naprawione | Wrapper desktopowy ignoruje repeat accept/skip/undo bez zmiany rdzenia lub Reviewera; unit i packaged smoke |
| P2-D: obce foldery i pozostawiony pusty projekt | Naprawione | Preflight obu folderów, precyzyjny kod i ścieżka, brak zapisu locka w obcym folderze; regresje niezmienionych danych |
| P2-E: niewyjaśnione start/update, brak logów | Naprawiona diagnostyka i udowodniony wyścig harnessu; historyczna przyczyna nieudawana | Jedna świeża próba wyłącznie timeoutu identity, fail-closed, metryki, failure logs, własne PID-y, kontrolowana porażka actual EXE, finalne start/update PASS |
| P3-A: close po obcym locku | Naprawione | LOCK_OWNER_UNKNOWN traktowany przy close jak LOCK_LOST, bez usunięcia obcych bajtów; testy i actual UX |
| P3-B: EXE podczas close | Naprawione | Jedno odroczone app.relaunch z właściwymi argumentami; actual dwa EXE → jeden nowy proces/okno |
| P3-C: nieaktualne dokumenty | Uporządkowane | D-545 bez fałszywego odroczenia0978, cztery plany, aktualny przedmiot odbioru0.1.3, taski/Outcome/state/traceability |
| P3-D: źródło brakującego seq JPEG | Uzupełnione | Instrukcja decisions[].imagePath/imageChecksumSha256/outputName, tylko identyczne bajty i brak nadpisywania istniejącego pliku |
| P3-E: zawartość ASAR bez automatycznej kontroli | Naprawione | Exact verifier siedmiu wpisów, SHA/provenance, 14 testów archive i każdy actual ZIP smoke |

Pierwszy audyt i reaudit uznały brak automatycznego repair JPEG, pełne SHA
przy open oraz nieznany recovery guard za jawne granice. Pozostają opisane
w instrukcji i architekturze; nie udajemy ich usunięcia. Dyski wymienne są
poza pilotem. Brak gwarancji zaniku zasilania lub synchronizacji projektu.

## Definition of Done i przekazanie

TASK-0984–0987 mają osobne commity, Outcome i sekcje stanu. Taski 0984–0986
zweryfikowano przy ich zamknięciu. TASK-0987 obejmuje finalne testy, release,
pomiar i dokumentację; wszystkie sześć jego kryteriów ma powyższy dowód.
Formalny audyt został jawnie odłożony przez operatora zgodnie z D-545.
[Końcowy brief](OFFLINE_PHOTO_SELECTOR_FINAL_CLAUDE_AUDIT_BRIEF_20261012.md)
pozwala przekazać całą implementację Claude Code bez składania kontekstu od nowa.

Nie uruchomiono usług operatora ani nie zmieniono jego danych, API, Admina,
Reviewera, OpenAPI lub bazy. Końcowy audyt Claude i fizyczny odbiór TASK-0979
pozostają zadaniami operatora.
