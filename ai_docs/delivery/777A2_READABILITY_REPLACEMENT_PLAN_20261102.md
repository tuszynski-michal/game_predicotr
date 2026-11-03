---
title: Nieczytelne i nałożone symbole 777 A2
status: accepted
last_updated: 2026-11-02
---

# Wykrywanie nieczytelności i wymiana całych zdjęć

## Zgody i warunki

Operator zatwierdził cały plan, jego koszt oraz audyt Claude Code Opus 5.5 po KAŻDYM zadaniu (także A3). Implementacja bez automatycznego merge/push, restartów usług, migracji bazy operatora i operacji na jego danych. Pełny skan wymaga pilota i odbioru operatora. Model bazowy: jawnie zatwierdzony kandydat nr 5 gry `777a2`, `9afa868a-70f8-42df-9f15-f2833cd98c10`, bez aktywacji. Gra `6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf`. Koszt i wybór kandydata zatwierdzone w czacie 2026-11-02.

Kandydat ma architekturę `spatial-symbol-cnn-v1`, input64. Checkpoint SHA `29fbc9862c347e472eb2c256ab58c2ad34feb06e91db7fab9a5c0c739598649d`; plik `artifacts/data/models/777a2/9afa868a-70f8-42df-9f15-f2833cd98c10/checkpoints/trained-0040-29fbc9862c347e472eb2c256ab58c2ad34feb06e91db7fab9a5c0c739598649d.pt`. Dataset `artifacts/data/training/777a2/d01db572f4eef1e98a51f0e5996e910003528c9b290a8b447a8a831edeb70e3a/manifests/696cac7e444436569bb7804917e40941ab01277951451e491bbd86a2d78180aa.json`. Sprawdzić pełne członkostwo splitu, checksumy i preprocessing przed użyciem; brak danych = STOP eksperymentu. Dane i pliki nie są kopiowane do git.

Dominujący problem: dwa RÓŻNE symbole NAŁOŻONE W TYM SAMYM MIEJSCU, także ostre i pewnie rozpoznawane. Ponad 11000 historycznych unreadable to deklarowana liczba i materiał do oceny, nie automatyczne etykiety nałożenia. Wymiana obejmuje stare i nowe potwierdzenia, wyłącznie źródła wybrane przez człowieka. Całe zdjęcie zwykle ma 9 plansz; rzeczywiste zakresy wynikają z relacji źródła. Nowe zdjęcia mają te same zakresy seq. Zachować modele, aktywację, historię, kohorty i potrzebne pliki; wycofać stare źródło z bieżących plansz, nie niszczyć dowodów.

## Zadania i kolejność

### TASK-1124 / A1 — Rdzeń detektora

Dwa niezależne heady: obecność nałożenia i nieczytelność. Zamrożone `SpatialSymbolCnn.features` 64x4x4, eval/inference_mode, bez zmian wag/BN/aktywacji; nie używać SmallSymbolCnn.encode. Preprocessing zgodny z checkpointem: INTER_AREA, [-1,1]. Dodatkowe cechy Laplacian/Sobel, kontrast P95-P5, entropia, ciemne/jasne piksele i kierunkowość liczyć na natywnym RGB przed resize. Standaryzacja tylko TRAIN. Top1/top2 nie są cechą ani filtrem skanu. Nie trzeba znać pary składowych symboli. Bez syntetycznych nałożeń i uczenia na sugestiach.

Liniowe heady L2: lambda {0.01,0.1,1,10}; mean BCE + lambda*sum(w²)/2; bias bez kary; LBFGS strong_wolfe, lr1, zero-init, max1000, tolerance_grad1e-6/tolerance_change1e-9, deterministic CPU. Niekonwergencja = błąd. Na VAL wybierać dla każdej lambdy najwyższy próg dający recall>=95%, potem wariant o najwyższej precision, remis silniejsza lambda. TEST nigdy nie stroi. Kandydat przy przekroczeniu dowolnego progu. Ranking max(score-próg), drugi margines, seq/cellId. Score nie jest deklarowanym skalibrowanym prawdopodobieństwem. Artefakt przypina checkpoint, dane/splity, scaler, solver, preprocessing, progi i wersję cech przez fingerprint.

