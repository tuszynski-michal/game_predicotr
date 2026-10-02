---
title: Standard planowania i przekazania implementacji
status: active
last_updated: 2026-09-06
---

# Plan gotowy do bezpiecznej implementacji

Planista rozstrzyga istotne decyzje; wykonawca nie powinien projektować
architektury ani odgadywać wymagań. Szczegółowość wynika z ryzyka, nie z chęci
wydłużenia dokumentu. Obowiązują istniejące zasady AGENTS.md, w tym zakres,
hierarchia dokumentacji, zgody, cykl tasków i wersjonowanie commitów.

## Zakres działania i analiza

- Prośba wyłącznie o plan upoważnia do analizy, nie do zmian aplikacji,
  zależności ani danych. Zapisz plan tylko na prośbę użytkownika lub gdy
  wymaga tego workflow konkretnego zadania. Prośba o implementację wymaga
  wykonania zmiany, a nie zakończenia prostego zadania samym dokumentem.
- Sprawdź stan repozytorium i obowiązujące instrukcje, także nadpisania.
  Prześledź punkty wejścia, przepływ danych, użycia kontraktów, typy, API,
  modele, konfigurację i testy w potrzebnym zakresie. Wykorzystuj istniejące
  mechanizmy zamiast projektować ich równoległe kopie.
- Istniejące elementy wskazuj jako sprawdzona ścieżka + symbol. Nowe pliki,
  symbole i statusy oznacz jako proponowane. Polecenia testów ustal z repo;
  nie wymyślaj nazw ani nie analizuj całego projektu bez potrzeby.
- Oddziel wymagania użytkownika, fakty z kodu/testów, decyzje projektu oraz
  założenia i niewiadome. Hipoteza przyczyny błędu nie jest diagnozą.
  Informacje z repo ustal sam; brak istotnej decyzji biznesowej lub dotyczącej
  bezpieczeństwa blokuje zależny fragment, z dokładnym opisem brakującej
  informacji. Aktualizując plan, usuń sprzeczne lub nieaktualne ustalenia.

## Decyzje, dane i błędy

- Wskaż jedno zalecane rozwiązanie i uzasadnienie. Ustal odpowiedzialności
  modułów, wejścia/wyjścia i typy, kolejność walidacji, zapis, granice
  transakcji oraz wpływ na API/UI. Drobne szczegóły zgodne z konwencjami
  pozostaw wykonawcy. Trudną logikę wyjaśnij pseudokodem, tabelą decyzji lub
  przykładami wejście → wynik, bez przepisywania całej implementacji.
- Określ źródło prawdy, identyfikatory, relacje, kolejność, liczności,
  unikalność, wyjątki i walidację. Przy rozbieżności źródeł wskaż nadrzędne
  i reakcję; dane pomocnicze lub rozpoznanie nie nadpisują ich po cichu.
  Konkretne liczby, wersje i reguły domeny pozostają w planie/wymaganiach,
  nie stają się automatycznie stałą instrukcją dla wszystkich zadań.
- Dla błędu podaj warunek, zasięg (element/etap/operacja), zapis, kontynuację
  albo zatrzymanie, status, komunikat i retry lub korektę. Opisz przejścia
  stanów i warunki następnego etapu. Uwzględnij właściwe przypadki brzegowe:
  niepełne dane, duplikaty, częściowy sukces, restart i istniejące rekordy.
  Nie maskuj błędów programistycznych ani infrastrukturalnych jako sukcesu
  przez ogólne przechwycenie wyjątków.
- Przy zmianie bazy sprawdź rekordy, relacje, ograniczenia, indeksy,
  kompatybilność i konieczność migracji schematu/danych. Dla ryzykownej
  migracji ustal weryfikację, kolejność wdrożenia i realną możliwość
  odtworzenia; nie obiecuj nieistniejącego rollbacku.
- Przy dużych zbiorach podaj skalę (zmierzoną lub założoną), granice pamięci,
  zapytań, transakcji i ponowień. Nowe zależności, cache, kolejki i szeroka
  przebudowa wymagają uzasadnienia, nie są domyślnym rozwiązaniem.

## Układ planu i rekomendacja wykonawcy

Zacznij od stanu obecnego, celu, zakresu, kluczowych reguł i decyzji.
Zadania porządkuj według zależności i opisuj według TASK_TEMPLATE.md.
Jedno zadanie oznacza spójną zmianę, nie pojedynczy plik ani ogólnik
„zaktualizuj backend i frontend”. Ma być wykonalne w nowej sesji wraz
z instrukcjami repo, bez odtwarzania historii rozmowy. Nieistotne pola pomijaj.

