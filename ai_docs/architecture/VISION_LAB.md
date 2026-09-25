---
title: Laboratorium geometrii i symboli — architektura
status: accepted
last_updated: 2026-09-25
---

# Architektura laboratorium wizji

Właścicielami reguł i kolejności są `requirements/VISION_LAB.md` oraz
`delivery/VISION_LAB_EXECUTION_PLAN.md`. Eksporter jest osobnym narzędziem
głównego środowiska. Czyta manifestem wskazane źródła, dostępne rewizje,
metadane pochodzenia, słowniki i związane zatwierdzenia; używa krótkiej
transakcji `REPEATABLE READ READ ONLY`, limitów czasu i partii. Snapshot
publikuje atomowo po kontroli checksum. Pierwotny `selective_board_review_v1_1`
i późniejsza ręczna reweryfikacja są odrębne; brak pierwszej wyklucza
porównanie. Laboratorium nie ma połączenia z bazą.

Manifest wejściowy v1 ma `schemaVersion`, `datasetName` i pozycje
`{gameId, sourceImageId, expectedSourceSha256, sourceFamilyId, role}`.
Eksporter czyta tylko wskazane `source_images`, związane
`image_source_geometry_revisions`, `image_page_geometry_overrides`,
`recognized_boards`, `image_board_geometry_revisions`,
`image_board_geometry_review_events`, `image_symbol_review_cells` i
`image_symbol_review_events` oraz niezbędne `games`, `symbols` i
`rules_version_symbols`. Pierwsza krótka transakcja RO zamraża ID,
rewizje i fingerprinty powiązanych wierszy. Kolejne partie w nowych
transakcjach czytają dokładnie te ID; zmiana albo brak wiersza blokuje
publikację. Następuje kopia zarządzanych obrazów po kontroli SHA-256,
tymczasowy manifest, fsync plików i atomowy rename na jednym wolumenie
(fsync katalogu tam, gdzie wspiera go system). Snapshot ID jest SHA-256
kanonicznego wejścia, wersji eksportera oraz zamrożonych ID/rewizji.
Idempotentny retry weryfikuje opublikowane pliki; konflikt kończy błędem.

Dane poza repo pod `C:\Users\tuszy\Documents\game_predictor_vision_data`
obejmują niezmienne manifesty, zarządzane kopie obrazów, anotacje,
checkpointy, raporty i backupy. Zapisy są atomowe; wykonuje się próbę
odtworzenia. `GeometryEngine`, `GeometryResult` i `SymbolRecognizer` są
proponowanymi wspólnymi kontraktami dla baseline, hybrid i neural_grid.
Wynik zachowuje źródło, topologię, plansze, węzły, pochodzenie punktów,
wersję modelu i powody korekty. Układ plansz ekranu jest niezależny od
`BoardTopology` pojedynczej planszy. 5 × 3 ma 24 węzły, 3 × 3 ma 16.
Nie zakłada się dziewięciu plansz; nieobecność, zasłonięcie i nieczytelność
są osobnymi stanami. Bramka kontroluje kolejność, przecięcia, dodatnie pola
i kompletność bez wymogu konkretnej techniki OpenCV.

Hybryda używa MobileNetV3-Small, narożników, perspektywy i opcjonalnego
dopasowania. Neural_grid przewiduje pełne węzły. Symbole bazują na
`SpatialSymbolCnn`: RGB, szarość powielona na trzy kanały i fuzja z
udziałem RGB 0/0,1/0,2/0,3. Kalibracja jest tylko na walidacji;
niezgodność modeli jest sygnałem niepewności.

Proponowany FastAPI `game_predictor_worker.vision_lab` działa na
`127.0.0.1:8102`, a Next.js `apps/vision-lab` na `127.0.0.1:3102`.
Frontend używa proxy z zamkniętą listą tras. FastAPI posiada OpenAPI i
osobny generowany klient kontrolowany w `openapi:check`/`quality`.
Oba wejścia kontrolują Host; zapis wymaga dozwolonego Origin i JSON.
Assety są identyfikowane w rejestrze, bez dowolnych ścieżek od klienta.
Zajęty port zgłasza błąd bez zabijania procesu; brak tunelu.

Testy importów chronią granice: lab nie importuje `storage`, `psycopg` ani
produkcyjnego handlera treningu; produkcyjne wejścia nie importują labu;
neutralny rdzeń nie zależy od bazy ani UI. Izolowane środowisko przypina
PyTorch 2.12.1, torchvision 0.27.1 i CUDA 13.0; główne środowisko pozostaje
bez zmian. Integracja CPU używa ONNX Runtime. Checkpoint v2 zawiera optimizer,
scheduler, RNG, konfigurację i SHA-256 danych. Odczyt v1 pozostaje możliwy
bez obietnicy numerycznie identycznego wznowienia. Produkcyjny
`training_job.py` użyje neutralnego rdzenia dopiero w T12 po regresjach.

Proponowany `vision_lab/runs.py::RunManager` powstaje w T04 i jest
właścicielem trwałego kontraktu runów; panel T08 jest jego klientem.
Stan jest zapisywany atomowo pod
blokadą międzyprocesową i tokenem lease. `requestId` oraz fingerprint
manifestu, konfiguracji, modelu, topologii, preprocessingu i seeda są
trwałe przed spawnem. To samo żądanie zwraca ten sam run; ten sam ID z
innym payloadem daje konflikt. Stany: `queued → running →
succeeded|failed|cancelled`, bez pauzy. `running` wiąże PID, czas startu,
lease i heartbeat, więc restart nie uruchamia duplikatu. Wygasły lease po
sprawdzeniu tożsamości procesu daje recoverable `failed`. Cancel jest
utrwaloną intencją i kończy się po checkpointcie; awaria zachowuje ostatni
poprawny checkpoint. Retry jest jawną nową próbą z nowym lease po kontroli
fingerprintu; stary proces zostaje odgrodzony. Sukces wymaga atomowo
opublikowanych checksumowanych artefaktów i raportu.