Pilot po A2: do600 rzeczywistych wycinków, połowa unreadable, połowa nieoznaczonych/zaakceptowanych, warstwowo po źródle/importach/klasach. Człowiek oznacza osobno overlap i czytelność, dopuszczalne niepewne (wyłączone z odpowiedniego fitu) oraz overlap+readable. Rodziny łączą reimporty/sourceSHA, znane nagrania i exactRGB. Najpierw TEST z bazowego TEST/REG lub nowych rodzin spoza bazowego TRAIN/VAL; reszta TRAIN/VAL bez chronionych bazowych TEST/REG. Docelowo60/20/20, bez łamania rozłączności. Minimum w VAL i TEST:40 overlap+unreadable,40 readable (10 trudnych podobnych),20 other unreadable. TEST dodatkowo10 ostrych overlap+unreadable/5rodzin oraz10 overlay+unreadable przy top1>=.95/5rodzin. TRAIN>=10rodzin każdego rodzaju. Brak provenance/liczności w limicie600=STOP, bez automatycznego zwiększania próby.

Bramka TEST recall>=90% overlap+unreadable i wszystkich unreadable. Osobne wyniki ostrych, pewnych top1 i FPR podobnych czytelnych, Wilson95, liczby rodzin. Top1 i poprzedni review wyłącznie warstwują ocenę. Dodatkowe200 losowych dotąd nieoznaczonych pól służy ocenie naturalnego szumu/przeoczeń, nigdy strojeniu. Pełny skan dopiero po bramce i odbiorze operatora; bez kolejnych automatycznych treningów. Brak grupy pewnych nałożeń oznacza skuteczność niezmierzoną, nie PASS. A1 implementuje narzędzia, testy i walidację; nie wykonuje pilota bez etykiet z A2.

Uściślenie odbioru A1 po audycie (2026-11-02): bazowy preflight sprawdza RGB64x64 KAŻDEGO assetu, aby różny resize treningowy/produkcyjny nie zmieniał tych wejść. Para checkpoint–dataset jest autoryzowana przez jawny wybór kandydata nr 5 i oba SHA z tego planu; checkpoint nie zawiera samodzielnie odtwarzalnego deskryptora datasetu. Nie wolno podmieniać pary dowolnym innym kandydatem.

Naturalny audit200 losuje jednostajnie dotąd nieoznaczone pola wyłącznie z rodzin poza pilotem oraz bazowym TRAIN/VAL. Losowanie i zapis receipt z seed/identity następują przed etykietami i fitem headów. Raport mierzy szum/przeoczenia tej jawnie ograniczonej puli, nie całej gry. Rodziny zachowują pełną izolację; łączny limit wynosi 800 pól (do600pilot + dokładnie200audit). Brak kwalifikowanej puli oznacza STOP, bez osłabiania splitu ani automatycznego powiększania próby.

### TASK-1125 / A2 — Trwały skan i przegląd

Rozszerzyć istniejący obszar weryfikacji symboli o trwały run/model artefakt, wyniki i etykiety związane z crop/geometry identity. Skan wszystkich aktualnych wycinków (także pewnych/approved), inwentarz i fingerprint modelu, checkpoint per source, ograniczone porcje i jedno zdjęcie naraz, restart i idempotencja. Statusy pending/readable/unreadable/skipped/stale/error i osobno overlap true/false/null. Zmiana pikseli unieważnia etykiety. Brak zdjęcia/outside/geometria osobne przyczyny.

UI: stare/nowe, typ problemu, crop/zoom/całe źródło, seq/pozycja, powody i osobne oceny nałożenia/czytelności; akcje grupowe. Readable nie zatwierdza nazwy ani nie usuwa historycznej quality_issue. Unreadable korzysta z istniejącej mutacji rewizyjnej. Overlap+readable nie kwalifikuje wymiany. Raport pola/plansze/źródła i CSV numerów. API/OpenAPI/generated client/wrapper/request test jednym pionem. Etykiety pilota dostarcza operator; bez nich model jakości pozostaje niegotowy.

### TASK-1126 / A3 — Shift

