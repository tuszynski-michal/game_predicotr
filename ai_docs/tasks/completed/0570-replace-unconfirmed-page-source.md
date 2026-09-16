---
title: TASK-0570 — podmiana zdjęcia przed zatwierdzeniem geometrii
status: done
last_updated: 2026-09-16
---

# TASK-0570 — podmiana zdjęcia przed zatwierdzeniem geometrii

## Goal

Operator może zastąpić źle przycięty JPEG w kolejce ręcznej korekty, zobaczyć
nowy obraz i poprowadzić go do importu plansz oraz symboli bez naruszania
ukończonych historycznych jobów.

## Context

Staging przeglądarkowy i preflight są przypięte do sum kontrolnych. Obecny
przycisk pozwala wykluczyć źródło, lecz podmiana bajtów w tym samym stagingu
złamałaby integralność manifestu. Folder `cut` nie jest zapisany jako ścieżka
stagingu; użytkownik musi ponownie wskazać folder z prawem zapisu.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Przycisk podmiany tylko dla źródła odroczonego do ręcznej geometrii, przed
  zatwierdzeniem geometrii tego konkretnego zdjęcia i przed importem stagingu.
- Weryfikacja oryginalnego pliku z katalogu `cut` po nazwie i SHA-256, po czym
  zapis nowego JPEG-a pod tą samą nazwą.
- Nowa, niezmienna rewizja stagingu z jednym zmienionym źródłem. Stara rewizja
  oraz preflight pozostają jako historia; nowa zachowuje wariant v1.0/v1.1.
- Natychmiastowy podgląd nowego zdjęcia w korekcie, a przed zapisem ręcznej
  geometrii ponowne przygotowanie zgodnego preflightu.
- Ponowne użycie geometrii niezmienionych źródeł; zmienione zdjęcie liczone
  od nowa. Nowy manifest i checksumy prowadzą dalej do zwykłego importu.

## Out of scope

- Podmiana po zatwierdzeniu geometrii danego zdjęcia albo po rozpoczęciu
  importu plansz i symboli.
- Przepisywanie historycznych wyników i decyzji człowieka.

## Acceptance criteria

- [x] Jedno źródło w ręcznej kolejce można podmienić i obejrzeć bez restartu.
- [x] Podmiana odrzuca niezgodny folder, stary plik, błędny JPEG i konflikt rewizji.
- [x] Stary staging i preflight pozostają poprawne; nowy manifest wskazuje
  wyłącznie nową checksumę dla podmienionego zdjęcia.
- [x] Pozostałe źródła korzystają ze zgodnych wyników; nowe przechodzi przez
  preflight, korektę i import do symboli.
- [x] Po akceptacji geometrii lub starcie importu podmiana jest zablokowana.
- [x] Restart i utrata odpowiedzi nie prowadzą do cichego pomieszania wersji.

## Outcome

Dodano wybór katalogu `cut`, kontrolę nazwy i SHA-256, zapis JPEG-a pod tą
samą nazwą oraz natychmiastowy podgląd. API tworzy nową niezmienną rewizję
stagingu, blokuje uruchomienia na rodzicu podczas przygotowania i po
potwierdzeniu oraz nie dopuszcza nowej rewizji do jobów przed potwierdzeniem.
Zachowuje wariant silnika i przypina manifest rodzica do inkrementalnego
preflightu; zmieniony obraz oraz zależne kotwice są przeliczane. Klient może
dokończyć przerwany zapis albo odrzucić go, gdy oryginał nie został zmieniony.

Weryfikacja: 66 testów API, 13 testów workera, 495 testów Admina, lint i
typecheck zmienionych obszarów, kontrola wygenerowanego OpenAPI/klienta oraz
produkcyjny build Admina — zaliczone. Testy obejmują restart, utraconą
odpowiedź i przerwanie między zapisami stanu obu rewizji. Nie uruchomiono
podmiany ani nowego joba na rzeczywistych katalogach i stagingach użytkownika;
operacyjne przejście aż do symboli nastąpi dopiero po jego wyborze zdjęcia.
