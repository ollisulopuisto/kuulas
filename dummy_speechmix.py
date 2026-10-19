import sys
import types
module = types.ModuleType("speechmix")
module.set_translator = lambda x: None
sys.modules["speechmix"] = module
sys.modules["nhsx"] = types.ModuleType("nhsx")
sys.modules["sounddevice"] = types.ModuleType("sounddevice")
