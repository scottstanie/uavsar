from .constants import EARTH_E2, EARTH_SMA
import numpy as np
from math import sin, cos, sqrt

from numba import njit


@njit(fastmath=True, nogil=True)
def orbitrangetime(
    xyz, tt, xx, vv, tline0=None, satx0=None, satv0=None, tol=5e-9, max_iter=100
):
    """Find the radar location (time, range) for the zero doppler point
    corresponding to `xyz`

    Args:
        xyz (ndarray): 3-vector for ground point (in ECEF)
        tt (ndarray): vector of orbit pulse times
        xx (ndarray): 2D vector, each row is (x, y, z) orbit position
        vv (ndarray): 2D vector, each row is (vx, vy, vz) orbit velocity
        tline0 (float): initial guess for time iteration
        satx0 (ndarray): initial guess for satellite position iteration
        satv0 (ndarray): initial guess for satellite velocity iteration
        tol (float): tolerance for time iteration convergence
        max_iter (int): maximum number of iterations for newton raphson loop

    Returns:
        tline (float): zero doppler time for `xyz`
        dr (ndarray): the relative 3-vector pointing from satellite to ground point

    """
    n = len(tt)
    if tline0 is None:
        tline0 = tt[n // 2]
    if satx0 is None:
        satx0 = xx[n // 2]
    if satv0 is None:
        satv0 = vv[n // 2]
    # starting state
    tline = tline0
    satx = satx0
    satv = satv0

    idx = 1
    tprev = tline + 1  # Need starting guess
    while abs(tline - tprev) > tol and idx < max_iter:
        tprev = tline

        dr = xyz - satx

        fn = np.dot(dr, satv)
        fnprime = -np.dot(satv, satv)

        tline = tline - fn / fnprime

        satx, satv = intp_orbit(tt, xx, vv, tline)

        idx += 1

    dr = xyz - satx

    return tline, dr  # r


@njit(fastmath=True, nogil=True)
def intp_orbit(tt, xx, vv, t):
    # if np.isposinf(t) or np.isneginf(t) or np.isnan(t):
    #     return None, None

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

    satx, satv = orbithermite(
        tt[ilocation : ilocation + 4],
        xx[ilocation : ilocation + 4],
        vv[ilocation : ilocation + 4],
        t,
    )
    return satx, satv


@njit(fastmath=True, nogil=True)
def orbithermite(tt, xx, vv, t):
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
    n = len(tt)
    # Lagrange basis polynomials
    li = np.ones(n)
    # basis polynomials alpha(t)
    a = np.zeros(n)
    # basis polynomials beta(t)
    b = np.zeros(n)
    # derivative of alpha(t)
    a2 = np.zeros(n)
    # derivative of beta(t)
    b2 = np.zeros(n)
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

    xout = np.zeros(3)
    vout = np.zeros(3)
    for j in range(3):
        xout[j] = 0
        vout[j] = 0
        for i in range(n):
            xout[j] += a[i] * xx[i][j] + b[i] * vv[i][j]
            vout[j] += a2[i] * xx[i][j] + b2[i] * vv[i][j]
    return xout, vout


def orbithermite_scipy(tt, xx, vv, t):
    """Hermite polynomial interpolation of orbits,
    using scipy.interpolate.CubicHermiteSpline

    Args:
        tt - 4-vector of times for each of the above data points
        xx - 3x4 matrix of positions at four times
        xv - 3x4 matrix of velocities
        t - time to interpolate orbit to

    Outputs
        xout: length 3 ndarray, position at time `t`
        vout: length 3 ndarray, velocity at tim:
    """
    from scipy.interpolate import CubicHermiteSpline

    x_intp = CubicHermiteSpline(tt[:4], xx[:4], vv[:4])
    xout = x_intp(t)
    v_intp = x_intp.derivative()
    vout = v_intp(t)
    return xout, vout


@njit(nogil=True)
# @njit
def llh_to_xyz(lat, lon, h):
    """Lat, lon (in radians), height to ECEF X,Y,Z"""
    rad_earth = EARTH_SMA / sqrt(1.0 - EARTH_E2 * sin(lat) ** 2)

    xyz = np.zeros((3,), dtype=np.float32)
    xyz[0] = (rad_earth + h) * cos(lat) * cos(lon)
    xyz[1] = (rad_earth + h) * cos(lat) * sin(lon)
    xyz[2] = (rad_earth * (1.0 - EARTH_E2) + h) * sin(lat)
    return xyz


@njit
def xyz_to_llh_f(xyz):
    """Copy from fortran code"""
    r_a = EARTH_SMA
    r_e2 = EARTH_E2

    # convert vector to lat,lon

    r_q2 = 1.0 / (1.0 - r_e2)
    r_q = sqrt(r_q2)
    r_q3 = r_q2 - 1.0
    r_b = r_a * sqrt(1.0 - r_e2)

    llh = np.zeros(3)
    llh[1] = np.arctan2(xyz[1], xyz[0])

    r_p = sqrt(xyz[0] ** 2 + xyz[1] ** 2)
    r_tant = (xyz[2] / r_p) * r_q
    r_theta = np.arctan(r_tant)
    r_tant = (xyz[2] + r_q3 * r_b * sin(r_theta) ** 3) / (
        r_p - r_e2 * r_a * cos(r_theta) ** 3
    )
    llh[0] = np.arctan(r_tant)
    r_re = r_a / sqrt(1.0 - r_e2 * sin(llh[0]) ** 2)
    llh[2] = r_p / cos(llh[0]) - r_re

    return llh