Ostatnią sekcją każdego planu musi być **Przypisanie modeli do zadań** z tabelą:

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|

Tabela jest źródłem prawdy dla przypisania wykonawczego i podlega regułom:

- zawiera dokładnie jeden jawny wiersz dla każdego taska planu, w tej samej
  kolejności; nie wolno pomijać taska ani używać skrótów „ten sam model”,
  „jak wyżej” lub wspólnego wiersza dla kilku tasków;
- plan bez numerowanych tasków zawiera jeden wiersz opisujący całe zadanie;
- każdy wiersz podaje dokładną nazwę modelu dostępnego w bieżącym środowisku,
  dokładny wspierany poziom rozumowania, krótkie uzasadnienie oraz informację,
  czy wymagany jest niezależny review; wymagany review wskazuje również model
  i poziom rozumowania;
- sekcja `Recommended execution` taska rozwija uzasadnienie i warunek
  eskalacji, ale jej model i poziom rozumowania muszą odpowiadać końcowej tabeli
  zaakceptowanego planu; rozbieżność blokuje rozpoczęcie taska do czasu spójnej
  aktualizacji planu i taska;
- przypisanie jest wskazówką wykonawczą, a nie zgodą na automatyczną zmianę
  modelu, uruchomienie agentów lub delegowanie pracy;
- wyraźne polecenie uruchomienia etapu zaakceptowanego planu upoważnia do
  wykonania wszystkich jego tasków i delegowania według tabeli. Obowiązuje
  reguła właścicielska `AGENTS.md`: osobny audyt, commit i Outcome każdego
  taska oraz zatrzymanie na granicy etapu lub przy blokerze;
- gdy przypisany model albo poziom nie jest dostępny, wykonawca zatrzymuje task
  i aktualizuje rekomendację w planie oraz tasku zamiast wybierać niejawny
  zamiennik.

Przy tworzeniu tabeli:

- konkretny model i wspierany poziom rozumowania, jedno–dwa zdania
  uzasadnienia oraz warunek ponownej analizy lub review mocniejszym modelem;
- dobieraj możliwie oszczędny wariant wystarczający do ryzyka i konkretności
  planu, uwzględniając złożoność, liczbę modułów, bezpieczeństwo danych oraz
  jakość testów. Nie obiecuj matematycznej optymalności kosztu lub jakości;
- sprawdź aktualną dostępność i obsługiwane ustawienia w bieżącym środowisku
  lub oficjalnej dokumentacji. Jeżeli nie można ich potwierdzić, oznacz
  rekomendację jako warunkową. Nie zapisuj tu stałych nazw modeli, rankingu,
  cen ani listy poziomów rozumowania;
- dla zadań o różnym ryzyku dobierz różne konfiguracje; nawet gdy konfiguracja
  się powtarza, wpisz ją jawnie w każdym wierszu.

## Bramka jakości planu

Przed oddaniem sprawdź: pokrycie każdego wymagania zadaniem i testem,
brak sprzeczności, potwierdzone pliki/symbole/polecenia, źródła prawdy,
zachowanie błędów, zależności i ochronę zachowania poza zakresem.
Nie ukrywaj decyzji pod „dostosuj odpowiednio”; jawnie wskaż niewiadome.
Dla większego planu dodaj mapę wymaganie → task → test/kryterium.
Zakończ odbiorem całego przepływu, ryzykami i zakresem wyłączonym, a następnie
obowiązkową tabelą `Przypisanie modeli do zadań` jako ostatnią sekcją planu.
Wyraźnie oddziel testy planowane od faktycznie uruchomionych i zaliczonych.

## Wykonanie w nowej sesji lub innym modelu

- Ponownie sprawdź warunki wejściowe i aktualny kod. Plan określa zamiar,
  nie dowodzi, że repo się nie zmieniło. Drobne różnice techniczne dostosuj
  i odnotuj; zmiana logiki biznesowej, kontraktu, architektury lub ochrony
  danych wymaga wstrzymania zależnego fragmentu i korekty planu.
- Realizuj zatwierdzony zakres i kolejność, bez dodatkowych refaktorów.
  Po spójnej zmianie testuj; nie osłabiaj walidacji ani asercji dla zieleni.
  Powtarzające się niepowodzenie wymaga podsumowania dowodów, blokady
  i potrzebnej decyzji, nie losowych zmian.
- Ukończenie wymaga kryteriów akceptacji. Raportuj wyniki, odstępstwa
  i konkretne powody niemożliwej weryfikacji. Zgoda na implementację nie
  zastępuje wymaganych zgód na push, wdrożenie lub operacje destrukcyjne;
  commity wykonuj zgodnie z obowiązującym cyklem repozytorium.
