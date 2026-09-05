# TASK-0472 — Odbiór v11
## Status
blocked — sixth independent quality gate failed strict precision
## Relevant docs
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
## Dependencies / goal
0471. Odbiór dokładnej ścieżki produkcyjnej bez strojenia na holdout.
## DoD / tests
Zero niebezpiecznych automatów i cropów reklamy, minimum 90% poprawnych
automatów na czytelnych kompletnych źródłach. Raport osobno dla wyglądów gry,
czasy/pamięć, testy core/Admin, lint/typecheck/format/build. Brak oryginałów
innej gry ogranicza odbiór. Nie aktywować jeśli bramka nie przejdzie.
## Outcome
### Iteracja 2026-09-06 — bezpieczeństwo poprawione, bramka nadal zablokowana

- Rozdzielono nieznaczne nakładanie pochylonych rzędów od rzeczywistego
  konfliktu oraz dodano deduplikację wariantów progowych dopiero po wykryciu
  niejednoznaczności. Różne przestrzennie układy nadal kończą się manualnie.
- Jeżeli poziom 960 wykrył pełne 3×3, lecz nie potwierdził numerów, poziom 1600
  może ponownie zbadać etykiety na przeskalowanym, już udowodnionym układzie.
  Nie uzupełnia to brakujących plansz i nie wykonuje trzeciego przebiegu.
- Dodano ograniczony fallback perspektywy oraz odzyskanie górnej granicy z
  położenia dziewięciu pasów numerów. Naprawiło to wykryte odcięcie górnego
  rzędu; konfiguracja pozostaje częścią fingerprintu.
- Ujawnione korpusy rozwojowe osiągają 9/10, 7/7 i 10/10. Piąta próba służyła
  dalszej diagnozie. Szósta, zamrożona przed uruchomieniem, ma 9 automatów i
  jeden manual; żaden automat nie odcina planszy ani numeru, ale tylko 6/10
  mieści się w ścisłych przedziałach obu linii. Trzy bezpieczne wyniki zostawiają
  za dużo tła. Bramka dokładności NIE przeszła.
- `CROP_V11_RELEASE_ENABLED` pozostaje `false`. Nie zmieniono katalogów źródłowych,
  katalogów cut, importów ani jobów. Brak oryginałów gry literowej nadal ogranicza
  odbiór. Wszystkie nowe próby są ujawnione i nie mogą ponownie pełnić roli holdout.

### Iteracja v0.10.185

- Dodano poziomo wydłużony element łączenia krawędzi (aspekty 1 i 2), bez
  syntetycznych brakujących plansz i bez zmiany budżetów 960/1600, 96 kandydatów.
- Analiza etykiety używa nachylenia wykrytego rzędu. Zakres wyszukiwania jest
  przeliczany do tej samej przestrzeni; wynik wraca do współrzędnych źródła.
  Dowód przejść dotyczy całego pasa, więc pełne białe wiersze pogrubionych cyfr
  nie znikają. Nie obracamy wyniku JPEG. Bufor początkowy zwiększono 15%→20%.
- Znana dziesiątka: 9/10 poprawnych, zero błędnych automatów, 1 manual.
- Zamrożona przed oceną nowa próba z siedmiu pozostałych katalogów: 5/7
  poprawnych, 1 z dolną linią ponad chronionym zakresem referencji, 1 manual.
  Bramka NIE przeszła; nie aktywowano v11 ani nie zakończono zadania.
- 101 testów core/runner/Admin i typecheck obu pionów OK. Dodano test nachylenia,
  zachowania pełnych pasów cyfr i mapowania ich obwiedni. Zmiana oczekiwanego
  paddingu w teście wynika z jawnej konfiguracji 20%, nie zmiany referencji zdjęć.
- Produkcyjny build Admina i format zmienionych plików przeszły. Pełny lint
  niezwiązanych modułów nie był ponawiany; znane wcześniejsze błędy poza zakresem.
- Nie zmieniono istniejących katalogów, OCR, geometrii ani jobów. Brak odbioru
  gry literowej pozostaje ograniczeniem. Nowe 7 zdjęć jest już ujawnione;
  nie wolno przedstawiać ich ponownie jako holdout po dalszym strojeniu.

