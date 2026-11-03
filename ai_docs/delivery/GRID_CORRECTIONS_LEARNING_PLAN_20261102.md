---
title: Ulepszanie wspólnego modelu siatek z korekt
status: accepted
last_updated: 2026-11-02
---

# Ulepszanie wspólnego modelu siatek — rewizja po drugim audycie

## Zgoda i zakres

Operator 2026-11-02 zlecił implementację całego planu T1–T4 po ostrzeżeniu
o koszcie. Zgoda obejmuje wykonawców według tabeli i obowiązkowy audyt
Claude Code Opus 5.5/high; operator jawnie pozwolił przekazać plan oraz
niezbędne fragmenty repozytorium do Anthropic. Nie obejmuje rzeczywistego
treningu, zmiany defaultu/przypisań, migracji bazy operatora, restartu usług
ani merge/push. Praca: `codex/grid-corrections-learning`.

2026-11-02, po limicie sesji Anthropic, operator polecił „Kontynuuj a potem
audyt”. T3 można implementować przed ukończeniem audytu T2, w oddzielnym
worktree z dokładną kopią jego stabilnego, niezatwierdzonego kodu. Nie jest
to rezygnacja z audytów: T2 i T3 zachowują osobne przeglądy Opus5.5/high oraz
osobne commity, każdy dopiero po zamknięciu własnych P0/P1. Bazę T2 i różnicę
T3 zachować osobno; ewentualne poprawki T2 integrować przed audytem T3.

Operator poprawia siatki, klika „Ulepsz siatki z korekt”, ogląda wynik
treningu i porównania, osobno zatwierdza „Zastosuj wersję”. Filmy i ręczna
rejestracja nagrań nie są wymagane. Panel podstawowy: model, dostępne
korekty/braki, start, postęp, wynik, zastosowanie, historia. Nagrania,
rodziny, kohorty, parametry i trening wielogrowy: zaawansowane. Kontrola
losowa i ponowne przetwarzanie: osobne narzędzia.

Plan w czacie przeszedł dwa audyty Opus 5.5/high: REVISE; ostatnia wersja
uwzględnia 2 P1 i 4 P2, ale nie ma jeszcze niezależnego PASS. Audyty
implementacji są obowiązkowe przed każdym commitem taska.

## TASK-1120 (T1) — Przygotowanie danych i trwały podział

Przed kodem ograniczony odczyt danych Mumie A2: aktualne human approvals,
24 punkty, zdjęcia/istnienie plików, importy, logiczne nazwy, atesty
zakresów, prior uses i aliasy. Raport liczbowy i sprawdzenie możliwości
podziału. Deklaracja >100 plansz nie dowodzi gotowości. Jeśli podział jest
niemożliwy, zgłosić przed implementacją; nie rozluźniać zasad.

Rozszerzyć rejestr D-554 i `GridCohortEvidenceReader`, bez równoległego
źródła prawdy. Używać aktualnych zatwierdzeń geometrii/24 punktów/rewizji,
nie predykcji ani zatwierdzeń samych symboli. Dołączać wcześniejsze
sprawdzone przykłady bieżącej gry i kwalifikujące dane wspólnej bazy.
Znane sesje i kopie między grami są nierozdzielne. Holdout i controls nie
przechodzą TRAIN; ancestor TRAIN nie jest niezależnym testem potomka.
Nieznane pochodzenie ma jawnie ograniczony poziom dowodu.

Metoda `attested-sequence-order-v1`: parsować logiczne nazwy źródłowe
istniejącym `parse_attested_sequence_range_filename`; wymagać zgodności
z atestami aktualnej geometrii i przypisaniem sequence_number do pozycji.
**Zmiana zatwierdzona przez operatora 2026-11-02 po preflight:** gdy nazwy
źródłowe są zarządzanymi nazwami SHA i pierwotne nazwy seq_ nie są dostępne,
dopuścić same zweryfikowane atesty aktualnej geometrii jako dowód kolejności.
Nadal wymagać poprawnego checksum atestu, zgodności slots/sequence_number,
jednoznacznych niekolidujących zakresów wszystkich źródeł importu oraz ochrony
aliasów/sesji/buforów. Nie rekonstruować fikcyjnej nazwy seq_ jako drugiego
dowodu. Snapshot zapisuje metodę `verified-attestation-order-v1` i ograniczenie
dowodu (brak potwierdzonej niezależności sesji i nieznanego ancestor use).
Jeśli oryginalna nazwa seq_ istnieje i jest sprzeczna z atestem, blokować użycie.
Po złączeniu dokładnych kopii wszystkie źródła importu muszą mieć
jednoznaczne zgodne niekolidujące zakresy. Sortować po początku/końcu.
UUID, ordinal, created_at i sam order_index nie są dowodem kolejności.
Brak wiarygodnej kolejności => cały import nierozdzielną grupą.