Zwykła weryfikacja i kandydaci: klik toggle+anchor, Shift dodaje inclusive range obu kierunków po pełnych danych bieżącej strony (max2500), nie DOM; pomija locked, nie przełącza już zaznaczonych. Zmiana gry/filtra/sortu/strony/refetch reset anchor. Bez anchor zwykły klik. Przekroczenie limitu10000 odrzuca cały range. All_matching usuwa wyłączenia tylko range. Zachować bulk preview/jobs i stare interakcje.

Uściślenie A3 (2026-11-03): limit10000 dotyczy zaznaczenia; label API zachowuje limit250/żądanie. Większy zapis to sekwencyjna trwała kolejka: cały snapshot targetów/identity/revisions i klucze wszystkich porcji zapisane przed pierwszym requestem, checkpoint po potwierdzeniu. Błąd/konflikt pauzuje ogon, UI pokazuje wykonane/pozostałe; ręczne retry używa oryginalnych kluczy i rewizji także po restarcie/lost response. Bez rebase, bez zmiany API. Małe komendy zachowują dotychczasowy workflow. Jawne porzucenie pozostałych porcji wymaga potwierdzenia operatora i nie cofa zapisów. Niepotwierdzona porcja mogła już zostać zapisana; UI mówi o tej niepewności. Porzucenie jest zablokowane podczas requestu i dostępne również dla uszkodzonej kolejki bez zgadywania postępu. Zaznaczenia jakości i ich snapshoty pozostają pomiędzy stronami250; zmiana strony zeruje tylko anchor, filtry/run/refetch także zaznaczenie.

### TASK-1127 / B1 — Manifest wymiany

Nowe game-scoped batch/entry/slot reservations/retired provenance, migracje Alembic i manifest schematu/RLS/indexy. Deduplikacja po rzeczywistym source, nie numerach zaokrąglonych do9. UI wybór całych źródeł i ich plansz, powody, zakresy, zależności/blokery. Manifest trwale PRZED wycofaniem: game/source/SHA/board/seq/revisions/powody/status; JSON i CSV. SHA pliku nie zastępuje serwerowej autoryzacji/stanu. Istniejący board-sources API rozszerzyć o replace_preserve_history, bez wywołania delete graph. Nowa jawna decyzja zawęża D-543. Każdy command idempotency+expected revision, preview token przypina exact identity, nie tylko counts.

Uściślenie B1 (D-579, 2026-11-03): exact sourceIds rozwijają aliasy wyłącznie tej samej gry/SHA/atestowanego zakresu; niejednoznaczność lub obcy właściciel blokuje całe źródło. POST board-sources zapisuje planned, GET w tym obszarze odtwarza/eksportuje, istniejący preview otrzymuje mode replace_preserve_history. Planned nie tworzy aktywnych reservations ani retired markers. Append-only ledger A2 zapisuje atomowo kolejność ocen człowieka: ostatnia decisive readable/unreadable dla current pixel identity, bez nadpisania przez pending/skipped/pusty nowy scan. Legacy zgodne oceny zachowują proof, sprzeczne wymagają świeżej oceny. Aktualne readable wyłącza tylko powód danego pola. Main40581449 zintegrowany przed B1; B2a obejmie grid_correction_split population/prepare/validate, photo-only use registration, freeze/currentness i workflow/recovery; historyczne frozen evidence pozostaje.

### TASK-1128 / B2a — Strażnicy własności

Uściślenie wykonawcze B2a (2026-11-03): zapisany exact receipt jest odtwarzany przed guardem retired; konflikt key/body nadal odmawia. Nowa próba ma kolejność receipt → retired → CAS/ownership. Serwerowy `replacementAdmission` przypina game/batch/entry/job/source/newSHA/revision oraz pełne `sequence_numbers` niezmiennego manifestu. Pozwala na INSERT/flush provisional review bez przedwczesnego FK. Wszystkie sloty pozostają reserved; finalizator dopiero po kompletnym zdjęciu atomowo ustawia pending_bound dla istniejących review przed projekcjami. Robocza, niepełna geometria korzysta z tego samego proof przez wewnętrzny adapter, bez widoczności current i bez publicznego force. Normalizowana referencja nowego źródła powstaje przed roboczym review/geometrią i pozostaje po restored/usunięciu slotów. Operatorowy admission/import/UI pozostaje w C2.

