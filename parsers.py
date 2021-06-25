import re
import sys
if sys.version_info.major == 2:
    from HTMLParser import HTMLParser
else:
    from html.parser import HTMLParser

# Filetype of real or complex depends on the polarization for .grd, .mlc
REAL_POLS = ("HHHH", "HVHV", "VVVV")
COMPLEX_POLS = ("HHHV", "HHVV", "HVVV")
CROSS_POLARIZATIONS = REAL_POLS + COMPLEX_POLS
SINGLE_POLARIZATIONS = ("HH", "HV", "VH", "VV")


class Base(object):
    """Base parser to illustrate expected interface/ minimum data available"""

    FILE_REGEX = None
    TIME_FMT = None

    def __init__(self, filename, verbose=False):
        """
        Extract data from filename
            filename (str): name of SAR/InSAR product
            verbose (bool): print extra logging into about file loading
        """
        self.filename = filename
        self.data_dict = self.full_parse()  # Run a parse to check validity of filename
        self.verbose = verbose

    def __str__(self):
        return "{} product: {}".format(self.__class__.__name__, self.filename)

    def __repr__(self):
        return str(self)

    def __lt__(self, other):
        return self.filename < other.filename

    def full_parse(self):
        """Returns all parts of the data contained in filename

        Returns:
            tuple: parsed file data. Entry order will match reged named fields

        Raises:
            ValueError: if filename string is invalid
        """
        if not self.FILE_REGEX:
            raise NotImplementedError("Must define class FILE_REGEX to parse")

        match = re.search(self.FILE_REGEX, self.filename)
        if not match:
            raise ValueError(
                "Invalid {} filename: {}".format(self.__class__.__name__, self.filename)
            )
        else:
            return match.groupdict()

    def _get_field(self, fieldname):
        """Pick a specific field based on its name"""
        return self.full_parse()[fieldname]

    def __getitem__(self, item):
        """Access properties with uavsar[item] syntax"""
        return self._get_field(item)


class Uavsar(Base):
    """UAVSAR NISAR sample product data reference:
    https://uavsar.jpl.nasa.gov/science/documents/nisar-sample-products.html

    Uavsar reference for Polsar:
    https://uavsar.jpl.nasa.gov/science/documents/polsar-format.html

    RPI/ InSAR format reference:
    https://uavsar.jpl.nasa.gov/science/documents/rpi-format-browse.html

    Example:
    SanAnd_23511_14128_002_140829_L090_CX_02
    SanAnd_23511_14128_002_140829_L090_CX_129_02.h5
    SanAnd_23511_14128_002_140829_L090HH_CX_129A_02.slc
    SanAnd_23511_14128_002_140829_L090HHVV_CX_129A_02.grd

    Example URL:
    https://uavsar.jpl.nasa.gov/cgi-bin/product.pl?jobName=SanAnd_23511_14128_002_140829_L090_CX_02

    Naming example:
    Dthvly_34501_08038_006_080731_L090HH_XX_01.slc

    Dthvly is the site name, 345 degrees is the heading of UAVSAR in flight,
    with a counter of 01, the flight was the thirty-eighth flight by UAVSAR in
    2008,this data take was the sixth data take during the flight, the data was
    acquired on July 31, 2008 (UTC), the frequency band was L-band, pointing at
    perpendicular to the flight heading (90 degrees counterclockwise), this
    file contains the HH data, this is the first interation of processing,
    cross talk calibration has not been applied, and the data type is SLC.

    For downsampled products (3x3 and 5x5), there is an optional extension
    of _ML3X3 and _ML5X5 tacked onto the end

    Examples:
        >>> fname = 'Dthvly_34501_08038_006_080731_L090HH_XX_01.slc'
        >>> parser = Uavsar(fname)

    """

    FILE_REGEX = (
        r"(?P<target_site>[\w\d]{6})_"
        # r"(?P<heading>\d{3})(?P<counter>\w+)_" # this is lineID
        r"(?P<line_id>\d{5})_"
        # r"(?P<year>\d{2})(?P<flight_number>\d{3})_" # this is FlightID
        r"(?P<flight_id>\d{5})_"
        r"(?P<data_take>\d{3})_"
        r"(?P<date>\d{6})_"
        r"(?P<band_squint_pol>\w{0,8})_"
        r"(?P<xtalk>X|C)(?P<dither>[XGD])_"
        r"(?P<nmode>\w{3,4})?_?"
        r"(?P<version>\d{2})\.?(?P<ext>\w{2,5})?"
    )
    TIME_FMT = "%y%m%d"


class LinkFinder(HTMLParser):
    """Finds EOF download links in aux.sentinel1.eo.esa.int page

    Example page to search:
    http://step.esa.int/auxdata/orbits/Sentinel-1/POEORB/S1B/2020/10/

    Usage:
    >>> import requests
    >>> resp = requests.get(form_url())
    >>> parser = LinkFinder()
    >>> parser.feed(resp.text)
    >>> print(sorted(parser.eof_links)[0])
    S1B_OPER_AUX_POEORB_OPOD_20201022T111233_V20201001T225942_20201003T005942.EOF.zip
    """

    def __init__(self, verbose=True):
        HTMLParser.__init__(self)
        self.products = []
        self.verbose = verbose

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href":
                    product = value.split("=")[1]
                    self.products.append(product)
                    if self.verbose:
                        print(product)
