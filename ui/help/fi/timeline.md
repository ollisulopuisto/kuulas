---
id: timeline
title: Aikajana
applies-to: [timeline]
commands: [transport.play, view.toggle, view.fit, view.fit_selection, view.zoom_in, view.zoom_out, view.back, view.wheel_mode, view.clip_words, view.follow, view.show_playhead, view.toggle_sidebar, panel.next, nav.home, spot, time.copy, help.open, help.keys]
related: [clip, track, bus]
---
Jokainen raita on oma kaistansa, ja aika kulkee vasemmalta oikealle. Napsautus missä tahansa kaistoilla siirtää toistokohdan siihen. Napsautus leikkeeseen myös valitsee sen; vaihto+napsautus lisää leikkeen valintaan tai poistaa sen. Vetämällä kaistoilla merkitset aikavälin. Vedon aikana kaistoilla näkyvä vihje kertoo, mikä näppäin muuttaa välin sen koskettamiksi leikkeiksi (ne valitaan ja sisään- ja ulosmerkit siirtyvät niiden ylle) ja mikä peruu vedon.

## Kuuntele
- Toista tai pysäytä: {key:transport.play}. Välilyönti kuuluu aina aikajanalle, missä paneelissa oletkin.

## Zoomaa ja liiku

Aikajanan yläpuolinen yleiskuva näyttää koko jakson. Sen yläreunassa on enintään neljä tasavälistä aikamerkintää. Asteikko kasvaa jakson pituuden mukana: lyhyissä jaksoissa sekunneista 1, 5, 10, 15, 20, 30 tai 60 minuuttiin. Siirrä näkyvää aluetta napsauttamalla tai vetämällä yleiskuvaa. Toistokohta ei siirry.
- Lähi- tai laajanäkymä: {key:view.toggle} {show:view-toggle}
- Lähennä tai loitonna: {key:view.zoom_in} tai {key:view.zoom_out}
- Näytä koko versio: {key:view.fit}
- Sovita valintaan tai alku–loppuvälille: {key:view.fit_selection}
- Takaisin edelliseen näkymään: {key:view.back}

Toiston aikana näkymä seuraa toistokohtaa (Seuranta-merkki kulmassa palaa). Vieritys, yleiskuvan vetäminen tai zoomaus kytkee seurannan pois ja näkymä pysyy siinä mihin sen jätit; reunan nuoli näyttää silloin missä toistokohta on. Napsauta merkkiä, nuolta tai itse toistokohtaa, tai aloita, pysäytä tai hyppää johonkin aikaan (Home, End, merkki, transkription sana, Hyppää aikaan (Spot), Tab seuraavaan pysäkkiin), niin seuranta palaa. Toistokohdan siirtely nuolinäppäimillä tai napsautus näkyvään kohtaan viivaimella ei palauta sitä. {run:view.follow} {run:view.show_playhead}

Tiheys, aaltomuoto ja seuranta ovat Näkymä-valikossa. {show:view-menu} Samoin Sovita raidat ikkunaan ja Pidä raidat sovitettuina ikkunaan. Yhden kaistan korkeutta säädät vetämällä sen otsikon alareunaa; kaksoisnapsautus palauttaa sen.

Kahden sormen vieritys ohjauslevyllä zoomaa aika-akselia osoittimen kohdalta oletuksena; sivuttain liikkuminen vierittää aikaa, ja ylös tai alas vaihtonäppäin pohjassa vierittää raitoja (myös vierityspalkki ja näppäimet toimivat). Hiiren rulla vierittää edelleen, ja vieritys komento- tai control-näppäin pohjassa sekä nipistys zoomaavat aina. Vaihda tästä: {run:view.wheel_mode}

Kun lähennys on tarpeeksi suuri sanojen lukemiseen, jokainen puheleike kirjoittaa sanansa nimensä alle, joten näet, missä aaltomuodon kohdassa mikin sana on. Toistokohdan alla oleva sana on kirkkaampi, ja litteraatiosta valitut sanat erottuvat. {run:view.clip_words}

Jos haluat aikajanalle enemmän leveyttä, piilota koko sivupaneeli (välilehtirivin x tai tästä). Ohjeen, Auto-Silencen asetusten tai sivuvälilehden avaaminen näyttää sen taas. {run:view.toggle_sidebar}

