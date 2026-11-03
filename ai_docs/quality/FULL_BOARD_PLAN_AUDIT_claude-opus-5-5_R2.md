# Focused review R2 — plan „Poprawa wykrywania pełnych plansz”

Werdykt: PASS

- **Audytor:** claude-opus-5-5 / high
- **Runda:** 2
- **Tryb:** przegląd statyczny. Żaden plik nie został zmieniony. Nie uruchamiałem shella, testów, usług ani nie czytałem danych operatora.
- **Zakres:** `ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md` (worktree `codex/full-board-detection`), raport R1 i 4 punktowe odczyty kodu potrzebne do rozstrzygnięcia uwag.

## Zamknięcie uwag R1

| Uwaga R1 | Status | Dowód |
|---|---|---|
| **P1-1** Automat ignoruje kody przyczyn, brak miejsc egzekwowania, brak wersji polityki | zamknięte | `PLAN:21-27`: nowy T0 przed treningiem. Blokują FIT_FAILED, FIT_OUTLIERS (rozstrzygnięte: blokuje), niepełne przypisanie pozycji, nieobsługiwany układ. Egzekwowanie nazwane z funkcji; obie istnieją (`neural_pending_geometry.py:57`, `v3_engine_acceptance.py:39`). API ponownie sprawdza dowody. Nowa wersja polityki; historyczne wersje zachowują swoją semantykę (`:25`). Mapa `:77`, `:86`. |
| **P1-2** „Ustalona przyczyna” zamiast hipotezy; ignorowanie screen+grid | zamknięte | Hipoteza: `PLAN:13` („dokładna przyczyna … wymaga T1”). Kryterium rozstrzygające T1 (brak poza wycinkiem): `:31`. Ponowne użycie `SCREEN_GRID_V1`, `ScreenGridBatches`, `photo_evaluator` bez drugiego trenera: `:47`. Istniejące augmentacje plus tylko asymetryczne błędy wykazane w T1: `:49`. Budżet i limit przed treningiem: `:41`. |
| **P1-3** Wielogłowicowy T2 bez danych i odbiorcy | zamknięte | Zakres jest ograniczony: `PLAN:17`. T2 deklaruje 5×3 / strona 3×3, sprawdza zgodność przed inferencją i akceptacją, a w razie braku zgodności blokuje z komunikatem. Nie wciska wyniku w 24 punkty i nie robi pozornej zmiany schematu: `:39`. Mapa `:82`. |
| **P1-4** Fałszywe bezpieczeństwo kalibracji (etykiety, liczebność, przeciek, syntetyki) | zamknięte (z P2-c poniżej) | Rozłączne TRAIN / VALIDATION-A / VALIDATION-B / REGRESSION, trwale zapisane, z ochroną grup, kopii i buforów: `PLAN:57`. Po ≥30 rzeczywistych złych i ≥30 dobrych przypadków, osobno w B i w REGRESSION. Etykiety z ludzkiej geometrii. Syntetyki nie liczą się do kalibracji ani odbioru. Przedziały ufności tylko przy uzasadnionej niezależności. Brak danych blokuje automat: `:59`. |
| **P2-1** Tańsze sygnały przed modelem | zamknięte | `PLAN:55`: reguły spójności (proporcje względem gry, sąsiedzi z perspektywą, zgodność obszaru). Bez nowej sieci kompletności. |
| **P2-2** Ratunek jako przesunięcie domeny, brak wyzwalacza | zamknięte | `PLAN:51`: limit to jedna ponowna detekcja plus jeden wycinek. Wyzwalacz: blokada z T0/T4. Wariant skali lub marginesu tylko po treningu i walidacji, inaczej korekta ręczna. |
| **P2-3** Zależność T5 od TASK-1153 | zamknięte | `PLAN:65`: integracja za osobną zgodą, bez niej T5 nie jest done. |
| **P2-4** Brak wersjonowanego zapisu wejścia sieci | zamknięte | `PLAN:33`: checksumy, ustawienia, macierz, rozmiar, interpolacja, wypełnienie. Odtwarzanie z metadanych, bez blobów. HTML odróżnia viewport od wejścia modelu: `:65`. Mapa `:78`. |
| **P2-5** Etapy, STOP, mapa wymaganie → task → test | zamknięte | Etapy A/B/C: `PLAN:19,43,61`. STOP przed treningiem: `:41`, `:88`. Mapa: `:73-86`. Konkretne nazwy testów powstają w taskach według TASK_TEMPLATE, zgodnie z ustaleniem operatora. |

## Pozostałe P0/P1

Brak.

## P2 (do ujęcia w szczegółowych taskach, nie blokują planu)

