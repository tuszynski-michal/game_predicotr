---
title: TASK-1010 — Diagnostyka siatek Mumii i 777a2
status: measured
last_updated: 2026-10-14
---

# Rzeczywiste liczniki siatek V3

## Zakres i sposób pomiaru

Odczyt wykonano z worktree `D:/game_predicotr/worktrees/v3-grid-fine-tuning`,
branch `codex/v3-grid-fine-tuning`, bazującego na bootstrapie v1.7.367 /
`b35a9ee7dadf3da485427f81a84149e63f0b8cfc`. Dane pochodzą z lokalnej bazy
operatora przez rolę aplikacji i `GameStorageRouter` z intencją READ/RLS właściwej
gry. Nowy raport i API używają oddzielnej transakcji REPEATABLE READ READ ONLY.
Każde zapytanie ma limit 30 s; proces pomiaru ma limit 120 s. Niczego nie zapisano
w bazie. Usługi, migracje, backfill, modele i cropy pozostawiono bez operacji.

| Gra | Identyfikator | Początek odczytu UTC | Koniec UTC | Czas |
| --- | --- | --- | --- | --- |
| Mumie a1 | `fea55cc1-ebf4-4cee-b3ab-a520017ed1be` | 2026-10-14 18:17:34.130551 | 18:18:22.736489 | 48,610 s |
| 777a2 | `6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf` | 2026-10-14 18:19:06.559670 | 18:19:23.076690 | 16,516 s |

To dwa osobne obrazy danych. Gry nie mają wspólnego snapshotu. Zakres obejmuje
całą grę, bez filtra importu i bez badania plików JPEG na dysku. Historycznej
gry 777 (kod `7`) nie odczytywano ani nie zmieniano. Artefakty surowe są zapisane
w ignorowanym `artifacts/audits/TASK-1010_mumie_diagnostics.json` i
`artifacts/audits/TASK-1010_777a2_diagnostics.json`. Powtórzenie:
`scripts/read_grid_diagnostics.py --game-id UUID --output PATH` uruchomione
przez Python z `.venv` w katalogu worktree.

## Pokrycie unikalnych sekwencji

| Licznik, jednostka: unikalna sekwencja | Mumie | 777a2 |
| --- | ---: | ---: |
| Oczekiwany zakres 1–500 000 | 500 000 | 500 000 |
| Dodane | 491 969 | 341 537 |
| Brakujące | 8 031 | 158 463 |
| Kwalifikujące się wyniki review | 491 969 | 341 537 |
| Kanoniczne | 1 284 | 76 |
| Przecięcie kanonu i kwalifikujących się wyników | 1 284 | 76 |
| Kanoniczne poza oczekiwanym zakresem | 0 | 0 |

Uzgodnienie: Mumie `491 969 + 1 284 − 1 284 = 491 969`; 777a2
`341 537 + 76 − 76 = 341 537`. Nadmiar kwalifikujących się rekordów względem
unikalnych sekwencji wynosi 0 w obu grach. Każdy kwalifikujący się wynik jest
kompletną planszą z żywym statusem pending/accepted/corrected; obecność
kanonu także kwalifikuje sekwencję. Nieznane lub niezatwierdzone symbole nie
uczestniczą w tym warunku.

| Rekordy review, jednostka: zapisany rekord planszy | Mumie | 777a2 |
| --- | ---: | ---: |
| Pending | 490 685 | 341 461 |
| Accepted | 1 223 | 75 |
| Corrected | 61 | 1 |
| Superseded | 246 | 27 |
| Rejected | 0 | 0 |
| Wszystkie wymienione rekordy | 492 215 | 341 564 |

Różnica 246/27 między rekordami a dodanymi sekwencjami wynika z historii
superseded. Nie jest brakiem plansz ani aktywnym duplikatem. Liczniki sekwencji
wewnątrz każdego statusu są tutaj równe licznikom rekordów; statusów ogólnie
nie wolno sumować jako rozłącznych zbiorów sekwencji.

## Przyczyny braków i odroczone sloty

