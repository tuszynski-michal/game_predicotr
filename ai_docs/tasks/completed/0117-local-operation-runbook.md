---
title: Local operation runbook
status: done
last_updated: 2026-07-30
---

# TASK-0117 — Local operation runbook

## Status

`done`

## Goal

Przygotować jedną, zweryfikowaną instrukcję dla właściciela projektu opisującą
uruchamianie panelu Admin, API, workera i aplikacji Reviewer oraz budowanie,
instalowanie, aktualizowanie i uruchamianie aplikacji mobilnej na Google Pixel
10 Pro XL.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MOBILE_APP.md`

## Scope

- opisać jednorazowe przygotowanie Windows i kontrolę toolchainu,
- opisać kolejność uruchamiania PostgreSQL, migracji, API, panelu i workera,
- opisać lokalną sesję Reviewera, link i kod,
- opisać build, audyt, instalację i aktualizację APK przez ADB,
- dodać bezpieczne instrukcje zatrzymywania usług i rozwiązywania typowych
  problemów,
- statycznie zweryfikować każdą nazwę komendy i istotną ścieżkę.

## Out of scope

- wykonywanie pełnego builda Android,
- instalacja APK i ręczny test na Pixelu,
- udostępnienie Reviewera przez Internet,
- reset lub usunięcie danych PostgreSQL.

## Acceptance criteria

- [x] instrukcja prowadzi od nowego PowerShell do działającego panelu Admin,
- [x] instrukcja prowadzi do lokalnego Reviewera z linkiem i kodem,
- [x] instrukcja rozróżnia pierwszą instalację APK od aktualizacji,
- [x] wskazuje, kiedy potrzebny jest nowy build APK, a kiedy wystarczy
  odświeżenie przeglądarki,
- [x] nie sugeruje wystawiania niezabezpieczonych portów do Internetu,
- [x] wszystkie komendy i ścieżki istnieją w repozytorium,
- [x] dokument jest podlinkowany z indeksu dokumentacji.

## Verification

```powershell
npm run windows:environment:check
```

Ponadto wykonać statyczny audyt skryptów `package.json`, parametrów PowerShell,
portów, ścieżek APK i linków Markdown. Pełne uruchomienie usług oraz test
telefonu są odłożone zgodnie z decyzją właściciela.

## Outcome

- Utworzono jeden przewodnik `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` z krótką
  procedurą codziennego startu i pełnymi instrukcjami dla Windows, Admina,
  workera, Reviewera oraz Androida.
- Opisano minimalny workflow sekcji Admina, generowanie lokalnego linku i kodu
  Reviewera, różnicę między bieżącym snapshotem a wydaniem z panelu oraz
  pierwszą instalację i aktualizację APK na Pixelu.
- Dodano kontrolowany powrót do testów urządzenia przez
  `android:device:accept`, procedurę offline, bezpieczne zatrzymywanie usług i
  diagnostykę typowych błędów.
- `windows:environment:check` przeszedł dla Node `24.14.0`, npm `11.18.0`, JDK
  `17.0.20`, ADB `1.0.41` i lokalnego SDK. Audyt potwierdził wszystkie 15
  użytych skryptów npm, 8 istotnych ścieżek, parametry builda/audytu urządzenia
  oraz porty loopback `3000`, `3001` i `8000`.
- Zgodnie z decyzją właściciela nie uruchamiano usług, builda Gradle,
  instalacji APK ani ręcznych scenariuszy na Pixelu.
