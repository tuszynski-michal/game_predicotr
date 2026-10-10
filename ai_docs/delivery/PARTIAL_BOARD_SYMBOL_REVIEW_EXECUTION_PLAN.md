---
title: Complete partial-board symbol review
status: accepted
last_updated: 2026-09-27
---

# Kompletna obsługa niepełnych plansz w Weryfikacji Symboli

## Zlecenie i reguły

Użytkownik zatwierdził cały plan T1–T4 2026-09-27. Wykonujemy kolejno,
z niezależnym audytem i osobnym commitem każdego zadania. Kod, testy i
podgląd naprawy są zlecone; wykonanie uzupełnienia produkcyjnych danych
pozostaje osobno zleconym krokiem zgodnie z T4. Bez push/merge/treningu.

Każda plansza 3 × 5 ma 15 logicznych pozycji do ręcznej weryfikacji.
Dostępność obrazu i przypisanie symbolu są niezależne.

| Dostępność | Początkowa grupa | Po ręcznym przypisaniu |
|---|---|---|
| full | rozpoznany symbol albo Nierozpoznany (?) | przypisany symbol |
| partial | Nierozpoznany (?) | przypisany symbol; badge częściowej widoczności |
| outside | Poza zdjęciem | wyłącznie przypisany symbol; trwały badge Poza zdjęciem |

Wszystkie obejmuje każdą pozycję. Outside jest grupą/filtem, nie symbolem
katalogowym. Outside bez przypisania nie należy do unknown, także po
oznaczeniu Nieczytelny. Operator może przypisać rzeczywisty symbol albo
oznaczyć Nieczytelny. Brak pikseli nie znika po decyzji i wyklucza uczenie
symboli. Nie tworzymy fikcyjnych cropów ani checksum. Widoczność wynika
z przecięcia wieloboku z obrazem, nie z samej obecności narożników.

## T1 / TASK-0708 — dostępność i komplet pozycji

Ujednolicić plikowy i wirtualny zapis pól dla importu, ręcznej korekty
i reprocessingu. Trwałe full/partial/outside z aktualnej geometrii i źródła.
Logiczna tożsamość gra/sequence_number/cell_index; geometria wersjonowana.
Partial bez początkowego przypisania; outside bez zasobu i predykcji.
Plansza, kolejka i liczniki atomowe; błąd projekcji nie może udawać sukcesu.
Migracja rozszerzająca Alembic, historyczne braki wymagają oceny geometrii.
Chronić decyzje ręczne i unieważniać zatwierdzenie obrazu po zmianie geometrii.
Odbiór: 62287, 62404, 62440 po 15 pozycji; retry bez duplikatów.

## T2 / TASK-0709 — grupy, API i decyzje

Po T1. Rozszerzyć symbolId o outside; sourceVisibility i jawny wariant bez
zasobu w odpowiedzi (nullable tożsamość cropa). Backend/OpenAPI/generated
client/wrapper/test żądania jako całość. Identyczne zakresy list, liczników,
paginacji, kursorów i bulk operacji. Partial po przypisaniu widoczny pod
symbolem. Outside: reassign i unreadable z CAS pola/geometrii bez zatwierdzania
nieistniejącego cropa. Brak predykcji nie oznacza confidence zero; confidence
nieaktywny dla outside. Zachować statusy blurry/unreadable/grid_issue.
Odbiór: dokładnie jedna grupa szczegółowa plus all; sumy zgodne.

## T3 / TASK-0710 — UI i statusy importu

Po T2. Poza zdjęciem w wyborze grup; istniejący badge pozostaje po przypisaniu.
Kafelek Brak obrazu pola, sequence i pozycja, podgląd źródła z siatką.
Zaznaczanie, klawiatura, zmiana symbolu i Nieczytelny; brak ustawienia grafiki
z outside. Nie żądać renderów outside także w batch preview.
Brakujące plansze rozdzielają niepełność źródła od dostępności weryfikacji.
Staging osobno pokazuje korektę geometrii, błędy przetwarzania i symbol review.
Odbiór: przypisanie przenosi outside do grupy symbolu z trwałym badge.

## T4 / TASK-0711 — uzupełnienie i odbiór

Po testach T1–T3. Read-only preview dokładnej listy 70 numerów:
aktualny owner, źródło, geometria, istniejące/brakujące pozycje i klasyfikacja.
Wspólny mechanizm T1, małe partie, trwały checkpoint, brak resetu decyzji.
Retry/restart/utrata odpowiedzi idempotentne. Konflikt rewizji zatrzymuje
daną planszę i trafia do raportu. Nie nadpisywać manifestów i nie uruchamiać
masowego rozpoznawania. Kolejność operacyjna: koniec aktywnych zapisów,
backup, migracja rozszerzająca, zgodne usługi/UI, kontrola, preview i
osobno zlecone apply. Po pilocie read-only audyt innych gier.
Wdrożenie/produkcja nie może wyprzedzić bramki testów i decyzji danych.

Lista pilota:
60856,61018,61027,61036,61852,61855,61864,61873,61879,61882,
61888,61891,61897,61900,61906,61909,61918,61927,62053,62062,
62071,62287,62296,62404,62440,62575,62977,62980,62986,62989,
62995,62998,63004,63007,63013,63016,63022,63025,63031,63034,
63040,63043,63049,63052,63058,63061,63067,63070,63076,63079,
63085,63088,63094,63097,63103,63106,63112,63115,63121,63124,
63133,63160,109591,109600,109627,109636,109645,114625,114628,114631.

Audyt wejściowy: 1050 pozycji, 985 rekordów, 20 pominiętych outside, 45
brakujących z trzech legacy plansz. To historyczny punkt odniesienia;
przed apply sprawdzić na nowo. Outside nie wymuszać na liczbie 20.
Odbiór produkcyjny: 1050 dostępnych pozycji, restart i zachowane decyzje.
Jeżeli brak zlecenia apply, narzędzia można odebrać, lecz wynik danych
pozostaje jawnie niewykonany.

## Testy i dokumentacja

Geometria full/partial/outside i wszystkie rogi poza obrazem przy dodatnim
przecięciu. Obie ścieżki zapisu, 15 pozycji, rollback błędu. Osiem symboli,
unknown/outside/all i wszystkie quality/review states. Nullable assets,
brak render request, ręczne decyzje. Retry/restart/CAS/human protection.
Zachować stronicowanie, ograniczyć pamięć/partie; bez benchmarków.
Focused domain/storage/API/UI tests, generated check, lint/typecheck/build,
browser i nowy proces usług w granicach zatwierdzonego wdrożenia.
Zmiany wymagań, architektury i decyzji dokumentować; osobny Outcome/commit.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / 0708 | gpt-6-sol | high | Geometria, migracja i atomowość | gpt-6-astra, medium |
| T2 / 0709 | gpt-6-sol | high | Kontrakt, filtry i decyzje | gpt-6-astra, medium |
| T3 / 0710 | gpt-6-sol | medium | UI i interakcje | gpt-6-astra, medium |
| T4 / 0711 | gpt-6-sol | high | Ochrona danych i wznowienia | gpt-6-astra, medium |
