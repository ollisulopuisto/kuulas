---
id: history
title: Historia
applies-to: [history]
commands: [edit.undo, edit.redo, app.save_named, app.save, history.saved_only, history.rename_version]
related: [clip, timeline]
---
Historiassa on jokainen muokkaus projektin alusta asti, uusin alimpana, tekoaikoineen. Viiva merkitsee, missä kukin työskentelykerta alkoi ja päättyi.

- Kumoa ja tee uudelleen: {key:edit.undo} ja {key:edit.redo}
- Palaa mihin tahansa aiempaan vaiheeseen: valitse se listasta. Mitään ei menetetä: sen jälkeiset vaiheet jäävät listaan, ja niihin voi palata.
- Tallennetut versiot: {key:app.save_named} (Tiedosto, Tallenna nimetty versio) nimeää nykyisen vaiheen. Se näkyy listassa kirjanmerkillä ja nimellään; kopion lähettämisestä tai viennistä syntyneissä versioissa on pieni merkintä, kumpi on kyseessä. Pelkkä {key:app.save} tekee vain varmuuskopion eikä lisää listaan mitään.
- Vain tallennetut versiot: ylhäällä oleva "Tallennetut versiot" -painike (tai valikosta Siirry, Näytä Historiassa vain tallennetut versiot) piilottaa tavalliset vaiheet. Valinta muistetaan. Vieressä oleva tekstikenttä suodattaa vaiheen tai version nimen sanoilla ja toimii yhdessä painikkeen kanssa.
- Tallennetun version nimeäminen uudelleen: valitse se ja käytä valikon kohtaa Siirry, Nimeä valittu tallennettu versio uudelleen. Palauta toimii tallennetulle versiolle kuten muillekin vaiheille.
- Tilastot: Tiedosto, Tilastot… (tai komentopaletti) laskee tämän istunnon: istunnon keston, jokaisen raidan jänteen, sisällön, mykistetyn ajan ja ajan ilman mykistyksiä, leikkeiden pituudet, kuka puhui, muokkausten määrän ja muokkaukseen käytetyn ajan. Voit kopioida ne tekstinä tai tallentaa JSON-tiedostona. Kumoamista ei tallenneta historiaan, joten sitä ei lasketa.

Kumoaminen ei koske leikepöytää. Katso myös [[timeline]].
