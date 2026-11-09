---
title: TASK-1174 — Weryfikacja kolejki geometrii
status: verified
last_updated: 2026-11-09
---

# TASK-1174 — Weryfikacja

Zakres: zapis i przejście w `reviewAll`, pomijanie materializowanej pozycji,
koniec zakresu, stare odpowiedzi, filtry oraz odczyt bez agregatów. Nie zmieniono
zatwierdzeń operatora ani działających usług.

## Wyniki

- API/domena: **24 PASS**, następnie API/domena/PG25 PASS (26.64s).
  Po audycie wzmocniony **PG2 PASS** (38.98s): min/max UUID zapewniają obie
  kolejności klucza materializowanej planszy, z asercjami import/source/position.
  Osobne bazy `*_test`, pełne migracje, rzeczywiste rozwiązanie deferred,
  materializacja projekcji i odczyt w nowej sesji.
- Reviewer: po poprawkach audytu **38 PASS** (34.67s), w tym save/ostatnia pozycja, deferred→review
  z innym UUID, drugi source z tym samym sequence, filtr zdjęcia, utrata
  odpowiedzi po zapisie i spóźniony sukces z poprzedniego importu. Ponadto
  przyjęcie/odrzucenie/odświeżenie propozycji po zapisie, świeża rewizja
  „Poprzedniej”, retry nieudanego odczytu następnej pozycji i wyjście z filtra
  bez wracania na początek. Ostatni retry zachowuje też skip materializacji.
- Klient API: **160 PASS**; request test sprawdza `counts=none` i kursor.
  Backend/OpenAPI/generowany enum/wrapper pozostają jednym kontraktem.
- Ruff format/check, scoped ESLint, mypy **4 moduły PASS**, Reviewer typecheck
  i produkcyjny build **PASS**. Po poprawkach audytu lint/typecheck/build ponownie PASS.
  Build ostrzega o dwóch lockfile w zagnieżdżonym worktree; exit0.
- `docs:check` i `code-map:check` **PASS**; startup43812B,11/11 budżetów.

Logi lokalne: `artifacts/t1174-{api-final,pg-materialized,navigation-final,
client-tests,mypy,reviewer-lint-final,reviewer-build-final,docs-final,map-final}.log`.
Końcowa delta audytu: `artifacts/t1174-r2-{pg,navigation-final,lint,types,build}.log`.
Generowany klient dodatkowo `check:generated` PASS.
To wyniki wykonawcy, audyt statyczny ich nie zastępuje.

## Ograniczony pomiar

Przed zmianą HTTP `view=all/limit1/counts=all`9.156s, `counts=correction`4.125s.
Nowy odczyt application/repository na tej samej bazie, bez agregatów,
początkowo5.657s, następnie2.397s. Rozdzielenie zapytań wskazało odczyt pending
1.872s. Po jawnym ograniczeniu złączeń do partycji gry całość1.236s,
4 zapytania,0 agregatów; ta sama pierwsza pozycja i obecny nextCursor.
Receipt: `artifacts/t1174-read-timing.json`; SQL bez wartości parametrów:
`artifacts/t1174-read-query-times.json`.

To pojedyncze ograniczone odczyty read-only, z wpływem cache/obciążenia.
Nie są benchmarkiem ani pomiarem całego ekranu. Ścieżka pomiaru używa właściciela
bazy, więc nie dowodzi identycznego czasu RLS/HTTP/przeglądarki. Nie uruchamiano
poprawionej usługi. Nie deklarujemy usunięcia wszystkich opóźnień źródła,
renderowania i zapisu na podstawie czasu samej listy.

## Trwałość i odbiór

Kod działa w świeżych procesach testów/builda; PG otwiera nową sesję po zapisie.
Utracona odpowiedź zachowuje klucz idempotencji. Correction nadal ładuje
pierwszą nierozwiązaną pozycję, all zachowuje kolekcję i przechodzi kursorem.
`counts=none` nie jest pomiarem zerowej liczby plansz: to jawnie nieobliczone
liczniki, których ten ekran nie pokazuje. Brak migracji, treningu, restartów,
aktywacji modelu, masowej akceptacji lub zmiany marginesu w tym tasku.

## Jedna runda poprawek po R1

OpusR1: REVISE (P0-1,P1-1,P1-2). Zachowano osobny raport i receipt R1.
Kursor bieżącej strony i kotwice historii są jawne; „Poprzednia” w all odczytuje
aktualną rewizję zamiast starego obiektu. Przejście po zapisie zachowuje
historię, a retry dokładne parametry niedokończonego odczytu. Propozycja korzysta
z tej samej ścieżki przejścia. Konflikt/odrzucenie/cofnięcie w all zachowują
bieżący kursor; correction zachowuje dotychczasowy powrót do swojej kolejki.
P2-2/3 obsłużono wyjściem z filtra i deterministycznym PG. P2-4: aktualizacja
Mumie pochodzi z wcześniejszej zakończonej operacji tego samego czatu i jej
`RESULT.json`, bez ponawiania importu; pozostałe pliki generatora mają wyłącznie
różnicę końców linii (brak diffu). Do commita tylko faktyczne hunki taska.
Skupione R2 **PASS**,0P0/0P1, raport i receipt zachowane. W Outcome zapisano
ograniczenia P2-4/5/6/7. SHA2fd6022c900673562dd7fc841aafea8a3ba2645c3eb8114b846abeda69b39d8d.
