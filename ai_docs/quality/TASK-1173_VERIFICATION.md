# TASK-1173 — weryfikacja HTML i odbioru

2026-11-09. Worktree: `D:/game_predicotr/worktrees/grid-symbol-crop-preview`.
Wykonawca: gpt-6.1-sol/high. Root prowadzi mapy/docs/audyt i zamknięcie.

## Implementacja

Istniejący `scripts/render_grid_correction_comparison.py` ma jawny tryb
`--crop-report`; legacy `--directory` zachowuje swój renderer. Osobny adapter
i template odczytują sealed `production-crop-comparison-v1`/capture bez SQL ani
inferencji. Strona pokazuje oryginał, dokładne 24 punkty, approved content albo
jego brak, actual wejścia NN i 15 par rastrów 8%/0% dla geometrii ludzkiej/modelu.
To diagnoza marginesów, nie nowy model ani zmiana produkcyjnego ustawienia.

TRAIN **i** visualExportAllowed=true są wymagane przed każdym pikselem/public
JSON. Wewnętrzne A/B/REG oraz protected TRAIN nie trafiają do galerii. Indeks
original-found wejść NN pozostaje odrębny od usable predictionIndex rastrów.
Unknown GT może nie mieć base/candidate assessment. Missing/ambiguous nie usuwa
pozostałych pól, a brak nodes modelu ma jawny komunikat. Błędna postać punktów
nie wchodzi do SVG. Output jest immutable i konflikt przerywa publikację.

T1 residual P2-7: ukryte obrysy nie mogą niewidocznie edytować quadu; P2-8:
ordinary niechronione TRAIN bez nodes zachowuje obraz/adnotację i informację
o braku geometrii. Instrukcja ordinary/HTML obejmuje pełną grafikę razem z
ozdobnym obramowaniem, bez tła i sąsiada; wspólne pola nie narzucają rozmiaru
obrysów J/10. Blind zachowuje dawną instrukcję i nie otrzymuje hintów/requestów.
Nie ma zmiany API/OpenAPI/SDK/schematu.

## Odtworzenie raportu

```powershell
.venv/Scripts/python.exe scripts/render_grid_correction_comparison.py `
  --crop-report D:/game_predicotr/artifacts/t1171-r1-final/report.json `
  --artifact-root D:/game_predicotr/artifacts `
  --output-directory D:/game_predicotr/artifacts/grid-symbol-crop-preview-20261109-t4-v4
