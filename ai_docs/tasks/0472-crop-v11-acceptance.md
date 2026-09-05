# TASK-0472 — Odbiór v11
## Status
blocked — second quality gate failed
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
