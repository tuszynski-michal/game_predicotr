---
title: TASK-0602 V7 label geometry calibration Admin screen
status: done
---

# TASK-0602 — Ekran Admina do anotacji geometrii etykiet V7

## Status

done

## Goal

Operator może utworzyć albo wznowić sesję kalibracji standard_3x3_numeric_labels_v1, oznaczyć jej canonical PNG i po odświeżeniu wznowić widok oraz niepotwierdzone operacje.

## Context

TASK-0601 dostarczył server-owned API: przeglądarka zna ID caseu, sesji i źródła, ale nie zna ścieżki ani nazwy JPEG-a. TASK-0603 potrzebuje trwałego ekranu operatora do zebrania punktów. Ekran nie może tworzyć outputu cut, uruchamiać V7 ani pozwalać wybrać reels_test.

## Dependencies / entry conditions

- TASK-0599 i TASK-0600 ukończyły kontrakt slotów, p95, export i durable receipt-y.
- TASK-0601, commit v0.10.336, dostarcza klienta sesji, mutacji, assetu, exportu i profilu.
- Minimalny zestaw UI ma dwa casey calibration pierwszej rodziny: small_777 oraz occluded_777. Ostateczna autoryzacja należy do manifestu serwera; reels_test nie jest opcją.
- V7 selection i adopcje pozostają zablokowane.

## Recommended execution

gpt-5.6-terra na xhigh: zadanie łączy interaktywną nakładkę, IndexedDB i współbieżne API, dlatego wymaga ścisłego rozdzielenia lokalnego zamiaru od potwierdzonej rewizji serwera. Po testach wymagany jest niezależny review gpt-6-astra na medium i poprawa wszystkich potwierdzonych uwag.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md, D-411–D-413
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/API_CONTRACT.md — Kalibracja geometrii etykiet V7
- .tmp/V7_LABEL_GEOMETRY_CALIBRATION_UI_PLAN.md
- apps/admin/src/features/imports/page-geometry-correction-panel.tsx
- apps/admin/src/features/manual-image-selection/filename-range-verification-store.ts
- packages/admin-api-client/src/index.ts

## Scope

- Dodać niezależny obszar Admina „Kalibracja etykiet V7”, dostępny bez wyboru gry, oraz ekran nowej i wznowionej sesji.
- Przekazać do API tylko stałą rodzinę i wybrane ID small_777/occluded_777. Błąd manifestu pokazuje komunikat API bez ścieżki.
- Renderować canonical PNG przez API, zwalniać object URL oraz normalizować kliknięcie względem elementu obrazu do [0,1].
- Pokazać dziewięć slotów, potwierdzone punkty, aktywną pozycję, akcję annotated z crop assessment, unavailable oraz captureGroupId.
- Trwale przechowywać w IndexedDB ID sesji, wybrane źródło/slot/assessment i uporządkowaną kolejkę niepotwierdzonych operacji.
- Każdy wpis kolejki ma UUID, pierwotną expectedRevision i payload. Jest wysyłany pojedynczo, nie jest kasowany przed receipt-em i może być ponowiony tym samym UUID po utraconej odpowiedzi.
- Konflikt rewizji, source drift albo niezgodność local state zatrzymuje flush. UI nie rebazuje operacji po cichu; operator może jawnie porzucić tylko lokalne, niepotwierdzone wpisy, a następnie odświeżyć sesję.
- Udostępnić export i próbę utworzenia profilu dla dokładnej rewizji. Niespełniona bramka pozostaje widoczna.

## Out of scope

- OCR, selection, cut, aktywacja V7, truth, validation i holdout.
- Zmiana manifestu, danych korpusu, API kontraktu oraz zapis bitmapy do browser storage.
- Service worker, synchronizacja między urządzeniami i automatyczne scalanie konfliktu drugiej zakładki.

## Acceptance criteria

- [ ] Nawigacja Admina otwiera ekran kalibracji, a reels_test nie jest możliwym casem.
- [ ] Tworzenie/wznowienie przekazuje tylko ID caseu i rodzinę; źródła są server-owned identyfikatorami bez ścieżek JPEG.
- [ ] Kliknięcie canonical PNG zapisuje centrum [0,1] wybranego slotu; zasłonięty slot może być unavailable bez sztucznego punktu.
- [ ] Crop assessment i capture group są jawnymi, kolejkowanymi operacjami kontraktu API.
- [ ] Szybkie kliknięcia zachowują kolejność/revizje, utracona odpowiedź nie tworzy duplikatu, a refresh przywraca sesję i queue.
- [ ] Konflikt rewizji nie zmienia expectedRevision; ręczne porzucenie czyści wyłącznie local queue.
- [ ] Asset jest zwalnianym Blob/object URL; IndexedDB nie zawiera PNG ani ścieżek.
- [ ] Testy pokrywają normalizację, częściową zasłonę, szybkie kliknięcia, opóźnioną odpowiedź, recovery i brak holdoutu.
- [ ] Testy, lint i typecheck przechodzą, a Astra Medium nie pozostawia P0–P2.

## Technical notes

V7LabelGeometryCalibrationLocalStore ma rekord widoku pod session UUID i rekordy kolejki pod [sessionId, sequence]. Po restore UI czyta aktualną sesję z API i porównuje manifest fingerprint. Niezgodność usuwa tylko wskaźnik widoku, zachowuje queue do jawnego rozstrzygnięcia i nie wykonuje mutacji.

