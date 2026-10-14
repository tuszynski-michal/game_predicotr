---
title: Odpowiedź na audyt planu doszkalania siatek V3
status: active
last_updated: 2026-10-14
---

# Odpowiedź na audyt planu doszkalania siatek V3

Zakres: rewizja 2 `ai_docs/delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`,
indeks i stan projektu, rejestr potrzeb V3 oraz warunek bezpieczeństwa
TASK-0957. Raport Claude pierwszej wersji pozostaje **REVISE**, bez zmian.
Ten dokument opisuje korektę planu przez jego autora; nie jest niezależnym
reaudytem ani podstawą do ogłoszenia PASS implementacji.

## Odpowiedź na uwagi P1

| Uwaga | Zmiana planu | Warunek wykonania |
| --- | --- | --- |
|P1-1: brak nowych gier|TASK-1004 jest pełnym pionem katalog → GameCreate → assignment/join/fork → formularz i test HTTP. TASK-0994 backfilluje istniejące dwa profile, zachowując archiwalną777.|Nowa gra może wybrać zgodną opublikowaną wersję bez własnych etykiet. Brak korekt blokuje doszkalanie, nie import z bazą. Kandydat wspólnej rodziny geometrii jest osobnym TASK-1006.|
|P1-2: brak stanu danych i minimum|Dodano datowane liczby audytora: 777a2 — 341564 plansze, 0 human approvals, 0 complete zdjęć; Mumie — 492215/44/4. TASK-0995 preview zwraca required/eligible/missing. FazaO obejmuje zbieranie korekt i czas operatora.|Proponowane minimum: TRAIN 30/10 zdjęć, VALIDATION 15/5 pełnych zdjęć, REGRESSION 15/5 pełnych zdjęć; co najmniej trzy niezależne nagrania. Dla 9 plansz/zdjęcie kontrolne minima dają 45+45 plansz, zTRAIN 30 łącznie 120. Progi są propozycją pilota do akceptacji, nie gwarancją jakości.|
|P1-3: nieokreślony szeroki zakres|TASK-0999 liczy stany pozycji istniejącą funkcją classify_position; TASK-1003 pokazuje rozkład, wybrane sloty, zdjęcia i potencjalne zmiany approvals. Default uncertain/deferred i pierwsza próba 100; szeroki zakres/all-automatic są opt-in.|uncertain może obejmować niemal całą 777a2. Nie obiecujemy małego zakresu z samego filtra. Nie wybieramy wszystkich sąsiadów na podstawie geometry_incomplete. TASK-0991 lub inny kolidujący runner blokuje start; admission guard obejmuje zarejestrowane operacje aplikacji, CAS chroni także przed zewnętrzną zmianą.|
|P1-4: bazowy checkpoint tylko na C|TASK-0994 obejmuje staging/kopię do zarządzanego root na D, manifest, SHA i receipt oraz rejestrację ścieżki. TASK-0957 ma warunek ochrony katalogu źródłowego do weryfikacji nowego procesu D-only.|Zweryfikowany checkpoint 777 v2 ma 106 729 511 B i SHA 2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8. Nie kopiowano go w trakcie planowania. Produkcyjny trener nie używa VISION_LAB_DATA_ROOT.|
|P1-5: niewłaściwa bramka audytu|Operator odpowiedział: Codex wykonuje, Claude Code audytuje. Każdy task i tabela wskazują gpt-6.1-sol medium/high oraz claude-fable-5-1 medium/high w sesji Claude Code.|Nie wymagamy instalacji Claude CLI w środowisku Codex. Audyt pozostaje read-only, z briefem/diffem i raportem repo. Wybór pary nie jest zgodą na implementację lub koszt.|

## Odpowiedź na uwagi P2

- **Granulacja:** zachowano numery istniejących tasków, dodano 1002 (nagrania
  i role), 1003 (preview/raport UI), 1004 (nowa gra), 1005 (preset/admission)
  i 1006 (wspólna geometria). Kohorta/snapshot 0995 i backend operacji 0999
  są oddzielone od swoich dodatkowych pionów. Łącznie14 tasków.
- **GPU:** bieżący trener symboli jest CPU. Ograniczamy dzierżawę do app
  grid runs i wymagamy wyłącznego okna operatora względem zewnętrznego CUDA.
  Nie obiecujemy nieistniejącej wspólnej blokady wszystkich trenerów.
- **Archiwalna 777:** nowa sekcja zachowuje wyłącznie odczyt aktywnego
  klasycznego profilu i historii, bez przycisków wycofanego workflow.
- **Preset:** usunięto arbitralne 20 epok/5000 kroków/30 min. TASK-1005
  korzysta z raportów finetune-D i aktualnej kohorty, następnie ograniczonego
  smoke za zgodą. Iteracja 03 ma 443/666/728 kroków, 1837 łącznie i 900,328s
  treningu; to dane historyczne, nie domyślny limit nowej funkcji.
- **GAME_SECTIONS:** potwierdzony moduł to
  `apps/admin/src/features/catalog/admin-navigation-state.ts`; komponent
  `catalog-workspace.tsx` renderuje etykiety/sekcje, nie definiuje tej stałej.
- **Koszt:** szacunek zastąpiono zgrubnym 9–21 dni roboczych z kontrolami
  i audytami. Etykietowanie oraz czas nagrań/GPU/odbioru są oddzielne;
  scenariusz 120 korekt to 2–6 h przy założeniu 1–3 min/plansza, do sprawdzenia
  pierwszą próbą 10 korekt. Nie podano zmyślonego procentu pakietu.

## Kierunek wskazany przez operatora po audycie

Operator zaproponował wspólny model geometrii Mumii i 777 ze względu na
podobieństwo plansz mimo różnych ramek. Plan nie odrzuca tego kierunku.
TASK-1006 tworzy jednego kandydata od sprawdzonego checkpointu, z mieszaną
kohortą i równymi wagami gier/nagrań. Wynik przechodzi bramkę osobno
w obu grach. Brak zaliczenia zachowuje dotychczasowe dwa modele; nie
uśredniamy ich wag i nie przełączamy przypisań automatycznie.

Wspólna rodzina dziedziczy role i wyłączenia obu bazowych linii. Niezależna
kontrola nie może pochodzić z filmu użytego w TRAIN jakiegokolwiek rodzica.
Nowa nazwa gry lub fork nie omija tej ochrony. Modele symboli/wypłat nie
są łączone. Nowy kierunek wymaga decyzji rozszerzającej D-527 przy akceptacji.

## Weryfikacja i ograniczenia

Odczytano kod tworzenia gry, enumy/schema/formularz, classify_position,
renderer/szkice, bazowe artefakty i raport iteracji. Odczyt artefaktów
obejmował konkretne pliki/hash, nie szeroki przebieg korpusu. Liczby bazy
przyjęto z audytu Claude; nie powtarzano kosztownego odczytu całych gier.
Kontrole wykonane przed oddaniem rewizji: `npm run docs:check` PASS
(42 aktywne taski, 10 sekcji done, 91 103 B stanu), `git diff --check` PASS
oraz kontrola struktury planu PASS (14 tasków, zgodne modele/reasoning
w rekomendacjach i tabeli, tabela modeli w ostatniej sekcji).
Są to kontrole dokumentacji, nie audyt niezależny lub test aplikacji.
Nie zmieniono kodu aplikacji, danych, usług,
modeli ani plików źródłowych na C. Nie wykonywano migracji, treningu,
inferencji ani nowego audytu krzyżowego. Plan pozostaje `proposed`.
