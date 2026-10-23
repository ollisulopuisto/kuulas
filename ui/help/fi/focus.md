---
id: focus
title: Keskittymistila
applies-to: [focus]
commands: [view.focus, view.focus_solo, view.focus_shrink, view.focus_hide_others, track.prev, track.next, nav.home]
related: [track, timeline, transcript]
---
Keskittymistila antaa tilaa yhdelle puhujalle. Valittu raita ja saman puhujan muut raidat kasvavat; muut raidat kutistuvat, mutta vain luettavaan kokoon (ne jakavat noin 40 % tilasta, enintään 64 px kukin, ja hyvin monen raidan kohdalla vähintään ohuen kaistaleen), joten niiden nimi, aaltomuoto ja leikkeiden reunat sekä tahdistus näkyvät yhä yhdellä silmäyksellä. Keskittyminen muuttaa sitä, mitä näet; soolo muuttaa sitä, mitä kuulet.

- Keskity valittuun raitaan: {key:view.focus}. Paina uudelleen tai {key:nav.home} lopettaaksesi. {key:nav.home} tyhjentää ensin valinnan tai alku- ja loppumerkit ja lopettaa sitten keskittymisen.
- Keskity ja soolota: {key:view.focus_solo}. Kun lopetat, aiemmat soolot palaavat ennalleen.
- {key:track.prev} ja {key:track.next} siirtävät keskittymisen edelliseen tai seuraavaan puhujaan. Napsautus kaistaleeseen keskittyy siihen raitaan.
- Muut raidat näkyvät harmaina kuten toiminnon ulkopuoliset raidat (Näytä > Toiminnon ulkopuoliset raidat).
- Kaistat muuttavat kokoaan nopeasti, toiston aikana ja animaation ollessa pois ilman animaatiota.

Litteraatissa muiden puhujien sanat himmennetään, jotta keskustelu on yhä luettavissa. Piilota ne sen sijaan: {run:view.focus_hide_others}

Pidä kaistojen koko ja vain harmaannuta muut raidat: {run:view.focus_shrink}

Kaikki nämä ovat valikossa Näytä > Keskittymistila. Keskittyminen kuuluu vain näkymään: sitä ei tallenneta projektiin eikä kumoushistoriaan.
