import os
import shutil
import numpy as np
from math import ceil, floor, cos, sin, sqrt
import numba
from numba import njit, cuda, jit
from uaquery.logger import get_log, log_runtime

log = get_log()

from . import orbit, orbit_gpu, parsers, utils

from joblib import Parallel, delayed


@log_runtime
def main(
    hdf5_file,
    demfile="elevation.dem",
    frequency="A",
    polarization="VV",
    dtype=np.complex64,
    outfile=None,
    gpu=True,
):
    frequency = frequency.upper()
    polarization = polarization.upper()
    if outfile is None:
        outfile = (
            hdf5_file.replace(".h5", "frequency{}_{}".format(frequency, polarization))
            + ".geo.slc"
        )
        log.info("Writing results to %s", outfile)
    uav = parsers.UavsarHDF5(hdf5_file)
    lam = uav.get_wavelength(frequency)

    # Get orbit time, position, velocity
    tt, xx, vv = uav.get_orbit()

    slant_ranges = uav.get_slant_ranges(frequency)
    # Slant range limits and spacing
    r_near, r_far = slant_ranges[0], slant_ranges[-1]
    delta_r = slant_ranges[1] - slant_ranges[0]
    log.info("Near, far range, delta_r: %s, %s, %s", r_near, r_far, delta_r)

    # Get azimuth time data: limits, spacing (pulse repitition interval)
    # prf = uav.get_prf(frequency)
    # pri = uav.get_pri()
    zero_dop_times = uav.get_zero_doppler_times()
    t_start, t_end = zero_dop_times[0], zero_dop_times[-1]
    pri = zero_dop_times[1] - zero_dop_times[0]
    log.info("Start, end pulse times, PRI: %s, %s, %s", t_start, t_end, pri)

    # Get DEM and DEM lat/lon data
    lon_arr, lat_arr = utils.get_latlon_arrs(demfile + ".rsc")
    lat_arr = np.deg2rad(lat_arr)
    lon_arr = np.deg2rad(lon_arr)

    log.info("Loading SLC:")
    # TODO: ever need to dump to flat file parts at a time?
    slc = uav.get_slc(frequency, polarization, dtype=dtype)

    log.info("slc.shape = %s", slc.shape)
    # assert slc.shape == (len(zero_dop_times), len(slant_ranges))

    if not gpu:
        # Call wrapper for parallel CPU version
        out = geocode_cpu(
            slc,
            demfile,
            lat_arr,
            lon_arr,
            lam,
            tt,
            xx,
            vv,
            t_start,
            t_end,
            pri,
            r_near,
            r_far,
            delta_r,
        )
    else:
        log.info("Loading DEM:")
        dem = utils.load_dem(demfile)
        log.info("dem.shape = %s", dem.shape)

        threadsperblock = (16, 16)
        blockspergrid_x = ceil(dem.shape[0] / threadsperblock[0])
        blockspergrid_y = ceil(dem.shape[1] / threadsperblock[1])
        blockspergrid = (blockspergrid_x, blockspergrid_y)
        log.info("Geocoding and phase compensating SLC on GPU")
        log.info(
            "(blocks per grid, threads per block) = ((%s, %s), (%s, %s))",
            *blockspergrid,
            *threadsperblock
        )

        out = np.zeros(dem.shape, dtype=slc.dtype)
        geocode_gpu[blockspergrid, threadsperblock](
            slc,
            dem,
            lat_arr,
            lon_arr,
            lam,
            tt,
            xx,
            vv,
            t_start,
            t_end,
            pri,
            r_near,
            r_far,
            delta_r,
            out,
        )

    if outfile:
        out.tofile(outfile)
    return out


