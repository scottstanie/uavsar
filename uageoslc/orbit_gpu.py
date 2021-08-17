import numba
from numba import cuda
from .constants import EARTH_E2, EARTH_SMA


from math import sin, cos, sqrt, isnan


@cuda.jit
def llh_to_xyz_arr(lat_arr, lon_arr, dem, xyz_out):
    """arrays of Lat, lon (in radians), heights, to 3D array of ECEF X,Y,Z"""
    # Check for GPU bounds
    i, j = cuda.grid(2)
    if not (0 <= i < dem.shape[0] and 0 <= j < dem.shape[1]):
        # Skip this thread if it's out of bounds
        return

    lat = lat_arr[i]
    lon = lon_arr[j]
    h = dem[i, j]
    rad_earth = EARTH_SMA / sqrt(1.0 - EARTH_E2 * sin(lat) ** 2)

    x = (rad_earth + h) * cos(lat) * cos(lon)
    y = (rad_earth + h) * cos(lat) * sin(lon)
    z = (rad_earth * (1.0 - EARTH_E2) + h) * sin(lat)
    xyz_out[0, i, j] = x
    xyz_out[1, i, j] = y
    xyz_out[2, i, j] = z


@cuda.jit(device=True)
def llh_to_xyz_single(lat, lon, h, xyz):
    """Lat, lon (in radians), height to ECEF X,Y,Z"""
    rad_earth = EARTH_SMA / sqrt(1.0 - EARTH_E2 * sin(lat) ** 2)

    xyz[0] = (rad_earth + h) * cos(lat) * cos(lon)
    xyz[1] = (rad_earth + h) * cos(lat) * sin(lon)
    xyz[2] = (rad_earth * (1.0 - EARTH_E2) + h) * sin(lat)
    return xyz


@cuda.jit(device=True)
def gdot(vec1, vec2):
    return vec1[0] * vec2[0] + vec1[1] * vec2[1] + vec1[2] * vec2[2]


# @njit(nogil=True)
# def orbitrangetime_gpu_cpu(xyz, tt, xx, vv, satx, satv, dr_vec):
@cuda.jit(device=True)
def orbitrangetime_gpu(xyz, tt, xx, vv, satx, satv, dr_vec):
    """Find the radar location (time, range) for the zero doppler point
    corresponding to `xyz`

    Args:
        xyz (ndarray): 3-vector for ground point (in ECEF)
        tt (ndarray): vector of orbit pulse times
        xx (ndarray): 2D vector, each row is (x, y, z) orbit position
        vv (ndarray): 2D vector, each row is (vx, vy, vz) orbit velocity
        satx (ndarray): container for satellite position iteration
        satv (ndarray): container for satellite velocity iteration

    Returns:
        tline (float): zero doppler time for `xyz`
        r (float): range from satellite to ground point

    """
    n = len(tt)
    # starting state
    tline = tt[n // 2]
    for i in range(3):
        satx[i] = xx[n // 2, i]
        satv[i] = vv[n // 2, i]

    tol = 5e-9
    max_iter = 51
    idx = 1
    tprev = tline + 1  # Need starting guess
    while abs(tline - tprev) > tol and idx < max_iter:
        tprev = tline

        dr_vec[0] = xyz[0] - satx[0]
        dr_vec[1] = xyz[1] - satx[1]
        dr_vec[2] = xyz[2] - satx[2]

        fn = gdot(dr_vec, satv)
        fnprime = -gdot(satv, satv)

        tline = tline - fn / fnprime
        if isnan(tline):
            return 0.0, 0.0  # should be out of bounds for range, will skip

        intp_orbit_gpu(tt, xx, vv, tline, satx, satv)

        idx += 1

    dr_vec[0] = xyz[0] - satx[0]
    dr_vec[1] = xyz[1] - satx[1]
    dr_vec[2] = xyz[2] - satx[2]
    r = sqrt(gdot(dr_vec, dr_vec))

    return tline, r


@cuda.jit(device=True)
def intp_orbit_gpu(tt, xx, vv, t, satx, satv):

    n = len(tt)
    ilocation = 0
    min_delta_t = 1.0e10
    # find the location of the sampling time that is closest to t
    for i in range(n):
        delta_t = abs(t - tt[i])
        if delta_t < min_delta_t:
            min_delta_t = delta_t
            ilocation = i
    # Four points are needed for the Hermite interpolation
    # ilocation = np.clip(ilocation, 1, n - 4)
    if ilocation < 1:
        ilocation = 1
    elif ilocation > n - 4:
        ilocation = n - 4
    # print(ilocation)

    orbithermite_gpu(
        # orbithermite_gpu_cpu(
        tt[ilocation : ilocation + 4],
        xx[ilocation : ilocation + 4],
        vv[ilocation : ilocation + 4],
        t,
        satx,
        satv,
    )


@cuda.jit(device=True)
def orbithermite_gpu(tt, xx, vv, t, xout, vout):
    """orbithermite - hermite polynomial interpolation of orbits

    Args:
        tt - 4-vector of times for each of the above data points
        xx - 3x4 matrix of positions at four times
        xv - 3x4 matrix of velocities
        t - time to interpolate orbit to

    Outputs
        xout: length 3 ndarray, position at time `t`
        vout: length 3 ndarray, velocity at time `t`
    """
    # Lagrange basis polynomials
    li = cuda.local.array(4, dtype=numba.float64)
    for i in range(4):
        li[i] = 1.0
    # basis polynomials alpha(t)
    a = cuda.local.array(4, dtype=numba.float64)
    # basis polynomials beta(t)
    b = cuda.local.array(4, dtype=numba.float64)
    # derivative of alpha(t)
    a2 = cuda.local.array(4, dtype=numba.float64)
    # derivative of beta(t)
    b2 = cuda.local.array(4, dtype=numba.float64)

    n = len(tt)
    for i in range(n):
        dl = 0.0  # derivative of Lagrange basis at tt[i]
        hdot = 0.0  # derivative of Lagrange basis at t
        for j in range(n):
            if i == j:
                continue
            dl = dl + 1.0 / (tt[i] - tt[j])
            li[i] = li[i] * (t - tt[j]) / (tt[i] - tt[j])
            p = 1.0 / (tt[i] - tt[j])
            for k in range(n):
                if k == i or k == j:
                    continue
                p = p * (t - tt[k]) / (tt[i] - tt[k])
            hdot = hdot + p
        l2 = li[i] * li[i]
        a[i] = (1 - 2 * (t - tt[i]) * dl) * l2
        b[i] = (t - tt[i]) * l2
        a2[i] = -2 * dl * l2 + (1 - 2 * (t - tt[i]) * dl) * li[i] * 2 * hdot
        b2[i] = l2 + (t - tt[i]) * li[i] * 2 * hdot

    for j in range(3):
        xout[j] = 0
        vout[j] = 0
        for i in range(n):
            xout[j] += a[i] * xx[i][j] + b[i] * vv[i][j]
            vout[j] += a2[i] * xx[i][j] + b2[i] * vv[i][j]