import numpy as np
from math import ceil, floor, cos, sin, sqrt
from numba import njit, prange, cuda
from download.logger import get_log

log = get_log()

from apertools import sario, latlon  # TODO: port just necessary functions
from . import orbit, orbit_gpu, parsers


def main(
    hdf5_file,
    demfile="elevation.dem",
    frequency="A",
    polarization="VV",
    dtype=np.complex64,
    outfile=None,
    gpu=True,
):
    if outfile is None:
        outfile = (
            hdf5_file.replace(".h5", "frequency{}_{}".format(frequency, polarization))
            + ".geo.slc"
        )
        log.info("Writing results to ", outfile)
    uav = parsers.UavsarHDF5(hdf5_file)
    lam = uav.get_wavelength(frequency)

    # Get orbit time, position, velocity
    tt, xx, vv = uav.get_orbit()

    # Get range data
    slant_ranges = uav.get_slant_ranges(frequency)

    # Get azimuth time data
    # prf = uav.get_prf(frequency)
    # pri = uav.get_pri()
    zero_dop_times = uav.get_zero_doppler_times()

    # Get DEM and DEM lat/lon data
    log.info("Loading DEM:")
    dem = sario.load(demfile)
    log.info("dem.shape = ", dem.shape)
    rsc_data = sario.load(demfile + ".rsc")
    lon_arr, lat_arr = latlon.grid(**rsc_data, sparse=True)
    lon_arr = lon_arr.reshape(-1)
    lat_arr = lat_arr.reshape(-1)

    log.info("Loading SLC:")
    slc = uav.get_slc(frequency, polarization, dtype=dtype)
    log.info("slc.shape = ", slc.shape)
    # assert slc.shape == (len(zero_dop_times), len(slant_ranges))

    if not gpu:
        out = geocode_cpu(
            slc,
            dem,
            np.deg2rad(lat_arr),
            np.deg2rad(lon_arr),
            lam,
            tt,
            xx,
            vv,
            zero_dop_times,
            slant_ranges,
            # max_line=1000,
        )
    else:
        threadsperblock = (16, 16)
        blockspergrid_x = ceil(dem.shape[0] / threadsperblock[0])
        blockspergrid_y = ceil(dem.shape[1] / threadsperblock[1])
        blockspergrid = (blockspergrid_x, blockspergrid_y)
        log.info("Geocoding and phase compensating SLC on GPU")
        log.info(
            "(blocks per grid, threads per block) = ", (blockspergrid, threadsperblock)
        )

        # # To convert all LLH to XYZ in one step:
        # xyz_out = np.zeros((3, *dem.shape), dtype=np.float32)
        # First, convert all lat, lon, height to XYZ vectors
        # orbit_gpu.llh_to_xyz_arr[blockspergrid, threadsperblock](
        #     np.deg2rad(lat_arr), np.deg2rad(lon_arr), dem, xyz_out
        # )
        # log.info(xyz_out[:, 4, 4])

        out = np.zeros(dem.shape, dtype=slc.dtype)
        geocode_gpu[blockspergrid, threadsperblock](
            slc,
            dem,
            np.deg2rad(lat_arr),
            np.deg2rad(lon_arr),
            lam,
            tt,
            xx,
            vv,
            zero_dop_times,
            slant_ranges,
            out,
        )

    if outfile:
        out.tofile(outfile)
    return out


@njit(nogil=True)
def interp(slc, az_idx, rg_idx):
    """Interpolate the image `slc` at az bin (row) `az_idx` over the
    fractional range bin index `rg_idx`"""
    rg_floor = int(floor(rg_idx))
    rg_ceil = int(ceil(rg_idx))
    pct_to_ceil = rg_idx - floor(rg_idx)
    return (1 - pct_to_ceil) * slc[az_idx, rg_floor] + pct_to_ceil * slc[
        az_idx, rg_ceil
    ]