| Dominująca przyczyna, jednostka: brakująca sekwencja | Mumie | 777a2 |
| --- | ---: | ---: |
| Oczekiwanie na geometrię | 259 | 373 |
| Brak znanego źródła numerowanej sekwencji (`no_source`) | 7 772 | 158 090 |
| Trwający import / częściowe źródło / błąd / odrzucenie / nierozstrzygnięta | 0 | 0 |
| Suma dominujących przyczyn | 8 031 | 158 463 |

`no_source` oznacza brak kwalifikującego się numerowanego wyniku i brak znanego
sygnału przyczyny w bieżącej bazie. Nie dowodzi braku pliku JPEG w katalogu.
Dokładna przyczyna każdego z 7 772/158 090 takich numerów pozostaje
nierozstrzygnięta bez osobnego rozliczenia źródła/importu. Nie utworzono
syntetycznych plansz i nie poprawiono danych podczas diagnozy.

| Sloty źródeł, jednostka: slot zdjęcia | Mumie | 777a2 |
| --- | ---: | ---: |
| Pending, powód `incomplete_lattice` | 262 | 373 |
| Pending z już dodaną sekwencją | 3 | 0 |
| Pending bez dodanej sekwencji w oczekiwanym zakresie | 259 | 373 |
| Unikalne brakujące numery powyższych slotów | 259 | 373 |
| Pending poza zakresem / bez numeru | 0 / 0 | 0 / 0 |
| Resolved | 44 | 0 |
| Superseded | 847 | 0 |
| Rejected | 0 | 0 |

Mumie: `262 = 259 + 3`; trzy nadal pending sloty nie tworzą braku sekwencji,
bo istnieje kwalifikujący się wynik. Nie zamknięto tych slotów automatycznie.
777a2: każdy z 373 pending slotów odpowiada brakującej sekwencji. W tych
pomiarach brak przecięć różnych znanych przyczyn brakujących numerów.
Implementacja zachowuje także wtórne sygnały i przecięcia przyczyn, gdy wystąpią.
Odrzucony slot bez planszy dostaje przyczynę odrzucenia w raporcie braków.

## Zdjęcia, pozycje i akceptacja geometrii

| Bieżąca klasyfikacja, jednostka: zdjęcie | Mumie | 777a2 |
| --- | ---: | ---: |
| Wszystkie zdjęcia | 54 915 | 37 993 |
| Kompletne | 5 | 0 |
| Z brakującymi pozycjami | 98 | 222 |
| Z pozycjami częściowymi | 0 | 0 |
| Z niepotwierdzoną geometrią | 54 595 | 37 768 |
| Z błędem importu | 3 | 0 |
| Bez geometrii źródła | 0 | 0 |
| Superseded | 214 | 3 |
| Niekompletne w bieżącej klasyfikacji | 54 696 | 37 990 |

| Stan zapisany bramki, jednostka: zdjęcie | Mumie | 777a2 |
| --- | ---: | ---: |
| Geometry complete | 4 | 0 |
| Geometry incomplete | 54 790 | 37 990 |
| Geometry exception | 0 | 0 |
| Outside gate | 120 | 3 |
| Jeszcze nie ocenione | 1 | 0 |
| Wstrzymane plansze, osobna jednostka | 0 | 0 |

Mumie: 54 790 zapisanych jako incomplete różni się od 54 696 bieżąco
niekompletnych o 94. To różne odczyty: zapisany stan bramki i klasyfikacja
najnowszej geometrii/żywych plansz. Bieżąca klasyfikacja wyłącza 214 zdjęć
superseded i ma 5 kompletnych; zapisane wartości obejmują 120 poza bramką,
4 kompletne i 1 nieocenione. Obie populacje sumują się do 54 915 zdjęć.
Dokładne historyczne przejście każdego z tych 94 zdjęć pozostaje
nierozstrzygnięte bez analizy zdarzeń per zdjęcie. Raport nie odświeża bramki.
777a2: oba liczniki niekompletności są równe, ale obejmują 37 768 zdjęć
niepotwierdzonych i 222 z brakującymi pozycjami; nie 37 990 błędów cięcia.

| Pozycje bieżących zdjęć, jednostka: slot | Mumie | 777a2 |
| --- | ---: | ---: |
| Oczekiwane pozycje | 494 226 | 341 937 |
| Poprawne i potwierdzone (`ok`) | 44 | 0 |
| Niepotwierdzone (`uncertain`) | 491 925 | 341 537 |
| Częściowe | 0 | 0 |
| Superseded | 1 980 | 27 |
| Missing | 18 | 0 |
| Deferred | 259 | 373 |

