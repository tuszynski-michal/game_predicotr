---
title: Cofanie korekt cięcia siatki, odrzucanie plansz i zdjęcie zastępcze — instrukcja operatora
status: active
last_updated: 2026-10-10
---

# Cofanie korekt cięcia siatki, odrzucanie plansz i zdjęcie zastępcze

Instrukcja wdrożenia i odbioru planu
[GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md](../delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md)
(decyzje D-542 i D-543, taski TASK-0966–TASK-0972). Wszystkie kroki wykonuje
operator ręcznie, w swoich terminalach. Agenci nie migrują bazy operatora, nie
uruchamiają ani nie zatrzymują usług i nie cofają korekt na danych operatora.

## 1. Przed wdrożeniem

- Kod gałęzi `feat/geometry-correction-revert` wymaga migracji
  `0154_geometry_correction_revert` (manifest v7). Jej rodzicem jest
  `0153_merge_compact_super_games`. Odczyt 2026-10-10: baza operatora jest na
  `0153_merge_compact_super_games`, więc wdrożenie wykonuje tylko `0154`.
- Sprawdź wersję bazy (odczyt, bez zmian):

  ```powershell
  docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT version_num FROM public.alembic_version"
  ```

- Zalecana kopia zapasowa przed migracją (procedura jak w
  `ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md`). Downgrade `0154` odmawia,
  gdy istnieje jakakolwiek historia cofnięć lub odrzuceń.

## 2. Zatrzymanie usług

Zatrzymaj w swoich terminalach (Ctrl+C), w tej kolejności:

1. worker (`npm run worker:poll`, także `worker:image-selection:*`, jeśli działa);
2. API (`npm run api:dev`, port 8000);
3. Admin (`npm run admin:dev` lub `admin:start`, port 3000);
4. Reviewer (`npm run reviewer:dev` lub `reviewer:start`, port 3001).

API 8000 działa z `--reload` z głównego checkoutu: po scaleniu kodu bez
migracji przestałoby startować (strażnik `ALEMBIC_HEAD_MISMATCH`), dlatego
usługi zatrzymuje się przed scaleniem.

## 3. Scalenie i push (za zgodą operatora)

W głównym checkoucie (`C:\Users\tuszy\Documents\game_predicotr`, gałąź
`v1.1-vision-lab-hybrid-geometry`):

```powershell
git fetch origin
git status                     # zachowaj niezapisaną pracę (nie usuwaj jej)
git merge --ff-only feat/geometry-correction-revert
git push origin v1.1-vision-lab-hybrid-geometry
```

Jeżeli `--ff-only` odmawia (gałąź integracyjna przesunęła się), najpierw scal
gałąź integracyjną do `feat/geometry-correction-revert` i sprawdź numery
migracji, TASK, D- i `vX.Y.N`.

## 4. Zależności, migracja i build

W głównym checkoucie:

```powershell
npm install
npm run db:migrate             # 0153_merge_compact_super_games -> 0154_geometry_correction_revert
npm run reviewer:build
```

Po migracji sprawdź (odczyt):

```powershell
docker exec game-predictor-postgres-1 psql -U game_predictor -d game_predictor -c "SELECT version_num FROM public.alembic_version" -c "SELECT DISTINCT manifest_version FROM public.game_storage_locations"
```

Oczekiwane: `0154_geometry_correction_revert` i `game-data-v2-manifest-v7`.

## 5. Start usług

Uruchom w swoich terminalach: `npm run api:dev`, `npm run admin:dev`,
`npm run reviewer:start` (albo `reviewer:dev`) i `npm run worker:poll`.
Sprawdź `http://127.0.0.1:8000/api/v1/health`.

## 6. Cofnięcie korekty w Reviewerze

1. Admin → „Otwórz lokalnie” (lokalny Reviewer w zakresie gry, D-541) →
   zakładka **„Do korekty”** (ekran „Korekta cięcia siatki”). Sesja Reviewera
   z wybranym importem pokazuje ten sam ekran dla jednego importu.
2. Pod kolejką jest sekcja **„Ostatnie korekty”**: godzina, sekwencja, pozycja,
   rodzaj (slot, plansza, odrzucenie) i autor. Lista dotyczy jednego importu:
   wybranego w sesji, a w zakresie gry — importu planszy widocznej na ekranie
   (po opróżnieniu kolejki zostaje ostatni import, więc ostatni zapis nadal
   można cofnąć). Po ponownym wczytaniu strony z pustą kolejką w zakresie gry
   lista się nie pokazuje (brak importu na ekranie); wtedy użyj sesji z
   wybranym importem.
