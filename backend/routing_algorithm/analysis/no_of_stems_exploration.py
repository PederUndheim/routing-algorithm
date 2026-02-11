import rasterio
import numpy as np
import matplotlib.pyplot as plt

forest_path = "data/tif/number_of_stems_ha.tif"

with rasterio.open(forest_path) as src:
    data = src.read(1, masked=True)  # read first band
    print("Shape:", data.shape)
    print("Data type:", data.dtype)
    print("Min:", data.min())
    print("Max:", data.max())
    print("Unique values:", np.unique(data.compressed())[:20])  # first 20 unique

hist, bin_edges = np.histogram(data.compressed(), bins=20)
print("Histogram counts:", hist)
print("Bin edges:", bin_edges)

print("CRS:", src.crs)
print("Transform:", src.transform)
print("NoData value:", src.nodata)
print("Driver:", src.driver)


plt.imshow(data, cmap="Greens")
plt.colorbar(label="Forest value")
plt.show()

from rasterio.plot import show
from rasterio.sample import sample

coords = [(500000, 6789000)]  # your coordinate (x, y in CRS of raster)
for val in sample(src, coords):
    print("Value at", coords[0], ":", val)
