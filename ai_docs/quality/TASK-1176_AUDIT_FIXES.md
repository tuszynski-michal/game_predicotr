---
title: TASK-1176 — Jedna runda poprawek po Opus R1
status: accepted
last_updated: 2026-11-09
---

# Poprawki do skupionego R2

Oryginał audytu: [Opus R1](TASK-1176_AUDIT_R1_claude-opus-5-5.md),
z zachowanym receipt i SHA pakietu4004b2b8…. Poniższe punkty są odpowiedzią
wykonawcy, nie niezależnym zamknięciem znalezisk. Werdykt R1 pozostaje REVISE.
Kontrolny [audyt R2](TASK-1176_AUDIT_claude-opus-5-5.md) zakończył się PASS,
zamykając P0-1/P1-1 i P2-1…4. Nowe P2-5/P2-6 przyjęto w Outcome taska.

- P0-1: `storage/grid_reinference.prepare` wyznacza politykę przez
  `acceptance_for_operation_pin`, oddzielnie zapisuje ten sam wynik w jobie,
  sygnaturze i dokumencie. Publiczna historyczna stała wróciła do v4.
  `operation_pin_blockers` oraz storage `recheck_operation_pin` odrzucają
  cel review z pinem innym niżv4. Ostatni guard jest pierwszą kontrolą
  `save_automatic_reinference_source`, przed zapisami; kwalifikacja domenowa
  również jawnie zwraca POLICY_MISMATCH. Nie ma obniżania v3→review.
- P1-1: dodano test realnego przygotowania z zakwalifikowanym pinemv3.
  Potwierdza politykęv4, identyczny pin, przekazanie `calibration_pin` do
  inferencji i obecność `calibrationPin` w rzeczywistym checkpoincie.
  Usunięcie dowodu wyniku daje COMPLETENESS_EVIDENCE_REQUIRED.
  Cały moduł testowy reinferencji wykonano w rozłącznych grupach (limit120s).
  Atrapa przyjmuje aktualny `operation_pin`, przypina executionPolicy review
  i symuluje pełne zdjęcie także przy jednym chronionym sąsiedzie.
  Fixture częściowego importu jawnie przypina historycznąv1; v2 poprawnie
  nie dopuszcza niekompletnego wiązania. Nie zmniejszono asercji wyników.
  Wyniki, w tym zastane błędy i dowody main, podaje raport weryfikacji.
- P2-1: brak recheck (`None`) oraz UNCHECKED blokują review. Nie są
  zwalniane razem z samym brakiem dowodu jakości. Testy obu przypadków.
- P2-2: jedna instancja produkcyjnego predyktora/cache ONNX na handler,
  współdzielona między jego zdjęciami. Predykcja pozostaje w transakcji
  odczytu; zapis ma osobną transakcję z aktualnymi fences. Nie deklarujemy
  benchmarku691 zdjęć. Pomiar czasu i ewentualnych blokad na rzeczywistym
  pilocie pozostaje elementem wdrożenia; nie uruchomiono operatorowej partii.
- P2-3: skrócono historyczny stan raportu i zaktualizowano CURRENT_STATE;
  aktualny wynik zastępuje wpis o limicie15min i braku PG.
- P2-4: testy rzeczywistych brakujących pikseli (węzły poza kadrem i partial
  visibility) oraz odrębne testy recheck dla reguł4×5 i obcej gry.

## Granice dowodu

Testy używają kontrolowanych wyników sieci i rzeczywistego zapisu/renderera.
Weryfikują również widoczność pending przez zapytanie używane w weryfikacji
symboli. Nie są dowodem poprawności wszystkich siatek ani zgodą na automat.
Rzeczywiste dane sprawdzono tylko odczytowo. Brak wdrożenia, migracji,
treningu, zmiany defaultu lub zapisu operatora. Po R2 wymagane właściwe
zamknięcie taska i osobna akceptacja integracji oraz operacji.
