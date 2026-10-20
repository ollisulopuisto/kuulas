---
id: clip
title: Leike
applies-to: [clip]
commands: [edit.split, edit.delete, edit.cut, edit.lift_cut, edit.close_gap_all, edit.paste, clip.mute, clip.quick_mute, clip.fade, edit.undo]
related: [timeline, track, transcript]
---
Leike on pala yhdestä äänityksestä raidalla. Samasta äänityksestä voi olla monta leikettä; kun valitset yhden, sen sisarleikkeet merkitään hakasella.

## Muokkaa
- Jaa toistokohdasta: {key:edit.split}
- Poista: {key:edit.delete}. Pehmeä leikkaus: ääni hiljenee, väli jää ja leikkauslistalta sen voi palauttaa. Leikepöytä ei muutu.
- Leikkaa: {key:edit.cut}. Kopioi leikepöydälle ja sulkee välin tahdistusryhmän jokaiselta raidalta.
- Nosta: {key:edit.lift_cut}. Kopioi leikepöydälle ja poistaa pehmeästi paikallaan: väli jää ja sen voi palauttaa.
- Sulje aukko kaikilta raidoilta: {key:edit.close_gap_all}. Poistaa valinnan tai merkityn välin jokaiselta raidalta ja sulkee aukon; leikepöytä ei muutu.
- Mykistä leike: {key:clip.mute}. Mykistetty leike on haalea ja viivoitettu.
- Pikamykistys (maiskahdukset): {key:clip.quick_mute}. Mykistää lyhyen jakson toistokohdan ympäriltä (oletus 0,5 s, asetus Asetuksissa) kaikilta raidoilta tai valituilta; toimii myös toiston aikana. Yksi kumoamisaskel; mitään ei poisteta.
- Häivytys sisään ja ulos: {key:clip.fade}

Jokaisen muokkauksen voi perua askel kerrallaan: {key:edit.undo}.

## Liitä
- Liitä: {key:edit.paste}. Liittää toistokohtaan valitsemallesi raidalle.
- Kohderaita on se, jonka otsikko on valittu (useasta valitusta ylin), muuten kohdistettu raita. Usean raidan kopio säilyttää asettelunsa: sen ensimmäinen raita menee tälle raidalle, muut sen alapuolelle.
- Jos raitaa ei ole valittu eikä kohdistettu, liitos menee raidalle, jolta se kopioitiin, jos se on vielä olemassa, muuten raidalle 1.
- Kaikki liitostavat (lisää, päälle, nykyiselle raidalle, samoille raidoille) noudattavat tätä sääntöä; vain "samat raidat" käyttää aina lähderaitoja. Puheleikkeen voi liittää musiikkiraidalle.

## Katso tarkemmin
Tarkastimessa näkyvät leikkeen taso, tahdistus ja lähde. {show:inspector}

Katso myös [[track]] ja [[transcript]].