## Näin hiljaisuus näkyy
- Täytetty aaltomuoto: kuuluu. Pelkkä ääriviiva: hiljaa, mykistetty tai Auto-Silencen sulkema; leikkeen pohja on siinä tummempi.
- Lukko merkitsee Auto-Silencen sulkemaa kohtaa; mykistetyssä leikkeessä ei ole lukkoa. Avoin lukko leikkeen nimen perässä tarkoittaa, että leike pitää mikin auki.
- Meripihkan väriset katkoviivat merkitsevät, mistä suljettu kohta alkaa ja mihin se päättyy; ne eivät ole leikkeen reunoja eikä niitä voi vetää. Leikkeen reunat pysyvät yhtenäisinä, näkyvät ja niitä voi vetää myös hiljaisen kohdan sisällä.
- Ohut pyöreäkulmainen ääriviiva useiden leikkeiden ympärillä merkitsee yhtä ryhmää.
- Harmaat tai himmeät raidat eivät kuulu seuraavaan toimintoon (Näytä > Toiminnon ulkopuoliset raidat).
- Leike, jonka äänitiedosto puuttuu, näyttää punaisen varoitusmerkin eikä aaltomuotoa. Kaksoisnapsauta sitä etsiäksesi tiedoston.

## Hyppää aikaan
- Napsauta nurkan isoa aikaa kopioidaksesi sen leikepöydälle; kaksoisnapsauta sitä tai paina {key:spot}, niin voit kirjoittaa ajan ja hypätä siihen. Vahvistus hyppää; kentästä poistuminen peruu.
- Kirjoita 1:23,5 (tai 83,2) tietylle ajalle, tai aloita merkillä + tai - siirtyäksesi toistokohdasta: +100 on 100 sekuntia eteenpäin, -30 on 30 taaksepäin, +1:30 on 90 eteenpäin, +500ms on puoli sekuntia. Tulos pysyy muokkauksen sisällä.
- Sama toimii Alku-, Loppu- ja Pituus-riveillä: aika asettaa merkin, +2 tai -2 siirtää sitä. Alt+napsautus rivillä kopioi sen ajan.

## Paneelit
{key:panel.next} siirtää näppäimistön seuraavaan paneeliin; {key:nav.home} tuo sen takaisin tänne.

## Valinnan vienti
Jokainen vienti vie vain valitun ja kertoo sen alkaessa ("Viedään vain valinta: raidat Anna, Ville, 12.00-18.30").
- In- ja Out-merkeillä (tai raitojen yli vedetyllä välillä): se aikaväli, niillä raidoilla, joita aluekomento käyttäisi.
- Kun leikkeitä on valittu eikä väliä ole: raidat, joilla valitut leikkeet ovat, ensimmäisen valitun alusta viimeisen loppuun. Mukana on kaikki näiden raitojen sisältö tuolla välillä, ei vain valitut leikkeet.
- Kun mitään ei ole valittu: koko miksaus.

Vientiasetukset ja automiksausikkuna näyttävät valinnan ja ruudun "Vie vain valinta", joka on valittuna, kun valinta on olemassa. Poista valinta, niin viedään kaikki. Tiedoston nimessä ovat väli ja raidat, eikä olemassa olevaa tiedostoa korvata. Mykistetyt raidat pysyvät mykkinä ja solo toimii kuten koko miksauksessa.

## Askel taaksepäin
{key:nav.home} peruu painallusta kohden yhden asian, uusimman ensin, ja vie sen jälkeen näppäimistön aikajanalle:
- Auto-Silence-esikatselu (hylätään, mitään ei otettu käyttöön)
- tekstikenttä, johon kirjoitat
- valitut raitojen otsikot
- valitut leikkeet, vedetty alue sekä sisään- ja ulos-merkit yhdessä
- kohdistustila
- sen jälkeen näppäimistö vain siirtyy tänne

Tekstityksessä valittu sanaväli menee ensin; leikepöydän suodattimessa kirjoitettu teksti menee ensin. Käynnissä oleva veto, valikko tai ikkuna suljetaan ennen näitä. {key:nav.home} ei koskaan pysäytä toistoa (sen tekee {key:transport.play}) eikä peru vientiä tai automix-ajoa: käytä ilmoituksen Peruuta-painiketta.

## Näppäimet, jotka eivät voi toimia
Muokkausnäppäin (leikkaus, poisto, jako, mykistys, kopiointi ja muut), jolla ei ole kohdetta, kertoo syyn yhdellä rivillä eikä piippaa. Muokkausnäppäimet toimivat kaikissa paneeleissa paitsi kirjoittaessa tai ikkunan ollessa auki; kun sellainen toimii sivupaneelista, näppäimistö palaa aikajanalle.

## Ohje
{key:help.open} avaa ohjeen siihen, mitä katsot; {key:help.keys} listaa kaikki näppäimet.

Katso myös [[clip]] ja [[track]].

Kun siirrät leikettä, pidä komentonäppäintä (Windowsissa ja Linuxissa ohjausnäppäintä) pohjassa, niin leikkeen reunat tarttuvat myös äänenvoimakkuuden automaatioon: ducking-liukuman päihin (vähintään 3 dB:n muutos), muiden leikkeiden verhokäyrien tasonmuutoksiin ja Auto-Silencen sulkemien jaksojen reunoihin. Pienet merkit lanejen yläreunassa näyttävät paikat; päästä irti näppäimestä ja ne katoavat.
