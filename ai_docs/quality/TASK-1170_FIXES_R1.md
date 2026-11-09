---
title: TASK-1170 — Jedna runda poprawek audytu R1
status: active
last_updated: 2026-11-09
---

# TASK-1170 — Poprawki R1

Źródło: `TASK-1170_AUDIT_claude-opus-5-5_R1.md`, werdykt REVISE.
Wykonano jedną rundę poprawek bez audytu własnej pracy, stage ani commita.
Poniższa mapa opisuje zmiany wykonawcy; o zamknięciu uwag rozstrzyga focused R2.

| ID | Zmiana / rozstrzygnięcie | Dowód |
|---|---|---|
| P0-1 | Pure walidacja produkcyjnego manifestu/komórki zwraca unavailable z zachowanymi24nodes i pozostałymi poprawnymi footprintami. Złe checksumy, brakujące klucze, błędne quady/konfiguracje i duplikaty nie blokują istniejącej zatwierdzonej adnotacji ani edytora. Legalne częściowe quady poza kadrem zachowują dokładne współrzędne; tolerancja EPS przy granicy realnych pikseli. Catch obejmuje wyłącznie KeyError/TypeError/ValueError w czystej walidacji dokumentu, nie DB/infrastrukturę. Eksport zachowuje taką planszę z jawnym brakiem zamiast przerywać galerię. | `test_grid_content_preview.py`: zmieniony świadomie test changed-pin zgodnie z D594 (11dobrych footprintów), produkcyjne [{x,y}], source+EPS, parametry malformed/missing/checksum/source/duplicate, zachowane humanApproved. `grid-content-reference.test.mjs`: unavailable proof zachowuje canvas i aktywny zapis bez automatycznej mutacji. Eksportuje również rekord z unavailable crop proof. |
| P0-2 | Przywrócona oddzielna reguła `.gridContentLattice,.gridContentQuad` z fill:none i #51caff; bursztynowy crop jest osobną regułą. Wspólny blind default zachowany. | Test rzeczywistego CSS w jsdom sprawdza computed fill/stroke/dasharray siatki i cropu oraz ich różnicę; pełny test:geometry wykonany. |
| P1-1 | Testowany rzeczywisty `export()` i zapis plików, nie tylko czysta strona. GET-only, A/B/REG odrzucone przed odczytem assetu, protected TRAIN przed JPEG; bad SHA nie zapisuje obrazu; byte-limit i deadline przed/po odczycie. | `test_grid_content_preview_export.py`: fake urlopen rejestruje żądania, kontrola braku JPEG/rekordu/requestassetu chronionych źródeł, checksum/size/time. |
| P2-1 | Pure fixture używa kontraktu SourceQuad.to_dict() → [{x,y}]. PostgreSQL czyta prawdziwy wiersz board_render_manifests wygenerowany przez _save_source i VirtualCellRenderer. | PG1PASS/30,43s:15footprintów, dokładne24nodes, cell6 zgodna z rzeczywistym paddedSourceQuad; receipt actualProductionManifestFootprints=15, coldRead/readOnlyPreview/protectedAliasOtherSlot=true, cleanup0/0. |
| P2-2 | Asercja całych argumentów ordinary controller, włącznie z czwartą parą cohortId/manifestSha256. | Istniejący test ordinary B/REG po rozszerzeniu; pełny geometry suite obejmuje tę asercję. |
| P2-3 | Wyłączenie Obrysy grafik ukrywa także uchwyty edycji quadu. Domyślnie warstwa pozostaje włączona, więc blind workflow zachowuje narzędzia. | Test toggles: quadcount0 i handlecount0 po wyłączeniu, cells/nodes bez zmiany. |
| P2-4 | Jawna akceptacja istniejącego ryzyka zakresu D594, bez rozszerzania polityki. Źródło dotąd nieobjęte zapisaną sesją może zostać obejrzane, a później wybrane do pomiaru; ochrona roli dotyczy przekazanej kohorty. | Zapis Accepted residual risk w Outcome i granicach verification; nie deklarujemy globalnej nieekspozycji ani niezależności takiego przyszłego pomiaru. |
| P2-5 | Wspólny ContentReferenceBase oddziela historyczne pola; read response dodaje ordinaryPreview, write response dziedziczy bazę bez tego pola. Backend/OpenAPI/SDK zachowują jeden kontrakt. | Test JSON schema write response nie zawiera ordinaryPreview; OpenAPI/SDK zregenerowane i drift check PASS, request4PASS i standardowy Admin typecheck PASS. |
| P2-6 | Wykonano dokładne npm run test:geometry --workspace @game-predictor/admin. Pełnego suite nie opisujemy jako zielonego. Build jawnie pozostaje bramką T4 według zaakceptowanego planu i potwierdzenia root. |438testów:428PASS/10FAIL; ograniczony baseline main24PASS/te same10FAIL supergames. Pierwsza próba miała przejściowy picker i błąd kolejności własnego fixture; końcowy picker PASS. Logi i ograniczenia w verification. |

Końcowe kontrole:52pytest PASS, rzeczywisty PG PASS, zmieniony content UI PASS
w pełnym suite,4SDK request PASS, scoped Ruff/ESLint/mypy i standardowy Admin
typecheck PASS, OpenAPI/SDK drift PASS. Logi:
`artifacts/t1170-r1-{api-tests,pg,admin-geometry,baseline-unrelated,sdk-request,ruff,admin-eslint,mypy,admin-typecheck,contract}.log`.
Root odświeża mapę/docs-check i wykonuje focused R2 po freeze.

Powody niedostępności mają w zwykłym UI i HTML krótkie polskie objaśnienia
(brak manifestu, niespójne dane, częściowy wycinek poza zdjęciem, ochrona).
Surowe kody pozostają w JSON i zwijanych szczegółach. Końcowa kontrola tej
czytelności:1UI PASS +6HTML/export pytest PASS, logi
`artifacts/t1170-r1-readable-ui.log` i `artifacts/t1170-r1-readable-html.log`.

Bez uruchamiania usług, inferencji, treningu, operatorowej bazy, zmian
adnotacji/modelu/marginesu, root helpers, merge ani push.

Root po freeze: regeneracja mapy, `docs:check` i `code-map:check` PASS;
logi `artifacts/t1170-r1-{code-map,docs-check,code-map-check}.log`.
