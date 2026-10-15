---
title: Nagrania źródłowe geometrii V3
status: active
---

# Nagrania źródłowe geometrii V3

TASK-1002 udostępnia deklaracje nagrań i prowizoryczną kwalifikację. Nie uruchamia
treningu, nie publikuje modelu i nie zmienia domyślnego przypisania. Chronione
źródła laboratoryjne wymagają osobnej instalacji zaufanych metadanych.

## Wdrożenie

Obecny profil migracji0161 wymaga połączenia Alembic z uprawnieniami
superuser (jak w lokalnym compose i sprawdzonych fixture). Sam właściciel
schematu bez tych uprawnień nie jest obsługiwany: transfer własności przy
upgrade i kontrola prywatnych tabel przy downgrade mogą zakończyć się42501.
To konto wdrożeniowe; API nadal używa ograniczonej roli runtime, bez fallbacku.

Zmian na bazie operatora agent nie wykonuje. Administrator najpierw uruchamia
`scripts/provision_database_roles.py --recording-capability` z właściwymi
konfiguracjami runtime/owner tej samej bazy. Flaga ta obsługuje wyłącznie
capability; z `--check` tylko sprawdza jej tożsamość i atrybuty. Dopiero potem
wykonuje migrację Alembic 0161, a po niej domyślny provisioning roli aplikacji.
Kanoniczne `npm run db:migrate` zachowuje tę kolejność: capability → Alembic →
runtime grants. Skrypt `db:reset:local` zachowuje ją po odtworzeniu schematu;
jego wykonanie usuwa dane i nadal wymaga osobnej jawnej zgody oraz ConfirmReset.
Migracja nie tworzy roli klastra. Brak poprawnej roli blokuje
wdrożenie; uprawnień owner nie stosuje się jako zastępstwa w API.

Rola capability ma tożsamość przypisaną do nazwy i OID bazy. Jej znacznik zawiera
własny nonce/OID. Nie wolno kopiować roli testowej do innej bazy. Ponowne
provisionowanie odtwarza dokładne wyjątki rejestru po ogólnych grantach,
zachowując zwykły CRUD aplikacji. `--check` sprawdza zgodność bez napraw.
Downgrade jest dozwolony wyłącznie dla całkowicie pustych pięciu tabel rejestru.
Jakikolwiek wiersz, także receipt lub provisional evidence, blokuje downgrade.
Pusty downgrade usuwa tylko dokładne obiekty1002 i odtwarza manifestv13;
zostawia rolę klastra oraz obce obiekty i granty.

Restore, rename lub clone zmienia nazwę/OID bazy i pozostawia obiekty należące
do starej capability. Zwykły reprovision nie przenosi tej własności. Wdrożenie
pozostaje wtedy zablokowane; repozytorium nie dostarcza narzędzia re-own.
Nie należy obchodzić tego konta owner w runtime ani nadawać membershipu.
Przyszła jawna naprawa własności wymaga osobnego rozwiązania i weryfikacji.

`scripts/install_recording_provider.py` instaluje przypięty SHA artefakt
przodka. `scripts/import_recording_lab_provider.py` obsługuje jawny import
deskryptora laboratoryjnego i stron metadanych do 200 źródeł. Są to jednorazowe
operacje wdrożeniowe administratora, a nie czynności wykonywane dla każdej
kohorty. Pomoc obu komend opisuje wymagane argumenty. Instalacja sprawdza SHA
provider/descriptor/split/stron i zapisuje prywatne dowody przed publikacją
indeksu. Wznowienie używa tych samych danych i potwierdzeń; nie tworzy nowego
użycia źródła. Do bazy nie trafiają ścieżki, obrazy, etykiety ani komentarze.

Po instalacji administrator zapisuje zwrócony
`GAME_PREDICTOR_RECORDING_PROVIDER_INDEX_SHA256` w trwałej konfiguracji API.
Zmiana konfiguracji wymaga restartu API wykonanego przez operatora. Brak
konfiguracji lub mapowania daje widoczne UNRESOLVED. Sam wpis pliku bez
zgodnego prywatnego dowodu instalacji nie pozwala zamrozić kwalifikacji.

## Praca w aplikacji

W obszarze jakości modelu wybierz import według opisu, daty i liczby zdjęć.
Jedna akcja rejestruje nagranie stronami do 200 elementów. Przerwanie zatrzymuje
się między stronami. Po odświeżeniu aplikacja tylko odczytuje stan; wznowienie
wymaga jawnego przycisku i korzysta z potwierdzonej przez serwer kolejnej strony.
Szczegóły techniczne, identyfikatory i hashe znajdują się w rozwijanej sekcji.
Lista importów ma obecny limit 200 pozycji; panel informuje o tym ograniczeniu.

Potwierdź niezależność całego nagrania i przypisz rolę dla wybranej rodziny.
Deklaracje można skorygować przed rzeczywistym użyciem. Zamrożenie kwalifikacji
pozostaje prowizoryczne. Nie tworzy kohorty ani trwałej informacji o użyciu.
Późniejszy alias może zablokować TRAIN lub unieważnić zależny raport bez
przepisywania jego historycznych danych. Odpowiedź nie ujawnia obcych nagrań.

HTTP409 może zachować wykryty alias, ochronę lub konserwatywnie konfliktową rolę
wraz z nowszą rewizją na serwerze. Najpierw wybierz „Odśwież nagrania” i sprawdź
bieżący stan oraz powód konfliktu. GET/reload nie usuwa lokalnego exactcommand;
ponowienie tego samego body/key nadal zwróci zapisany409. Przed nowym zamiarem
świadomie zaznacz „Potwierdzam porzucenie lokalnego polecenia po zapisaniu
archiwum”, następnie wybierz „Zachowaj archiwum i porzuć polecenie”. Dopiero
potem utwórz nowe polecenie z odczytaną bieżącą rewizją. Porzucenie lokalne nie
cofa zapisu na serwerze. Brak potwierdzonego archiwum zachowuje stare body/key.

## Nierozstrzygnięte mapowania

Photo-only Mumie, Reels i Treasure nie dowodzą całego nagrania. Zaufany import
zachowuje znaną ochronę zdjęć. Późniejsze potwierdzone przypisanie zdjęć do
pełnego filmu może rozwiązać wcześniejszy brak mapowania z zachowaniem historii.
Nie należy tworzyć fikcyjnej gry ani wskazywać przypadkowej grupy MAIN.

Atestacja strony MAIN jest obecnie wszystko albo nic. Jedno źródło bez
zaufanego pixelSHA lub zgodnej rewizji geometrii zatrzymuje stronę jako
`RECORDING_SOURCE_IDENTITY_UNRESOLVED`. Rejestracja pozostaje nieukończona;
aplikacja nie podaje dokładnego licznika takich źródeł. To zaakceptowane
ograniczenie P2-3 po audycieR1, a nie zero braków ani potwierdzona kwalifikacja.

TASK-0995 pozostaje producentem prowadzonej w aplikacji kwalifikacji i dowodów
rzeczywistego użycia kohort. TASK-0997 wiąże rzeczywiste raporty; TASK-1002 nie
fabrykuje wyników ani nie deklaruje gotowości brakujących deskryptorów.
