---
title: TASK-0217 manual image-selection gallery
status: done
release: "0.4"
last_updated: 2026-08-11
---

# TASK-0217 — Galeria ręcznej selekcji

## Goal

Pozwolić wybrać historyczny job, obejrzeć miniatury całej zachowanej grupy,
otworzyć pełny podgląd i zatwierdzić istniejący JPEG bez szukania na dysku.

## Verification

Mysz i klawiatura, lazy thumbnails, pełny preview, statusy błędów oraz zachowany
fallback uploadu pojedynczego JPEG-a.

## Outcome

Workspace ma sekcję `Zapisane procesy`, a modal galerię lazy-load, pełny podgląd
i wybór istniejącego kandydata. Nowy worker utrwala lekkie rekordy wszystkich
źródeł grupy; nie są one używane przy wznowieniu algorytmu. Starszy run pokazuje
licznik zachowanej shortlisty względem `sourceCount`. Manualny test przeglądarki
pozostaje w TASK-0218.

Automatyczna regresja Admina przeszła 179/179 wraz z typecheckiem. Obejmuje
historię procesu, bounded kolejki manualne, fallback pojedynczego JPEG-a,
natychmiastowy zapis grupy i stany dostępności. Mysz, klawiatura, lazy loading
i końcowa ocena ergonomii pozostają do odbioru przez właściciela.

Odbiór rzeczywistego runu wykrył błąd adresu zasobu: modal pomijał prefiks
`/api/v1`, dlatego lista kandydatów była dostępna, ale każda miniatura i duży
podgląd otrzymywały HTTP 404. Generator URL-u wskazuje teraz pełny endpoint
kontraktu OpenAPI, a test kontraktowy zabezpiecza oba miejsca renderowania.

Galeria ma teraz własny przewijany viewport ze stałą informacją o liczbie
zdjęć. Wybrany JPEG otwiera się w pełnoekranowym podglądzie, który oferuje jeden
jawny poziom powiększenia i powrót do dopasowania. `Escape` zamyka najpierw
podgląd, nie cały modal decyzji.

Regresja Admina po rozszerzeniu przeszła 180/180 wraz z typecheckiem i kontrolą
formatowania. Test przeglądarkowy na rzeczywistej grupie 13 zdjęć potwierdził
przewijanie całej galerii, podgląd dopasowany do viewportu oraz pojedynczy zoom
do oryginalnych 1080×1920 z przewijaniem. Nie zapisano decyzji domenowej.

Ponowny odbiór ujawnił, że licznik łączył `manually_selected` z `missing_image`,
więc komunikat `1 / N zatwierdzonych` mógł w rzeczywistości oznaczać jedną grupę
pominiętą. Dodatkowo Enter użyty na aktywnej miniaturze był zatrzymywany przed
handlerem dialogu i nie wykonywał zapisu. W sprawdzonym runie baza zawierała
`0` ręcznych wyborów i `1` pominięcie, co wyjaśniało powrót do drugiej grupy po
ponownym otwarciu modala.

Modal wybiera teraz deterministyczną podpowiedź: środkowy JPEG dla galerii do
20 elementów i dziesiąty dla większej. Podpowiedź nie jest zapisywana
automatycznie. `Enter`, strzałka w prawo oraz przycisk `Zatwierdź` zapisują
aktualny wybór i przechodzą do następnej nierozwiązanej grupy, a strzałka w lewo
tylko wraca. Podczas ładowania galerii zapis `bez zdjęcia` jest zablokowany.
Nagłówek pokazuje oddzielnie wybrane, pominięte i pozostałe grupy.

Do workspace dodano także kontrolę grup `auto_selected`. Przycisk
`Weryfikuj wybory algorytmu` ładuje wyłącznie automatyczne wybory wskazanego
runu i otwiera ten sam duży podgląd, przewijaną galerię oraz zoom. Oryginalny
reprezentant ma stałe oznaczenie `Wybór algorytmu`, więc obejrzenie innej
miniatury nie zaciera informacji, co faktycznie wybrał selektor. Tryb jest
celowo tylko do odczytu i nie mutuje joba ani katalogu wynikowego.
