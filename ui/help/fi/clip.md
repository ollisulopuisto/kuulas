---
id: clip
title: Leike
applies-to: [clip]
commands: [edit.split, edit.delete, edit.cut, edit.lift_cut, edit.close_gap_all, clip.mute, clip.fade, edit.undo]
related: [timeline, track, transcript]
---
Leike on pätkä yhdestä äänityksestä raidalla. Samasta äänityksestä voi olla monta leikettä; kun valitset yhden, sen sisarleikkeet merkitään hakasella.

## Muokkaa
- Jaa toistokohdasta: {key:edit.split}
- Poista: {key:edit.delete}. Pehmeä leikkaus: ääni hiljenee, väli jää ja leikkauslistalta sen voi palauttaa. Leikepöytä ei muutu.
- Leikkaa: {key:edit.cut}. Kopioi leikepöydälle ja sulkee välin tahdistusryhmän jokaiselta raidalta.
- Nosta: {key:edit.lift_cut}. Kopioi leikepöydälle ja poistaa pehmeästi paikallaan: väli jää ja sen voi palauttaa.
- Sulje aukko kaikilta raidoilta: {key:edit.close_gap_all}. Poistaa valinnan tai merkityn välin jokaiselta raidalta ja sulkee aukon; leikepöytä ei muutu.
- Mykistä leike: {key:clip.mute}. Mykistetty leike on haalea ja viivoitettu.
- Häivytys sisään ja ulos: {key:clip.fade}

Jokaisen muokkauksen voi perua askel kerrallaan: {key:edit.undo}.

## Katso tarkemmin
Tarkastimessa näkyvät leikkeen taso, tahdistus ja lähde. {show:inspector}

Katso myös [[track]] ja [[transcript]].