### Iteracja naprawcza — v0.10.184

Usunięto sztuczny margines dylatacji z pomiaru wsparcia planszy (z ochroną
przypadków dotykających brzegu źródła). Scalanie nie opiera się już na samym
zawieraniu mniejszego komponentu. Dodano pośrednie promienie oraz ścieżkę
krawędzi bez minimalnej jasności. Etykiety przechodzą kontrolę kształtu przed
rankingiem odległości od dołu planszy; równorzędne propozycje nadal odrzucamy.
Fingerprint obejmuje zmiany. V10 i domyślna polityka pozostają bez zmian.

Stare dwa przypadki: 2/2 poprawnych cięć. Nowa próba niezależna, wybrana przed
uruchomieniem detektora: 10 medianowych plików z 10 innych katalogów, 5 poprawnych
automatów, 1 automat ze zbyt dużym tłem u dołu, 4 ręczne korekty. Zero odciętych
plansz/numerów w tym materiale NIE zastępuje bramki >=90%. Odbiór ponownie
nieprzejściowy; task nieukończony, release=false, bez podmiany danych operatora.

Referencje nowych zdjęć mają SHA oraz przedziały poziomych linii i chronione
ekstrema wszystkich plansz/numerów, oznaczone przed pomiarem w podglądzie 360×640.
To oracle pasa, nie nowe referencje dokładnych narożników. Odbiór gry literowej
pozostaje niepotwierdzony. Nowa próba jest od tej chwili ujawniona i nie może być
ponownie przedstawiana jako niezależny holdout po dalszym strojeniu.

Kontrole: 75 core + 7 runner/recovery + 18 Admin contract = 100 testów OK;
typecheck core i Admin OK. Testy obejmują halo, containment i ranking etykiet.
Produkcjny build Admina i format zmienionego pionu OK; replay v10 7/7 bez zmian.
Pełny lint pozostałych modułów nie był ponawiany (znane błędy poza zakresem).
Dalsza praca: odrzucone układy pochylone i granice obszarów numerów; bez
osłabiania bramek, podmieniania referencji pod wynik czy deklarowania sukcesu.

### Poprzedni odbiór

Wznowiono na jawne polecenie użytkownika. Poprzedni holdout po diagnozie jest
materiałem regresyjnym, nie niezależnym odbiorem kolejnej iteracji. Nie obniżamy
bramek bezpieczeństwa ani nie podmieniamy katalogów. Zakres: ekstrakcja i łączenie
kandydatów v11, testy, niezależny odbiór oraz dokumentacja. Nowa konfiguracja
zmieni fingerprint; wcześniejsze wyniki nie mogą być pomijane jako zgodne.

2026-09-05: odbiór wykonano dokładną ścieżką renderCropSource, bez zapisu
wynikowych JPEG-ów. Holdout: 0/2 poprawnych automatów (wymagane >=90%),
0 błędnych automatów, 2 obowiązkowe korekty: incomplete_layout po 960 i 1600.
Zero błędów przy zerowej liczbie akceptacji nie oznacza sukcesu jakości.

Na polecenie użytkownika zatrzymano strojenie i wdrożenie. Release gate pozostaje
false; istniejące katalogi, importy i decyzje nie zostały zmienione. Task nie
spełnia DoD i pozostaje aktywny jako blocked, zamiast trafić do completed.

Weryfikacja: 72 testy core, 18 kontraktów Admina, 7 testów runnera (w tym
EXIF 1–8), typecheck core/Admin, scoped lint, scoped format i build Admina OK.
Replay baseline v10: 7/7 zgodnych. Pełny lint Admina blokują dwa wcześniejsze,
niezwiązane błędy set-state-in-effect w geometry-guard-resolution-panel.tsx.
Nie wykonano pełnych testów aplikacji ani live QA przeglądarki. Zgodność samplerów
dotyczy tych samych RGBA; różnice dekoderów JPEG Node/przeglądarka nie zostały
zmierzone. Oryginały gry literowej pozostają niedostępne.

Raport: ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md. Dalsza praca wymaga
osobnego polecenia: analiza ekstrakcji kandydatów, nie osłabienie ochrony granic.
