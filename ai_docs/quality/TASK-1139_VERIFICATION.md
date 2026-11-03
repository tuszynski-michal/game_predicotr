# TASK-1139 — Weryfikacja przyrostowego podziału

Zakres: izolowany worktree `D:/game_predicotr/worktrees/grid-correction-growth`.
Bez zmian bazy operatora (0171), usług, modelu, danych źródłowych i przypisań.
Wszystkie skończone polecenia miały timeout do 120 s, proces potomny sprawdzający
trwałość do 30 s. Audyt Opus i zamknięcie wykonuje prowadzący.

## Wyniki

| Kontrola | Wynik |
|---|---|
| Domena split v1/v2, adapter, kontrakt policy | 35 PASS; 1 jawnie pominięty zastany test opisany poniżej |
| API learning, worker dataset, admission | 104 PASS |
| Evaluator częściowych kontroli v1/v2, restart i porównanie przypisania | 5 PASS |
| Request klienta: liczniki, gotowość, istniejące trasy | 3 PASS |
| Scoped ruff/format | 28 plików PASS |
| Scoped mypy | 19 modułów produkcyjnych PASS; `follow-imports=silent`, tylko torch pominięty w lokalnej konfiguracji |
| TypeScript admin-api-client | PASS |
| docs:check | PASS: decyzje, okno stanu, budżety, kopie skills |
| Mapa kodu | Zregenerowana |
| PostgreSQL capability i freeze | PASS 52,65 s, w tym świeży interpreter po committed release |

Test PostgreSQL używa disposable database oraz osobnych ról aplikacji i capability.
Sprawdza migrację 0172, odmowę bezpośredniego dostępu runtime do release history
i internal context, preview bez zapisów, atomowy rollback release/freeze, ponowne
zamrożenie, historyczny binding v1 po nowym TRAIN, twarde rezerwy v2, rzeczywiste
użycie kopii i ponowny odczyt po połączeniu. Świeży interpreter otrzymuje hasło
wyłącznie przez środowisko i w transakcji READ ONLY sprawdza rolę TRAIN oraz
waliduje obie kohorty dwukrotnie.

Końcowe uruchomienie przechodzi w całości, w tym nowy interpreter z runtime rolą.
Po dopisaniu jawnej odmowy dla sprzecznych lub nieokreślonych ochron komponentu
powtórzono tylko adapter: 7 PASS. Ostatnia korekta formatu nie zmienia zachowania.

Testy workera parametryzują oba identyfikatory polityki. Nowa polityka obsługuje
częściowe VALIDATION/REGRESSION bez utraty etykiet, odrzuca screen+grid, wybiera
istniejący preset korekt i przechodzi pełny raport oceny oraz wznowienie bez GPU.
Regresja adaptera pokazuje, że zmiana statusu pending rezerwy blokuje nowe freeze,
ale nie historyczną walidację populacji.

## Odstępstwa i wcześniejsze wyniki

### Jedna runda poprawek po audycie R1

P1-1: downgrade 0172 odmawia tylko przy historii zwolnień albo rezerwacjach
`incremental-v2`. Pusta historia pozwala przywrócić oryginalne funkcje 0171,
usunąć dodatki 0172 i ponownie wykonać upgrade. Readiness wymaga teraz dokładnie
0172; test wykrywa rozjazd stałej z rzeczywistym head Alembic.

P1-2: test capability obejmuje siedem rzeczywistych konfiguracji SQL: holdout,
ancestor, use, role head, użycie innego zdjęcia z połączonej sesji, sprzeczne role
oraz ochronę bez roli. Register odmawia jako `RECORDING_ROLE_CONFLICT`, nie
zapisuje zwolnień i zachowuje proof. Adapter odmawia niejednoznacznego kontekstu
jako `GRID_CORRECTION_PROTECTION_CONFLICT`; to dwa różne istniejące poziomy kontraktu.

P2-1: API_CONTRACT opisuje konieczność nowego preview dla niezamrożonych draftów
v1 sprzed 0172. Adapter v1 nie dołącza nowych identyfikatorów aliasów do solvera.
P2-2: rezerwa liczy tylko pending; pozostałe chronione zdjęcia bez etykiet mają
powód `GRID_CORRECTION_CONTROL_NOT_PENDING`. Użycie TRAIN oznacza zapis w zamrożonej
kohorcie, nie zakończenie treningu. Zmieniony reprezentant identycznej kopii
rozpoznaje ten sam target po pikselach, pozycji i węzłach. Rewizja własnego źródła
nadal musi zgadzać się dokładnie. P2-3: aliasComponentIds są nieprzezroczystymi
skrótami komponentu. P2-4: odległości dla przyszłej rezerwy są liczone liniowo;
test 1250 oczekujących zdjęć mieści się w 10000 kroków i zachowuje wybór oraz
deterministyczność. P2-5: wyjątek historycznej roli unused wymaga dokładnego
zapisanego zwolnienia danego członka; konflikt ochrony bez release nadal odmawia.

Kontrole po poprawkach (logi `artifacts/task1139-r1-*.log`):

