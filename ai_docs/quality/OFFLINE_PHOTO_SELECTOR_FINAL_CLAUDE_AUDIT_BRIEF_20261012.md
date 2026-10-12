---
title: Końcowy audyt Claude Code — lokalny selektor Windows 0.1.3
status: ready_for_review
last_updated: 2026-10-12
---

# Zlecenie końcowego audytu selektora Windows

Przeprowadź niezależny audyt całej implementacji i finalizacji lokalnego
selektora. Operator wykonuje ten audyt po zakończeniu kodowania, zgodnie
z D-545. To zlecenie nie jest raportem audytu i nie nadaje kodowi PASS.
Model/reasoning potwierdź w swoim środowisku; plan zaleca Claude Sonnet 5.5
medium, a dla trwałości TASK-0985 high. Nie zastępuj Claude modelem Codex.

## Repozytorium, zakres i paczka

- Worktree: `D:\game_predicotr\worktrees\offline-photo-selector`.
- Gałąź: `codex/offline-photo-selector`; główny checkout pozostaje osobny.
- Cały tor implementacji: baza `bb883b5902cb0934b9732d1bc24361d01085051d`
  (v1.7.316) do bieżącego HEAD tej gałęzi.
- Przyrost po niezależnym audycie rundy 2: baza
  `c7b9d52ea09b22b4a5f174d4ce8212a242a43eca` (v1.7.332), TASK-0984–0987.
- Runtime finalnego ZIP-a: v1.7.337 /
  `0b1ab3302df2119efb2519661e2f82b8bdf545df`.
- Finalny ZIP 0.1.3:
  `apps/selector-desktop/out/releases/pilot-0.1.3-0b1ab330/Selektor zdjec-win32-x64-0.1.3.zip`.
- Rozmiar: 149410942 B. ZIP SHA-256
  `cfb078b5f86a57cd781d99210ff699849485031a1ac173b6acb1861c1a145761`.
- app.asar SHA-256
  `23e0fa358455e6796fa01fd6951e695a6d6b9e9312730c86ec3382a8bad0e3a2`.
- BuiltAt `2026-10-12T15:33:25.902Z`, releasedAt
  `2026-10-12T15:33:52.292Z`, dirty=false, applicationSourceDirty=false.
  Sąsiadujące `.sha256` i `.release.json` identyfikują ten sam artefakt.

Commity po v1.7.337 mogą zawierać dokumentację i harness aktualizacji.
Porównaj zakres zamiast przypisywać taki HEAD do starego build-info.
Aktualny runtime i rdzeń muszą być identyczne ze źródłami finalnego buildu.
Historyczne ZIP-y, pierwszy REVISE i późniejszy PASS pozostają zachowane.

## Dokumenty do przeczytania

Stosuj lokalne AGENTS.md, ale unikaj ponownego ładowania całych archiwów.
Przeczytaj właściwe fragmenty:

1. `ai_docs/README.md`, bieżące ograniczenia, plan selektora, TASK-0979
   i ostatnie sekcje selektora w `process/CURRENT_STATE.md`.
2. D-545 i D-546 w `process/DECISION_LOG.md`; pełny wpis roczny tylko jeśli
   indeks i kopie nie wystarczają. Hierarchia źródeł prawdy obowiązuje.
3. Sekcje desktopu w `requirements/MANUAL_IMAGE_SELECTION.md`
   i `architecture/MANUAL_IMAGE_SELECTION.md`.
4. Cztery plany: `delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md`,
   `OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md`,
   `OFFLINE_PHOTO_SELECTOR_START_PLAN_20261012.md`
   i `OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md`.
5. Odpowiednie pliki tasków 0975, 0976, 0977, 0978, 0980–0987 w
   `tasks/completed/`, w szczególności Acceptance, Verification i Outcome.
   Aktywny `tasks/0979-selector-desktop-release-acceptance.md` pozostaje blocked.
6. `guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`,
   `project/TRACEABILITY.md`, `quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md`
   oraz `OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_HANDOFF.md`.
7. Zachowane raporty `quality/OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md`
   i `OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md`.
8. Aktualne dowody wykonawcy:
   `quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md`,
   `OFFLINE_PHOTO_SELECTOR_MEASUREMENT_20261012.md`
   i `TASK-0985_ENGINEERING_REVIEW_CODEX.md`.

