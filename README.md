Contains two tools for working with [UAVSAR data](uavsar.jpl.nasa.gov/)

# Query and download tool: `uaquery`

Made for downloading the [NISAR-simulated products]() for UAVSAR, but can download any PolSAR images by not specifying `--nisar-mode`.

## Examples

To download all 20 MHz data as HDF5 products for one flight over the Central Valley:

```bash
uaquery 14511 --nisar-mode 129a --file-type h5
```

To just see which are available
```bash
uaquery 14511 --nisar-mode 129a --file-type h5 --query-only
```

To download just the annotation files for the non-NISAR products:
```bash
uaquery 14511 --file-type ann
```

See [the notebooks](https://github.com/scottstanie/uavsar/blob/main/notebooks/ISCE2%20Stack%20Processing%20of%20NISAR-simulated%20UAVSAR%20products.ipynb) for fuller usage examples.

```bash
$ uaquery -h
usage: uaquery [-h] [--file-type FILE_TYPE] [--start-date START_DATE] [--end-date END_DATE] [--nisar-mode {129a,129b,138a,138b,143a,143b}]
               [--pol {hh,hv,vh,vv,hhhh,hvhv,vvvv,hhhv,hhvv,hvvv}] [--out-dir OUT_DIR] [--query-only] [--url-file URL_FILE] [--quiet]
               flight_line

positional arguments:
  flight_line           UAVSAR flight line

optional arguments:
  -h, --help            show this help message and exit
  --file-type FILE_TYPE
                        Extension of radar product (default=ann)
  --start-date START_DATE
                        Starting date for query (formats accepts: YYYYMMDD, YYYY-MM-DD, yymmdd)
  --end-date END_DATE   Ending date for query (formats accepts: YYYYMMDD, YYYY-MM-DD, yymmdd)
  --nisar-mode {129a,129b,138a,138b,143a,143b}
                        If searching for NISAR-simulated products, NISAR mode of product (default=None)
  --pol {hh,hv,vh,vv,hhhh,hvhv,vvvv,hhhv,hhvv,hvvv}
                        Polarization (for non-NISAR products, default=vv)
  --out-dir OUT_DIR, -o OUT_DIR
                        Path to directory for saving output files (default=.)
  --query-only          display available data in format of --query-file, no download
  --url-file URL_FILE   File to save the URLs found for download (default=uavsar_download_urls_{file_type}{pol}{nisar_mode}.txt)
  --quiet               Limit output printing

```


# Create geocoded SLCs for easy use in InSAR: `uageocode`

Works on the HDF5 products (`--file-type h5` for the download tool) to geocode and remove topographic phase from SLC images.
See the [walkthrough notebook](https://github.com/scottstanie/uavsar/blob/main/notebooks/Geocode%20SLCs%20for%20NISAR%20simulated%20UAVSAR%20data.ipynb) for full example, including extra installation requirements (numpy, numba, h5py, joblib).