3. Przy korekcie, którą wolno cofnąć, jest przycisk **„Cofnij”**; inaczej lista
   pokazuje powód blokady (np. „To nie jest ostatnia zmiana geometrii tej
   planszy…”, „Po tej korekcie poprawiono inny slot tego zdjęcia…”).
4. „Cofnij” otwiera podgląd skutków (liczba usuwanych komórek, czy usuwana jest
   plansza, liczba przepinanych sąsiadów, przywracane decyzje komórek,
   poprzednia rewizja źródła). **„Potwierdź cofnięcie”** wysyła jedno żądanie.
   Przy błędzie sieci modal zostaje otwarty z przyciskiem „Spróbuj ponownie”
   (to samo żądanie, bezpieczne do powtórzenia).
5. Po cofnięciu slotu odroczonego slot wraca do kolejki z propozycją z
   poprzedniej rewizji źródła; po cofnięciu korekty planszy plansza wraca do
   stanu sprzed korekty (komórki z problemem siatki wracają do kolejki).

### Slot 69004 (gra Mumie)

Plan powstał dla slotu `378a273f-…` (sekwencja 69004, pozycja 0, import
`092ff7a4-e652-4273-9c0a-a30e38ebd8cc`). **Stan bazy 2026-10-10:** ten slot i
jego korekta już nie istnieją. Zdjęcie `seq_69004-69012.jpg` usunięto
2026-10-09 w partii 1 wymiany 275 zdjęć Mumii
([manifest](../quality/MUMIE_SOURCE_REPLACEMENT_20261009.md)); sekwencje
69004–69012 wróciły 2026-10-10 08:49 UTC w nowym imporcie
`344ce332-acda-4ebe-bf80-fc116f8d7e17` jako 9 plansz `pending`. Import
`092ff7a4-…` nie ma już ani jednego zdarzenia `geometry_saved` ani slotu
odroczonego. Cofnięcia 69004 nie da się więc wykonać.

Odbiór cofnięcia wykonaj na nowej korekcie: popraw siatkę dowolnego slotu
odroczonego albo planszy w „Korekta cięcia siatki”, a następnie od razu ją
cofnij z „Ostatnie korekty” (przed weryfikacją symboli i przed poprawieniem
innego slotu tego zdjęcia). Zapisz identyfikator slotu/planszy, import i
godzinę i wykonaj zapytania z sekcji 9.

## 7. Odrzucenie przyciętej planszy

1. „Korekta cięcia siatki” (albo ekran operacyjny planszy) → **„Odrzuć
   planszę”**.
2. Wybierz powód: **„Plansza przycięta”**, „Rozmyta” albo „Inny” (wymaga
   opisu) → **„Potwierdź odrzucenie”**.
3. Slot odroczony znika z kolejki i nie jest cięty na symbole. Odrzucona
   plansza wypada z weryfikacji symboli, liczników i wyszukiwarki (jej komórki
   zostają w bazie jako historia).
4. Bramka kompletności się nie zmienia: całe zdjęcie czeka
   (`geometry_incomplete`), dopóki sekwencja nie dostanie planszy z innego
   zdjęcia albo nie ustawisz wyjątku.
5. Odrzucenie można cofnąć z „Ostatnie korekty”, dopóki zdjęcie zastępcze nie
   przejęło sekwencji. Kanonicznego właściciela sekwencji nie da się odrzucić
   (`BOARD_REJECT_CANONICAL`).

## 8. Zdjęcie zastępcze (zwykły import)

1. Przygotuj lepsze zdjęcie z nazwą `seq_<od>-<do>.jpg` obejmującą odrzucone
   sekwencje i zaimportuj je zwykłym importem w Adminie.
2. Nowa plansza przejmuje tylko sekwencje odrzucone albo bez właściciela.
   Żywej planszy `pending` innego zdjęcia nie zastępuje: nowa plansza dostaje
   wtedy `superseded` z alternatywą `superseded_existing_owner_kept` (licznik
   „Pominięte — sekwencja ma właściciela”). Kanoniczny właściciel zawsze
   wygrywa. Ponowne przetworzenie tego samego pliku (ta sama checksuma) działa
   jak dawniej.
3. W tej samej transakcji odrzucony slot starego zdjęcia przechodzi do
   `superseded`, a stare zdjęcie jest przeliczane; gdy jego pozostałe plansze są
   poprawne, zostaje dopuszczone i pocięte.
4. Raport importu w Adminie (sekcja kompletności geometrii wybranego importu)
   pokazuje „Zastąpione sekwencje” i „Pominięte — sekwencja ma właściciela” z
   numerami.

