import pytest

from kuulas import messages
from kuulas.messages import KuulasError
from kuulas.region_names import region_filenames


def test_bad_characters_are_removed_and_spaces_collapsed():
    got = region_filenames([
        ('what? "why" / no', 0.0),
        ("a  |\t*b: name\\", 1.0),
        ("ends. . ", 2.0),
    ])

    assert got == ["01 what why no.wav", "02 a b name.wav", "03 ends.wav"]


def test_finnish_letters_stay():
    got = region_filenames([("Äänite ö", 0.0)])

    assert got == ["01 Äänite ö.wav"]

    # Uniqueness is case-insensitive over full Unicode, as macOS and
    # Windows file systems are, not ASCII-only.
    got = region_filenames(
        [("Äänite ö", 0.0), ("ÄÄNITE Ö", 1.0)], template="{name}")
    assert got == ["Äänite ö.wav", "ÄÄNITE Ö 2.wav"]


def test_a_long_name_is_cut_to_120_characters():
    got = region_filenames([("x" * 300, 0.0)])

    # The cut is on the whole rendered stem, template and all.
    assert got == ["01 " + "x" * 117 + ".wav"]
    assert len(got[0].removesuffix(".wav")) == 120


def test_windows_reserved_names_get_an_underscore():
    got = region_filenames([
        ("CON", 0.0),
        ("com3", 1.0),
        ("LPT9 region", 2.0),
    ], template="{name}")

    assert got == ["CON_.wav", "com3_.wav", "LPT9 region.wav"]

    # The part before the first dot decides, as on Windows: "NUL.5.wav"
    # would be reserved, so the underscore goes after that part.
    got = region_filenames([("NUL.5", 0.0)], template="{name}")
    assert got == ["NUL_.5.wav"]

    # The check is case-insensitive.
    got = region_filenames([("Aux", 0.0)], template="{name}")
    assert got == ["Aux_.wav"]


def test_an_empty_name_becomes_region():
    got = region_filenames([("", 0.0), ("///", 1.0)], template="{name}")

    assert got == ["region.wav", "region 2.wav"]


def test_names_are_unique_without_existing():
    got = region_filenames(
        [("Take", 0.0), ("Take", 1.0), ("take", 2.0)], template="{name}")

    assert got == ["Take.wav", "Take 2.wav", "take 3.wav"]


def test_names_are_unique_against_existing():
    got = region_filenames(
        [("Interview", 0.0), ("Interview", 1.0)],
        template="{name}",
        existing=("interview.wav", "interview 2.wav"))

    # Case-insensitive against existing names, and the counter skips
    # past the suffixes existing already holds.
    assert got == ["Interview 3.wav", "Interview 4.wav"]


def test_the_template_tokens_and_format_specs():
    regions = [("Äänite ö", 3725.0), ("Second", 65.0)]

    # {n} is 1-based and honours the format spec; {start} is hh-mm-ss.
    got = region_filenames(regions, template="{n:03d} - {name} [{start}]")
    assert got == ["001 - Äänite ö [01-02-05].wav", "002 - Second [00-01-05].wav"]

    got = region_filenames(regions, template="{n}")
    assert got == ["1.wav", "2.wav"]

    got = region_filenames(regions, template="{name} at {start}")
    assert got == ["Äänite ö at 01-02-05.wav", "Second at 00-01-05.wav"]

    # The defaults: "{n:02d} {name}" and "wav".
    got = region_filenames(regions)
    assert got == ["01 Äänite ö.wav", "02 Second.wav"]

    # A dotless extension and an extension with a leading dot.
    assert region_filenames([("A", 0.0)], extension="flac") == ["01 A.flac"]
    assert region_filenames([("A", 0.0)], extension=".mp3") == ["01 A.mp3"]


def test_a_name_with_braces_is_not_treated_as_a_template():
    got = region_filenames([("{name} and {start}", 0.0)])

    # The name is a value, never re-scanned for tokens.
    assert got == ["01 {name} and {start}.wav"]


def test_a_bad_template_raises():
    with pytest.raises(KuulasError) as err:
        region_filenames([("A", 0.0)], template="{what}")
    assert err.value.key == "error.regions.bad_template"

    with pytest.raises(KuulasError) as err:
        region_filenames([("A", 0.0)], template="broken {n")
    assert err.value.key == "error.regions.bad_template"

    with pytest.raises(KuulasError) as err:
        region_filenames([("A", 0.0)], template="{0}")
    assert err.value.key == "error.regions.bad_template"


def test_the_error_text_is_translated_to_both_languages():
    with pytest.raises(KuulasError) as err:
        region_filenames([("A", 0.0)], template="{what}")
    assert str(err.value) == "The region file name template is invalid: {what}."

    messages.set_language("fi")
    try:
        with pytest.raises(KuulasError) as err:
            region_filenames([("A", 0.0)], template="{what}")
        assert str(err.value) == (
            "Aluenimien malli ei kelpaa: {what}.")
    finally:
        messages.set_language("en")
