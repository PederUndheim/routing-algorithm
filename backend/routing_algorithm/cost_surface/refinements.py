import numpy as np
from scipy.ndimage import distance_transform_edt
from typing import Optional, Union

def release_area_buffer_penalty(
        release_area_mask: np.ndarray,
        pixel_size_m: float,
        max_dist: float,
        max_cost: float,
        exp_scale: float,
        mode: str,
) -> np.ndarray:
        """Build a penalty buffer layer around release areas. The penalty is highest close to the release area and decreases with distance."""

        release_mask = release_area_mask.astype(bool)

        # Compute distance to nearest release area pixel, then find distance in meters
        dist_px = distance_transform_edt(~release_mask)
        dist_m = dist_px.astype(np.float32) * float(pixel_size_m)

        # Normalize distances to [0..1] within the buffer
        d = np.clip(dist_m, 0.0, float(max_dist))

        if mode == "linear":
                u = 1.0 - (d / float(max_dist)) # 1 near release, 0 at max_dist
        elif mode == "exp":
                # Strong near release, fades with distance
                u = np.exp(-d / float(exp_scale))
                # Make sure it hits ~0 at max_dist
                u0 = float(np.exp(-float(max_dist) / float(exp_scale)))
                if u0 > 0:
                        u = (u - u0) / (1.0 - u0)
        else:
                raise ValueError(f"Unknown mode '{mode}'")
        
        u = np.clip(u, 0.0, 1.0).astype(np.float32)

        penalty = np.full(release_area_mask.shape, 0, dtype=np.float32)
        outside = ~release_mask
        in_buffer = outside & (dist_m < max_dist)

        penalty[in_buffer] = u[in_buffer] * max_cost

        return penalty


def steep_area_penalty(
        slope_arr: np.ndarray,
        start_deg: float,
        full_deg: float,
        max_penalty: float,
) -> np.ndarray:
        """
        Returns an additive penalty:
        - 0 below start_deg
        - smooth increase from start_deg to full_deg
        - max_penalty above full_deg

        Uses smoothstep for a gradual, monotonic ramp.
        """
        s = slope_arr.astype(np.float32, copy=False)
        denom = max(full_deg - start_deg, 1e-6)
        t = (s - start_deg) / denom
        t = np.clip(t, 0.0, 1.0)

        # Smoothstep function
        w = t * t * (3.0 - 2.0 * t)

        return (w * max_penalty).astype(np.float32, copy=False)


def extreme_steep_barrier(
        slope_arr: np.ndarray,
        threshold_deg: float,
        barrier_value: float,
) -> np.ndarray:
        """
        Hard barrier for extreme slopes. Returns barrier_value where slope >= threshold_deg,
        0 elsewhere. Apply via max_combine so it overrides the normal 1-99 cost ceiling.

        This addresses narrow cliff bands: even 2-3 pixels at barrier_value (e.g. 200)
        make traversal far more expensive than routing around, unlike the 99 ceiling where
        a thin cliff may still be cheaper than a long detour.
        """
        s = slope_arr.astype(np.float32, copy=False)
        out = np.where(s >= float(threshold_deg), float(barrier_value), 0.0)
        return out.astype(np.float32)




