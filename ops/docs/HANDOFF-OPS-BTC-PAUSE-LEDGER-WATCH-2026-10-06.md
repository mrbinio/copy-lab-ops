# Handoff — pauza, księga, nadzór, 6 października 2026

## Executive summary

155 zakupów po zejściu okresu poniżej zera należało do procesu, który jeszcze liczył całą księgę. Kod okresu wszedł o 19:31 i od razu wstrzymał portfel. Trzy późniejsze zakupy są skutkiem powrotu po jednej dodatniej obserwacji, nie ominięciem kontroli. Księga przy błędzie zostawia ostatni poprawny wynik, pokazuje awarię osobno i wstrzymuje zakupy tylko tego portfela. Piąty restart nie wyłącza już usługi na stałe.

PAPER, `clob_live=false`, baza, historia, hasło i port 8769 zostają. LIVE zostaje wyłączone.

## Co się zmieniło i dlaczego

Portfel `218d69a9` pierwszy raz miał ujemny bieżący okres o 05:29:36. Działający wtedy proces pochodził z 5 października, 23:24, i pauzował dopiero gdy cała księga była ujemna. Cała księga była jeszcze na plusie, więc zakupy szły dalej. O 19:31:32 audyt zapisał pauzę okresu: −25,60 USD na 118 rozliczeniach. Od 05:29:36 do tej chwili było 155 `COPIED_BUY`: 112 nowych lotów i 43 dokupienia. W tym samym oknie źródło ma 8320 wierszy aktywności. To zdarzenia źródła, nie kopie.

O 20:32:40 audyt zapisał powrót: jedna obserwacja otwarta po pauzie, +1,14 USD, próbka niepewna. Powrót wyzerował początek okresu, więc następny zakup widział okres równy zero i przeszedł kontrolę. Trzy nowe loty, bez dokupień: 20:37:19 `0x81666129e1c643b2`, 20:40:46 `0x7a2518275375ae66`, 20:50:28 `0x81e9a409eeaf3e9d`. O 20:58:16 okres znowu zszedł poniżej zera i portfel stoi.

Zakup i dokupienie czytają pauzę oraz wstrzymanie księgi w tej samej transakcji, która rezerwuje gotówkę. Test równoczesny trzyma rozliczenie straty na blokadzie zapisu; czekający zakup dostaje `COPY_PAUSED` i nie rusza salda.

Błąd księgi o 05:20:01 nie ma w logu portfela ani kwot. Linia brzmiała tylko `copy ledger mismatch`. Wyjątek sprzed 18:34 nie zawierał końcówki portfela. Skończone zadanie publikacji podnosiło ten sam wyjątek co 30 sekund, więc ekran został na zamknięciu z 05:07, chociaż odbiór i kopiowanie szły dalej. To tłumaczy zatrzymanie ekranu. Nie tłumaczy, która z trzech nierówności padła, bo tych liczb nikt nie zapisał. O 19:28 wszystkie 86 kont spełniało równość i spełnia ją też teraz. Kontrola zostaje. Przy następnym błędzie zapis idzie osobno: portfel, gotówka, suma księgi, ekspozycja, wynik, obie różnice. Ostatni poprawny wynik zostaje. Ekran pisze, że wynik jest nieaktualny, o której była ostatnia poprawna publikacja i że nowe zakupy dotyczą tylko wskazanego portfela. Drugi projekt nie dostaje tej blokady.

Po piątym starcie w dziesięć minut wrapper wcześniej kończył się kodem 0. launchd traktował to jako sukces i nie podnosił usługi. Teraz wrapper zostaje w pamięci, zapisuje `logs/service-stopped.json` i startuje sam, gdy któryś start wypadnie z okna dziesięciu minut. Nadzór restartuje tylko przy nieświeżym tętnie. Spóźniona publikacja, błąd połączenia i niespójna księga są wpisem statusu, bez restartu całego systemu. Czekanie na okno startów też nie jest kolejnym restartem.

Pięć portfeli Mitcha ma `POLL_OK` w odstępie sekund. Nie było nowego zakupu, który przeszedł kwalifikację. Dziennik ma 505 spóźnionych zakupów, 658 zdarzeń spoza BTC 15m i 2 sprzedaże bez znanej proporcji źródła. Pozycji Mitcha jest zero. Nic nie zostało dopisane na pokaz.

Kilka wykonań jednego zakupu sumuje udziały i dolary raz. Ponowne pobranie tego samego wykonania nic nie dodaje. Szybka cena arkusza jest podmieniana potwierdzoną ceną źródła i nie wchodzi do średniej.

## Liczby

- 155 kopii przed wdrożeniem pauzy okresu, w tym 43 dokupienia i 112 nowych lotów.
- 8320 wierszy aktywności źródła w tym oknie.
- 3 kopie po powrocie o 20:32:40, wszystkie nowe loty.
- 86 kont księgi, 0 niespełnionych równości w bieżącym odczycie.
- Pięć portfeli Mitcha odpytywanych. 0 pozycji. 0 kwalifikujących się zakupów.

## Changelog

- Pauza i wstrzymanie księgi siedzą w transakcji zakupu i dokupienia.
- Błąd księgi publikuje status awarii i nie nadpisuje ostatniego wyniku.
- Piąty start czeka i wraca, zamiast zostawiać usługę wyłączoną.
- Nadzór rozdziela zawieszenie procesu, publikację, połączenie i księgę.
- Wypełnienia jednego zakupu sumują się raz. Cena arkusza nie zastępuje ceny zapłaconej.

## Następna decyzja

Powrót po jednej niepewnej obserwacji jest zgodny z wcześniejszą regułą i właśnie on puścił trzy zakupy. Jeśli jedna obserwacja nie ma zdejmować pauzy, to jest osobna decyzja. Brak zdalnego alarmu zostaje: baner i plik statusu nie są telefonem. Opóźnienie poniżej 1 s nie jest potwierdzone.