Mapa kodu: najpierw `architecture/CODE_MAP.md`, potem wyszukiwanie symboli
w `CODE_MAP_SYMBOLS.md`, a następnie konkretne moduły. Pliki większe niż
200 KB czytaj z offset/limit. Nie wczytuj całej historii niezwiązanych tasków.

## Co sprawdzić funkcjonalnie

- Jeden wybór katalogu zdjęć; automatyczne foldery projektu i wyniku obok
  źródła. Dla `D:\Mumie\123`: `123 selekcja` i `123 wybrane`.
- Nazwa gry jest etykietą historii. Rozwijana historia i ponowne wskazanie
  źródła wznawiają ten sam projekt, ostatnie zdjęcie i numerację bez resetu.
- Naturalna kolejność JPEG-ów jest niezależna od kierunku numeracji.
  Sprawdź rosnące i malejące pozycje, zakres z rangeForStart, krótszy zakres
  wyłącznie na końcu sesji, Enter/F +1 niezależnie od skoku, Tab bez zmiany
  zdjęcia, powrót do pominiętego zakresu, undo i restart z preview.
- Decyzje są szeregowane, licznik zmienia się dopiero po trwałym zatwierdzeniu.
  Repeat Enter/F/Tab/A/Ctrl+Z nie tworzy kolejnych decyzji, pola tekstowe
  chronione. Nawigacja strzałkami może się powtarzać.
- Nieobecny projekt z historii: jawna ścieżka, anulowanie zachowuje pracę,
  Nowa partia wymaga potwierdzenia i zapomina wyłącznie martwy cache.
  Niepusty wynik nadal blokuje nową partię; obce dane nigdy nie są usuwane.
- Oba foldery są sprawdzane przed utworzeniem któregokolwiek. Otwieranie
  obcego folderu nie zapisuje w nim locka. Najnowszy wpis historii wygrywa.
- Zamknięcie po LOCK_LOST i LOCK_OWNER_UNKNOWN kończy własny store,
  zachowując obcy lock. Drugie EXE podczas close otwiera jedno nowe okno
  po zakończeniu procesu, z zachowaniem właściwego profilu.
- View debounce/flush, zoom 100–3000%, fullscreen i preview ±3.
  Pickery można anulować. Źródło jest tylko do odczytu.

## Trwałość i bezpieczeństwo — priorytet audytu

Przeanalizuj `project/project-store.ts`, `project-storage.ts`, `state-codec.ts`,
`types.ts`, `project-lock.ts`, SecureFiles, controller oraz testy compact.

- Logiczny ProjectState schema1 i manifest operator-local schema v2 pozostają
  zgodne; nazwa manifestu nadal `manual-image-selection-output-v1.json`.
  Nie zapisujemy pod nią rdzeniowego wariantu items.
- Head2 pod dotychczasowymi nazwami primary/backup wskazuje dwie niezmienne
  kopie inventory/baseline i zatwierdzony prefix dwóch ledgerów append-only.
  Cała historia operationId pozostaje; brak wygaszania receiptów.
- Journal3 utrwala zamiar przed JPEG-em, a receipt dopiero po JPEG/ledgerach/
  head/manifest/backup. Crash, utrata odpowiedzi i retry nie dublują decyzji.
  Partial suffix może być uzupełniony tylko przy dokładnym dowodzie zgodności;
  obcy ogon, checksumy i oba uszkodzone mirrory blokują zapis.
- Upgrade journal1/2 po starym recovery: trwały descriptor przed pierwszym
  sidecarem, dwie kopie inventory/baseline, ledger, oba head2, descriptor
  usunięty na końcu. Stary reader musi odmówić na schema3 lub head2.
  Sprawdź rzeczywiste starsze EXE 0.1.0 i 0.1.2 na migrowanej kopii.
- Dwie P1 wewnętrznego review Codex zostały poprawione. Sprawdź szczególnie:
  frozen legacy relink musi być trwale potwierdzony i migrowany przed ack,
  retry po ENOSPC nie może ominąć upgrade; samo upgradeIntent w RAM nie
  dowodzi trwałego descriptoru przed sidecarami. Raport zachowuje REVISE.
- Pełne open/recovery sprawdza źródło i SHA wyników. Relink podczas pending
  operacji/upgrade sprawdza tożsamość, nie przyjmuje pustego zamiennika.
- Lock powstaje atomowo, zna host/proces/tożsamość. Timeout/heartbeat nie
  dowodzi śmierci właściciela. Jedno ponowienie wyłącznie timeoutu identity
  nie osłabia fail-closed. Reparse pointy i wyjście poza korzeń odrzucane.
