import re
import sys

from .constants import C
from .logger import get_log

log = get_log()

if sys.version_info.major == 2:
    from HTMLParser import HTMLParser
else:
    from html.parser import HTMLParser

try:
    import h5py
except ImportError:
    log.info("Can't import h5py,", exc_info=True)




# Filetype of real or complex depends on the polarization for .grd, .mlc
REAL_POLS = ("HHHH", "HVHV", "VVVV")
COMPLEX_POLS = ("HHHV", "HHVV", "HVVV")
CROSS_POLARIZATIONS = REAL_POLS + COMPLEX_POLS
SINGLE_POLARIZATIONS = ("HH", "HV", "VH", "VV")


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

    def __init__(self, verbose=True, nisar=True, split_products=True):
        HTMLParser.__init__(self)
        self.products = []
        self.links = []
        self.verbose = verbose
        self.nisar = nisar
        self._split_products = split_products

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href":
                    self.links.append(value)
                    if self.verbose:
                        print(value)
                    # For the first attempt at gathering product names,
                    # result is like "/cgi-bin/product.pl?jobName={product}"
                    if self._split_products:
                        product = value.split("=")[1]
                        self.products.append(product)
                        if self.verbose:
                            print(product)

    def handle_data(self, data):
        # This is inside a <small> tag after the NISAR version
        if not self.nisar and data == "#simulated-nisar #dithered":
            self.products.pop()


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

    @property
    def line_id(self):
        return self._get_field("line_id")

    @property
    def flight_id(self):
        return self._get_field("flight_id")

    @property
    def data_take(self):
        return self._get_field("data_take")

    @property
    def date(self):
        return self._get_field("date")


class UavsarHDF5(Base):
    """UAVSAR NISAR sample product data reference:
    https://uavsar.jpl.nasa.gov/science/documents/nisar-sample-products.html

    Example:
    SanAnd_23511_14128_002_140829_L090_CX_129_02.h5

    Example URL:
    https://uavsar.jpl.nasa.gov/cgi-bin/product.pl?jobName=SanAnd_23511_14128_002_140829_L090_CX_02

    Dthvly is the site name, 345 degrees is the heading of UAVSAR in flight,
    with a counter of 01, the flight was the thirty-eighth flight by UAVSAR in
    2008,this data take was the sixth data take during the flight, the data was
    acquired on July 31, 2008 (UTC), the frequency band was L-band, pointing at
    perpendicular to the flight heading (90 degrees counterclockwise), this
    file contains the HH data, this is the first interation of processing,
    cross talk calibration has not been applied, and the data type is SLC.

    Examples:
        >>> fname = 'Snjoaq_14511_13129_010_130719_L090_CX_138_02.h5'
        >>> uav = UavsarHDF5(fname)

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
        r"(?P<version>\d{2})\.h5"
    )
    TIME_FMT = "%y%m%d"

    SLC_GROUP = "/science/LSAR/SLC/"
    SWATH_GROUP = SLC_GROUP + "swaths/"
    METADATA_GROUP = SLC_GROUP + "metadata/"

    def get_slc(
        self,
        frequency="A",
        polarization="HH",
        output=None,
        dtype="complex64",
    ):
        """Extract the complex SLC image for one NISAR frequency/polarization

        If `output` is given, will save to a binary SLC file"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(frequency, polarization)
        if self.verbose:
            log.info("Getting data from %s:%s", self.filename, h5path)
        with h5py.File(self.filename, "r") as hf:
            ds = hf[h5path]
            with ds.astype(dtype):
                if output:
                    with open(output, "wb") as fout:
                        ds[()].tofile(fout)
                else:
                    return ds[()]

    def _get_data(self, h5path):
        if self.verbose:
            log.info("Getting data from %s:%s", self.filename, h5path)
        with h5py.File(self.filename, "r") as hf:
            return hf[h5path][()]

    def get_prf(self, frequency="A"):
        """Nominal pulse repitition frequency"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(
            frequency, "nominalAcquisitionPRF"
        )
        return self._get_data(h5path)

    # Another way for 1/prf... seems to be equivalent
    def get_pri(self):
        """Pulse repitition interval/ zero doppler time spacing"""
        h5path = self.SWATH_GROUP + "zeroDopplerTimeSpacing"
        return self._get_data(h5path)

    def get_zero_doppler_times(self):
        """Times for each line/pulse of image"""
        h5path = self.SWATH_GROUP + "zeroDopplerTime"
        return self._get_data(h5path)

    def get_veff(self):
        """Effective velocity"""
        # TODO: find out what the shape is
        # Out[95]: (804, 225)
        h5path = (
            self.METADATA_GROUP + "processingInformation/parameters/effectiveVelocity"
        )
        return self._get_data(h5path).mean()

    def get_wavelength(self, frequency="A"):
        """Wave wavelength in meters from `hdf5_file`"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(
            frequency, "processedCenterFrequency"
        )
        center_freq = self._get_data(h5path)
        return C / center_freq

    def get_d_range(self, frequency="A"):
        """Slant range spacing"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(
            frequency, "slantRangeSpacing"
        )
        return self._get_data(h5path)

    def get_slant_ranges(self, frequency="A"):
        """Array of ranges to each slant range bin"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(frequency, "slantRange")
        return self._get_data(h5path)

    def get_orbit(self):
        """Extract the arrays of time, position, and velocity
        Group: science/LSAR/SLC/metadata/orbit

        Also available:
        /science/LSAR/SLC/metadata/orbit/acceleration
        /science/LSAR/SLC/metadata/orbit/orbitType
        """
        orbit_group = self.METADATA_GROUP + "orbit/"
        time = self._get_data(orbit_group + "time")
        position = self._get_data(orbit_group + "position")
        velocity = self._get_data(orbit_group + "velocity")
        return time, position, velocity

    @property
    def line_id(self):
        return self._get_field("line_id")

    @property
    def flight_id(self):
        return self._get_field("flight_id")

    @property
    def data_take(self):
        return self._get_field("data_take")

    @property
    def date(self):
        return self._get_field("date")
