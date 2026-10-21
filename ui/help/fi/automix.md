---
id: automix
title: Miksaus automixerilla
applies-to: []
commands: [export.automix, transport.render_listen]
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

**Nopea esikuuntelu välistä.** Koko automix kestää suunnilleen yhtä kauan kuin leikkaus on pitkä. Kun haluat kuulla muutoksen nopeammin, aseta In ja Out jonkin kohdan ympärille ja valitse "Vain In–Out-väli (nopea esikuuntelu)": vain se väli miksataan, parin minuutin leikkauksesta muutamassa minuutissa. Tiedoston nimi on kuin koko miksauksen, lisänä "preview" ja väli, eikä se koskaan korvaa koko miksausta. Tasot, puhujien tasapaino, taustamusiikin taso ja masterointi mitataan pelkästä otteesta, joten esikuuntelu on kuuntelua varten tehty arvio, ei lopullinen miksaus.

**Kuuntele miksausta.** Miksauksen jälkeen kuljetinkulmassa on Leikkaus | Miksaus (myös Toisto > Kuuntele miksausta). Miksaus soittaa tiedoston raitojen sijaan sen omalla paikallaan aikajanalla (välin esikuuntelu välin kohdalla), joten toisto, siirtyminen, silmukka ja nopea kuuntelu toimivat tavalliseen tapaan ja kuulet kaiken, mitä automixer teki. Raitojen päällä oleva palkki kertoo, mikä soi; Takaisin leikkaukseen tai Leikkaus palaa. Mykistys, soolo ja vahvistus ovat sillä aikaa himmennettyjä: ne eivät muuta tiedostoa. Tiedosto on masteroitu (noin -16 LUFS), joten se kuulostaa leikkausta kovemmalta; tasoja ei soviteta.

Miksaus vastaa leikkausta vain niin kauan kuin leikkaus soi kuten silloin: mikä tahansa muutos leikkeisiin, vahvistuksiin, mykistyksiin, portteihin, duckaukseen tai raitojen ja väylien asetuksiin vanhentaa sen, ja kuuntelu palaa itsestään leikkaukseen ja kertoo sen. Merkit, nimet ja toistokohta eivät vaikuta. Vanhentunut tai kadonnut miksaus pysyy näkyvissä (Miksaus on harmaana ja kertoo syyn) seuraavaan miksaukseen asti; sen tiedostoa ei koskaan poisteta.
