---
id: clip
title: Leike
applies-to: [clip]
commands: [edit.split, edit.delete, edit.cut, edit.lift_cut, edit.close_gap_all, edit.paste, edit.paste_insert, clip.mute, clip.quick_mute, clip.fade, clip.relink_media, edit.undo]
related: [timeline, track, transcript]
---
Leike on pala yhdestä äänityksestä raidalla. Samasta äänityksestä voi olla monta leikettä; kun valitset yhden, sen sisarleikkeet merkitään hakasella.

## Muokkaa
- Jaa toistokohdasta: {key:edit.split}
- Poista: {key:edit.delete}. Pehmeä leikkaus: ääni hiljenee, väli jää ja leikkauslistalta sen voi palauttaa. Leikepöytä ei muutu.
- Leikkaa: {key:edit.cut}. Kopioi leikepöydälle ja sulkee välin tahdistusryhmän jokaiselta raidalta.
- Nosta: {key:edit.lift_cut}. Kopioi leikepöydälle ja poistaa pehmeästi paikallaan: väli jää ja sen voi palauttaa.
- Sulje aukko kaikilta raidoilta: {key:edit.close_gap_all}. Poistaa valinnan tai merkityn välin jokaiselta raidalta ja sulkee aukon; leikepöytä ei muutu.
- Mykistä leike: {key:clip.mute}. Mykistetty leike säilyttää värinsä, mutta sen aaltomuodosta jää vain ääriviiva, joten näet yhä, mikä on hiljennetty.
- Pikamykistys (maiskahdukset): {key:clip.quick_mute}. Mykistää lyhyen jakson toistokohdan ympäriltä (oletus 0,5 s, asetus Asetuksissa) kaikilta raidoilta tai valituilta; toimii myös toiston aikana. Yksi kumoamisaskel; mitään ei poisteta.
- Muokkasitko äänityksen toisessa ohjelmassa (vaikkapa poistit kohinan)? Leikkeen valikon **Etsi / vaihda äänitiedosto…** vaihtaa äänityksen kaikkiin leikkeisiin valitsemasi tiedoston näytettyään molemmat pituudet; yksi kumoamisaskel, eikä kumpaakaan tiedostoa muuteta. Leike, jonka tiedosto puuttuu, näyttää punaisen varoitusmerkin; kaksoisnapsauta sitä etsiäksesi tiedoston.
- Häivytys sisään ja ulos: {key:clip.fade}

Jokaisen muokkauksen voi perua askel kerrallaan: {key:edit.undo}.

## Liitä
- Liitä: {key:edit.paste}. Liittää toistokohtaan valitsemallesi raidalle nykyisen materiaalin päälle: liitettyjen alle jäävät leikkeet lyhenevät, jakautuvat tai poistuvat, eikä mikään myöhempi siirry. Yksi kumoamisaskel; äänitteisiin ei koskaan kosketa.
- Liitä ja lisää: {key:edit.paste_insert}. Työntää myöhempää materiaalia eteenpäin päälle kirjoittamisen sijaan.
- Kun In ja Out on merkitty, liitos alkaa In-pisteestä ja leikataan Outissa, jos se on pidempi; lyhyempi leike säilyttää oman pituutensa. Usean leikkeen kopio säilyttää asettelunsa ja jokainen leike leikataan Outissa.
- Kohderaita on se, jonka otsikko on valittu (useasta valitusta ylin), muuten kohdistettu raita. Usean raidan kopio säilyttää asettelunsa: sen ensimmäinen raita menee tälle raidalle, muut sen alapuolelle.
- Jos raitaa ei ole valittu eikä kohdistettu, liitos menee raidalle, jolta se kopioitiin, jos se on vielä olemassa, muuten raidalle 1.
- Kaikki liitostavat (päälle, lisää, nykyiselle raidalle, samoille raidoille) noudattavat tätä sääntöä; vain "samat raidat" käyttää aina lähderaitoja. Puheleikkeen voi liittää musiikkiraidalle.

## Katso tarkemmin
Tarkastimessa näkyvät leikkeen taso, tahdistus ja lähde. {show:inspector}

Leike, joka pitää mikin auki, näyttää Taso-osiossa rivin "Mikki pidetään auki"; sen painike antaa Auto-Silencen hiljentää leikkeen taas (sama kuin Pidä mikki auki valittujen leikkeiden alla, Leike-valikossa).

Katso myös [[track]] ja [[transcript]].