Bufor 10 kolejnych źródłowych zdjęć między rolami liczy wszystkie zdjęcia,
także bez etykiet. Snapshot zapisuje metodę, klucze, zakresy i bufory.
Bufory utrwalane przy freeze chronią również następne iteracje; nowe
źródła naruszające ochronę blokują użycie, nie przepisują historii.
Bufor ogranicza podobieństwo, nie dowodzi niezależności sesji.

Cel 70/15/15 po zdjęciach po odjęciu buforów; TRAIN >=30 plansz/10 zdjęć,
VALIDATION i REGRESSION każda >=15 plansz/5 zdjęć (mogą być częściowe).
Utrwalone role/sesje/kopie/bufory mają pierwszeństwo. Z dopuszczalnych
podziałów wybrać minimalne łączne odchylenie od proporcji; remisy stabilnym
porządkiem identyfikatorów grup i granic. Podgląd prowizoryczny, freeze
atomowo utrwala role/bufory. Brak rozwiązania blokuje start z liczbami.
Migracja Alembic; obrazy w plikach, w DB identyfikatory/metadane.

Doprecyzowanie techniczne przyjętego podziału z preflight: uporządkowany import
ma od jednego do trzech kolejnych odcinków, każda rola najwyżej raz. Solver
sprawdza wszystkie permutacje ról i dopuszczalne granice w tej klasie podziałów.
Limit pracy zwraca jawny błąd, nigdy częściowe optimum ani stwierdzenie
matematycznej niemożliwości. Nierozdzielny import stanowi jeden odcinek.

Jawna zależność odbioru T1: adapter rozdziela korekty własnej gry. Dołączenie
kwalifikujących historycznych kohort wspólnej bazy realizuje TASK-1121 w istniejącym
SharedGridCandidateService i readerze workera, z zachowaniem ról, aliasów, ancestry
i aktualności każdej gry. Ten punkt nie jest zakończony przez sam split T1; do czasu
pełnego konsumenta API blokuje nową politykę przed utworzeniem joba treningowego.

## TASK-1121 (T2) — Trening i ocena częściowych zdjęć

Nowa polityka kohort/snapshot, raport v3, `grid-model-per-game-gate-v2`.
Starsze formaty zachowują semantykę. Aktualizacja D-549/554/556/559 nową
decyzją, bez przepisywania historii.

Częściowe VALIDATION i REGRESSION grid-only przechodzą cały pion:
capture.used/reasons, role_summary/minima, materializacja/manifest/freeze,
aktualność, GridBoardDataset._sources/counts, CohortPhotos, wejście
walidacyjne także joint, worker obu ról i reader raportu. Screen+grid
i stare polityki zachowują full-only. Bez cichego odfiltrowania źródeł.

Przypiąć globalny default i artefakty; readiness sprawdza training-base,
runtime, worker GPU i budżet. Przekroczenie budżetu blokuje, bez shrink.
Wykorzystać grid-only/frozen detector, wagi 4:1, GPU lane/checkpointy.
Trwały parent workflow automatyzuje strony, file checks, freeze, trening,
ocenę. Restart/retry nie duplikuje runu/kandydata ani budżetu.

Checkpoint: maksymalny udział board_correct na VALIDATION, przy remisie
minimalny średni znormalizowany błąd, dalej wcześniejszy krok. Agregacja
po zdjęciach, joint z równą wagą gier. Zapisać regułę, metryki i early
stopping w checkpoint/raporcie. REGRESSION nie wybiera checkpointu.

Base/candidate na tych samych oryginałach. Reuse jednoznacznego matching
metrics-v1; jedno prediction nie obsługuje dwóch targets. Board error:
średnia odległość 24 punktów / przekątna obwiedni GT; clamp do 1, missing=1;
agregacja po planszach zdjęcia, potem zdjęciach. Partial => tylko labeled
targets, bez deklaracji photo-complete/false positives na unlabeled.
Full => dodatkowo non-regression false/duplicate i complete-correct.
Każda wymagana gra/rola: brak spadku detected/correct i wzrostu błędu
(epsilon 1e-9). Bieżąca gra REGRESSION: +>=1 correct board albo spadek
błędu >=5% względnie i >=0,001 bezwzględnie. Inne gry: non-regression.
Progi produktowe, nie deklaracja istotności statystycznej.