- IPC sprawdza nadawcę, typy i identyfikatory. Sandbox, contextIsolation,
  nodeIntegration=false, CSP, brak zewnętrznej nawigacji/okien/sieci.
  Obrazy strumieniowane przez własny protokół, bez base64 w IPC.
- Log rotowany bez zdjęć/ścieżek/tożsamości; bounded metadata. Failure smoke
  zachowuje log poza fixture, sprząta tylko zapisane własne PID-y, a przy
  błędzie capture zostawia fixture. Automatyczny verifier sprawdza świeży
  rzeczywisty ZIP, SHA, dokładne siedem wpisów ASAR oraz provenance.

## Testy i pomiar — jak oceniać dowody

Wykonawca raportuje desktop 262/262, core 110/110 i operator-local Reviewer
16/16 PASS, lint/typecheck/format oraz docs/mapy/diff. Dokładne komendy,
limity i finalne smoke są w raporcie wykonawcy. Nie traktuj wcześniejszych
testów ani analizy jako nowych wyników audytora.

Pomiar jest osobnym, jawnie zatwierdzonym zakresem: 15 000 własnych JPEG 8×8,
100 operacji na wersję, baseline c4181f7d i current c43434c2. Finalny runtime
v1.7.337 ma identyczne src. NAV p50/p95 918,79/979,36 → 95,08/106,66 ms;
accept 976,16/1024,35 → 124,49/143,81 ms. Zero nowych warm worker spawns,
niezmienne inventory/baseline, zachowane prefixy ledgeru i wszystkie SHA/
mtime oryginałów. Surowe pliki są w
`artifacts/selector-measurements/final-20261012/summary.json`; własne fixture
w `.tmp/selector-measurements/final-20261012/` zachowano do weryfikacji.
Nie powtarzaj benchmarku ani nie twórz kolejnego dużego fixture bez osobnej
zgody. Pomiar nie obejmuje wielkich JPEG, renderowania, tysięcy decyzji,
transportu Electron IPC, zimnego fizycznego dysku ani utraty zasilania.
Create/open, manifest O(D), source IPC O(N) i retencja pozostają jawne.

Każdą skończoną kontrolę uruchamiaj z jawnym limitem. W PowerShell z root:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run code-map:check
```

Testy actual ZIP opcjonalnie powtórz dopiero po kontroli ich zakresu z
raportu wykonawcy, osobno z limitem 120 s. Nie buduj nowej paczki zamiast
audytować istniejącą. Pierwsze porażki i zachowane logi są częścią dowodów;
nie podmieniaj ich samą deklaracją końcowego PASS.

## Granice i oczekiwany raport

Pracuj tylko do odczytu. Nie zmieniaj runtime, tasków, manifestów ani danych
operatora, nie wykonuj commit/push/merge. Nie uruchamiaj/zatrzymuj API/Admin/
Reviewera ani nie przejmuj portów lub cudzych procesów. Własne małe testowe
kopie tylko zgodnie z lokalnymi regułami, bez usuwania obcych plików.
Zdjęcia i wyniki pozostają u użytkownika. Brak uploadu, linków i integracji
Proton Drive, chmury, instalatora lub podpisu.

Zaakceptowane granice: pełne SHA przy open, ręczne odtworzenie brakującego
JPEG z decisions[].imagePath po identycznej checksumie, nieznany recovery
guard wymaga diagnostyki operatora, dyski wymienne poza pilotem, brak
certyfikacji zaniku zasilania. Fizyczny odbiór TASK-0979 (drugi komputer,
rzeczywista dystrybucja, restart Windows, ochrona i aktualizacja odbiorcy)
jest PENDING; nie oznaczaj go PASS z lokalnego smoke.

Przekaż raport zgodny z `quality/AUDIT_REPORT_TEMPLATE.md`: PASS albo REVISE,
P0–P2 z plik:linia, zamknięte i otwarte uwagi poprzednich audytów, testy
faktycznie wykonane i proponowane oraz granice dowodów. Rozróżnij przegląd
statyczny i uruchomione testy. Raport skieruj do
`ai_docs/quality/OFFLINE_PHOTO_SELECTOR_FINAL_AUDIT_CLAUDE_20261012.md`
przez operatora; jedynym dopuszczonym zapisem jest ten raport, jeśli operator
zleci jego zapis. Nie zmieniaj źródeł. Otwarte P0/P1 muszą być widoczne;
wewnętrzny review Codex nie zastępuje niezależnego audytu Claude.
