#!/usr/bin/env python
import argparse
from datetime import datetime
from . import query_uavsar
from . import parsers
from .logger import get_log

log = get_log()


def cli():
    p = argparse.ArgumentParser()
    p.add_argument(
        "flight_line",
        type=int,
        help="UAVSAR flight line",
    )
    p.add_argument(
        "--file-type",
        help="Extension of radar product (default=%(default)s)",
        default="ann",
        type=str.lower,
    )
    p.add_argument(
        "--start-date",
        help="Starting date for query (formats accepts: YYYYMMDD, YYYY-MM-DD, yymmdd)",
        type=_valid_date,
    )
    p.add_argument(
        "--end-date",
        help="Ending date for query (formats accepts: YYYYMMDD, YYYY-MM-DD, yymmdd)",
        type=_valid_date,
    )
    p.add_argument(
        "--nisar-mode",
        default=None,
        choices=MODE_CHOICES,
        help=(
            "If searching for NISAR-simulated products, "
            "NISAR mode of product (default=%(default)s)"
        ),
        type=str.lower,
    )
    p.add_argument(
        "--pol",
        default="vv",
        choices=POLARIZATION_CHOICES,
        help="Polarization (for non-NISAR products, default=%(default)s)",
        type=str.lower,
    )
    p.add_argument(
        "--out-dir",
        "-o",
        help="Path to directory for saving output files (default=%(default)s)",
        default=".",
    )
    p.add_argument(
        "--query-only",
        action="store_true",
        help="display available data in format of --query-file, no download",
    )
    p.add_argument(
        "--url-file",
        default=URL_FILE_DEFAULT,
        help="File to save the URLs found for download (default=%(default)s)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Limit output printing",
    )
    args = p.parse_args()
    _check_valid_pol(args.pol, args.file_type)
    args.verbose = not args.quiet
    log.info("Arguments for search:")
    log.info(vars(args))

    if args.query_only:
        log.info("Only finding URLs for download:")
        url_list = query_uavsar.find_data_urls(**vars(args))
        log.info("\n".join(url_list))
    else:
        log.info("Searching and downloading to " + args.out_dir)
        query_uavsar.download(**vars(args))


def _check_valid_pol(pol, file_type):
    file_type_nodot = file_type.lstrip(".").lower()
    if file_type_nodot in ("mlc", "grd"):
        if pol and pol.upper() not in parsers.CROSS_POLARIZATIONS:
            raise ValueError(
                "{} not a valid pol for .mlc, .grd files. "
                "Choices: {}".format(pol.upper(), parsers.CROSS_POLARIZATIONS)
            )
    elif file_type_nodot == "slc":
        if pol and pol.upper() not in parsers.SINGLE_POLARIZATIONS:
            raise ValueError(
                "{} not a valid pol for .slc "
                "Choices = {}".format(pol.upper(), parsers.SINGLE_POLARIZATIONS)
            )


def _valid_date(arg_value):
    """Parse the date, making some guesses if they pass extra stuff
    Try and accept 2013-01-01, 13_01_01, 2013/01/01, 20130101, 130101"""
    arg = arg_value.replace("_", "").replace("-", "").replace("/", "")
    err_msg = "Not a valid date: '{}'.".format(arg_value)
    try:
        if len(arg) == 8:  # YYYYmmdd:
            return datetime.strptime(arg, "%Y%m%d")
        elif len(arg) == 6:
            return datetime.strptime(arg, DATE_FMT)
    except ValueError:
        raise argparse.ArgumentTypeError(err_msg)

    # Other cases don't match accepted format
    raise argparse.ArgumentTypeError(err_msg)


if __name__ == "__main__":
    cli()