@cuda.jit
def geocode_gpu(
    slc,
    dem,
    lat_arr,
    lon_arr,
    lam,
    tt,
    xx,
    vv,
    zero_dop_times,
    slant_ranges,
    out,
):
    # num_lines = slc.shape[0]
    # nlat = len(lat_arr)
    # nlon = len(lon_arr)

    # Check for GPU bounds
    i, j = cuda.grid(2)
    if not (0 <= i < out.shape[0] and 0 <= j < out.shape[1]):
        # and not (0 <= i < dem.shape[0] and 0 <= j < dem.shape[1]):
        # Skip this thread if it's out of bounds
        # Maybe need more checks if i break into DEM blocks
        return

    # Slant range limits
    r_near, r_far = slant_ranges[0], slant_ranges[-1]
    delta_r = slant_ranges[1] - slant_ranges[0]
    log.info("Near, far range, delta_r:", (r_near, r_far, delta_r))
    # azimuth time data
    t_start, t_end = zero_dop_times[0], zero_dop_times[-1]
    pri = zero_dop_times[1] - zero_dop_times[0]
    log.info("Start, end pulse times, PRI:", (t_start, t_end, pri))

    lat = lat_arr[i]
    lon = lon_arr[j]
    h = dem[i, j]
    # output: into the thread-local xyz
    xyz_temp = cuda.local.array(3, dtype="float")
    orbit_gpu.llh_to_xyz_single(lat, lon, h, xyz_temp)

    # make thread-local containers for sat x/v and LOS vec
    satx = cuda.local.array(3, dtype="float")
    satv = cuda.local.array(3, dtype="float")
    dr_vec = cuda.local.array(3, dtype="float")
    tline, cur_range = orbit_gpu.orbitrangetime_gpu(
        xyz_temp,
        tt,
        xx,
        vv,
        satx,
        satv,
        dr_vec,
    )

    if tline < t_start or tline > t_end:
        return
    if cur_range < r_near or cur_range > r_far:
        return

    az_idx = round((tline - t_start) / pri)
    rg_idx = (cur_range - r_near) / delta_r

    # Interpolate between range, add the phase compensation for range
    slc_interp = interp(slc, az_idx, rg_idx)
    phase = 4.0 * 3.1415926535 * cur_range / lam
    complex_phase = cos(phase) + 1j * sin(phase)
    out[i, j] = slc_interp * complex_phase


# @njit(parallel=True)  # can't figure out why parallel is slower...
@njit
def geocode_cpu(
    slc,
    dem,
    lat_arr,
    lon_arr,
    lam,
    tt,
    xx,
    vv,
    zero_dop_times,
    slant_ranges,
    max_line=1000000,
):
    nlat = len(lat_arr)
    nlon = len(lon_arr)
    out = np.zeros((nlat, nlon), dtype=slc.dtype)

    # Slant range limits
    r_near, r_far = slant_ranges[0], slant_ranges[-1]
    delta_r = slant_ranges[1] - slant_ranges[0]
    log.info("Near, far range, delta_r:", (r_near, r_far, delta_r))
    # azimuth time data
    t_start, t_end = zero_dop_times[0], zero_dop_times[-1]
    pri = zero_dop_times[1] - zero_dop_times[0]
    log.info("Start, end pulse times, PRI:", (t_start, t_end, pri))

    r_near, r_far = slant_ranges[0], slant_ranges[-1]

    # prange here seems to make it slower when parallel = true?
    for i in prange(nlat):
        lat = lat_arr[i]
        if i > max_line:
            break
        if not i % 50:
            log.info("Line ", i, " / ", nlat)
        for j in range(nlon):
            lon = lon_arr[j]
            h = dem[i, j]
            xyz = orbit.llh_to_xyz(lat, lon, h)

            tline, dr_vec = orbit.orbitrangetime(xyz, tt, xx, vv)
            if tline < t_start or tline > t_end:
                continue
            cur_range = sqrt(dr_vec[0] ** 2 + dr_vec[1] ** 2 + dr_vec[2] ** 2)
            if cur_range < r_near or cur_range > r_far:
                continue

            az_idx = round((tline - t_start) / pri)
            rg_idx = (cur_range - r_near) / delta_r

            # Interpolate between range, add the phase compensation for range
            slc_interp = interp(slc, az_idx, rg_idx)
            phase = 4.0 * 3.1415926535 * cur_range / lam
            complex_phase = cos(phase) + 1j * sin(phase)
            out[i, j] = slc_interp * complex_phase
    return out
