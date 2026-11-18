"""
37-Term Fringe Zernike Polynomial Wavefront Decomposition Module
Fulfills Objective 2 & Addresses Optical Figure Research Gaps (Li et al. [22], Harbin Institute Dataset)
Implements standard 37 Fringe Zernike polynomials Z_1 to Z_37 on annular optical apertures.
"""

import math
import numpy as np

# Table of 37 Fringe Zernike radial orders (n) and azimuthal frequencies (m)
# Format: (j, n, m, description)
FRINGE_ZERNIKE_37 = [
    (1,  0,  0, "Piston"),
    (2,  1,  1, "X-Tilt"),
    (3,  1, -1, "Y-Tilt"),
    (4,  2,  0, "Power / Defocus"),
    (5,  2,  2, "Primary Astigmatism 0 deg"),
    (6,  2, -2, "Primary Astigmatism 45 deg"),
    (7,  3,  1, "Primary X-Coma"),
    (8,  3, -1, "Primary Y-Coma"),
    (9,  4,  0, "Primary Spherical"),
    (10, 3,  3, "Primary Trefoil 0 deg (3-Fold Whiffletree)"),
    (11, 3, -3, "Primary Trefoil 30 deg"),
    (12, 4,  2, "Secondary Astigmatism 0 deg"),
    (13, 4, -2, "Secondary Astigmatism 45 deg"),
    (14, 5,  1, "Secondary X-Coma"),
    (15, 5, -1, "Secondary Y-Coma"),
    (16, 6,  0, "Secondary Spherical"),
    (17, 4,  4, "Primary Tetrafoil 0 deg"),
    (18, 4, -4, "Primary Tetrafoil 22.5 deg"),
    (19, 5,  3, "Secondary Trefoil 0 deg (3-Fold Whiffletree)"),
    (20, 5, -3, "Secondary Trefoil 30 deg"),
    (21, 6,  2, "Tertiary Astigmatism 0 deg"),
    (22, 6, -2, "Tertiary Astigmatism 45 deg"),
    (23, 7,  1, "Tertiary X-Coma"),
    (24, 7, -1, "Tertiary Y-Coma"),
    (25, 8,  0, "Tertiary Spherical"),
    (26, 5,  5, "Pentafoil 0 deg"),
    (27, 5, -5, "Pentafoil 18 deg"),
    (28, 6,  4, "Secondary Tetrafoil 0 deg"),
    (29, 6, -4, "Secondary Tetrafoil 22.5 deg"),
    (30, 7,  3, "Tertiary Trefoil 0 deg (3-Fold Whiffletree)"),
    (31, 7, -3, "Tertiary Trefoil 30 deg"),
    (32, 8,  2, "Quaternary Astigmatism 0 deg"),
    (33, 8, -2, "Quaternary Astigmatism 45 deg"),
    (34, 9,  1, "Quaternary X-Coma"),
    (35, 9, -1, "Quaternary Y-Coma"),
    (36, 10, 0, "Quaternary Spherical"),
    (37, 6,  6, "Hexafoil 0 deg (6-Fold 18-Point Whiffletree Symmetry)")
]