## 9. Zapytania odbioru (tylko odczyt)

Uruchamiaj w `psql` (zawsze `BEGIN READ ONLY … ROLLBACK`); podstaw
identyfikatory gry, importu, slotu i sekwencji. Gra Mumie:
`fea55cc1-ebf4-4cee-b3ab-a520017ed1be`.

```powershell
docker exec -it game-predictor-postgres-1 psql -U game_predictor -d game_predictor
```

```sql
BEGIN READ ONLY;
SET LOCAL game_predictor.game_id = 'fea55cc1-ebf4-4cee-b3ab-a520017ed1be';
SET LOCAL search_path = game_data_v2, public;

-- Ostatnie cofnięcia i odrzucenia (audyt).
SELECT id, kind, import_job_id, sequence_number, position_index,
       reverted_geometry_revision, restored_geometry_revision, actor, created_at
FROM image_geometry_correction_reverts
WHERE game_id = current_setting('game_predictor.game_id')::uuid
ORDER BY created_at DESC LIMIT 10;

-- Cofnięcie slotu (przypadek B): slot pending, brak planszy i pozycji.
SELECT id, status, recognized_board_id, review_item_id, resolved_geometry_revision
FROM image_board_geometry_pending
WHERE game_id = current_setting('game_predictor.game_id')::uuid
  AND id = '<slot-id>';
SELECT count(*) AS boards FROM recognized_boards
WHERE game_id = current_setting('game_predictor.game_id')::uuid AND id = '<slot-id>';

-- Rewizje źródła zdjęcia: cofnięta ma status reverted.
SELECT revision, status, engine_kind, created_by, created_at
FROM image_source_geometry_revisions
WHERE game_id = current_setting('game_predictor.game_id')::uuid
  AND source_image_id = '<source-image-id>'
ORDER BY revision;

-- Sąsiedzi wrócili na poprzednią rewizję źródła.
SELECT b.sequence_number, b.position_index, b.geometry_revision, s.revision AS source_revision
FROM recognized_boards b
JOIN image_source_geometry_revisions s ON s.game_id = b.game_id AND s.id = b.source_geometry_revision_id
WHERE b.game_id = current_setting('game_predictor.game_id')::uuid
  AND b.source_image_id = '<source-image-id>'
ORDER BY b.position_index;

-- Cofnięcie korekty planszy (przypadek A): zdarzenie geometry_reverted.
SELECT geometry_revision, action, previous_approved_geometry_revision,
       approved_geometry_revision, actor, created_at
FROM image_board_geometry_review_events
WHERE game_id = current_setting('game_predictor.game_id')::uuid
  AND recognized_board_id = '<board-id>'
ORDER BY created_at;

-- Odrzucenia slotów i ich los (rejected, rejection_reverted, superseded).
SELECT pending_geometry_id, rejection_revision, action, reason, successor_review_item_id,
       actor, created_at
FROM image_board_geometry_pending_events
WHERE game_id = current_setting('game_predictor.game_id')::uuid
ORDER BY created_at DESC LIMIT 20;

-- Zamiennik: właściciel sekwencji i stan bramki starego zdjęcia.
SELECT ri.sequence_number, ri.status, ri.import_job_id, b.source_image_id,
       si.geometry_completeness_status
FROM image_review_items ri
JOIN recognized_boards b ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id
JOIN source_images si ON si.game_id = b.game_id AND si.id = b.source_image_id
WHERE ri.game_id = current_setting('game_predictor.game_id')::uuid
  AND ri.sequence_number = <sekwencja>
ORDER BY ri.created_at;

-- Alternatywy sekwencji po imporcie zastępczym.
SELECT sequence_number, reason, created_at
FROM image_sequence_alternatives
WHERE game_id = current_setting('game_predictor.game_id')::uuid
  AND sequence_number = <sekwencja>;

ROLLBACK;
```

Wynik zapisz w `Outcome` TASK-0972 (`ai_docs/tasks/0972-geometry-correction-revert-acceptance.md`).

## 10. Sprzątanie

- Baza testowa `game_predictor_task0760_e7d125df587d_test` została po
  przebiegu audytora (DROP przekroczył czas). Usuń ją ręcznie, gdy żadna sesja
  testowa nie działa: `docker exec game-predictor-postgres-1 psql -U game_predictor -d postgres -c "DROP DATABASE game_predictor_task0760_e7d125df587d_test"`.
  Nigdy nie usuwaj bazy `game_predictor`.
