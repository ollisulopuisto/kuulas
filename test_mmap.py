import numpy as np
import tempfile
import os

with tempfile.TemporaryDirectory() as d:
    spill = os.path.join(d, "test.npy")
    arr = np.ones((10, 100), dtype=np.float32)
    np.save(spill, arr)
    loaded = np.load(spill, mmap_mode='r')
    print(type(loaded), loaded.shape)