Reservation przed canonical/incumbent w decide_sequence_claim: KEEP_RESERVED/CLAIM_RESERVED tylko pasujący game/batch/entry/newSHA/review. Jeden storage claim worker/manual pod sequence lock. sequence_source_selection reserved_gap; append_source_override blokuje reserved/retired; pending list/count tylko bound entry; _claim_canonical_sequence waliduje binding. select_board_search_document/reconcile_sequence/_rebuild_fast_documents identycznie wykluczają retired i obce alternatywy. Ten sam predykat w review/count/bulk start+execute/backfill/geometrii/reinferencji/training preview+freeze/recovery. Nowa kohorta nie dopuszcza retired; stare frozen pozostają.

FK RESTRICT i retention źródeł/cropów/model artifacts; cleanup źródeł/reset gry/delete_release/GC preview+execute blokują SOURCE_REPLACEMENT_REFERENCED także po restored. Reset blocker przed detach_grid_source_links, release przed mutacją. _retained_source_paths/_delete_crop_registry respektują cross-game public.source_image_crops. Historyczny UI retired/replaced bez wyboru źródła. Late commands najpierw retired niezależnie od fazy: SOURCE_REPLACEMENT_RETIRED bez zmiany reason/previous resolved_value. Dotyczy późniejszego przypisania sequence_number. Nie zmieniać zwykłego reject canonical.

### TASK-1129 / B2b — Wycofanie

Po B2a i osobnym potwierdzeniu świeżego preview: jedna transakcja/source. Blokady exclusive, seq rosnąco, sources rosnąco, potem item/board. Preview i execute wykrywają obcy live pending pod canonical: SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT blokuje całe źródło z linkiem do dotychczasowego rozstrzygnięcia. Własne pending atomowo superseded z source_replacement_retired, nowym builderem resolved_value bez wymagania canonical, pełnym poprzednim stanem i append-only eventem. Zachować accepted/corrected/history cells/geometrie/kohorty/models.

Zapisać pełny snapshot canonical, reservations wszystkich slotów, retired marker, usunąć tylko current canonical/read-model references. Manifest istnieje wcześniej i eksport można ponowić. record_super_game_input_change i invalidation projection states; current reads od razu wykluczają stale. Luka nie skleja sekwencji/supergry i nie ma starych current payouts. Nowy snapshot mobile gry z otwartą rezerwacją blokowany; wydane snapshoty pozostają. Shared inne gry bez zmian. Retry utrwala wynik. Stany planned/gap_open/replacement_staged/importing/awaiting_review/restored; failed zachowuje fazę. Cancel tylko planned; reservation nie wygasa; brak zamiennika=jawna wznawialna luka, restore_retired poza v1.

### TASK-1130 / C1 — Uzupełnij luki

Istniejący ekran przyjmuje source-replacement-request-v1. Tylko potwierdzone gap_open/wybrane zakresy, nie min-max gaps. Nowy repair-v3/source_replacement z allowedRanges i batch/entry/digest; bez fikcyjnych v2 deletion receipts/activeFiles. Folder nowych seq JPEG read-only, exact range, duplicate manual choose, zapis do osobnego outputu. Journal intent/write/hash/commit i recovery, obcy plik fail closed. v1/v2 bez zmian i odrzucają v3. deriveReplacementFilledGaps(v3) daje NIEZMIENIONY filled-gaps-v1 wyłącznie z ukończonych zweryfikowanych JPEG; sourcePath/fillOperationId z journala. Binding wyłącznie v3 i staging request. Lokalny plik nie zamyka backendowej luki.

### TASK-1131 / C2 — Import zamienników

Obowiązkowe domknięcia po audycie B2a R1 (P2-1/P2-2), przed udostępnieniem admission/restored: korekta niepełnej roboczej geometrii tego samego slotu ma zachować jeden skuteczny review i doprowadzić do whole-photo bindingu bez konfliktu duplikatów/unikalności. Restore lub porzucenie admission zamyka/wycofuje provisional atomowo PRZED zwolnieniem slotów; test po restarcie potwierdza brak current/queue/count/search/canonical orphan review. B2b ma jedynie cancel planned, bez restore. Nie rozszerza to B2a o operacyjne komendy.