```

Strona: `D:/game_predicotr/artifacts/grid-symbol-crop-preview-20261109-t4-v4/index.html`.
V2/V3 i starsze galerie zachowane. Cold CLI usuwa PYTHONPATH; skrypt sam przypina
własny checkout. Receipt `artifacts/TASK-1173-html-receipt.json` zawiera SHA,
returncode, kontrolę PNG i identyczności SHA/mtime wejść oraz wyjść po replay.
Końcowy dowód R1/v4: `artifacts/TASK-1173-html-v4-receipt.json`; wcześniejszy
receipt pozostaje dowodem v3, nie został nadpisany.
Pilot: 1 TRAIN, 9 plansz, 270 par, 540 cropów, 10 wejść NN, łącznie551 PNG z
oryginałem. Approved content/class GT brak; większy kadr nie dowodzi jakości.

## Kontrole

Każdy proces miał timeout110s i do8s sprzątnięcia własnego procesu. `.venv`
jest junctionem; PYTHONPATH wskazuje własne services/api/src i worker/src.
Testy mają nowy krótki TEMP/TMP/basetemp. PostgreSQL: tylko własna baza
jednorazowa, nie operator. Kolekcja Worker i cold CLI bez PYTHONPATH.

| Kontrola | Wynik i log w artifacts/ |
|---|---|
| Początkowy nowy pion Worker/export/LF | 21 PASS/46,37s, `t1173-unit.log` |
| Końcowy Worker HTML | 13 PASS/28,87s, `t1173-worker-final.log`: real JPEG/canonical SHA, approved J/class, missing/ambiguous, index spaces, escape, konflikty, malformed footprint |
| Ordinary export po końcowej kopii | 8 PASS/4,98s, `t1173-preview-export-final.log` |
| LF fresh checkout | 1 PASS w zestawie21; actual checkout-index autocrlf=true/eol=crlf, raw SHA zgodny z immutable receipt |
| Legacy Worker | 39 PASS, `t1173-legacy.log` |
| Legacy HTML CLI | 3 PASS/1,77s z dedykowanym TMP, `t1173-legacy-cli.log` |
| Admin content interactions | 28 PASS/3,79s, `t1173-admin-content.log`; także zawarte w pełnym geometry po końcowej kopii |
| Cały Admin geometry | 427 PASS/11 FAIL/24,07s, `t1173-admin-geometry.log`: 10 znanych supergames baseline oraz przejściowy picker |
| Wąski rerun pickera | 2 PASS/2,69s, `t1173-picker-rerun.log`; nie przepisuje wyniku całej próby |
| Disposable PostgreSQL reader | 1 PASS/43,18s, `t1173-pg-reader.log`: coldRead, 15 manifest footprints, alias/other slot protected, legacy read, readOnly i cleanup0 |
| Samodzielna kolekcja Worker | Końcowe 3636 testów/23,18s, `t1173-worker-collection-final.log` (wcześniej3635/23,44s); kolekcja, nie wykonanie suity |
| Real HTML JS / v3 | CROP_HTML_DOM_PASS, `t1173-final-html-js.log`: 15 pól, selector/warstwy/geometrie, brak pustych img, wykonany template |
| Cold CLI/551 PNG | `t1173-final-html-assets.log`, receipt z kontrolą SHA pliku/pikseli/wymiarów i niezmienności wejść/wyjść |
| Ruff/format 6 Pythonów | PASS, `t1173-ruff.log`, `t1173-pyformat.log` |
| Mypy adapter/oba CLI | 3 source files PASS, `t1173-mypy.log` |
| Scoped ESLint Canvas/test | PASS, `t1173-eslint.log`, cwd apps/admin |
| Standard Admin typecheck | PASS, `t1173-typecheck.log`, bez alias configu |
| Prettier TSX/MJS/HTML | `t1173-format.log` |

Pierwszy build: `artifacts/t1173_run_check.py --log artifacts/t1173-admin-build.log
-- cmd.exe /c npm run build --workspace @game-predictor/admin`. Pełny log zawiera
compile6,0s, TypeScript18,9s, static pages3/3 i końcową tabelę routów. BUILD_ID
`KhIm5nsbLefQOL-q7w2w8`. Helper nie utrwalił child returncode: końcowy print
gotowego logu dostał UnicodeEncodeError cp1250, więc wrapper exit1 nie dowodzi
błędu buildu ani child exit0. Root wykonał jedną uzasadnioną ponowną próbę
z zapisaniem returncode przed drukowaniem; końcowy wynik poniżej. Warning
Next dotyczy kilku lockfile/inferred root. Workspace SDK rozwiązuje własny
worktree; biblioteki Next/React pochodzą z istniejącej instalacji. Junctiony
trzeba później odpinać bez following target (`worktree-dependency-layout.json`).

Końcowy wymagany build gate root: **PASS**, child exitCode0, timedOutfalse,
29,38s. Receipt `artifacts/t1173-root-admin-build.json` zapisano przed drukowaniem;
pełny log `artifacts/t1173-root-admin-build.log`, BUILD_ID `S-beaSLp3C3uEHrZuxbxF`.
Polecenie to samo standardowe npm build; bez usług i mutacji operatora.

## Nieudane próby i granice

- Pierwsza fixture była PNG, którego canonical loader nie wspiera; poprawiono
  ją na rzeczywisty JPEG i canonical SHA, bez osłabienia kontraktu.
- Legacy CLI początkowo3FAIL/3ERROR przez Windows TMP; dedykowane testowe
  TEMP/TMP dało3PASS. Pierwszy ESLint z root nie znalazł configu; właściwe cwd PASS.
- Znane10supergames odtworzono na main w T1. Picker osobno PASS; pełna suita
  nie ma zielonego wyniku. Nie naprawiano niezwiązanych modułów.
- Próba cold replay po kanonizacji reprezentacji poprawnych quadów wykryła
  immutable output conflict; zachowano oryginalną postać quadu po jego walidacji.
  Nie nadpisano v3 ani źródeł. Końcowy replay potwierdza identyczne pliki.
- CUA blokuje file://; brak ręcznego screenshot/browser PASS strony. Root
  obejrzał kilka zweryfikowanych PNG (parę cropów i input3rzędów), nie cały HTML
  ani metryki. Użytkownik ma otwartą wersję raportu do odbioru wizualnego.
- Nie powtarzano długiego treningowego workflow T3 bez PASS; odmienne objawy
  T3/main i nieustalona przyczyna pozostają w raporcie odbioru.

Celowana `.gitattributes` LF obejmuje checksum-bound `TASK-*_AUDIT_*.md`.
Nie zmieniono treści/hashów raportów audytora. Test fresh checkout nie stage'uje.
Punktowy DoD i ograniczenia T1–T3: `GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md`.
Mapy/docs/audyt/close pozostają krokami root przed commitem.

Root po freeze:16 wykonawczych SHA i SHA strony/receipt sprawdzone przed
edycją metadanych. Mapa zregenerowana; docs:check i code-map:check PASS
(startup43612B). Oczekuje niezależnego audytu, bez deklaracji PASS.

## Jedna runda poprawek R1

Opus R1 REVISE0P0/2P1; exact report/receipt zachowane. Mapa wszystkich uwag:
`TASK-1173_FIXES_R1.md`. GeometryMetrics.matches daje zgodność względem zapisanych
punktów, nie content-dependent usable ani niezależną jakość. Label jest ordinalem
pierwotnych targets; partial position7/label0 ma actual evaluator i DOM test.
Matched-but-incorrect, false detection i partial None są jawnym tekstem.
Approved DOM wykonuje preserved/clipped oraz wrongCell/tie/foreignFullSymbol,
fragmenty z przerywanym stylem i znaną klasę człowieka bez klasyfikatora.
Stałe marginesy są sprawdzane; pominięte TRAIN mają tylko agregat bez IDs.

Końcowy Worker HTML: **16 PASS/35,92s** (`t1173-r1-worker-final.log`). Canvas/blind
**28 PASS/4,01s** (`t1173-r1-admin-content.log`), także hidden delete/numeric disabled.
Ruff/format2, mypy adapter1, scoped ESLint i standard Admin typecheck PASS.
Samodzielna kolekcja Worker bez PYTHONPATH:3639testów/19,20s,
`t1173-r1-collection.log` (kolekcja, nie wykonanie całej suity).
Pełnej geometrii z10baseline, PG i niezmienionego długiego workflow nie powtarzano.
Pierwsze błędy nowych fixture: brak expected source SHA, następnie niedopasowany
sequence range dla physical pos7. Naprawiono fixture na sequence8/range1..9;
kontrakt canonical decode/slot pozostał bez zmian. Wąskie i końcowe testy PASS.

Końcowy build po zmianie Canvas: **PASS exitCode0**, timedOutfalse,28,64s,
BUILD_ID `HL5cDtyH9xkxRaRsCc0zN`. Receipt zapisany przed print:
`artifacts/t1173-r1-root-admin-build.json`, pełny log obok. Poprzednie buildy
pozostają historią, bez ponawiania zielonej próby.

V4 DOM PASS (`t1173-r1-v4-dom.log`), cold CLI exit0,551 PNG file/pixel SHA/wymiary
PASS,552źródła/553wyjścia identyczne SHA/mtime (`t1173-r1-v4-assets.log`).
Page SHA `eaff2369972d84e000a93c522b9d118fb13cdf7527ab78f84f88b9f5ed4bf6f0`.
Brak nowych operatorowych etykiet/inferencji; brak manual browser PASS nadal jawny.

**Granica ochrony file-only:** TRAIN+visualExportAllowed odzwierciedla moment
capture. Renderer nie sprawdza sesji blind zapisanych później. Przed kolejną
galerią przygotuj świeży capture; sam cold replay nie poświadcza bieżącej
ochrony. Nie dodano SQL/API/inferencji do renderowania. Dotyczy to także
wcześniej wyeksportowanych plików, których nie wycofuje automatycznie nowa sesja.

Root po rundzie poprawek:17 frozen SHA i SHA v4/receipt sprawdzone;
mapa zregenerowana, docs:check i code-map:check PASS(startup43612B).
Focused R2 jest następny; bez deklaracji niezależnego PASS.

## Końcowy odbiór root — 2026-11-09

Focused R2 przez terminal: **PASS, 0 P0 / 0 P1**, rzeczywisty model główny
`claude-opus-5-5`, High żądane (bez niezależnego dowodu ustawienia effort).
Czas243,62s; receipt potwierdzony po rzeczywistym zakończeniu procesu.
Pakiet SHA `293ed2a525aa0176ef022b1890705afd7e4c352736518203abccb1c68b93f45a`;
raport SHA `de0b237218f0719c5c3e43cd76b2daabee88c7f6496b8479e87ad051dafa2186`.
Raport i receipt: `TASK-1173_AUDIT_claude-opus-5-5.md` i plik `.receipt.json`;
oryginalna runda1 zachowana w plikach `_R1`. Audyt był statyczny, nie zastępuje
wykonanych testów ani operatorowego pomiaru jakości modelu.

Przyjęte resztkowe P2 rundy2: P2-8 — niedostępny wycinek może zgubić opis
istniejącej oceny `missing` i wyświetlić zbyt ogólny brak odniesienia; porażka
pozostaje widoczna jako niedostępność, bez pozytywnej oceny. P2-9 — stan
`borderline` ma surową angielską etykietę zamiast polskiego opisu. Obie uwagi
dotyczą opisów zatwierdzonego content GT, którego pilot nie ma. Nie wykonano
kolejnej rundy zmian po zaakceptowanym focused review; nie osłabiono kontroli.

T1–T4 mają osobne Opus PASS. Wszystkie powyższe ograniczenia testów, danych,
ochrony capture i ręcznego odbioru pozostają aktualne. Gotowość narzędzia nie
jest rekomendacją zmiany marginesu ani dowodem poprawy modelu. Bez operatorowych
mutacji, treningu, wdrożenia i merge/push. Końcowe docs/map i task-close są
kontrolą metadanych po audycie, bez zmiany audytowanego kodu.
