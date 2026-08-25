---
title: TASK-0178 image selection v10 accuracy-first selection
status: done
release: "0.4"
last_updated: 2026-08-21
---

# TASK-0178 — Image selection v10 accuracy-first selection

## Goal

Zastąpić szybką, lecz niedokładną politykę v9 selektorem, który przegląda całą
grupę, wybiera najlepszy obraz i zapisuje ukończone wyniki w trakcie runu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/delivery/VERSION_0_4_EXECUTION_PLAN.md`

## Vertical tasks

- [x] TASK-0178: porównać v7–v9 i wskazać regresję `first usable`, top-2 oraz
      usunięcie pełnej weryfikacji.
- [x] TASK-0179: ocenić każde zdjęcie lekko, utrzymać top-12 całej grupy i
      usunąć early exit.
- [x] TASK-0180: dodać pełną weryfikację shortlisty, większy margines etykiety
      wielocyfrowej i konsensus zakresu z wielu klatek.
- [x] TASK-0181: utrwalić kierunek rosnący/malejący i opcjonalny pierwszy numer
      w domenie, API, bazie oraz jobie.
- [x] TASK-0182: przywrócić `seq_<od>-<do>.jpg` i udostępnić ukończoną grupę
      przez bounded endpoint.
- [x] TASK-0183: wymagać wyboru katalogu zapisu przed wejściem i zapisywać
      ukończone grupy progresywnie bez nadpisywania kolizji.
- [x] TASK-0184: użyć hardlinku dla końcowego outputu na jednym woluminie oraz
      kopiowania jako bezpiecznego fallbacku.
- [x] TASK-0185: zakończyć regresje Python/TypeScript, migrację i krótki,
      poglądowy profil syntetyczny bez uruchamiania kosztownego runu 5000.
- [ ] TASK-0186: ręczny odbiór właściciela na około 5000, potem 32 000 zdjęć.
- [x] TASK-0187: usunąć ujawnioną przez run 32 079 pętlę utraty lease podczas
      długiego batcha i przywrócić rzeczywisty postęp przed wznowieniem odbioru.
- [x] TASK-0188: usunąć wymuszoną ciągłość zakresów i aktywować osobny,
      odtwarzalny manifest v10.1.
- [x] TASK-0189: rozdzielić ocenę reprezentanta od dowodu zakresu bez zmiany
      publicznego API i bazy.
- [x] TASK-0190: dopuścić pełną geometrię 1–9 jako lokalny `board_count` i
      uruchamiać jeden batch OCR kotwic przed fallbackiem.
- [x] TASK-0191: dodać adaptacyjny konsensus zakresu `2 -> 4 -> 8 -> 12` bez
      zatrzymywania oceny reprezentantów całej shortlisty.
- [x] TASK-0192: dodać progresywny fallback cropów `18 -> 36 -> 72` z pełnym
      poziomem 72 zachowanym dla trudnych przypadków.
- [x] TASK-0193: dodać bezpieczną, deterministyczną równoległość dwóch
      izolowanych verifierów przy zachowaniu budżetu lane.
- [x] TASK-0194: powtórzyć profil 200 zdjęć przed odbiorem 5000/32 000;
      właściciel wybrał `optimize`, więc duży odbiór pozostaje wstrzymany.
- [x] TASK-0195: poprawić niezależny dowód OCR trudnej grupy 55–63 bez
      przywracania zgadywanej ciągłości zakresów.
- [x] TASK-0196: ograniczyć koszt pełnej geometrii z zachowaniem kanonicznie
      identycznego wyniku i zaliczyć ponowny profil pierwszych 200 zdjęć.
- [ ] TASK-0197: wykonać kontrolowany profil pierwszych 5000 zdjęć i przekazać
      reprezentanty do ręcznej decyzji właściciela.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_fast_image_selector.py services/worker/tests/test_image_selection_adapters.py services/worker/tests/test_image_selection_job.py
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_selections.py services/api/tests/test_image_imports_api.py
npm.cmd run typecheck --workspace @game-predictor/admin
npm.cmd run test --workspace @game-predictor/admin
```

Benchmark jest poglądowy. Właściciel podejmuje decyzję po realnych runach; nie
ma automatycznej bramki czasu.

## Outcome

Implementacja v10 jest kompletna i oczekuje na TASK-0186, czyli ręczny odbiór
właściciela. Selektor skanuje całą grupę, utrzymuje top-12 i wykonuje dokładną
weryfikację całej shortlisty bez early exit. Panel wymaga katalogu wejściowego i
wyjściowego, zapisuje każdą ukończoną grupę podczas runu oraz używa historycznej
nazwy `seq_<od>-<do>.jpg`. Kierunek i opcjonalna kotwica pierwszego numeru są
utrwalone przez migrację `0033_image_selection_sequence_order`.

Weryfikacja 2026-08-08:

- 105 testów workera: passed,
- 28 testów API: passed,
- 168 testów Admina: passed,
- 32 testy klienta Admin API: passed,
- typecheck Admina i kontrola aktualności OpenAPI: passed,
- migracja lokalnego PostgreSQL do `0033`: passed,
- syntetyczny smoke v10: 240 zdjęć, 12 grup, precision/recall 1.0, brak
  false merge/split oraz 30,252698 s. Wynik znajduje się w
  `ai_docs/quality/image-selection-v10-smoke-report.json`.

Smoke jest tylko kontrolą techniczną. Zmierzone 30,25 s wobec 6,11 s
historycznego smoke daje około 4,95 raza dłuższy przebieg, ale nie zastępuje
oceny jakości na realnych zdjęciach. Nie uruchamiano automatycznego benchmarku
5000/40 000; odbiór 5000 i około 32 000 wykona właściciel.

Wstępny profil rzeczywistego stagingu 2026-08-08 objął wyłącznie pierwsze 200
z 32 079 zdjęć i nie wykonywał publikacji plików ani zapisu domenowego. Zimny
run v10 bez produkcyjnego cache trwał 377,530649 s, rozpoznał automatycznie 9
grup `1–9` do `73–81`, nie miał błędów skanu i wykonał 99 pełnych weryfikacji.
Mediana czasu domknięcia grupy wyniosła 45,519357 s; ostatnia grupa miała tylko
3 zdjęcia, dlatego dla ośmiu pełniejszych grup miarodajny czas wynosi około
44,1–47,7 s na grupę. Największym kosztem był OCR: 291,673863 s czasu
etapowego. Raport operatorski znajduje się w
`artifacts/image-selection-v10-first-200-timing.json`, a powtarzalny profil w
`scripts/profile_image_selection_slice.py`. Wynik jest materiałem do decyzji
właściciela i nie zamyka TASK-0186.

Właściciel 2026-08-11 jawnie polecił rozpocząć pełny przebieg 42 403 zdjęć na
domyślnym v10.7 i dopuścił jego przerwanie po obserwacji wczesnych wyników.
Run `45c80055-5beb-43bc-bc35-8c84b3e2b19c` używa istniejącego kompletnego
stagingu v10.5, dodatniej kotwicy `19810` oraz osobnego pustego katalogu
wynikowego. Start potwierdził właściwy fingerprint v10.7, etap skanowania,
świeży lease i brak błędów. Nie oznacza to jeszcze zaliczenia jakości ani
ukończenia TASK-0186/TASK-0197.

Run v10.7 został następnie kontrolowanie anulowany na checkpointcie
10 176 / 42 403 po wyniku 34 automatyczne, 603 `range_required` i 11 duplikatów.
TASK-0238 wprowadził v10.8 z pozycyjną kotwicą layoutów, poprawnym czterocyfrowym
oknem mimo błędów poza nim, bounded `9/18` OCR i scalaniem fragmentów przejścia.
Profil 400 zakończył się zerem elementów review, ale TASK-0197 pozostaje otwarty:
nie wykonano jeszcze ręcznego odbioru około 5000 ani nowego pełnego runu.

Po restarcie komputera właściciel 2026-08-11 jawnie zastąpił profil 5000 pełnym
runem v10.8 na 42 403 JPEG-ach. Run `d43aa481-7efe-467b-8dbc-998b609d4ae8`, job
`861a42d0-e3e0-4425-b9ba-f45665bb33b2` i monitor PID `2608` używają istniejącego
stagingu v10.5 bez ponownego uploadu. API działa na porcie 8003 jako PID `11492`,
a jedyny worker selekcji jako PID `12068` (launcher `13608`). Wynik jest
progresywnie zapisywany do `C:\Users\user\Documents\19810 - 45152`; raport i
stan PID to odpowiednio `artifacts/image-selection-v108-live-19810-45152.json`
oraz `.runtime/live-image-selection-v108-19810-45152.pid.json`. Snapshot
`160 / 42 403` miał 10 automatycznych grup, zero manualnych i zero błędów.

Run v10.8 został następnie anulowany na checkpointcie 1440 / 42 403: 50 grup
automatycznych, 39 `range_required` i 11 pominiętych. TASK-0239 wprowadził v10.9
z częściową kotwicą 3×3 i pozycyjnym dopasowaniem wariantów OCR. Finalna bramka
tych samych pierwszych 1440 źródeł trwała 110,883022 s i dała w pierwszych 100
domkniętych grupach dokładnie 60 automatycznych unikalnych zakresów oraz 40
duplikatów, bez review i nieznanego zakresu. Raport:
`artifacts/image-selection-v109-first-1440-gate-final.json`. Pełny run 42 403
jest odblokowany i ma użyć nowego pustego katalogu outputu.

## Closure

Zamknięto jako zastąpione 2026-08-21. Plan v10 accuracy-first został rozwinięty
w późniejszych wersjach selektora, a właściciel przyjął ręczną selekcję jako
niezależny workflow. Historyczne wyniki zachowano wyłącznie do audytu.