Dodanie zamiaru najpierw utrwala rekord queue. expectedRevision to confirmedRevision plus liczba wcześniejszych wpisów. Flush wybiera pierwszy wpis. Receipt usuwa tylko ten wpis, utrwala zwróconą rewizję i uruchamia następny. Błąd sieci zachowuje wpis; 409 lub drift zatrzymują queue. Porzucenie niepotwierdzonych nie dotyka serwera.

Kliknięcie mierzy HTMLImageElement.getBoundingClientRect(), wyprowadza (clientX-left)/width i (clientY-top)/height, a potem clampuje. Punkt równy 0 albo 1 nie trafia jednak do kolejki, ponieważ API wymaga ścisłego wnętrza przedziału. Slot unavailable nie zawiera środka ani assessmentu. capture group używa set_capture_group bez slotu i trzyma tekst operatora osobno od rewizji sesji. Starter casey są wyłącznie stałym minimalnym zestawem T0603, a manifest serwera jest źródłem prawdy.

## Expected files

- Istniejące: apps/admin/src/features/catalog/admin-navigation-state.ts, apps/admin/src/features/catalog/catalog-workspace.tsx, apps/admin/src/app/globals.css, ai_docs/process/*.
- Nowe: apps/admin/src/features/v7-label-geometry/v7-label-geometry-calibration-workspace.tsx, v7-label-geometry-calibration-store.ts, v7-label-geometry-calibration-queue.ts i testy `apps/admin/test/v7-label-geometry-*.test.mjs` oraz `apps/admin/test-interactions/v7-label-geometry-calibration-workspace.test.mjs`.

## Test cases

- Kliknięcia rogów i poza granicą → zawsze [0,1].
- Pięć szybkich akcji → kolejność 0–4 i rewizje R…R+4; acknowledgement pierwszej nie usuwa kolejnych.
- Utracona odpowiedź → ten sam operationId pozostaje do replayu.
- Refresh → odtwarza session/view/queue i przed flush odczytuje serwer.
- Druga zakładka → 409 zatrzymuje queue bez rebase; porzucenie czyści tylko local queue.
- Częściowo zasłonięta etykieta → unavailable bez punktu.
- UI oferuje tylko small_777 i occluded_777.

## Verification

    npm run test --workspace @game-predictor/admin
    npm run lint --workspace @game-predictor/admin
    npm run typecheck --workspace @game-predictor/admin

## Risks / open questions

- Należy sprawdzić rzeczywisty Blob assetu w przeglądarce, nie tylko deklarację OpenAPI.
- Bez bezpiecznego discovery contractu starter casey są jawne; błąd manifestu nie otwiera inputu ścieżki.
- Niedostępne IndexedDB nie unieważnia odczytu, ale blokuje mutację przed ryzykiem utraty kliknięcia.

## Outcome

### Changed

- Dodano niezależny ekran Admina „Kalibracja etykiet V7” bez kontekstu gry,
  dostępny wyłącznie dla `small_777` i `occluded_777`.
- Ekran pobiera canonical PNG po API, zwalnia object URL i wiąże go z sesją,
  source ID oraz SHA. Stary albo opóźniony asset nie może przyjąć kliknięcia
  po przełączeniu źródła.
- IndexedDB utrwala widok oraz kolejkę operacji. Wpis techniczny nie jest
  serializowany do HTTP; wysyłane są tylko pola kontraktu API. Kolejka
  odtwarza utracony receipt bez rebase, trwale zatrzymuje się po konflikcie,
  driftcie albo blokadzie i blokuje flush/nowe kliknięcia podczas porzucania.
- Pole grupy ujęć trzyma draft per source, dzięki czemu receipt innej operacji
  nie usuwa wpisywanego tekstu ani fokusu.

### Verification results

- Przeszło 10 testów jednostkowych kolejki i kontraktu ekranu.
- Przeszły 2 testy interakcyjne z opóźnionym IndexedDB, mutacją API,
  przełączeniem assetu, kliknięciem granicznym, draftem grupy i porzuceniem
  kolejki.
- `npm run lint --workspace @game-predictor/admin` — bez błędów; pozostało
  wcześniejsze ostrzeżenie `no-img-element` w
  `features/imports/image-folder-import-panel.tsx:1906` poza zakresem taska.
- `npm run typecheck --workspace @game-predictor/admin` i
  `npm run build --workspace @game-predictor/admin` przeszły.
- Końcowy review Astra Medium: brak P0–P2 po poprawkach.

### Not completed

- Pełne `npm run test --workspace @game-predictor/admin` pozostaje czerwone
  przez wcześniejszy, niezmieniony test
  `test/page-geometry-correction-panel-contract.test.mjs:52`. Oczekuje on
  jednoliniowego formatu filtra w niepowiązanym panelu; plik źródłowy i test
  nie należą do tego taska.
- Nie uruchamiano V7 selection, OCR, zapisu `cut` ani bramki aktywacji.

### Documentation updates

- Uzupełniono `CURRENT_STATE.md` i D-414 o trwałą kolejkę UI oraz jej granice.

### Recommended next task

- TASK-0603 — instrukcja operatora i pierwszy rzeczywisty zestaw anotacji
  kalibracyjnych; nie odblokowuje V7.
