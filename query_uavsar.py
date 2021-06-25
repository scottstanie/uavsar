#!/usr/bin/env python
"""
Download NISAR-simulated UAVSAR products from specified flight lines

Author: Scott Staniewicz
"""
import argparse
from datetime import datetime
import os
import subprocess
import requests
import parsers

import sys
try:
    from concurrent.futures import ThreadPoolExecutor
    PARALLEL = True

except ImportError:
    PARALLEL = False

if sys.version_info.major == 2:
    from urllib import urlencode
else:
    from urllib.parse import urlencode


# URL for all UAVSAR searches
BASE_URL = "https://uavsar.jpl.nasa.gov/cgi-bin/data.pl?{params}"

# DOWNLOAD_URL = "https://downloaduav.jpl.nasa.gov/Release2{char}/{product}/{data}"
# ^^ this gets redirected to the following:
DOWNLOAD_URL = "https://uavsar.jpl.nasa.gov/Release2{char}/{product}/{data}"
# e.g., SanAnd_23511_14068_001_140529_L090_CX_02/SanAnd_23511_14068_001_140529_L090_CX_143_02.h5
# Not sure what possible chars are... so we'll test all a-z
RELEASE_CHARS = [chr(n) for n in range(ord("a"), ord("z") + 1)]

# info for one product
INFO_URL = "https://uavsar.jpl.nasa.gov/cgi-bin/product.pl?jobName={product}"
# For example:
# https://uavsar.jpl.nasa.gov/cgi-bin/product.pl?jobName=SanAnd_23511_14128_002_140829_L090_CX_02#data

# Loaction to save URLS, which is file-type/pol-specific
URL_FILE_DEFAULT = "uavsar_download_urls_{file_type}{pol}.txt"

DATE_FMT = "%y%m%d"
# Make all possible NISAR mode combinations
MODE_CHOICES_H5 = ["129", "138", "143"]
MODE_CHOICES = [num + ab for num in MODE_CHOICES_H5 for ab in ["a", "b"]]

# These files have no polarization in file name (e.g. only L090, not L090VV)
NO_POL_FILETYPES = ("ann", "inc", "flat.inc", "slope", "rtc", "hgt", "kmz", "h5")
POLARIZATION_CHOICES = [
    p.lower() for p in parsers.SINGLE_POLARIZATIONS + parsers.CROSS_POLARIZATIONS
]

# default query params for narrowing dates
EARLIEST = datetime(2008, 1, 1)
FUTURE = datetime(2030, 1, 1)


def download(
    flight_line,
    nisar_mode=MODE_CHOICES[0],
    file_type="h5",
    pol="vv",
    start_date=None,
    end_date=None,
    url_file=URL_FILE_DEFAULT,
    out_dir=".",
    verbose=True,
    **kwargs
):
    """Gather all download urls associated with one flight line

    Function will search for just one file_type/pol/nisar-mode combination.

    These will be optionally written to `url_file` if provided.
    If the `url_file` provided already exists, this function will just read from it.

    Args:
        flight_line (int): flight line of the UAVSAR mission
        nisar_mode (str): optional
        file_type (str): Type of UAVSAR product to download (e.g. h5 for HDF5, slc, mlc, inc...)
            default=h5
        pol (str): polarization. Optional for h5 products.
        start_date (str or datetime): starting date to limit search. If str, format = YYMMDD
        end_date (str or datetime): ending date to limit search. If str, format = YYMMDD
        url_file (str): Name of file to save urls from query.
            default= "uavsar_download_urls_FILE_TYPE.txt", e.g.
            "uavsar_download_urls_h5.txt" for the HDF5 files
        out_dir (str): Directory to save downloaded products. Default=current directory.
            If out_dir doesn't exist, will create.
        verbose (bool): Print debug information (default=True)

    Returns:
        url_list (list[str]): urls for downloading each data product

    Reference: https://uavsar.jpl.nasa.gov/science/documents/nisar-sample-products.html
    """
    if out_dir != ".":
        mkdir_p(out_dir)

    url_list = find_data_urls(
        flight_line,
        nisar_mode=nisar_mode,
        file_type=file_type,
        pol=pol,
        start_date=start_date,
        end_date=end_date,
        url_file=url_file,
        verbose=verbose,
    )
    for url in url_list:
        cmd = "wget --no-clobber {url}".format(url=url)
        print(cmd)
        subprocess.run(cmd, shell=True)
        # Move the output from wget into the output dir, if specified
        if out_dir != ".":
            saved_file = url.split("/")[-1]
            os.rename(saved_file, os.path.join(out_dir, saved_file))


def find_data_urls(
    flight_line,
    nisar_mode=MODE_CHOICES[0],
    file_type="h5",
    pol="vv",
    start_date=None,
    end_date=None,
    url_file=URL_FILE_DEFAULT,
    verbose=True,
    **kwargs
):
    """Search and save download urls for a flight line.
    See `download` for all option information
    """
    # clear '.' if it was passed
    file_type_nodot = file_type.lstrip(".").lower()
    # Check / remove polarization, depending on file type
    if pol:
        pol = pol.upper()
    if file_type_nodot in NO_POL_FILETYPES:
        pol = ""

    if url_file == URL_FILE_DEFAULT:
        url_file = URL_FILE_DEFAULT.format(file_type=file_type_nodot, pol=pol)
    print("url_file = {}".format(url_file))
    if url_file and os.path.exists(url_file):
        print("Found existing {} to read from.".format(url_file))
        with open(url_file) as f:
            return f.read().splitlines()

    product_list = find_nisar_products(
        flight_line,
        start_date=start_date,
        end_date=end_date,
        verbose=verbose,
    )
    url_list = []
    print("Finding urls for {} products".format(len(product_list)))
    for product in product_list:
        data = _form_dataname(
            product, nisar_mode=nisar_mode, file_type=file_type_nodot, pol=pol
        )
        url = _check_letters(product, data)
        if url:
            url_list.append(url)

    if url_file:
        print("Writing urls to {}".format(url_file))
        with open(url_file, "w") as f:
            f.write("\n".join(url_list) + "\n")

    return url_list


