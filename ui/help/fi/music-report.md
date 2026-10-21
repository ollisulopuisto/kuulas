---
id: music-report
title: Musiikkiraportti Teostoa ja Gramexia varten
applies-to: []
commands: [export.music_report]
related: [track, clip]
---
Musiikkiraportti listaa kaiken musiikin, jonka avoin leikkaus todella soittaa, tekijänoikeusilmoituksia varten (Teosto, Gramex). Avaa se kohdasta Tiedosto, Musiikkiraportti… tai hae komentopaletista sanalla "Teosto", "Gramex" tai "musiikkiraportti".

Kuulluksi lasketaan musiikkiraitojen leikkeet, ei kuitenkaan mykistettyjä leikkeitä, mykistettyjä raitoja eikä kohtia, jotka portti tai raidan automaatio on hiljentänyt. Saman äänitteen peräkkäiset palat, joiden väli on alle 2 sekuntia, lasketaan yhdeksi käytöksi.

Jokaisella rivillä on äänitteen tunnisteista nimi, esittäjä, säveltäjä, kustantaja, ISRC ja tiedostonimi, ohjelma-aika jolloin kappale alkaa ja päättyy, kesto sekä se, soiko se puheen alla (Taustalla) vai ei (Etualalla). Ajat ovat täysiä sekunteja ohjelman alusta, ja osa sekunnista lasketaan kokonaiseksi, joten alku, kesto ja loppu täsmäävät aina.

- Tallenna CSV… ja Tallenna HTML… tekevät tiedostot, jotka saavat projektin nimen, esimerkiksi "Ohjelmani music-report.csv". CSV käyttää puolipisteitä ja aukeaa oikein suomenkielisessä Excelissä. Olemassa olevaa tiedostoa ei koskaan korvata: selain tai työpöytäikkuna antaa uudelle tiedostolle oman nimen.
- Kopioi taulukkona vie raportin leikepöydälle sarkaimilla erotettuna, jolloin sen voi liittää taulukkolaskentaan.
- Kappale, jolta puuttuu nimi tai esittäjä, luetellaan yhteenvedon alla nimeltä ja sen rivi väritetään. Täydennä tiedot ennen kuin lähetät raportin.
- Jos leikkauksessa ei ole musiikkia, ikkuna sanoo "Tässä leikkauksessa ei ole musiikkia" ja kertoo syyn: musiikkiraitaa ei ole, musiikkiraidat on mykistetty, niillä ei ole leikkeitä tai musiikki on hiljennetty.

Raportti koskee nyt avointa leikkausta. Se ei muuta projektia eikä äänitteitäsi. Katso myös [[track]] ja [[clip]].