Pozycje sumują się do oczekiwanych pozycji zdjęć. Pozycje różnych zdjęć mogą
powtarzać numer sekwencji, a pozycja superseded ma inne aktualne źródło.
Dlatego 18 pozycji missing Mumii nie oznacza automatycznie 18 dodatkowych
brakujących numerów. Pokrycie 500 000 ocenia się wyłącznie jako zbiór
sekwencji, nie przez mnożenie liczby zdjęć przez dziewięć.

## Błędne siatki i problemy symboli

| Geometria, jednostka: plansza | Mumie | 777a2 |
| --- | ---: | ---: |
| Aktualne zgłoszenie „Zła siatka” | 0 | 98 |
| Kompletna geometria bez bieżącej akceptacji | 491 925 | 341 537 |
| Przecięcie zgłoszonej i niepotwierdzonej | 0 | 98 |

Zgłoszenie jest liczone raz na planszę, nawet gdy kilka jej komórek zgłasza
problem. Musi dotyczyć bieżącej rewizji cropa i pending jakości grid_issue.
Nie jest liczbą slotów deferred ani brakujących sekwencji.

| Symbole, jednostka: widoczna komórka bieżącej rewizji | Mumie | 777a2 |
| --- | ---: | ---: |
| Wszystkie | 7 379 535 | 5 123 055 |
| Pending | 7 341 221 | 5 116 528 |
| Approved | 38 314 | 6 527 |
| Nieznane | 22 | 141 |
| Nieczytelne | 22 | 0 |
| Poza źródłem | 0 | 0 |
| Pending z pewnością <60% | 2 367 | 1 723 |
| Nieznane i pending | 22 | 141 |
| Nieczytelne i pending | 22 | 0 |
| Nieznane, pending i z pewnością <60% | 22 | 38 |

Nieznana komórka ma brak przypisania albo aktualny problem grid_issue/unreadable,
z wyłączeniem komórek outside. Widoczność odpowiada source_available/outside;
dodatkowo wymagana jest zgodna geometry_revision planszy. Odrzucone i
superseded review items są wyłączone. Filtr niskiej pewności wykorzystuje
istniejące pasmo „poniżej 60%” z `symbol-review-state.ts`, nie nowy próg
kwalifikacji planszy. Nieznane, nieczytelne i niskiej pewności przecinają się.

W obu pomiarach wszystkie komórki są zgodne z `dodane × 15`: Mumie
`491 969 × 15 = 7 379 535`, 777a2 `341 537 × 15 = 5 123 055`. Brak rozpoznanego
symbolu nie jest brakiem planszy. D-523 dopuszcza automatyczne cięcie V3 bez
ręcznej akceptacji; liczba niepotwierdzonych plansz/zdjęć nie jest pomiarem
błędu pikseli. Realna jakość wymaga osobnej kontroli operatora TASK-1009.

## Ograniczenia i weryfikacja

Mumie ma także 90 zapisanych błędów plików importu bez znanego zakresu numerów
(osobna populacja od trzech zdjęć import_failed). Tych zdarzeń nie przypisano
arbitralnie do konkretnych brakujących numerów; ich wpływ pozostaje
nierozstrzygnięty. Obie gry mają 0 aktywnych importów w pomiarze. Pokrycie,
kanon, bieżące symbole i znane odroczenia są liczbowo uzgodnione.

Pierwsze dwa robocze zapytania symboli przekroczyły limit 30 s. Finalne SQL
ogranicza kolumny i bezpośrednio łączy komórkę z jej planszą przez id oraz
geometry_revision, zamiast dwóch dużych złączeń przez review item. Finalne
pomiary powyżej zakończyły się poprawnie; timeouty nie są traktowane jako PASS.
Kosztowniejsza diagnostyka jest opt-in i nie jest automatycznie odpytywana co
15 s. Kontrole implementacji, błędy prób i wynik audytu znajdują się w Outcome
TASK-1010. Nowej wersji API nie wdrożono do działającej usługi.
