# TASK-1152 — Zachowanie postępu między etapami zastosowania modelu

## Status

`done`

## Goal

Wznowione zastosowanie modelu kończy publish/default/activate bez regresji zapisanych liczników.

## Context

Jawne polecenie operatora zastosowania PASS jako default i dla MumieA2 utworzyło apply a2eeba17-405a-42d1-952f-1a469a1fcfce. Publish zakończone, kolejny lease odrzuca success_count0 wobec1 z JOB_PROGRESS_REGRESSION. Default/przypisanie niezmienione. Nie ponawiać startu ani nie zmieniać SQL/statusu ręcznie.

## Recommended execution

gpt-6-astra/high, lokalna mechaniczna poprawka. Jeden claude-opus-5-5/high przed commitem.

## Relevant docs

- AGENTS.md; process/DEFINITION_OF_DONE.md.
- requirements/VISION_LAB.md: Correction learning and scoped evaluation.
- architecture/VISION_LAB.md: Explicit correction apply.
- domain/jobs.py: monotonic progress and lease checks.

## Scope

Istniejący handler zachowuje zapisane success/failure/review counters na wejściu nowego lease. Końcowy sukces nadal pochodzi z ukończonych steps, failure/review pozostają zachowane. Nie zmieniać guardów domenowych, receiptów, identyfikatorów, CAS ani publikacji. Test wykorzysta prawdziwy checkpoint_job i nowy handler/context między etapami, także waiting/comparison i failure/resume.

## Expected files

services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py; services/worker/tests/test_grid_correction_apply_handler.py; architecture/VISION_LAB.md; dokumentacja taska/planu/mapa.

## Acceptance criteria

- [x] Regresja odtworzona rzeczywistą walidacją domeny, test czerwony przed poprawką.
- [x] Trzy etapy i ponowne waiting zachowują monotoniczne liczniki po odtworzeniu kontekstu.
- [x] Lint/types, właściwe regresje, docs/map i Opus bezP0/P1.
- [x] Osobny commit task-close; wdrożenie i restart general worker dopiero po osobnej zgodzie.

## Risks / open questions

Przed wdrożeniem wymagano osobnej zgody na merge/push i restart wyłącznie general worker. Operator następnie ją wyraził; wykonanie i końcowe potwierdzenie opisano w ostatniej sekcji. Zachowano to samo apply i receipt publikacji.

## Outcome

Commit: v1.7.553 / `5a9fcb148920fe1c702568cc94e58159d7babc4b`.

### Changed

Handler zachowuje success/failure/review counts między lease. Finalny success nadal wynika wyłącznie z ukończonych etapów. Nie zmieniono guardów domeny, receiptów, API ani CAS.

### Verification results

Nowe testy na starym kodzie: 3FAIL/3PASS, wszystkie z prawdziwego checkpoint_job/JOB_PROGRESS_REGRESSION. Po poprawce worker apply/learning8PASS i domenowe progress4PASS. Test przechodzi przez3etapy na nowych handlerach/kontekstach, JSONrestored checkpoint, rzeczywiste requeue_job po failed, zachowuje ID/receipts. Osobno2waiting ze stałymi licznikami i niezerowe failure/review. Ruff format/check PASS. Logi w root artifacts/grid-applied-comparison-20261103/task1152-*.log. Scoped mypy produkcyjnego handlera PASS (1moduł; project config z tylko torch skip, follow-imports=silent), mapa odnowiona. Opus przed commitem; operacja operatora wciąż failed po publish, default/przypisanie stare.

### Not completed

Brak pozostałych kroków wdrożenia i zastosowania po późniejszej zgodzie operatora. Wizualny podgląd HTML w przeglądarce agenta niedostępny przez blokadę protokołu file; plik, dane, interakcje i obrazy zweryfikowane statycznie.


### Audit and final verification

Rzeczywisty Claude Code claude-opus-5-5/high R1: PASS bezP0/P1. Raport quality/TASK-1152_AUDIT_claude-opus-5-5.md. Jedna runda poprawekP2: P2-1 test używa teraz rzeczywistych defer_job_for_dependency/start_job/fail_job/requeue_job zamiast podmieniania stanu; P2-2 parametryzacja obejmuje comparison waiting i prawdziwyUUID waitingForJobId; P2-3 poprawiono link i pozycję planu w DOC_INDEX/Dostarczanie. Produkcyjny kod po audycie bez zmian, bez kolejnego audytu. Worker apply/learning po rozszerzeniu10PASS; domain progress4PASS; ruff i scoped mypy1moduł PASS. Mapa i docs przed i po domknięciu sprawdzane osobno.

Naprawa gotowa do zatwierdzenia jako konkretny diff/commit. API i Admin nie wymagają restartu; po zgodzie trzeba scalić/push i zrestartować tylko general worker, następnie oficjalne resume tego samego apply a2eeba17. Bez nowego treningu, bez resetu danych/stanów i bez ponawiania publish. Runtime potwierdzenie zależy od tej osobnej zgody; nie zgłaszamy zastosowania modelu jako wykonanego.


### Operator deployment and final apply acceptance

Operator po zapoznaniu się z commitem/audytem osobno zatwierdził merge/push i restart tylko general worker. Wykonano preflight bez kolizji/migracji, stopgeneral, fast-forwardmain do7ebbc3a5, startgeneral7 (worker37496) i push. Nie zatrzymywano API/Admin/GPU. Oficjalne resume tego samego applya2eeba17-405a-42d1-952f-1a469a1fcfce zakończyło się13:55:53UTC completed, bez błędu; publish/default/activate completed. Istniejący receipt publikacji identyczny po wznowieniu, lista zawiera jedną operację. W nowym procesie GET default i assignment potwierdziły revision2 i version3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e. Wersja wspólna i MumieA2 rzeczywiście zastosowane, bez nowego treningu.

Dodatkowo wykonano plikowe porównanie oryginałów dla aktualnej kolejki:151plansz/102zdjęcia, oba modele odczytały wszystkie obrazy,151par,145zmian≥1px, mediana1,824px. Kolejka/revision/checksum geometrii po porównaniu identyczne. Żadne źródło raportu nie jest TRAIN tego runa (sprawdzone na checksummed frozen snapshot); nie dowodzi to niezależności sesji ani braku użycia przez starsze modele. Bez zatwierdzonych punktów tych151plansz nie znamy ich trafności; raport nie nazywa zmiany poprawą. Formalny test na opisanych kontrolach pozostaje15→17/21 i błąd -18,15%.

HTML: root artifacts/grid-applied-comparison-20261103/comparison.html. Statyczna weryfikacja151unikalnychplansz,102zdjęć,13stron, search/filter/pagination/toggle,topologia3x5,24punkty i wszystkie obrazy PASS. Podglądu browserowego nie wykonano: wbudowana przeglądarka odrzuca protokółfile; nie obchodzono tej blokady. Dowody zastosowania: apply-final.json, apply-before-resume.json, apply-resume-afterfix-response.json; porównania: inputs.json, comparison-data.json, verification.json i logi obu modeli.

Końcowy podgląd aktualizuje snapshot do150plansz/101zdjęć: podczas pracy kolejka zmniejszyła się o jedną pozycję. Początkowe151 zachowane w inputs-initial-151.json. Pozostałe150ma identyczne rewizje/checksum geometrii i te same oryginalne piksele, więc wykorzystano ich wcześniej obliczone wyniki obu modeli, bez kolejnego uruchomienia. HTML150unikalnychplansz/101zdjęć ponownie przeszedł statyczne kontrole. Zestaw jest datowanym snapshotem; operator może dalej zmieniać kolejkę.
