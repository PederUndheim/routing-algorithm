import rasterio
from rasterio.transform import Affine
from rasterio.crs import CRS
import numpy as np
import os

def validate_data_matching(rasterfiles: list[str]) -> None:
    """
    Validates a list of raster files to check if they all have the same CRS, dimensions,
    georeferencing, and most importantly, pixel size.

    Args:
        rasterfiles (list[str]): A list of file paths to the raster files to validate.
    """
    print("Starting raster validation script...\n")

    # --- Step 1: Open and get properties of the first file in the list ---
    first_file_path = rasterfiles[0]
    try:
        with rasterio.open(first_file_path) as first:
            first_crs = first.crs
            first_width = first.width
            first_height = first.height
            first_transform = first.transform
            first_bounds = first.bounds
            
            # Extract and print the pixel size of the first raster
            first_pixel_x = first_transform.a
            first_pixel_y = first_transform.e
            
            print(f"First file loaded: {os.path.basename(first_file_path)}")
            print(f"  - CRS: {first_crs.to_string()}")
            print(f"  - Dimensions: {first_width}x{first_height}")
            print(f"  - Pixel Size: {first_pixel_x} x {first_pixel_y}")
            print(f"  - Bounding Box: {first_bounds}\n")
            
    except rasterio.errors.RasterioIOError as e:
        print(f"Error: Could not open the first file at {first_file_path}. Please check the path and file integrity.")
        return

    # --- Step 2: Validate each other file against the first ---
    for file_path in rasterfiles[1:]:
        print(f"--- Validating: {os.path.basename(file_path)} ---")
        
        if not os.path.exists(file_path):
            print(f"  - FAIL: File not found at path: {file_path}")
            print("-" * 30 + "\n")
            continue
            
        try:
            with rasterio.open(file_path) as src:
                # Compare CRS
                if src.crs != first_crs:
                    print(f"  - FAIL: CRS mismatch. File CRS: {src.crs.to_string()}")
                else:
                    print("  - PASS: CRS matches.")
                
                # Compare Dimensions (width and height)
                if src.width != first_width or src.height != first_height:
                    print(f"  - FAIL: Dimension mismatch. File dimensions: {src.width}x{src.height}")
                else:
                    print("  - PASS: Dimensions match.")
                
                # Compare Georeferencing (transform)
                # Check pixel size and origin separately for more granular output
                src_pixel_x = src.transform.a
                src_pixel_y = src.transform.e

                pixel_size_match = np.allclose([src_pixel_x, src_pixel_y], [first_pixel_x, first_pixel_y])
                if not pixel_size_match:
                    print(f"  - FAIL: Pixel size mismatch. File pixel size: {src_pixel_x} x {src_pixel_y}")
                else:
                    print("  - PASS: Pixel size matches.")

                # The full transform check is still the most comprehensive way to check alignment
                if not np.allclose(src.transform.to_gdal(), first_transform.to_gdal()):
                    print("  - FAIL: Full transform mismatch (origin, rotation, or shear).")
                else:
                    print("  - PASS: Full transform matches.")
                
                # Compare Bounding Box (spatial extent)
                if src.bounds != first_bounds:
                    print(f"  - FAIL: Bounding box mismatch. File bounds: {src.bounds}")
                else:
                    print("  - PASS: Bounding box matches.")

        except rasterio.errors.RasterioIOError as e:
            print(f"  - FAIL: Could not open file. Error: {e}")
        
        print("-" * 30 + "\n")


if __name__ == "__main__":
    files_to_validate = [
        "data/tif/slope.tif",
        "data/tif/dem.tif",
        "data/tif/number_of_stems_ha.tif",
        "data/tif/pra_binary.tif",
        "data/tif/pra_raw.tif",
        "data/tif/windshelter.tif",
        "data/flow-py_outputs/tif/FP_travel_angle.tif",
        "data/flow-py_outputs/tif/FP_travel_distance.tif",
        "data/flow-py_outputs/tif/FP_z_delta.tif",
        "data/tif/roads.tif",
        "data/tif/tractorroads_trails.tif",
        "data/tif/rivers.tif"]
    
    validate_data_matching(files_to_validate)
