from urllib.parse import urlencode
from datetime import datetime
import subprocess
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


def download(
    flight_line,
    nisar_mode=MODE_CHOICES[0],
    file_type="h5",
    pol="VV",
    start_date=datetime(2008, 1, 1),
    end_date=datetime(2030, 1, 1),
    verbose=True,
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
    start_date=datetime(2008, 1, 1),
    end_date=datetime(2030, 1, 1),
    verbose=True,
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
    start_date=datetime(2008, 1, 1),
    end_date=datetime(2030, 1, 1),
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
    start_date=datetime(2008, 1, 1),
    end_date=datetime(2030, 1, 1),
    flight_line=23511,
    **kwargs,
):
    """"""
    start_date = start_date.strftime(DATE_FMT)
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
