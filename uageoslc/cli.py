import argparse
from uageoslc.geocode_slc import main


def cli():
    p = argparse.ArgumentParser()
    p.add_argument(
        "hdf5_file",
        help="UAVSAR HDF5 file containing SLCs",
    )
    p.add_argument(
        "--demfile",
        "-d",
        help="Filename of DEM to use for geocoding (default=%(default)s)",
        default="elevation.dem",
    )
    p.add_argument(
        "--pol",
        default="VV",
        choices=["HH", "HV", "VH", "VV"],
        help="Polarization (default=%(default)s)",
        type=str.upper,
    )
    p.add_argument(
        "--frequency",
        default="A",
        choices=["A", "B"],
        help="Frequency band to use ( choices = %(choices)s, default=%(default)s)",
        type=str.upper,
    )
    p.add_argument(
        "--outfile",
        "-o",
        help="File to save output (default = '{hdf5_file}_frequency{frequency}_{pol}.geo.slc')",
    )
    p.add_argument(
        "--gpu",
        action="store_true",
        help="Geocode on the GPU (requires numba/cuda installation), "
        "See https://numba.readthedocs.io/en/stable/cuda/overview.html#requirements",
    )

    args = p.parse_args()
    main(
        args.hdf5_file,
        demfile=args.demfile,
        frequency=args.frequency,
        polarization=args.pol,
        outfile=args.outfile,
        gpu=args.gpu,
    )