Admission C2 przed przypięciem `slots.new_sha256` wykonuje pod wspólnym lockiem fresh preflight nowego SHA. Istniejące niewybrane current źródło tej gry z tym SHA w innym lub nieznanym zakresie blokuje całą operację `SOURCE_REPLACEMENT_SHA_SCOPE_CONFLICT`; bez ukrycia cudzych plansz ani rozszerzenia scope. Dopuszczony wyłącznie jednoznaczny exact entry/range alias oraz własny exact replay. Regresja z obcym zakresem 1200 sprawdza brak mutacji i niezmienioną widoczność current po odmowie.

Istniejące staging/preflight/import: optional batchId/entryIds/digest i przypięte noweSHA, bez generic force. Zwykły import reserved odmawia z linkiem do replacement. Ścisłe scope/range/identity, stareSHA/obce/niedopasowane pliki odrzucane. Target dopiero po jednoznacznym seq. reserved->pending_bound atomowo dla całego kompletnego zdjęcia; nie canonical z samego importu. Niepełna geometria zostaje robocza i trzyma reservation. Per-board canonical tylko normalnym accepted/corrected z binding validation. Częściowe review nie zwalnia reservation; rejected nowy zostaje w obrębie entry. Bez przenoszenia starych approvals. restored dopiero wszystkie sloty canonical z nowego source oraz operator potwierdzi czytelność wskazanych pól. Numery bez zmian; nowe boardId dopuszczalne. Derived wygrane/serie/search odświeżone. Retry/restart bez duplikatu. Tombstone starego źródła/SHA i historii pozostaje po zwolnieniu reservation.

### TASK-1132 / D1 — Odbiór

Testy pionów i całego przepływu: ostre overlay z pewnym top1; czytelne podobne; brak leakage base/head/scaler; neutralność wag/BN/model activation; stale pixel identity; Shift poza DOM i locked; source dedup9 i boundary<9; obcy pending/races; late commands po restored; późny seq; incremental/rebuild parity; retained model/cohort/shared crops obu gier; snapshots blocked while gap; journal i API lost response/restarts każdego etapu; niepełny batch/import/review nie udaje sukcesu. Najpierw testy pionu/lint/typecheck, potem szersze/build. API contract i request tests, map generator i docs:check. Mały operacyjny pilot i większy scan wymagają odbioru/zgód operatora. Testy opisane tutaj są planowane, nie wykonane.

## Dostarczanie

Osobny task, audyt Opus5.5 przed commitem, jedna runda poprawek P0/P1 według AGENTS, Outcome, task-close, wersjonowany commit, record-hash. Kontynuować cały zlecony plan, zatrzymując zależny zakres na rzeczywistym blokerze lub bramce operatora. Implementacja narzędzia nie oznacza wykonania operacji danych. Każda skończona komenda z timeoutem domyślnie<=120s, audyty<=480s, bez usług agenta.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1124 / A1 | gpt-6.1-sol | high | Cechy i niezależny eksperyment jakości | claude-opus-5-5 / high |
| TASK-1125 / A2 | gpt-6.1-sol | high | Trwały pion API/UI | claude-opus-5-5 / high |
| TASK-1126 / A3 | gpt-6.1-sol | medium | Zakres zaznaczenia i regresje UI | claude-opus-5-5 / medium |
| TASK-1127 / B1 | gpt-6-astra | high | Model danych i dowody | claude-opus-5-5 / high |
| TASK-1128 / B2a | gpt-6-astra | high | Własność i ochrona historii | claude-opus-5-5 / high |
| TASK-1129 / B2b | gpt-6-astra | high | Transakcje wycofania | claude-opus-5-5 / high |
| TASK-1130 / C1 | gpt-6.1-sol | high | Zgodność manifestów i recovery | claude-opus-5-5 / medium |
| TASK-1131 / C2 | gpt-6-astra | high | Import i własność sekwencji | claude-opus-5-5 / high |
| TASK-1132 / D1 | gpt-6.1-sol | medium | Odbiór i instrukcja | claude-opus-5-5 / medium |