@njit(nogil=True)
def interp(slc, az_idx, rg_idx):
    """Interpolate the image `slc` at fractional az bin (row) `az_idx`
    and fractional range bin index `rg_idx`"""
    az_floor = int(floor(az_idx))
    az_ceil = int(ceil(az_idx))
    pct_to_ceil_az = az_idx - floor(az_idx)

    rg_floor = int(floor(rg_idx))
    rg_ceil = int(ceil(rg_idx))
    pct_to_ceil_rg = rg_idx - floor(rg_idx)

    # Interpolate in the range direction for floor, ceil of az index
    rg_interped_low = (1 - pct_to_ceil_rg) * slc[
        az_floor, rg_floor
    ] + pct_to_ceil_rg * slc[az_floor, rg_ceil]
    rg_interped_high = (1 - pct_to_ceil_rg) * slc[
        az_ceil, rg_floor
    ] + pct_to_ceil_rg * slc[az_ceil, rg_ceil]
    # Then interpolate these results in the azimuth direction
    return (1 - pct_to_ceil_az) * rg_interped_low + pct_to_ceil_az * rg_interped_high


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
    t_start,
    t_end,
    pri,
    r_near,
    r_far,
    delta_r,
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

    lat = lat_arr[i]
    lon = lon_arr[j]
    h = dem[i, j]
    # output: into the thread-local xyz
    xyz_temp = cuda.local.array(3, dtype=numba.float64)
    orbit_gpu.llh_to_xyz_single(lat, lon, h, xyz_temp)

    # make thread-local containers for sat x/v and LOS vec
    satx = cuda.local.array(3, dtype=numba.float64)
    satv = cuda.local.array(3, dtype=numba.float64)
    dr_vec = cuda.local.array(3, dtype=numba.float64)
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

    # if i == 0 and j == 0:
    #     print(tline, cur_range)
    az_idx = (tline - t_start) / pri
    rg_idx = (cur_range - r_near) / delta_r

    # Interpolate between az/range
    slc_interp = interp(slc, az_idx, rg_idx)
    # add the phase compensation for range
    phase = 4.0 * 3.1415926535 * cur_range / lam
    phase_cpx = cos(phase) + 1j * sin(phase)
    out[i, j] = slc_interp * phase_cpx


# @njit
def _geocode_cpu_row(
    i,
    slc,
    dem,
    lat_arr,
    lon_arr,
    lam,
    tt,
    xx,
    vv,
    t_start,
    t_end,
    pri,
    r_near,
    r_far,
    delta_r,
    out,
):

    if i % 100 == 0:
        print("Processing row", i, "/", dem.shape[0])

    row = np.zeros(dem.shape[1], dtype=np.complex64)
    for j in range(dem.shape[1]):
        lat = lat_arr[i]
        lon = lon_arr[j]
        h = dem[i, j]
        xyz = orbit.llh_to_xyz(lat, lon, h)

        tline, dr_vec = orbit.orbitrangetime(xyz, tt, xx, vv)
        if tline < t_start or tline > t_end:
            continue
        cur_range = sqrt(dr_vec[0] ** 2 + dr_vec[1] ** 2 + dr_vec[2] ** 2)
        if cur_range < r_near or cur_range > r_far:
            continue

        # Get the fractional indices for range and azimuth
        az_idx = (tline - t_start) / pri
        rg_idx = (cur_range - r_near) / delta_r

        # Interpolate az/range, add the phase compensation for range
        slc_interp = interp(slc, az_idx, rg_idx)
        # add the phase compensation for range
        phase = 4.0 * 3.1415926535 * cur_range / lam
        phase_cpx = cos(phase) + 1j * sin(phase)
        # return slc_interp * phase_cpx
        # out[i, j] = slc_interp * phase_cpx
        row[j] = slc_interp * phase_cpx
    out[i, :] = row
    # return row


def geocode_cpu(
    slc,
    demfile,
    lat_arr,
    lon_arr,
    lam,
    tt,
    xx,
    vv,
    t_start,
    t_end,
    pri,
    r_near,
    r_far,
    delta_r,
):
    # Storing temporary output as a memory map
    folder = "./joblib_memmap"
    try:
        os.mkdir(folder)
    except FileExistsError:
        pass
    tmp_slc = os.path.join(folder, "tmp.slc")
    log.info("Dumping SLC to %s", tmp_slc)
    slc.tofile(tmp_slc)
    log.info("Memmapping SLC and DEM")
    slc = np.memmap(tmp_slc, dtype=slc.dtype, shape=slc.shape, mode="r")
    dem = np.memmap(
        demfile, dtype=np.int16, shape=(len(lat_arr), len(lon_arr)), mode="r"
    )

    output_filename_memmap = os.path.join(folder, "output_memmap")
    # memmap for shared writing
    out = np.memmap(
        output_filename_memmap, dtype=slc.dtype, shape=dem.shape, mode="w+"
    )

    # Process one row at a time in parallel
    par = Parallel(n_jobs=min(os.cpu_count(), 20))
    par(
        delayed(_geocode_cpu_row)(
            i,
            slc,
            dem,
            lat_arr,
            lon_arr,
            lam,
            tt,
            xx,
            vv,
            t_start,
            t_end,
            pri,
            r_near,
            r_far,
            delta_r,
            out,
        )
        # for i in range(1000)
        for i in range(dem.shape[0])
    )
    # out = np.vstack(rows)
    try:
        shutil.rmtree(folder)
    except:  # noqa
        log.warning("Could not clean-up automatically.")
    return out
