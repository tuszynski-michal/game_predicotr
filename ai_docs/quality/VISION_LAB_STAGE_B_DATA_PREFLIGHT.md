# Vision Lab — preflight danych etapu B

Odczyt: 2026-09-27, 07:48 UTC (09:48 Europe/Warsaw). Repo: `57e703acb16d435e03521b6ddd02d9857bfa5c72` (`v1.7.17`). Zakres: wyłącznie diagnostyka odczytowa; bez zmiany danych, rodzin, roli 777, splitu, usług lub treningu.

## Wynik

**Mechanicznie PASS: 63 aktualnie zaakceptowane zdjęcia, 180 pełnych obecnych geometrii, wszystkie 5×3. Freeze/T04: jeszcze NO-GO.** Akceptacje użytkownika dotyczą geometrii, nie poprawności symboli; dane nie uprawniają do treningu symboli. Poprawność mechaniczna nie jest niezależną oceną wizualną ani dowodem niezależności zdjęć.

## Źródła i integralność

- Snapshot: `C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9`.
- Stan: `C:\Users\tuszy\Documents\game_predictor_vision_data\annotations\82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9\state.json`.
- Globalna rewizja: **259**. SHA256 pliku stanu przed i po diagnostyce identyczne: `22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586`.
- SHA256 manifestu: `e6171676136ab4f9a028040126dfca36e797cdbbdbb8076229d8d6519bb1ec7c`.
- `state.snapshot_id` i ponownie obliczony digest katalogu: `3bd45272544136648fd73e02fe55825e094773ff86d7dd605e49fc1c4db977c1`. Jest to digest kontraktu katalogu, nie nazwa folderu snapshotu.
- GET stanu z API `8102` i przez proxy lab `3102`: rewizja 259, oba payloady zgodne ze stanem dyskowym.
- `Catalog` sprawdził inwentarz i SHA plików całego snapshotu (993 źródła); 63 anotowane obrazy dodatkowo odkodowano do kontroli wymiarów. Odczyt koperty stanu sprawdził checksum. Nie użyto blokady ani zapisu store.
- Reprodukowalna diagnostyka lokalna: ignorowane `artifacts/vision-lab/stage_b_preflight_readonly.py`; wynik `artifacts/vision-lab/stage-b-preflight-output.json`, pusty error log. Uruchomienie zakończone kodem 0 w około 6,6 s, limit 120 s.

## Pokrycie

| Gra | Zdjęcia w katalogu | Zaakceptowane zdjęcia | Pełne geometrie 5×3 | Rola źródeł anotowanych | Kandydaci nazw w anotowanych zdjęciach, nie rodziny |
| --- | ---: | ---: | ---: | --- | ---: |
| 777 | 240 | 11 | 30 | `comparison_only` | 3 |
| blazing zd | 99 | 10 | 30 | `data` | 3 |
| gang zd | 160 | 11 | 30 | `data` | 4 |
| mumie wybrane | 125 | 11 | 30 | `data` | 11 |
| reels | 226 | 10 | 30 | `data` | 7 |
| tresure zd | 143 | 10 | 30 | `data` | 8 |
| **Razem** | **993** | **63** | **180** | | **36** |

Topologia 3×3: **0** zaakceptowanych geometrii. Bez 777 pozostają 52 zdjęcia / 150 geometrii, lecz nadal nie są kwalifikowane do splitu bez spełnienia pozostałych bramek. Wcześniejsza zgoda na wykorzystanie nowych ręcznych geometrii 777 wymaga rozstrzygnięcia wobec obowiązującego `comparison_only`; ten preflight nie zmienia roli ani pochodzenia.

## Kontrole geometrii i akceptacji

- 180/180 zapisów ma status `full_approved`, obecność planszy i zgodny identyfikator/SHA źródła; rewizje poszczególnych plansz 1–17, nie większe od globalnej 259.
- 4320/4320 węzłów: właściwa liczba dla topologii, skończone współrzędne, granice odkodowanego obrazu; zapisane provenance `human`. To ostatnie jest deklaracją zapisu, nie dodatkowym audytem wizualnym.
- 2700/2700 komórek przechodzi istniejący walidator: wypukłość, dodatnia orientacja/pole oraz brak niedozwolonego nakładania. Narożniki zgodne z węzłami brzegowymi i granicami; digests geometrii zgodne.
- 63/63 akceptacji wiąże aktualne SHA źródła i dokładne aktualne mapy rewizji zapisanych plansz. Odrzucone zdjęcia: 0; zgłoszenia poprawek: 0. Lista błędów mechanicznych: pusta.
- Stan zawiera 259 zdarzeń historii i 259 receipts; sprawdzono ich obecność/liczność, nie przeprowadzono odrębnej analizy całej historii decyzji.
- 196 zapisów czasu nie stanowi porównania baseline/hybrid ani pełnego czasu pracy użytkownika. Nie dowodzi wymaganej oszczędności czasu.

Nie wykonano nowego przeglądu wizualnego 63 zdjęć, kontroli symboli, wyszukiwania podobieństwa percepcyjnego ani wnioskowania o nagraniach na podstawie nazw.

## Rodziny, duplikaty i istniejący split

Zapisane rodziny: **0**. `split = null`, `split_stale = false` — brak splitu, a nie potwierdzenie jego gotowości. Nazwy dostarczają tylko kandydatów (np. prefiksy BLAZING/GANG/REELS, zakresy `seq_…`); nie ma wspólnego potwierdzonego standardu nazw. Jedenaście różnych zakresów mumii nie dowodzi jedenastu niezależnych rodzin.