- Domena v1/v2, adapter, readiness: 54 PASS, w tym odrzucenie operatora 0171
  i równość numeryczna węzłów kopii (int/float/ujemne zero).
  Scoped mypy: 20 modułów PASS.
- Guarded migration: 1 PASS, 26,14 s; oba rodzaje historii blokują downgrade.
- Końcowy registry lifecycle: 1 PASS, 45,83 s, w tym siedem ochron SQL,
  metadane zmienionego reprezentanta kopii, rollback i świeży interpreter.
- Scoped ruff/format: 32 pliki PASS. Mapa kodu ponownie zregenerowana.
- Istniejący recording migration lifecycle: 5 PASS, 82,73 s.
- Istniejące source crop runs: 4 PASS, 70,36 s.
- Istniejący evaluation bridge: 1 PASS, 37,02 s.
- Reinference: 6 PASS, następnie FAIL `cleanup_reset` przez istniejący FK RESTRICT
  przy usuwaniu review items. Zakończenie po 111,76 s; nie zmieniano reset_game.
- Reinference stats: timeout 120 s, bez deklaracji PASS. Proces nie pozostał;
  odczyt potwierdził brak testowej bazy i połączeń. Własne pozostałe role usunięto
  po weryfikacji dokładnych OID, znaczników capability i braku zależności.
  Dowody: `task1139-r1-timeout-inspection.log`, `task1139-r1-timeout-cleanup.log`.

Nie powtarzano całych plików reinference po tych wynikach. Wymagany cykl
head → downgrade → upgrade jest niezależnie zielony w testach migracji i lifecycle.
Końcowa READ ONLY symulacja używa obu pól etykiet tak jak SQL v2 i nadal daje
TRAIN 146 plansz = 77 zapisanych wcześniej + 69 nowych, bez rezerw pending.

`test_shared_candidate_rejects_correction_policy_before_creating_plan` zakłada
odrzucenie polityki korekt przed przygotowaniem planu, choć przyjęty wcześniej
workflow już ją obsługuje. Test ustawia `session_factory=None` i kończy się
`TypeError: 'NoneType' object is not callable`. Odtworzenie modułu
`application/shared_grid_model_candidate.py` z HEAD v1.7.536 oraz starej stałej
polityki w świeżym procesie dało identyczny wynik na linii 96. Pozostawiono poza
zmianą. Skrypt dowodowy: `artifacts/task1139-baseline.py`.

Pierwsze uruchomienia ujawniły stare fixture bez nowego pola lub argumentu;
uzupełniono je zgodnie z addytywnym kontraktem. Początkowe błędy TEMP i pięć
FileNotFoundError w evaluatorze wynikały z ograniczeń katalogu i MAX_PATH Windows.
Końcowe testy używają unikalnego krótkiego katalogu pod `.tmp/t1139`; kod produktu
nie otrzymał obejścia ani osłabienia asercji.

## Odczyt operatora

`GRID_CORRECTION_GROWTH_SIMULATION_20261103.json` dokumentuje READ ONLY symulację
nowej domeny i istniejącego czytnika etykiet przed migracją operatora. Registry v2
zasymulowano z istniejących użyć v1 po sprawdzeniu braku recording_occurrences.
Wynik: TRAIN 98 zdjęć/146 plansz (nowe 38/69), VALIDATION 13/17, REGRESSION 13/21,
bufory 53 zdjęcia/12 plansz, wykluczenia 9/12, rezerwy 0/0. Brak bezpiecznej rezerwy
nie blokuje istniejących kontroli. To nie jest trening ani nowy wynik jakości.

## Odbiór

Focused R2 Opus 5.5/high: PASS. P1-1/P1-2 i P2-1–P2-5 zamknięte; raporty R1 i R2 zachowano osobno. P2-6 przyjęto jako ograniczenie szerszej weryfikacji: nie wykonano świeżego baseline cleanup_reset na HEAD v536 ani pełnego stats. Dokładny błąd DELETE image_review_items przed image_symbol_review_cells jest zapisany w `V3_GRID_FINE_TUNING_ACCEPTANCE.md:101–107` jako wcześniejszy FAIL. Nie oznacza to PASS obecnego testu.

P2-7 doprecyzowano w API_CONTRACT: nieokreślona ochrona holdout/ancestor/use powoduje bezpieczną odmowę nowego dowodu także dla kohort v1. Historia nie jest przepisywana. Na źródłach Mumie A2 nie stwierdzono recording_occurrences.

Wymagania planu: przyrost nieużytej rezerwacji, brak przenoszenia rzeczywistych
kontroli, historia, kopie/sesje, bufory, atesty, minima, brak kolejności, atomowość,
replay i read-only preview są pokryte domeną i testem capability. Kontrakt liczników
przechodzi backend → OpenAPI → klient → request. UI należy do TASK-1140.
Migracja 0172 i restart operatora pozostają wymagane przed użyciem nowej polityki
na danych rzeczywistych. Nie wykonano pełnych testów całego repo ani treningu GPU.