Scope: current game + wszystkie gry TRAIN + zweryfikowany scope poprzedniego
defaultu. Legacy scope tylko jawne game IDs z verified report/publication;
brak => historyczny scope nieudokumentowany. Utrata wymaganych danych blokuje.
Zaawansowane wyłączenie gry: preview/powód/confirmation, historia/holdouty
zostają, exclusion w nowym raporcie, gra nie przełączana. Inne untested gry
nie blokują nowego defaultu, bez automatycznej aktywacji. Spójnie zmienić
create-evaluation/family guard/readers/publish/activate/default.

## TASK-1122 (T3) — Panel i zastosowanie

API gotowość/preview/start/status/cancel/resume/report/apply z pełnym pionem
backend/OpenAPI/generated-client/wrapper/request-test. GET-only on entry.
Run/cohort/report wiązane automatycznie. Pokazać coverage/liczniki/evidence.
Photo-only PASS wymaga ręcznego potwierdzenia ograniczenia przy apply.
Domyślnie default+current, inne gry opt-in z oceną. Game assigned != default:
non-regression również względem assigned. Concurrent default => nowy preview.
Trwałe idempotentne publish/assignment ze stanem każdego kroku i resume po
partial success. History/rollback; bez recropu wcześniejszych importów.

## TASK-1123 (T4) — Odbiór i dokumentacja

Testy: old approvals bez resave; same partial validation/regression end-to-end
z count parity; UUID/order/timestamps nie dowodzą chronologii; attestation
conflict => indivisible; buffer na wszystkich źródłach trwa przy nowych runach;
session/alias/prior-use bez przecieku; preview nie utrwala, freeze atomowy;
checkpoint/restart deterministic; validation-only improvement nie daje PASS;
regression dowolnej wymaganej gry/false detections blokuje; legacy scope bez
fikcyjnej wiedzy; narrowing audytowalny; retry bez duplicates; legacy contracts;
new import pins version, manual history unchanged.

Testy domeny/Postgres/workera/UI, lint/typecheck/build/docs:check/code-map:check.
Out of scope: symbol classifier, automatic full-screen detector training.
Każdy task: dokumentacja/Outcome, audyt, task-close, osobny wersjonowany commit
i record-hash. Numery wersji z git log. Migracje operatora/trening/restarty/
main integration mają osobne zgody. Nie ingerować w pozostałe worktrees.

## Wynik realizacji 2026-11-02

T1–T4 zaimplementowane i ocenione przez Claude Code Opus 5.5/high: wszystkie
cztery taski otrzymały PASS bez otwartych P0/P1. T1: v1.7.517, T2: v1.7.518,
T3: v1.7.519, T4: v1.7.520. Nie jest to deklaracja wzrostu jakości
modelu operatora — rzeczywisty trening i porównanie wymagają uruchomienia.

Pokrycie wymagań, wyniki i ograniczenia:
[raport odbioru](../quality/GRID_CORRECTIONS_LEARNING_ACCEPTANCE_20261102.md).
Pełny projektowy mypy nie ma PASS (limit czasu); scoped checks zmienionych części
przeszły. Akceptowalne ryzyko P2 według audytu T4, dalszy pełny baseline wymaga
osobnego, uzgodnionego limitu. Migracje operatora 0170/0171, integracja/push,
restarty usług, trening i zmiany defaultu pozostają niewykonane i wymagają
właściwych zgód. Historia pierwotnego planu i audytów została zachowana.

## Wdrożenie zaakceptowane 2026-11-02

Po osobnej zgodzie operatora kod scalono fast-forward do main i wypchnięto do
origin (74bfd2490286d386d9fe272567bb2b07d36be581). Baza operatora jest na 0171;
API, Admin oraz general/grid-training działają. Ręczne korekty i przypisania
zachowane, HTTP i rzeczywisty panel sprawdzone, trening nie był uruchamiany.
Szczegóły i ograniczenia w raporcie odbioru. Końcowy zapis operacyjny ma osobny
commit dokumentacyjny; nie zmienia kodu ocenionego czterema audytami.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1120 (T1) | gpt-6-astra | high | Dane, kolejność i trwałe zabezpieczenia | Obowiązkowy: Claude Code claude-opus-5-5/high, przed commitem |
| TASK-1121 (T2) | gpt-6-astra | high | Trening, metryki i publikacja | Obowiązkowy: Claude Code claude-opus-5-5/high, przed commitem |
| TASK-1122 (T3) | gpt-6.1-sol | high | UI i trwałe polecenia | Obowiązkowy: Claude Code claude-opus-5-5/high, przed commitem |
| TASK-1123 (T4) | gpt-6.1-sol | high | Pełny odbiór i historia | Obowiązkowy: Claude Code claude-opus-5-5/high, przed commitem |
