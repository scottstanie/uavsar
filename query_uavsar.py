import argparse
from datetime import datetime
import subprocess
from urllib.parse import urlencode

import requests
import parsers

# todo: no way to ask for 1 specific pol file, like ..._L090HHHH_CX_02.grd

BASE_URL = "https://uavsar.jpl.nasa.gov/cgi-bin/data.pl?{params}"
DOWNLOAD_URL = "http://downloaduav.jpl.nasa.gov/Release2t/{product}/{data}"
# e.g., SanAnd_23511_14068_001_140529_L090_CX_02/SanAnd_23511_14068_001_140529_L090_CX_143_02.h5

# info for product
INFO_URL = "https://uavsar.jpl.nasa.gov/cgi-bin/product.pl?jobName={product}"
# https://uavsar.jpl.nasa.gov/cgi-bin/product.pl?jobName=SanAnd_23511_14128_002_140829_L090_CX_02#data

DATE_FMT = "%y%m%d"
MODE_CHOICES_H5 = ["129", "138", "143"]
MODE_CHOICES = [num + ab for num in MODE_CHOICES_H5 for ab in ["A", "B"]]

# default query params
EARLIEST = datetime(2008, 1, 1)
FUTURE = datetime(2030, 1, 1)


def download(
    flight_line,
    nisar_mode=MODE_CHOICES[0],
    file_type="h5",
    pol="VV",
    start_date=None,
    end_date=None,
    verbose=True,
    **kwargs,
):
    url_list = find_data_urls(
        flight_line,
        nisar_mode=nisar_mode,
        file_type=file_type,
        pol=pol,
        start_date=start_date,
        end_date=end_date,
        verbose=verbose,
    )
    for url in url_list:
        cmd = f"wget {url}"
        print(cmd)
        subprocess.run(cmd, shell=True)


def find_data_urls(
    flight_line,
    nisar_mode=MODE_CHOICES[0],
    file_type="h5",
    pol="VV",
    start_date=None,
    end_date=None,
    verbose=True,
    **kwargs,
):

    product_list = find_nisar_products(
        flight_line,
        start_date=start_date,
        end_date=end_date,
        verbose=verbose,
    )
    url_list = []
    for product in product_list:
        data = _form_dataname(
            product, nisar_mode=nisar_mode, file_type=file_type, pol=pol
        )
        url = DOWNLOAD_URL.format(product=product, data=data)
        url_list.append(url)
    return url_list


def _form_dataname(product, file_type=".slc", nisar_mode="129A", pol="VV"):
    # the NISAR HDF5 files have no pol or A/B
    file_type_nodot = file_type.replace(".", "")
    if file_type_nodot == "h5":
        nisar_mode = nisar_mode.upper().strip("AB")
        pol = ""
    elif file_type_nodot in ("mlc", "grd"):
        if pol and pol not in parsers.POLARIZATIONS:
            raise ValueError(f"{pol} not a valid pol for .mlc, .grd files")

    # clear and period if it was passed
    parsed = parsers.Uavsar(product)
    # pol is placed in the "band_squint_pol" field
    if pol:
        bsp = parsed["band_squint_pol"]
        product = product.replace(bsp, bsp + pol)
    xtalk = parsed["xtalk"]
    dither = parsed["dither"]
    product = product.replace(f"_{xtalk}{dither}_", f"_{xtalk}{dither}_{nisar_mode}_")
    return product + "." + file_type_nodot


def find_nisar_products(
    flight_line,
    start_date=None,
    end_date=None,
    verbose=True,
):
    search_url = form_url(
        flight_line=flight_line, start_date=start_date, end_date=end_date
    )
    print(f"Querying {search_url}")
    response = requests.get(search_url)
    lf = parsers.LinkFinder(verbose=verbose)
    lf.feed(response.text)
    if verbose:
        for product in lf.products:
            print(INFO_URL.format(product=product))
    return lf.products


def form_url(
    start_date=None,
    end_date=None,
    flight_line=23511,
    **kwargs,
):
    """"""
    if not start_date:
        start_date = EARLIEST
    if not end_date:
        end_date = FUTURE
    if isinstance(start_date, datetime):
        start_date = start_date.strftime(DATE_FMT)
    if isinstance(end_date, datetime):
        end_date = end_date.strftime(DATE_FMT)
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
    )
    p.add_argument(
        "--nisar-mode",
        default="129A",
        choices=MODE_CHOICES,
        help="NISAR mode of product (default=%(default)s)",
    )
    p.add_argument(
        "--relativeOrbit",
        type=int,
        help="Limit to one path / relativeOrbit",
    )
    p.add_argument(
        "--start-date",
        help=f"Starting date for query (YYMMDD)",
    )
    p.add_argument(
        "--end-date",
        help=f"Ending date for query (YYMMDD)",
    )
    # p.add_argument(
    #     "--out-dir",
    #     "-o",
    #     help="Path to directory for saving output files (default=%(default)s)",
    #     default="./",
    # )
    p.add_argument(
        "--query-only",
        action="store_true",
        help="display available data in format of --query-file, no download",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Limit output printing",
    )
    args = p.parse_args()
    args.verbose = not args.quiet
    print(vars(args))

    if args.query_only:
        find_data_urls(**vars(args))
    else:
        download(**vars(args))


if __name__ == "__main__":
    cli()
