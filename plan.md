1. **Optimize startup speed on Mac:**
   - In `src/kuulas/messages.py`: `_language` is evaluated eagerly when the module is imported. `default_language()` spawns `defaults read -g AppleLanguages` on macOS.
   - We will change `_language = default_language()` to `_language = None` and initialize it lazily when `language()`, `t()`, or other functions need it.

2. **Optimize memory usage:**
   - Big audio sessions use a lot of memory because `np.load(spill)` loads entire multi-GB numpy arrays into RAM.
   - We will change `np.load(spill)` to `np.load(spill, mmap_mode='r')` in `src/kuulas/memory.py` so memory is mapped instead of fully resident in RSS.
   - We will also change `np.load(source)` to `np.load(source, mmap_mode='r')` in `src/kuulas/peaks.py` if possible (though `np.load` on an `.npz` file might require caution, wait, `.npz` files can't be easily mmapped without issues if they are zipped, but `np.savez` writes uncompressed by default. Wait, `np.load` doesn't support `mmap_mode` for `.npz`. Let's stick to `src/kuulas/memory.py` where `np.save` is used and `np.load(spill, mmap_mode='r')` works well. And `src/kuulas/media.py` `_base_peaks` which uses `np.load(where)` (this is a `.npy` file? Yes, `np.save(f, levels[LEVELS[0]])`).
   - Wait, `mmap_mode='r'` on `.npy` is safe.
   - We will review tests (`pytest`) and make sure everything passes.

3. **Complete pre-commit steps:**
   - Ensure proper testing, verifications, review, and reflection are done by running `pytest`, `ruff`, etc.

4. **Submit change.**
