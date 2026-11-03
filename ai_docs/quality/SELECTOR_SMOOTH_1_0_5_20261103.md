# Selektor 1.0.5 — ciągły podgląd i lekka nawigacja

## Zakres

TASK-1142–1144, zaakceptowany plan SELECTOR_SMOOTH_NAVIGATION_20261103.md oraz koszt 2–4 godzin. Bez dodatkowego audytu zgodnie z tabelą planu. Implementacja i paczka Windows; bez merge/push i zmian danych operatora.

Źródło: D:/materiały game predictor/777 a2/1-27999 — 42420 plików, 4487051647 B. Źródło tylko do odczytu. Istniejący projekt ma blokadę i nie był otwierany ani modyfikowany. Każdy pomiar tworzył osobny projekt i wynik w katalogu testowym.

## Zmiany

- Zachowany oznaczony poprzedni JPEG do atomowej podmiany; brak pustej klatki, stabilny rozmiar i scroll. F/Enter nadal przypina cel, a nie pozostawiony obraz.
- Prefetch trzech celów w każdą stronę według skoku i ostatniego kierunku; 7 wpisów, estymata 128 MiB z przejściową ochroną widocznego i docelowego obrazu.
- Indeks inventory zamiast findIndex na każdym kroku, wąskie projekcje i cache podsumowania decyzji. Nawigacja IPC bez listy wyborów, ze zgodną rewizją bazową. Snapshot/retry odtwarza pełny stan.
- Współdzielona serializacja projekcji manifestu w transakcji; rzeczywiste kontrole plików, SHA, dzienników, receiptów, blokad i kolejności commita zachowane. Zapis manifestu nadal O(D).

## Metoda i ograniczenia

Harness smoke-large-navigation.mjs: istniejące JPEG, osobny nowy projekt bez wcześniejszej historii, początek/środek/koniec kolekcji; skoki 1/2/3/4/20, kierunek w obie strony. 150 warm i 15 pierwszych przejść; dodatkowe powroty przygotowują następne próbki. Nie czyszczono cache systemu. To lokalny odbiór, nie gwarancja sprzętu odbiorcy.

Pomiar wejście–paint to zdarzenie Chromium i klatka z właściwym src oraz następny requestAnimationFrame. Licznik pustych klatek sprawdza obecność i szerokość obrazu. Dodatkowy smoke decode-barrier porównuje src i dokładny bounding box przed i podczas ładowania. Pamięć to suma workingSetSize procesów tego Electrona (KiB przeliczone na MiB), nie sam cache bitmap ani twardy limit RAM.

Odbiór dużej partii nie odwzorowuje istniejącej historii decyzji operatora. Testy recovery/undo/manifestu i oddzielny mały pomiar obejmują decyzje, utratę odpowiedzi i nowy proces. Fizyczny restart Windows i odbiór na innym komputerze nie były wykonywane.

## Wyniki bazowe

- 1.0.4, mała partia: warm p95 24,4 ms.
- 1.0.4, 42420 JPEG, 150 warm: p95 38,9 ms, max 45,6 ms; 108 pustych klatek w 165 zapisanych przejściach. Pełne zakończenie harnessu PASS. Pamięć w czterech punktach: 789,8 / 944,1 / 1351,6 / 1313,1 MiB.
- Pierwsze pełne próbki nowego kodu: warm p95 25,2 ms, max 25,6 ms, zero pustych klatek; pamięć 819,3 / 808,1 / 760,0 / 780,7 MiB. To próbki, nie PASS całej próby, której zamykanie przekroczyło limit helpera.

## Weryfikacja

- P1: 34/34 cache/intents/UI PASS, lint/typecheck i Electron fluency PASS.
- P2: 78/78 project/intents/workspace PASS, lint/typecheck/build i Electron fluency PASS.
- P3: 46/46 UI/foundation/catalog/output/release/diagnostics/workspace PASS; compact persistence 51/51 + 32/32 PASS; native/start/legacy/archive 110/110 PASS. Zestawy częściowo się pokrywają; liczb nie sumujemy jako unikalnych testów.
- Format zmienionego kodu, lint, typecheck, docs:check i code-map:check PASS.
- Poprawiony finalny ZIP: fluency, workflow, measurement i shortcuts PASS, w tym pozycja obrazu, zoom/scroll/fullscreen, protokół, IPC, retry, crash, handshake, kierunek numeracji i relink.
- Mały pomiar finalnego ZIP: 30 warm, mediana 23,2 ms / p95 24,2 ms / max 24,8 ms; 4 cold, p95 39,1 ms; 10 potwierdzeń zapisu, p95 189,3 ms. Wszystkie 10 wyborów i dokładne SHA JPEG zachowane po nowym procesie; podgląd wyświetlony przed kontrolowanie opóźnioną odpowiedzią native.

## Nieudane próby i poprawki

Początkowy Electron i testy systemowe bez wymaganych uprawnień kończyły się błędem uruchomienia/NATIVE_CHECK_FAILED; powtórzenie z uprawnieniami PASS. Jeden test katalogu gier wymagał cwd aplikacji; poprawne uruchomienie PASS. Dwie zbyt duże grupy persistence przekroczyły 120 s, bez potwierdzonego błędu asercji; podzielono je, oba mniejsze zestawy PASS.

