---
title: V3 import presentation and initial application review
status: accepted
last_updated: 2026-10-06
---

# V3 import presentation and initial application review

## Stan obecny i cel

Mumie mają profil grid_profile_mumie_v1 i aktywny import neuronowy D-523.
Panel pokazuje wyłącznie stare radio V1.0/V1.1/V1.2. API normalizuje V1.1
do ścieżki sieci; to nie jest dowód użycia klasycznego silnika w Mumii.
Cel: poprawić wybór i opis faktycznie wykonywanego silnika oraz dać
operatorowi instrukcję i powierzchowny rejestr przyszłych zmian.

## Zakres i reguły

- TASK-0887 wykonuje wyłącznie prezentację/importowe argumenty istniejącego
  kontraktu i dokumentację. Polecenie użytkownika obejmuje tę odwracalną zmianę.
- Profil gry jest źródłem informacji o V3; strukturalna polityka magazynu
  nie zastępuje profilu. CatalogWorkspace przekazuje istniejące pole gry.
- Mumie: widoczny V3 i brak argumentu klasycznego wariantu. Inne gry:
  V1.1; 777 zachowuje dotychczasowe wykonanie.
- V1.0/V1.2 znikają z wyboru nowych przebiegów, dostają informację o
  wycofaniu. Przypięta wersja historycznego raportu i ponowienie pozostają.
- Pełne cropy D-523, kolejka korekty i zbiorcza weryfikacja bez zmian logiki.
- Usunięcia, przesunięcia sekcji i osobny panel online trafiają do roboczego
  rejestru, bez implementacji. Dane mają tylko podgląd zajętości.

## Wykonanie TASK-0887

1. Przekazać opcjonalny profil gry do ImageFolderImportPanel. Wybrać V3
   tylko dla obsługiwanej konfiguracji Mumii, bez nowego endpointu.
2. Usunąć stare opcje z widoku, zachować kod historycznych odczytów, poprawić
   opis raportu/startu i nie pokazywać Mumii akcji „Przetwórz w v1.1”.
3. Dodać regresje interakcji V3, V1.1 oraz historycznego raportu; sprawdzić
   jawność startu i działanie po świeżym montowaniu.
4. Rozwinąć instrukcję operatorską o dokładne etapy i trening. Utworzyć
   APP_V3_FUNCTIONAL_INVENTORY.md: bieżący ekran, potrzebna funkcja,
   proponowana zmiana, status i przyszły odnośnik do osobnego taska.
5. Zmierzyć katalog bazy, rozmiary baz testowych i wolne miejsce; opisać
   kandydatów bez usuwania, VACUUM lub kopii całej bazy.

## Odbiór, ryzyka i granice

TASK-0887 ukończony: testy jednostkowe66, interakcji8, typy, lint,
format i build PASS. Świeży MAIN ekran oraz przeładowanie potwierdziły V3;
rzeczywisty ekran 777 zachował V1.1. Podgląd bazy jest tylko odczytem.
Instrukcja i roboczy rejestr ekranów są zapisane; pozostałe funkcje pozostają.

Przypadki TASK-0887 odpowiadają każdemu wymaganiu zmiany. Odbiór obejmuje
testy interakcji, lint, typecheck i świeży MAIN ekran. Nie uruchamiać realnego
uploadu wyłącznie dla testu UI. Brak modelu nadal blokuje właściwy etap przez
API. Nie obiecywać automatycznego uczenia sieci cięcia: obecny przycisk
kalibracji jej nie trenuje. Nie usuwać historii ani pracy człowieka.
Faktyczne wyniki wpisać w Outcome po testach, osobny commit v1.7.229.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0887 | gpt-6.1-sol | high | Mała zmiana UI, ochrona przypiętych raportów i analiza retencji. | Review własny z regresją V1.1; bez delegowania. |