W katalogu wykryto **20 par identycznych bajtowo zdjęć**, wszystkie w `reels`: 40 plików, 973 unikalne SHA w całym katalogu. W samych 63 zaakceptowanych zdjęciach nie ma powtórzonego SHA. Jednak **5 par** zawiera jedno zdjęcie zaakceptowane i drugi, nieanotowany alias:

| Prefiksy pary plików w `reels` | Wspólne końcówki zdjęć z jednym zaakceptowanym członkiem |
| --- | --- |
| `REELS450100__REELS450100` / `REELS451200__REELS451200` | `004967.jpg`, `006386.jpg`, `010643.jpg` |
| `REELS471200__REELS471200` / `REELS475500__REELS475500` | `005939.jpg`, `011029.jpg` |

Obecny `freeze_splits` łączy źródła po SHA, rodzinach i relacjach **w całym katalogu**, a nie tylko w wybranych 63 zdjęciach. Każdy członek kwalifikowanej grupy musi mieć potwierdzoną rodzinę, lokalizację i aktualną akceptację zdjęcia. Dlatego nawet po dostarczeniu pochodzenia pięć powyższych grup nadal może być wykluczonych przez nieanotowane aliasy. Rozwiązanie wymaga świadomego wyboru: dodatkowe jawne zatwierdzenie aliasów albo zmiana kontraktu na kanoniczną próbkę/cohort przy zachowaniu wszystkich powiązań przeciw leakage. Nie skopiowano anotacji ani akceptacji automatycznie. Identyczne SHA nie wykrywają innych klatek tego samego nagrania, cropów ani ponownie zakodowanych kopii.

## Konkretne blokery freeze/T04

1. Brak potwierdzonych rodzin i zależności źródeł: w obecnym kontrakcie **0 kwalifikowanych grup**. Potrzebne rzeczywiste informacje albo jawnie zaakceptowany inny protokół eksperymentu — nie sztuczne „verified” na podstawie prefiksu.
2. Brak wyboru measurement i unseen oraz sprawdzenia rozłączności. Measurement wymaga co najmniej dwóch niezależnych grup w każdej objętej warstwie gra × trudność; obecne dane tego nie dowodzą. `gang zd` pozostaje kandydatem, nie zamrożonym wyborem.
3. Pięć zaakceptowanych zdjęć Reels ma nieanotowane dokładne aliasy w katalogu; obowiązuje wyżej opisana bramka całej grupy.
4. 777 nadal `comparison_only`; ewentualna kwalifikacja jego nowych geometrii wymaga jawnej aktualizacji polityki, bez twierdzenia o nowym pochodzeniu zdjęć.
5. Dane pokrywają tylko 5×3. Pilot 3×3 wymaga dodatkowego zbioru; alternatywnie trzeba jawnie ograniczyć bieżący pilot do 5×3 i nie raportować gotowości 3×3.

## Alternatywa do decyzji: podział całymi grami

Jeśli nie ma wiarygodnych powiązań z nagraniami, można rozważyć konserwatywne traktowanie każdej gry jako nierozdzielnej grupy. To ogranicza ryzyko przeniesienia klatek tej samej gry pomiędzy częściami, ale **nie jest dowodem niezależności źródeł ani potwierdzoną rodziną**. Znane identyczne duplikaty mieszczą się w Reels; nie rozwiązano nieznanych zależności pomiędzy źródłami.

Przy pozostawieniu 777 poza treningiem dostępnych jest pięć gier `data`: przykładowo jedna cała gra unseen, jedna validation, jedna final-test i dwie development dawałyby 60 geometrii development. To tylko przykład liczebności, nie wybór ról ani zamrożenie. Wszystkie części pokrywałyby wyłącznie 5×3; mały trening i mieszanie oceny generalizacji pomiędzy grami ograniczają wnioski.

**Obecny kontrakt nie pozwala po prostu zastosować tej alternatywy:** jedna nierozdzielna grupa na grę nie zapewnia dwóch niezależnych grup measurement w warstwie gra × trudność. Konieczna byłaby jawna zmiana protokołu, np. osobny pilotaż geometrii 5×3 z odłożonym pomiarem czasu, bez twierdzenia o poprawie ≥30%, oraz decyzja o obsłudze kanonicznych aliasów. Nie należy osłabiać bieżącego freeze ani wpisywać fikcyjnych rodzin, aby uzyskać sukces.

Najmniejszy kolejny krok: odpowiedź na już zadane pytanie o dostępność oryginalnych nagrań lub wiarygodnego mapowania zdjęć. Nie trzeba ponownie pytać o znaczenie prefiksów. Jeśli mapowania nie ma, użytkownik powinien zdecydować o zmienionym, ograniczonym protokole całych gier; kwalifikacja 777 pozostaje osobną jawną decyzją. Do tego czasu nie uruchamiać treningu ani freeze.

## Niezależne potwierdzenie

Audytor odczytowo potwierdził rewizję 259, 180 pełnych geometrii / 63 aktualne akceptacje, 0 rodzin, brak splitu, po 30 geometrii 5×3 na grę, rolę 777 oraz zgodne SHA/mapy rewizji/liczby węzłów. SHA stanu przed/po jego odczycie również identyczne. To potwierdzenie mechaniczne, nie certyfikacja pochodzenia lub symboli.
