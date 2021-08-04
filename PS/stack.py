import os
import re
from glob import glob

import numpy as np
import rasterio as rio
import hdf5plugin
import h5py
from download.logger import get_log
from geoslc.parsers import UavsarHDF5


log = get_log()
PSDIR = "ps_data"
SLC_DSET = "slcs"
DATE_DSET = "date"
AZ_DIM = "az_idx"
RANGE_DIM = "range_idx"

__all__ = ["create_slc_stack"]


def create_slc_stack(
    path=".",
    h5dir="data/",
    outname="PS/slc_stack.h5",
    dset_name=SLC_DSET,
    overwrite=False,
    compress=False,
):
    outpath = os.path.abspath(os.path.join(path, outname))
    h5path = os.path.abspath(os.path.join(path, h5dir))

    fnames = find_slcs(path)
    log.info("Found %s SLCs" % len(fnames))

    h5files = find_h5files(path + "/data")
    log.info("Found %s HDF5 files" % len(h5files))

    mkdir_p(os.path.dirname(outpath))
    if not check_dset(outpath, dset_name, overwrite):
        log.info("Skipping creation of %s/%s", outpath, dset_name)
        return

    h5files = find_h5files(h5path)

    rows, cols = _get_image_size(fnames[0])
    num_slc = len(fnames)
    shape = (num_slc, rows, cols)

    create_dset(outpath, dset_name, shape, "complex64", compress=compress)
    slc_date_list = []

    for idx, (fname, cur_h5) in enumerate(zip(fnames, h5files)):
        with rio.open(fname) as src, h5py.File(outpath, "a") as hf_out:
            coreg_slc = src.read(1)
            # Get the calibration file to normalize
            uav = UavsarHDF5(cur_h5)
            cal_slc = uav.calibrate_slc(to="gamma0", slc=coreg_slc, row_end=rows)
            log.info(f"Writing {idx + 1}/{num_slc}")
            hf_out[dset_name][idx] = cal_slc

            slc_date_list.append(get_slc_date_str(fname))

    # Now add the dates and dummy indexes as scales of the dataset
    with h5py.File(outpath, "a") as hf:
        stack = hf[dset_name]
        ndate, naz, nrange = stack.shape

        dim_names = [DATE_DSET, AZ_DIM, RANGE_DIM]
        az_idxs = np.arange(naz, dtype=int)
        range_idxs = np.arange(nrange, dtype=int)
        dim_data = [slc_date_list, az_idxs, range_idxs]
        for idx, (name, data) in enumerate(zip(dim_names, dim_data)):
            hf[name] = data
            hf[name].make_scale(name)
            stack.dims[idx].label = name
            stack.dims[idx].attach_scale(hf[name])


def create_dset(h5file, dset_name, shape, dtype, chunks=True, compress=True):
    """Create an empty [chunked] [compressed] dataset"""
    comp_dict = hdf5plugin.Blosc() if compress else dict()
    with h5py.File(h5file, "a") as f:
        f.create_dataset(
            dset_name, shape=shape, dtype=dtype, chunks=chunks, **comp_dict
        )


def find_files(path, search_term):
    return sorted(glob(os.path.join(path, search_term)))


# Assumption based on the ISCE strimpmapStack processor layout
def find_slcs(path="."):
    return find_files(path, "merged/SLC/*/*.slc.vrt")


def get_slc_date_str(slc_path):
    fname = os.path.split(slc_path)[1]
    match = re.search(r"\d{8}", fname)
    if not match:
        raise ValueError("{} does not contain date as YYYYMMDD".format(fname))
    return match.group()


def find_h5files(path="."):
    return sorted(glob(os.path.join(path, "*h5")))


def find_ifgs(path="."):
    return find_files(path, "Igrams/*/2*.int")


def _get_image_size(fname):
    with rio.open(fname) as src:
        return src.shape


def mkdir_p(path):
    """Emulates bash `mkdir -p`, in python style. Ignores if exists"""
    import errno

    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def check_dset(h5file, dset_name, overwrite, attr_name=None):
    """Returns false if the dataset exists and overwrite is False

    If overwrite is set to true, will delete the dataset to make
    sure a new one can be created
    """
    with h5py.File(h5file, "a") as f:
        if attr_name is not None:
            if attr_name in f.get(dset_name, {}):
                log.info(f"{dset_name}:{attr_name} already exists in {h5file},")
                if overwrite:
                    log.info("Overwrite true: Deleting.")
                    del f[dset_name].attrs[attr_name]
                else:
                    log.info("Skipping.")
                    return False
        else:
            if dset_name in f:
                log.info(f"{dset_name} already exists in {h5file},")
                if overwrite:
                    log.info("Overwrite true: Deleting.")
                    del f[dset_name]
                else:
                    log.info("Skipping.")
                    return False

        return True
