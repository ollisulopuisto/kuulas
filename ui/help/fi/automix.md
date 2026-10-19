---
id: automix
title: Miksaus automixerilla
applies-to: []
commands: [export.automix]
related: [track, timeline]
---
Automixer miksaa valmiin leikkauksen puolestasi: puhe tasataan ja viimeistellään, musiikki painuu puheen alle ja kokonaisuus saatetaan tavoiteäänekkyyteen. Kuulas antaa sille leikkauksen erillisinä raitoina, joten et vie tai siirrä tiedostoja itse.

- Käynnistä Tiedosto-valikosta Vie miksaus (automixer)… tai komentopaletista: {key:export.automix}
- Aseta tavoiteäänekkyys ja halutessasi mainoskohta ja mainoksen pituus.
- Miksaus ajetaan taustalla. Ilmoitus näyttää automixerin viimeisimmän viestin; Peruuta pysäyttää sen.
- Miksaus tallentuu projektin .kuulas-kansion viereen (kansioon, jossa se on, ei koskaan sen sisään), nimenä leikkaus ja kellonaika. Dialogissa voi valita toisen kansion. Näytä Finderissä avaa kansion.

Miksataan vain puhe- ja musiikkiraidat. Väylät ovat oman kuunteluvalvontasi tasapainoa ja toiseen sovellukseen vietäviä kiinteitä vientejä varten; automixer ei käytä niitä, joten ne jätetään tästä ajosta pois (tavalliset viennit eivät muutu). Raitojen liukusäätimiä ja panorointia ei myöskään käytetä: automixer tasaa raidat ja levittää puhujat itse. Leikkeen vahvistus ja leikkauksesi otetaan huomioon. Äänitteet voivat olla missä tahansa muodossa ja näytteenottotaajuudella, koska kuulas renderöi ne automixerille; itse projektin on oltava 48000 Hz. Miksaus on 16-bittinen WAV.

Tarkista ensimmäisellä kerralla komento dialogin kohdasta Automixer. Se on ohjelma, jonka kuulas ajaa, yleensä `uv run automixer` podcast-kansiossasi. Jos ohjelmaa ei löydy, viesti kertoo sen nimen.

Mykistetyt raidat ja raidat, joita ei ole soolotettu toisen ollessa soolossa, jätetään pois kuten missä tahansa viennissä. Katso myös [[track]].
