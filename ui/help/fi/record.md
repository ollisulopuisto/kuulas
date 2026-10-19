---
id: record
title: Oton äänittäminen
applies-to: [index]
commands: [transport.record, record.stop_mode, record.preroll]
related: [track, timeline]
---
Äänitä yksi tulon kanava raidalle: {key:transport.record} avaa äänitysnäkymän. Valitse tulo, kanava ja raita (tai uusi raita) ja paina Äänitä. Otto alkaa toistokohdasta ja ilmestyy siihen leikkeenä, kun pysäytät.

- Ennakko: et voi painaa Äänitä liian myöhään. Kun äänitysnäkymä on auki, tuloa kuunnellaan ja viimeiset 60 sekuntia pidetään muistissa; otto alkaa niin paljon ennen Äänitä-painallusta, ja leike sijoitetaan niin, että ennakko päättyy toistokohtaan (aikajanan alun yli menevä osa leikataan pois). Valitse pois, 10, 30, 60 tai 120 sekuntia: {key:record.preroll} tai Ennakko-asetus äänitysnäkymässä. Näkymä kertoo "Valmiina: kuunnellaan, ei äänitetä", kun tämä on päällä. Levylle ei kirjoiteta mitään ennen kuin painat Äänitä; näkymän sulkeminen, sovelluksen sulkeminen tai kaatuminen hävittää puskurin.

- kuulas ei soita mitään äänittäessään. Kuuntele äänikortin omasta suoramonitoroinnista.
- Pysäyttäminen vaatii oletuksena kaksi painallusta Pysäytä-painikkeesta (tai välilyönnistä): ensimmäinen kysyy "Pysäytetäänkö äänitys?", toinen neljän sekunnin sisällä pysäyttää. Jos et paina uudelleen, äänitys vain jatkuu. Voit valita sen sijaan yhden painalluksen tai 2 sekunnin painalluksen: {key:record.stop_mode} tai asetus äänitysnäkymän alaosassa.
- Äänitysnäkymän piilottaminen, ikkunan sulkeminen tai edes editorin kaatuminen ei pysäytä ottoa. Työkalupalkin punainen "Äänitetään"-merkki tuo näkymän takaisin, ja projektin avaaminen uudelleen näyttää sen.
- Tiedostot ovat tavallisia WAV-tiedostoja projektin äänityskansiossa, ja ne kirjoitetaan niin, että kaikki viimeiseen sekuntiin asti säilyy kaatumisen tai irronneen johdon jälkeen. Kaatumisen keskeyttämä otto tarjotaan tuotavaksi, kun avaat projektin seuraavan kerran; sitä ei koskaan tuoda kysymättä.
- Jos tulo irrotetaan, otto odottaa sitä ja jatkuu; aukko jää aikajanalle aukoksi. Vähäisestä levytilasta kerrotaan, kun jäljellä on 30, 10 ja 2 minuuttia.

Macissa ensimmäinen äänitys kysyy lupaa käyttää mikrofonia. Kun kuulas ajetaan päätteestä, lupa tarvitaan päätteelle (Järjestelmäasetukset, Tietosuoja ja suojaus, Mikrofoni). Ilman lupaa tulo on hiljainen: seuraa tasomittaria.

Katso myös [[track]].
