import sys
import types


def ensure_stubs():
    if "speechmix" in sys.modules:
        return
    sm = types.ModuleType("speechmix")
    sm.set_translator = lambda f: None
    sm.messages = types.ModuleType("speechmix.messages")
    sm.messages.set_translator = lambda f: None
    sm.messages.FALLBACK = {}
    sm.dsp = types.ModuleType("speechmix.dsp")
    sm.dsp.FLOOR_DB = -96.0
    sm.envelopes = types.ModuleType("speechmix.envelopes")
    sm.grid = types.ModuleType("speechmix.grid")
    sm.grid.FLOOR_MARGIN_DB = 6.0
    sm.masks = types.ModuleType("speechmix.masks")
    sm.masks.DUCK_DB = -12.0
    sm.masks.DUCK_DOMINANCE_DB = 6.0
    sm.masks.DUCK_LOOKAHEAD = 0.2
    sm.masks.DUCK_HOLD = 0.4
    sm.meter = types.ModuleType("speechmix.meter")
    sm.meter.IntegratedMeter = object
    sm.meter.Meter = object
    sm.stems = types.ModuleType("speechmix.stems")
    sm.stems.pan_gains = lambda *a, **k: (1.0, 1.0)
    sm.stems.Lanes = object
    sm.blocks = types.ModuleType("speechmix.blocks")
    sm.programme = types.ModuleType("speechmix.programme")
    sm.chain = types.ModuleType("speechmix.chain")
    sm.chain.true_peak = lambda *a, **k: 0.0
    sm.binaries = types.ModuleType("speechmix.binaries")
    sm.binaries.get_binary_path = lambda *a, **k: "ffmpeg"
    sys.modules["speechmix"] = sm
    sys.modules["speechmix.messages"] = sm.messages
    sys.modules["speechmix.dsp"] = sm.dsp
    sys.modules["speechmix.envelopes"] = sm.envelopes
    sys.modules["speechmix.grid"] = sm.grid
    sys.modules["speechmix.masks"] = sm.masks
    sys.modules["speechmix.meter"] = sm.meter
    sys.modules["speechmix.stems"] = sm.stems
    sys.modules["speechmix.blocks"] = sm.blocks
    sys.modules["speechmix.programme"] = sm.programme
    sys.modules["speechmix.chain"] = sm.chain
    sys.modules["speechmix.binaries"] = sm.binaries

    nh = types.ModuleType("nhsx")
    nh.NhsxError = Exception
    nh.locate = lambda *a, **k: None
    nh.read = lambda *a, **k: None
    nh.tracks = lambda *a, **k: None
    nh.activity = types.ModuleType("nhsx.activity")
    nh.activity.GAP_CLOSE_S = 0.2
    nh.activity.MIN_RUN_S = 0.5
    nh.musicbed = types.ModuleType("nhsx.musicbed")
    nh.mix = types.ModuleType("nhsx.mix")
    nh.mix.level_at = lambda *a, **k: 0.0
    nh.mix.plan = lambda *a, **k: None
    nh.read_mod = types.ModuleType("nhsx.read")
    nh.read_mod.children = lambda *a, **k: []
    nh.read_mod.descendants = lambda *a, **k: []
    nh.read_mod.localname = lambda *a, **k: ""
    nh.read_mod.time_to_seconds = lambda *a, **k: 0.0
    sys.modules["nhsx"] = nh
    sys.modules["nhsx.activity"] = nh.activity
    sys.modules["nhsx.musicbed"] = nh.musicbed
    sys.modules["nhsx.mix"] = nh.mix
    sys.modules["nhsx.read"] = nh.read_mod

    sl = types.ModuleType("silencelearn")
    sys.modules["silencelearn"] = sl

    wa = types.ModuleType("wordalign")
    sys.modules["wordalign"] = wa

ensure_stubs()
