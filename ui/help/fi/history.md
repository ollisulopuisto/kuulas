---
id: history
title: Historia
applies-to: [history]
commands: [edit.undo, edit.redo, history.restore, history.goto_restore_point, history.expand_all, app.save_named, app.save, history.saved_only, history.open_saved, history.rename_version]
related: [clip, timeline]
---
Historiassa on jokainen muokkaus projektin alusta asti, uusin ylimpänä, tekoaikoineen. Viiva merkitsee, missä kukin työskentelykerta alkoi ja päättyi. Jokainen vaihe on nimetty sen mukaan, mitä se teki ja mihin ("Raidan asetukset: Olli · taso −3,0 dB", "Jako: Anna kohdassa 12:34,5"), nyt käyttämälläsi kielellä. Useampi peräkkäinen vaihe samaan kohteeseen näkyy yhtenä rivinä ("×4"); oikea nuoli näyttää jokaisen.

- Kumoa ja tee uudelleen: {key:edit.undo} ja {key:edit.redo}
- Palaa mihin tahansa aiempaan vaiheeseen: valitse se ja käytä Palauta-toimintoa (painike, {key:history.restore} tai kaksoisnapsautus). Pelkkä valinta ei muuta mitään. Palautus lisää uuden vaiheen, joka on samanlainen kuin valitsemasi, joten mitään ei menetetä: jättämäsi tila on yhden Kumoa-komennon päässä ja jokainen vaihe jää listaan. Palautus koskee vain muokkausta; mediaa ja synkkaa se ei palauta.
- Palautuksen jälkeen uusi vaihe on "Palautettu: …", vaiheessa, johon palattiin, on merkintä "palautuskohta", ja vasemman reunan sulje yhdistää ne. Palautuksen ohittamat vaiheet kootaan yhdeksi riviksi "↩ Palautus ohitti N vaihetta". {key:history.goto_restore_point} palautusrivillä hyppää sen palautuskohtaan.
- Kumoamasi vaiheet ovat nykyisen yläpuolella avoimessa "↶ Kumottu" -ryhmässä (Tee uudelleen tuo ne takaisin). Kumoamisen jälkeinen muokkaus jättää kumotut vaiheet sivupolulle: suljettu "⑂ Sivupolulle jääneet" -ryhmä. Kullakin lajilla on oma kuvake ja sana; kaikki voi yhä palauttaa.
- Ryhmät: oikea nuoli avaa ryhmän, vasen sulkee, ja {key:history.restore} ryhmärivillä avaa tai sulkee. Siirry, Avaa Historian kaikki ryhmät avaa kaikki kerralla; uudelleen palauttaa ne ennalleen.
- Tallennetut versiot: {key:app.save_named} (Tiedosto, Tallenna nimetty versio) nimeää nykyisen vaiheen. Se näkyy listassa kirjanmerkillä ja nimellään; kopion lähettämisestä tai viennistä syntyneissä versioissa on pieni merkintä, kumpi on kyseessä. Pelkkä {key:app.save} tekee vain varmuuskopion eikä lisää listaan mitään.
- Vain tallennetut versiot: ylhäällä olevassa kytkimessä on kaksi tilaa, "Kaikki vaiheet" ja "Tallennetut versiot" (tai valikosta Siirry, Näytä Historiassa vain tallennetut versiot); "Tallennetut versiot" piilottaa tavalliset vaiheet. Sen alla oleva rivi muistuttaa, että minkä tahansa vaiheen voi palauttaa, ja siinä on linkki takaisin kaikkiin vaiheisiin. Siirry, Avaa Historia tallennettujen versioiden kohdalta avaa välilehden suodatin valmiiksi päällä. Jokaisesta versiosta kerrotaan, missä se on: nykyisessä tilassa, kumottu, palautuksen ohittama tai jäänyt sivupolulle. Valinta muistetaan. Vieressä oleva tekstikenttä suodattaa vaiheen tai version nimen sanoilla ja toimii yhdessä painikkeen kanssa.
- Tallennetun version nimeäminen uudelleen: valitse se ja käytä valikon kohtaa Siirry, Nimeä valittu tallennettu versio uudelleen. Palauta toimii tallennetulle versiolle kuten muillekin vaiheille.
- Tilastot: Tiedosto, Tilastot… (tai komentopaletti) laskee tämän istunnon: istunnon keston, jokaisen raidan jänteen, sisällön, mykistetyn ajan ja ajan ilman mykistyksiä, leikkeiden pituudet, kuka puhui, muokkausten määrän ja muokkaukseen käytetyn ajan. Voit kopioida ne tekstinä tai tallentaa JSON-tiedostona. Kumoamista ei tallenneta historiaan, joten sitä ei lasketa.

Kumoaminen ei koske leikepöytää. Katso myös [[timeline]].
