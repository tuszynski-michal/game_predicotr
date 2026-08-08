---
title: TASK-0178 image selection v10 accuracy-first selection
status: in_progress
release: "0.4"
last_updated: 2026-08-08
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
- [ ] TASK-0194: powtórzyć profil 200 zdjęć przed odbiorem 5000/32 000.

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
