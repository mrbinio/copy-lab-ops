# Instalacja na prywatnym Macu Intel / Monterey

Instalator uruchamiasz w Terminalu na prywatnym Macu. Asystent nie uzyskuje dostępu do komputera, konta Apple ani portfela. Nie wysyłaj żadnych haseł do czatu.

## Instalacja

Pobierz `install-macos.sh` z tego katalogu i uruchom przez `/bin/bash`. Skrypt sprawdza Pythona 3.11–3.14, pobiera konkretny commit Twojego repozytorium, instaluje zależności w oddzielnym środowisku i uruchamia testy. Jeśli brakuje Pythona, otwiera oficjalną stronę pobierania i kończy pracę. Zainstaluj aktualne wydanie 3.13 dla macOS, uruchom `Install Certificates.command` z folderu Python w Applications i ponów instalację BTC Lab.

Hasło ustawiane podczas instalacji jest nowym hasłem do dashboardu, a nie hasłem administratora Maca. Skrypt nie wymaga `sudo`. Dane i konfiguracja znajdują się w `~/Library/Application Support/BTC Lab`. W konfiguracji przechowywany jest skrót hasła; plik jest dostępny tylko dla Twojego konta.

Dashboard: adres zostanie wypisany i otwarty przez instalator, login `damian`. Domyślny port to 8765; jeśli jest zajęty, instalator wybiera wolny port i zapisuje go w konfiguracji. Nie zatrzymuje innych aplikacji.

## Działanie

- Procesy startują po zalogowaniu na to konto. Nie startują przed odblokowaniem FileVault lub przed zalogowaniem po restarcie.
- Mac musi pozostać włączony, zalogowany i mieć internet. Zablokowany ekran nie zatrzymuje programu.
- `caffeinate` zapobiega bezczynnemu usypianiu podczas pracy procesu. Nie zabezpiecza przed wyłączeniem, ręcznym uśpieniem, zamknięciem pokrywy ani utratą zasilania. Laptop pozostaw otwarty i podłączony do zasilacza.
- Rejestr transakcji przetrwa restart. Logi mają limit rozmiaru i rotację. Pięć restartów w dziesięć minut zatrzymuje automatyczne próby do przeglądu.
- Stale zbierane dane nie są automatycznie publikowane na GitHubie. Publiczny dashboard na Pages nadal jest podglądem interfejsu.
- Prywatny zdalny podgląd wymaga osobnego tunelu/VPN zgodnego z Monterey. Instalator niczego nie wystawia do internetu ani do sieci domowej. Nie przekierowuj portów routera.

## Zatrzymanie i ponowny start

```sh
launchctl bootout "gui/$(id -u)/com.btc-lab.paper"
```

Ponowne włączenie po zatrzymaniu:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.btc-lab.paper.plist"
```

Po pięciu szybkich awariach najpierw sprawdź `logs/service.log`, usuń przyczynę i odczekaj dziesięć minut. Nie kasuj bazy danych ani pozycji, aby uruchomić program ponownie.

## Zakres weryfikacji

Sprawdzono składnię instalatora, generowanie plist z nazwami zawierającymi spacje oraz testy aplikacji. Instalacji `launchd`, braku usypiania i rzeczywistych feedów nie sprawdzono na Twoim Macu — potwierdzimy je po uruchomieniu. Nie zakładaj, że sam otwarty dashboard oznacza działające dane lub gotową strategię.
