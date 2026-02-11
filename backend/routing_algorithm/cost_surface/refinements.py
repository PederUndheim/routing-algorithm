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




def real_tracks_modifier(
        tracks_arr: np.ndarray,
        w: Union[float, np.ndarray],
        p_high_quantile: float,
        gamma: float,
        validity_w: Optional[np.ndarray] = None,
        exclude_mask: Optional[np.ndarray] = None,
        only_mask: Optional[np.ndarray] = None,
        effect_weight: Optional[np.ndarray] = None,     # Possibly make a more advanced effect weight later??
) -> np.ndarray:
        """
        Returns a multiplicative modifier in [1-w, 1].
        1 means no change.
        1-w means strongest reduction (most travelled cells).

        strava_count can have NaN (NoData). NaN is treated as 0 density (neutral).
        """
        tracks = tracks_arr.astype(np.float32, copy=False)
        # Treat NaN as 0 density (neutral)
        tracks = np.where(np.isnan(tracks), 0.0, tracks)
        # Log transform to reduce skew
        tracks = np.log1p(np.maximum(tracks, 0.0))

        # Robust scalinf to [0,1] using a high quantile
        finite = tracks[np.isfinite(tracks)]
        if finite.size == 0:
                p = np.zeros_like(tracks, dtype=np.float32)
        else:
                q = np.quantile(finite, float(p_high_quantile))
                if q <= 0.0:
                        p = np.zeros_like(tracks, dtype=np.float32)
                else:
                        p = tracks / float(q)
                        p = np.clip(p, 0.0, 1.0).astype(np.float32)

        # Contrast control: major-only vs all tracks
        gamma = float(max(gamma, 1e-6))
        p = p ** gamma

        # Apply validity mask if provided
        if validity_w is not None:
                p = p * validity_w.astype(np.float32, copy=False)

        if effect_weight is not None:
                ew = effect_weight.astype(np.float32, copy=False)
                ew = np.clip(np.where(np.isnan(ew), 1.0, ew), 0.0, 1.0)
                p = p * ew
        
        # Apply exclude/only masks if provided
        if exclude_mask is not None:
                p = p * (~exclude_mask).astype(bool)
        if only_mask is not None:
                p = p * only_mask.astype(bool)

        if np.isscalar(w):
                w_arr = np.full_like(p, float(w), dtype=np.float32)
        else:
                w_arr = w.astype(np.float32, copy=False)
                if w_arr.shape != p.shape:
                        raise ValueError("w raster shape must match")
        
        w_arr = np.clip(w_arr, 0.0, 0.9).astype(np.float32, copy=False)
        
        # Convert to modifier
        modifier = (1.0 - w_arr * p).astype(np.float32)

        return modifier




# def cliff_buffer_penalty(
#         cliff_mask: np.ndarray,
#         pixel_size_m: float,
#         max_dist: float,
#         penalty_cost: float,
# ) -> np.ndarray:
#         """Build a penalty buffer layer very close to steep cliffs."""
#         cliff_mask = cliff_mask.astype(bool)

#         # Compute distance to nearest steep pixel, then find distance in meters
#         dist_px = distance_transform_edt(~cliff_mask)
#         dist_m = dist_px.astype(np.float32) * float(pixel_size_m)

#         # Find pixels in buffer zone
#         outside = ~cliff_mask
#         in_buffer = (dist_m <= max_dist)
        
#         # Penalize every pixel in the buffer with fixed penalty cost
#         penalty = np.full(cliff_mask.shape, 0, dtype=np.float32)
#         penalty[in_buffer] = penalty_cost

#         return penalty