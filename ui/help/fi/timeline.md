---
id: timeline
title: Aikajana
applies-to: [timeline]
commands: [transport.play, view.toggle, view.fit, view.fit_selection, view.zoom_in, view.zoom_out, view.back, view.wheel_mode, view.clip_words, panel.next, nav.home, spot, time.copy, help.open, help.keys]
related: [clip, track, bus]
---
Jokainen raita on oma kaistansa, ja aika kulkee vasemmalta oikealle. Napsautus missä tahansa kaistoilla siirtää toistokohdan siihen. Napsautus leikkeeseen myös valitsee sen; vaihto+napsautus lisää leikkeen valintaan tai poistaa sen. Vetämällä kaistoilla merkitset aikavälin. Vedon aikana kaistoilla näkyvä vihje kertoo, mikä näppäin muuttaa välin sen koskettamiksi leikkeiksi (ne valitaan ja sisään- ja ulosmerkit siirtyvät niiden ylle) ja mikä peruu vedon.

## Kuuntele
- Toista tai pysäytä: {key:transport.play}. Välilyönti kuuluu aina aikajanalle, missä paneelissa oletkin.

## Zoomaa ja liiku
- Lähi- tai laajanäkymä: {key:view.toggle} {show:view-toggle}
- Lähennä tai loitonna: {key:view.zoom_in} tai {key:view.zoom_out}
- Näytä koko versio: {key:view.fit}
- Sovita valintaan tai alku–loppuvälille: {key:view.fit_selection}
- Takaisin edelliseen näkymään: {key:view.back}

Tiheys, aaltomuoto ja seuranta ovat Näkymä-valikossa. {show:view-menu} Samoin Sovita raidat ikkunaan ja Pidä raidat sovitettuina ikkunaan. Yhden kaistan korkeutta säädät vetämällä sen otsikon alareunaa; kaksoisnapsautus palauttaa sen.

Kahden sormen vieritys ohjauslevyllä zoomaa aika-akselia osoittimen kohdalta oletuksena; sivuttain liikkuminen vierittää aikaa, ja ylös tai alas vaihtonäppäin pohjassa vierittää raitoja (myös vierityspalkki ja näppäimet toimivat). Hiiren rulla vierittää edelleen, ja vieritys komento- tai control-näppäin pohjassa sekä nipistys zoomaavat aina. Vaihda tästä: {run:view.wheel_mode}

Kun lähennys on tarpeeksi suuri sanojen lukemiseen, jokainen puheleike kirjoittaa sanansa nimensä alle, joten näet, missä aaltomuodon kohdassa mikin sana on. Toistokohdan alla oleva sana on kirkkaampi, ja litteraatiosta valitut sanat erottuvat. {run:view.clip_words}

## Hyppää aikaan
- Napsauta nurkan isoa aikaa kopioidaksesi sen leikepöydälle; kaksoisnapsauta sitä tai paina {key:spot}, niin voit kirjoittaa ajan ja hypätä siihen. Vahvistus hyppää; kentästä poistuminen peruu.
- Kirjoita 1:23,5 (tai 83,2) tietylle ajalle, tai aloita merkillä + tai - siirtyäksesi toistokohdasta: +100 on 100 sekuntia eteenpäin, -30 on 30 taaksepäin, +1:30 on 90 eteenpäin, +500ms on puoli sekuntia. Tulos pysyy muokkauksen sisällä.
- Sama toimii Alku-, Loppu- ja Pituus-riveillä: aika asettaa merkin, +2 tai -2 siirtää sitä. Alt+napsautus rivillä kopioi sen ajan.

## Paneelit
{key:panel.next} siirtää näppäimistön seuraavaan paneeliin; {key:nav.home} tuo sen takaisin tänne.

## Ohje
{key:help.open} avaa ohjeen siihen, mitä katsot; {key:help.keys} listaa kaikki näppäimet.

Katso myös [[clip]] ja [[track]].