def evaluate_fringe_zernike_term(j, rho, theta):
    """
    Evaluates Fringe Zernike polynomial Z_j(rho, theta) for normalized radial distance rho in [0, 1]
    and azimuthal angle theta in [0, 2*pi].
    """
    r = np.asarray(rho, dtype=np.float64)
    th = np.asarray(theta, dtype=np.float64)

    if j == 1:
        return np.ones_like(r)
    elif j == 2:
        return r * np.cos(th)
    elif j == 3:
        return r * np.sin(th)
    elif j == 4:
        return 2.0 * (r**2) - 1.0
    elif j == 5:
        return (r**2) * np.cos(2.0 * th)
    elif j == 6:
        return (r**2) * np.sin(2.0 * th)
    elif j == 7:
        return (3.0 * (r**3) - 2.0 * r) * np.cos(th)
    elif j == 8:
        return (3.0 * (r**3) - 2.0 * r) * np.sin(th)
    elif j == 9:
        return 6.0 * (r**4) - 6.0 * (r**2) + 1.0
    elif j == 10:
        return (r**3) * np.cos(3.0 * th)
    elif j == 11:
        return (r**3) * np.sin(3.0 * th)
    elif j == 12:
        return (4.0 * (r**4) - 3.0 * (r**2)) * np.cos(2.0 * th)
    elif j == 13:
        return (4.0 * (r**4) - 3.0 * (r**2)) * np.sin(2.0 * th)
    elif j == 14:
        return (10.0 * (r**5) - 12.0 * (r**3) + 3.0 * r) * np.cos(th)
    elif j == 15:
        return (10.0 * (r**5) - 12.0 * (r**3) + 3.0 * r) * np.sin(th)
    elif j == 16:
        return 20.0 * (r**6) - 30.0 * (r**4) + 12.0 * (r**2) - 1.0
    elif j == 17:
        return (r**4) * np.cos(4.0 * th)
    elif j == 18:
        return (r**4) * np.sin(4.0 * th)
    elif j == 19:
        return (5.0 * (r**5) - 4.0 * (r**3)) * np.cos(3.0 * th)
    elif j == 20:
        return (5.0 * (r**5) - 4.0 * (r**3)) * np.sin(3.0 * th)
    elif j == 21:
        return (15.0 * (r**6) - 20.0 * (r**4) + 6.0 * (r**2)) * np.cos(2.0 * th)
    elif j == 22:
        return (15.0 * (r**6) - 20.0 * (r**4) + 6.0 * (r**2)) * np.sin(2.0 * th)
    elif j == 23:
        return (35.0 * (r**7) - 60.0 * (r**5) + 30.0 * (r**3) - 4.0 * r) * np.cos(th)
    elif j == 24:
        return (35.0 * (r**7) - 60.0 * (r**5) + 30.0 * (r**3) - 4.0 * r) * np.sin(th)
    elif j == 25:
        return 70.0 * (r**8) - 140.0 * (r**6) + 90.0 * (r**4) - 20.0 * (r**2) + 1.0
    elif j == 26:
        return (r**5) * np.cos(5.0 * th)
    elif j == 27:
        return (r**5) * np.sin(5.0 * th)
    elif j == 28:
        return (6.0 * (r**6) - 5.0 * (r**4)) * np.cos(4.0 * th)
    elif j == 29:
        return (6.0 * (r**6) - 5.0 * (r**4)) * np.sin(4.0 * th)
    elif j == 30:
        return (21.0 * (r**7) - 30.0 * (r**5) + 10.0 * (r**3)) * np.cos(3.0 * th)
    elif j == 31:
        return (21.0 * (r**7) - 30.0 * (r**5) + 10.0 * (r**3)) * np.sin(3.0 * th)
    elif j == 32:
        return (56.0 * (r**8) - 105.0 * (r**6) + 60.0 * (r**4) - 10.0 * (r**2)) * np.cos(2.0 * th)
    elif j == 33:
        return (56.0 * (r**8) - 105.0 * (r**6) + 60.0 * (r**4) - 10.0 * (r**2)) * np.sin(2.0 * th)
    elif j == 34:
        return (126.0 * (r**9) - 280.0 * (r**7) + 210.0 * (r**5) - 60.0 * (r**3) + 5.0 * r) * np.cos(th)
    elif j == 35:
        return (126.0 * (r**9) - 280.0 * (r**7) + 210.0 * (r**5) - 60.0 * (r**3) + 5.0 * r) * np.sin(th)
    elif j == 36:
        return 252.0 * (r**10) - 630.0 * (r**8) + 560.0 * (r**6) - 210.0 * (r**4) + 30.0 * (r**2) - 1.0
    elif j == 37:
        return (r**6) * np.cos(6.0 * th)
    else:
        raise ValueError(f"Fringe Zernike term j={j} outside supported range 1..37")


def fit_fringe_zernike(x, y, w, R, nterms=37):
    """Least-squares fit of Fringe Zernike coefficients to surface data w(x, y) on an aperture of radius R.
    (The former hand-written fixed-ratio 'synthesis' template was removed - coefficients now always come
    from fitting real FE surface deflections.)"""
    rho = np.hypot(x, y) / R
    th = np.arctan2(y, x)
    B = np.column_stack([evaluate_fringe_zernike_term(j, rho, th) for j in range(1, nterms + 1)])
    coef, *_ = np.linalg.lstsq(B, w, rcond=None)
    return coef


def reconstruct_wavefront_grid(zernike_coeffs, grid_size=64, central_obscuration_ratio=0.214):
    """
    Reconstructs 2D surface figure deformation map W(x, y) on a regular grid from 37 Zernike coefficients.
    Returns: X, Y, W (grid_size x grid_size numpy arrays, masked NaN outside annular mirror).
    """
    coeffs = np.asarray(zernike_coeffs, dtype=np.float64)
    lin = np.linspace(-1.0, 1.0, grid_size)
    X, Y = np.meshgrid(lin, lin)
    R = np.sqrt(X**2 + Y**2)
    Theta = np.arctan2(Y, X)

    # Annular aperture mask: between central bore and outer rim
    mask = (R >= central_obscuration_ratio) & (R <= 1.0)
    W = np.full((grid_size, grid_size), np.nan, dtype=np.float64)

    W_valid = np.zeros(np.sum(mask), dtype=np.float64)
    r_val = R[mask]
    th_val = Theta[mask]

    for j in range(1, min(38, len(coeffs) + 1)):
        c_j = coeffs[j - 1]
        if abs(c_j) > 1e-4:
            basis = evaluate_fringe_zernike_term(j, r_val, th_val)
            W_valid += c_j * basis

    W[mask] = W_valid
    return X, Y, W


if __name__ == "__main__":
    # self-test: fit recovers known coefficients
    rng = np.random.default_rng(0)
    x, y = rng.uniform(-1, 1, (2, 4000))
    m = np.hypot(x, y) <= 1
    x, y = x[m], y[m]
    true = np.zeros(37); true[3], true[8], true[36] = 10.0, -4.0, 2.5
    w = sum(true[j - 1] * evaluate_fringe_zernike_term(j, np.hypot(x, y), np.arctan2(y, x)) for j in range(1, 38))
    print("max |fit - true| =", np.abs(fit_fringe_zernike(x, y, w, 1.0) - true).max())
