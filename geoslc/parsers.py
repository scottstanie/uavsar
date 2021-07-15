from .constants import C
from download.logger import get_log
from download.parsers import Base

log = get_log()

try:
    import h5py
except ImportError:
    log.info("Can't import h5py,", exc_info=True)


# Filetype of real or complex depends on the polarization for .grd, .mlc
REAL_POLS = ("HHHH", "HVHV", "VVVV")
COMPLEX_POLS = ("HHHV", "HHVV", "HVVV")
CROSS_POLARIZATIONS = REAL_POLS + COMPLEX_POLS
SINGLE_POLARIZATIONS = ("HH", "HV", "VH", "VV")


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
