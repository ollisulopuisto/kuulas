"""The production default of the disk-backed master, read with nothing patched."""
import importlib

from speechmix import programme

from kuulas import export


def test_module_default_is_streaming():
    # A fresh import of the module's own constant: no fixture has touched it.
    assert importlib.util.find_spec("kuulas.export") is not None
    source = open(export.__file__, encoding="utf-8").read()
    assert "\nSTREAM_MASTERING_ENABLED = True\n" in source
    assert export.STREAM_MASTERING_ENABLED is True


def test_streams_follows_both_speechmix_functions():
    has_both = (callable(getattr(programme, "master_stream", None))
                and callable(getattr(programme, "master_scratch_bytes", None)))
    assert export._streams() is has_both
