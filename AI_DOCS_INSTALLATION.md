# Instalacja pakietu dokumentacji

Pakiet jest przygotowany do rozpakowania w katalogu głównym istniejącego repozytorium.

Po skopiowaniu repozytorium powinno zawierać co najmniej:

```text
AGENTS.md
AI_DOCS_INSTALLATION.md
ai_docs/
```

## Zalecany sposób użycia

1. Rozpakuj archiwum do katalogu głównego repozytorium.
2. Przejrzyj `ai_docs/project/OPEN_QUESTIONS.md`.
3. Uzupełnij odpowiedzi w `ai_docs/tasks/0001-architecture-clarification.md`.
4. Zmień status zaakceptowanych decyzji w `ai_docs/process/DECISION_LOG.md`.
5. Dopiero potem zleć Codexowi inicjalizację projektu według `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`.

## Pierwszy prompt dla Codex

```text
Przeczytaj AGENTS.md oraz dokumenty wskazane w ai_docs/tasks/0001-architecture-clarification.md.
Nie twórz jeszcze kodu. Przeanalizuj odpowiedzi na pytania, wskaż sprzeczności i zaproponuj aktualizacje dokumentacji oraz decyzji architektonicznych.
```

Po zamknięciu pytań:

```text
Przeczytaj AGENTS.md, ai_docs/process/CURRENT_STATE.md,
ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md oraz
ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md.
Utwórz wyłącznie pierwsze zadanie wskazane w planie i nie rozpoczynaj kolejnego
podetapu przed przejściem jego bramki jakości.
```