Harness dużej partii poprawiono po błędnej odpowiedzi dialogu, zbędnych ponownych skanach i ukrytym limicie helpera 110 s. Duży odbiór ma jawny wewnętrzny limit 220 s i zewnętrzny 240 s, po uprzedzeniu operatora. Nie zmieniono limitów istniejących smoke.

Narzędzie smoke-update początkowo dopuszczało tylko 0.1.0/0.1.2/1.0.3. Dodano jawny przypadek 1.0.4: współczesna nazwa wyniku oraz zgodność formatu head2, bez oczekiwania odmowy starego readera. Stare asercje odmowy pozostają dla 0.1.x; nowy test sprawdza ponowne otwarcie w 1.0.4 bez zmian bajtów. Otwarcie przez 1.0.4 publikuje identyczne bajtowo oba heady, więc wyłącznie ich mtime może się zmienić; wszystkie pozostałe mtime i całe wyniki nadal są porównywane dokładnie. Początkowe oczekiwanie braku publikacji identycznych headów w nowym przypadku 1.0.4 było zbyt szerokie; istniejące asercje odmowy readerów 0.1.x pozostały bez zmian. Jest to rozszerzenie harnessu po zbudowaniu ZIP, bez zmiany kodu aplikacji w artefakcie.

Pierwszy ZIP (kod 40f43052, SHA e91dbacd2b1a61aa291ae41abb37fd0173ea1cb74a620bf297dad76743b1defc) nie jest paczką do przekazania. Nowy test wykrył przesunięcie y o 149,45 px: host display:contents ignorował grid-area. Poprawiono na display:block; ścisły test pozycji PASS. Kandydat zachowany w artifacts/selector-releases/1.0.5-candidate-40f43052. Nieudane próby i logi: artifacts/selector-smoke-diagnostics i .tmp/ w worktree.

## Finalny artefakt

Kod: v1.7.538 / 1f1131c15c70c6c040db3e2a69d6d9927044a673; dirty=false, applicationSourceDirty=false.
ZIP: 149421371 B. SHA-256: b941c615c8f72eae9aed592dc6df8a31978255e99a9b037b1537cf3754e6aac3.
app.asar SHA-256: 618238f8d437c243503cac9283e2d9eb888689a0162bd22b24625bc579361006.
Finalny pomiar programu z ASAR identycznym z rozpakowanym ZIP PASS: 42420 zdjęć, 150 warm, p95 25,4 ms, maksimum 54,9 ms; zero pustych klatek w 165 zapisanych przejściach. P95 spełnia cel <=50 ms, pojedyncze maksimum go przekracza i pozostaje w raporcie. Program zamknięty poprawnie, fixture posprzątany przez kontrolowany helper.

Pamięć wszystkich procesów Electron w czterech punktach (MiB): 826.3 / 801.2 / 667.8 / 697.6. Są to próbki, nie dowód braku każdej postaci wycieku ani limit RAM. Rozdzielczości próbek początek/środek/koniec: [{'width': 1080, 'height': 960}, {'width': 1080, 'height': 960}, {'width': 1080, 'height': 960}].

Finalny ZIP: fluency / workflow / measurement / shortcuts / pełny offline smoke PASS. Rzeczywiste wydania 1.0.4 do 1.0.5, dalsza praca na kopii i nowy proces PASS. Ponowne otwarcie kopii w 1.0.4 potwierdza zgodność formatu. Oryginalne fixture upgrade pozostały bez zmian.

Paczka do przekazania: D:/game_predicotr/artifacts/selector-releases/1.0.5/Selektor zdjec-win32-x64-1.0.5.zip; obok SHA, metadane, instrukcja i measurements/. Surowe dane w worktree: artifacts/selector-smooth-20261103/large-final-zip.json, large-baseline-complete.json, measurement-final-zip.json; logi smoke i testów w .tmp/.

## Ocena Definition of Done i planu

P1: brak pustej klatki, stabilny bounding box podczas decode, skoki i cache z regresjami PASS. P2: indeksy i pominięcie listy w nawigacji z wymaganym fallbackiem; testy stanu i trwałości PASS. P3: pomiar przed/po na tej samej kolekcji, cel warm, testy pełnego przepływu i finalny ZIP PASS. Dokumentacja oraz Outcome aktualizowane i taski zamykane osobno. API HTTP, baza, oryginalne projekty/zdjęcia operatora i usługi nie były zmieniane. Merge/push nie wykonano.

## Uruchomienie

Zamknąć poprzednią wersję Selektora, rozpakować cały ZIP do osobnego folderu i uruchomić Selektor-zdjec.exe. Wskazać dotychczasowy folder/projekt; aplikacja wznawia postęp. Fizyczny restart Windows i praca na innym komputerze pozostają niezweryfikowane. Rosnący koszt manifestu O(D) oraz historia aktywnego projektu operatora nie są objęte gwarancją czasu <=50 ms dla każdej operacji.