def _check_letters(product, data):
    """Searches all possible download urls for the variation on
    uavsar.jpl.nasa.gov/Release2{char}

    TODO: If I find any pattern as to why some products are under,
    for example, Release2a, then stop this hack and just use that.
    """
    print("searching for product = {} , data = {}".format(product, data))
    # Just send a HEAD request until one returns a 200
    possible_urls = [
        DOWNLOAD_URL.format(product=product, data=data, char=testchar)
        for testchar in RELEASE_CHARS
    ]
    # Search 10 at a time for correct url
    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = executor.map(requests.head, possible_urls)
        codes = [resp.status_code for resp in responses]
        for url, status_code in zip(possible_urls, codes):
            if status_code == 200:
                return url
        print(
            "WARNING: no successful download url from {}. "
            "Check {}".format(product, INFO_URL.format(product=product))
        )
        return None


def _form_dataname(product, file_type=".slc", nisar_mode="129a", pol="vv"):
    """Combine the product, file-type, nisar mode, and polarization
    to make the correct file name to download
    """
    file_type_nodot = file_type.lstrip(".").lower()
    if file_type_nodot in ("mlc", "grd"):
        if pol and pol not in parsers.CROSS_POLARIZATIONS:
            raise ValueError("{} not a valid pol for .mlc, .grd files".format(pol))
    elif file_type_nodot == "slc":
        if pol and pol not in parsers.SINGLE_POLARIZATIONS:
            raise ValueError(
                "{} not a valid pol for .slc "
                "(choices = {}".format(pol, parsers.SINGLE_POLARIZATIONS)
            )

    nisar_mode = nisar_mode.upper()
    if file_type_nodot == "h5":
        # only HDF5 files have the NISAR mode stripped, inlcudes both
        nisar_mode = nisar_mode.strip("AB")

    # pol is placed in the "band_squint_pol" field
    parsed = parsers.Uavsar(product)
    if pol:
        bsp = parsed["band_squint_pol"]
        product = product.replace(bsp, bsp + pol)
    xtalk = parsed["xtalk"]
    dither = parsed["dither"]
    before = "_" + xtalk + dither + "_"
    after = before + nisar_mode + "_"
    product = product.replace(before, after)
    return product + "." + file_type_nodot


def mkdir_p(path):
    """Emulates bash `mkdir -p`, in python style
    Used for output directory creation
    """
    import errno

    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def find_nisar_products(
    flight_line,
    start_date=None,
    end_date=None,
    verbose=True,
):
    """Parse the query results for one flight line, scraping the url for all
    related products.

    The url from `form_url` gives just an HTML snippet, which is parsed by
    `LinkFinder` for all the <a> tags
    """
    search_url = form_url(
        flight_line=flight_line, start_date=start_date, end_date=end_date
    )
    print("Querying {}".format(search_url))
    response = requests.get(search_url)
    lf = parsers.LinkFinder(verbose=False)
    lf.feed(response.text)
    if verbose:
        for product in lf.products:
            print(INFO_URL.format(product=product))
    return lf.products


def form_url(
    start_date=None,
    end_date=None,
    flight_line=23511,
    **kwargs
):
    """Given a flight line and date range, create url query to grab all flights"""
    if not start_date:
        start_date = EARLIEST
    if not end_date:
        end_date = FUTURE
    if isinstance(start_date, datetime):
        start_date = start_date.strftime(DATE_FMT)
    if isinstance(end_date, datetime):
        end_date = end_date.strftime(DATE_FMT)

    # These all seem to be required for the UAVSAR query to work
    params = [
        ("fname", "searchUavsar"),
        ("args", flight_line),
        ("searchText", flight_line),
        ("args", start_date),
        ("startDate", start_date),
        ("args", end_date),
        ("endDate", end_date),
        ("args", "PolSAR"),
        ("modeList", "PolSAR"),
        ("args", "L-band,simulated-nisar"),
        ("bandList", "L-band,simulated-nisar"),
        ("args", "single-pol,quad-pol"),
        ("polList", "single-pol,quad-pol"),
        ("args", flight_line),
        ("flownData", flight_line),
        ("args", flight_line),
        ("lineID", flight_line),
        ("args", "simulated-nisar"),
        ("simulatedNisar", "simulated-nisar"),
    ]
    return BASE_URL.format(params=urlencode(params))


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
        default="h5",
        type=str.lower,
    )
    p.add_argument(
        "--nisar-mode",
        default="129a",
        choices=MODE_CHOICES,
        help="NISAR mode of product (default=%(default)s)",
        type=str.lower,
    )
    p.add_argument(
        "--start-date",
        help="Starting date for query (YYMMDD)",
    )
    p.add_argument(
        "--end-date",
        help="Ending date for query (YYMMDD)",
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
    args.verbose = not args.quiet
    print("Arguments for search:")
    print(vars(args))

    if args.query_only:
        print("Only finding URLs for download:")
        url_list = find_data_urls(**vars(args))
        print("\n".join(url_list))
    else:
        print("Searching and downloading to ", args.out_dir)
        download(**vars(args))


if __name__ == "__main__":
    cli()