1. **T0: porównania wersji polityki przez równość.** Kod porównuje pojedynczą stałą `NEURAL_AUTO_CROP_POLICY` w kilku miejscach:
   - `lateral_reprocess_protection.py:32` (blokady sekwencji),
   - `v3_engine_acceptance_repository.py:63` (pochodzenie rewizji),
   - obok tego osobna stała `V3_ENGINE_ACCEPTANCE_POLICY` (`:53`).

   Jeśli dodamy nową wersję bez inwentaryzacji tych miejsc, nowe zadania mogą stracić blokady sekwencji albo dostać `V3_ACCEPTANCE_REVISION_PROVENANCE_INVALID`.
   **Minimalna poprawka w tasku T0:** spisać wszystkie porównania obu stałych, zamienić je na zbiór znanych wersji z jawną semantyką i dodać testy dla starej i nowej wersji.

2. **462205 w odbiorze T0.** Plan zakłada, że zapisany kandydat ma `FIT_OUTLIERS` (`PLAN:27`). R1 stwierdził, że obecny kod nie ma dla 462205 sygnału zatrzymania (R1:16). Nie potwierdziłem tego faktu statycznie.
   **Poprawka w tasku T0:** sprawdzić reasonCodes w zapisanym artefakcie. Jeśli kodu nie ma, odbiór T0 ma jawnie stwierdzać, że T0 nie zatrzymuje 462205, a ochrona przechodzi do T4.

3. **Przykłady diagnostyczne a pule progowe.** Plan mówi tylko, że „nie są niezależnym testem” (`PLAN:35`). Nie wyklucza ich wprost z VALIDATION-B.
   **Poprawka w T1/T4:** jawnie wykluczyć 462205 i inne przykłady użyte diagnostycznie z VALIDATION-B i REGRESSION.

4. **Definicja „rzeczywistego błędnego przypadku”.** „Etykiety z ludzkiej geometrii” (`PLAN:59`) nie określają kryterium porównania.
   **Poprawka w T4:** przed etykietowaniem B ustalić i zapisać kryterium. Może to być brak dopasowania wiersza lub kolumny, próg IoU albo błąd węzła w px względem zatwierdzonej geometrii.

5. **Baza dla „wzrostu poprawnych automatycznych”** (`PLAN:59`, `:69`). T0 sam zmniejszy liczbę wyników automatycznych, więc baza sprzed T0 i baza po T0 dadzą różne wnioski.
   **Poprawka w T4/T6:** wskazać bazę (zalecam: obecny model z polityką T0) i raportować obie wartości.

## Ograniczenia

- Przegląd był wyłącznie statyczny i dotyczył planu oraz R1. Kod czytałem tylko w 4 miejscach: definicje funkcji egzekwowania, użycia `NEURAL_AUTO_CROP_POLICY` i `FIT_OUTLIERS`, `v3_engine_acceptance_repository.py:50-74` oraz `lateral_reprocess_protection.py:20-39`.
- Nie weryfikowałem reasonCodes zapisanego kandydata 462205. Przeszukanie `artifacts/` przekroczyło limit czasu.
- Nie oceniam skuteczności: żadna poprawa wykrywania ani skuteczność blokad nie jest zadeklarowana przed pomiarem.

## Potrzebne testy (do szczegółowych tasków)

- **T0:**
  - zgodność decyzji workera i API dla FIT_FAILED (fallback), FIT_OUTLIERS, niepełnego przypisania, nieobsługiwanego układu i braku pikseli;
  - stara wersja polityki zachowuje dotychczasową decyzję;
  - nowa wersja zachowuje blokady sekwencji i pochodzenie rewizji (integracja PostgreSQL);
  - regresja dla 462205 zgodna z wynikiem weryfikacji z P2-2.
- **T1:** deterministyczne odtworzenie wycinka i transformacji z metadanych (zgodność z checksumem).
- **T2:** blokada nieobsługiwanego układu i innej liczby plansz przed inferencją i przed akceptacją, z zachowanym źródłem.
- **T3:**
  - nowa polityka korekt mapuje się na screen+grid;
  - częściowe zdjęcia nie trafiają do detektora;
  - wznowienie nie odnawia budżetu i nie duplikuje treningu.
- **T4:**
  - rozłączność A/B/REGRESSION na poziomie grup, kopii i buforów;
  - wykluczenie przykładów diagnostycznych;
  - syntetyki są nieobecne w B i REGRESSION;
  - blokada automatu przy mniej niż 30 przypadkach w jednej z klas.
- **T5:** pełen pion API (OpenAPI, wygenerowany klient, wrapper, request test); panel odróżnia propozycję, automat i zatwierdzenie.
