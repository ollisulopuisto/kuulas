---
id: record
title: Oton äänittäminen
applies-to: [index]
commands: [transport.record, record.stop_mode, record.preroll, marker.add]
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

Kun äänite on käynnissä, Lisää merkki (tai {key:marker.add}) laittaa merkin kohtaan, jossa äänite on nyt, ei toistokursorin kohtaan, joten voit merkitä hyvän vastauksen tai virheen heti. Merkit pysyvät paikoillaan, kun äänitteen leikkeet tulevat aikajanalle.

Jos haluat äänittää usealta laitteelta yhtä aikaa, yhdistä ne ensin macOS:ssä: Audio MIDI Setup > Create Aggregate Device, valitse laitteet (ja Drift Correction kaikille paitsi kellolaitteelle). Kuulas näkee silloin yhden laitteen, jolla on kaikki kanavat, ja jokaisen kanavan voi ohjata omalle raidalleen.

Kun äänite on käynnissä, sen raidat piirtyvät aikajanalle sitä mukaa kuin ääni tulee: palkki jokaiselle pikselille kovimman näytteen mukaan ja punainen kärki siihen, missä äänite on nyt. Uusi raita (jota ei vielä ole) piirtyy vasta kun äänite pysähtyy. Leikkeet ottavat piirroksen paikan, kun pysäytät.

Kun painat Äänitä, äänitysnäkymä väistyy ja aikajana on edessä, äänite piirtyy sen raidoille (uusi raita luodaan juuri silloin). Näkymä seuraa äänitettä niin kauan kuin katsot sitä ja jättää sen rauhaan, kun vierität pois. Työkalupalkin merkki tuo äänitysnäkymän ja Pysäytä-painikkeen takaisin. Äänitteen aikana muokkaus on tauolla (leikkaus tai siirto ennen äänitettä veisi sen väärään paikkaan); voit vierittää, zoomata, valita, lukea ja lisätä merkkejä.

Asetuksissa "Soitetut leikkeet menevät raidalle" valitsee raidan leikkeille, joita soitat leikepöydältä (cart-näppäimillä tai merkinnän soittopainikkeella) äänityksen aikana: uusi raita nimeltä Kysymykset tai mikä tahansa raita, jolle ei äänitetä. Jokainen soittamasi leike asetetaan myös tälle raidalle kohtaan, jossa äänite on sillä hetkellä, joten kysymys on vastauksen vieressä. Jos raidalla on jo ääntä toistokursorista eteenpäin, varoitus kertoo että leikkeet kirjoittavat sen päälle.
