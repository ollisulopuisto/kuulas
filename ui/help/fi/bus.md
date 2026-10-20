---
id: bus
title: Väylä
applies-to: [bus]
commands: [bus.collapse, bus.expand, bus.role_speech, bus.role_music, bus.role_none, bus.reapply_role, track.match_role, track.mute, track.solo]
related: [track, timeline]
---
Väylä kokoaa yhteen raidat, jotka miksataan yhdessä, esimerkiksi kaikki äänet tai kaikki musiikki. Sen väri kulkee raitojen vasemmassa reunassa selkärankana, ja sen kirjaintunnus (A, B …) näkyy kaikkialla, missä väylä mainitaan.

- Supista väylä yhdeksi riviksi: {key:bus.collapse}. Supistetussa väylässä on jokaiselle raidalle ohut nauha, joka on täytetty siltä osin kuin raidalla on ääntä.
- Laajenna takaisin: {key:bus.expand}
- Väylän mykistys ja soolo koskevat kaikkia sen raitoja; sen liukusäädin asettaa koko väylän tason.

Väylällä voi olla rooli, puhe tai musiikki. Sen valinta antaa kaikille väylän raidoille saman roolin yhdellä kumoamisaskeleella, ja väylälle siirretty raita seuraa sitä:
- Aseta rooli: {key:bus.role_speech}, {key:bus.role_music}, tai poista se: {key:bus.role_none}
- Raidan Rooli-valinta (tarkastin tai otsakkeen valikko) on oletuksena "Sovita väylän rooliin"; valitse Puhe tai Musiikki ohittaaksesi sen, tai {key:track.match_role} seurataksesi väylää taas.
- Raita, jonka rooli on käsin asetettu eri kuin väylän, saa "!"-merkin, ja väylä näyttää roolinsa tähdellä ja Käytä uudelleen -painikkeella: {key:bus.reapply_role} antaa kaikille raidoille väylän roolin uudelleen.

Väylä, jossa on vain yksi raita, yhdistyy raidan otsakkeeseen. Raidan saa väylälle otsakkeen väylävalitsimesta tai tarkastimesta.

Katso myös [[track]].
