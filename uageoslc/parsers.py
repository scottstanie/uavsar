import datetime
from .constants import C
from uaquery.logger import get_log
from uaquery.parsers import Base

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
    CAL_GROUP = "/science/LSAR/SLC/metadata/calibrationInformation/"
    DT_FMT = "%Y-%m-%d %H:%M:%S"  # Used in attrs['units']: "seconds since ___"

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

    def _get_attrs(self, h5path):
        if self.verbose:
            log.info("Getting attributes from %s:%s", self.filename, h5path)
        with h5py.File(self.filename, "r") as hf:
            return dict(hf[h5path].attrs)

    def get_prf(self, frequency="A"):
        """Nominal pulse repitition frequency"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(
            frequency, "nominalAcquisitionPRF"
        )
        return self._get_data(h5path)

    # Another way for 1/prf... seems to be equivalent
    def get_pri(self, attrs=False):
        """Pulse repitition interval/ zero doppler time spacing"""
        h5path = self.SWATH_GROUP + "zeroDopplerTimeSpacing"
        return self._get_data(h5path) if not attrs else self._get_attrs(h5path)

    def get_zero_doppler_times(self, as_datetime=False, attrs=False):
        """Times for each line/pulse of image"""
        h5path = self.SWATH_GROUP + "zeroDopplerTime"

        if attrs:
            return self._get_attrs(h5path)
        if as_datetime:
            return self._get_as_datetime(h5path)
        else:
            return self._get_data(h5path)

    def get_veff(self, attrs=False):
        """Effective velocity"""
        # TODO: find out what the shape is
        # Out[95]: (804, 225)
        h5path = (
            self.METADATA_GROUP + "processingInformation/parameters/effectiveVelocity"
        )
        return self._get_data(h5path).mean() if not attrs else self._get_attrs(h5path)

    def get_wavelength(self, frequency="A", attrs=False):
        """Wave wavelength in meters from `hdf5_file`"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(
            frequency, "processedCenterFrequency"
        )
        if attrs:
            return self._get_attrs(h5path)
        center_freq = self._get_data(h5path)
        return C / center_freq

    def get_d_range(self, frequency="A", attrs=False):
        """Slant range spacing"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(
            frequency, "slantRangeSpacing"
        )
        return self._get_data(h5path) if not attrs else self._get_attrs(h5path)

    def get_slant_ranges(self, frequency="A", attrs=False):
        """Array of ranges to each slant range bin"""
        h5path = self.SWATH_GROUP + "frequency{}/{}".format(frequency, "slantRange")
        return self._get_data(h5path) if not attrs else self._get_attrs(h5path)

    def get_orbit(self, attrs=False, as_datetime=False):
        """Extract the arrays of time, position, and velocity
        Group: science/LSAR/SLC/metadata/orbit

        Also available:
        /science/LSAR/SLC/metadata/orbit/acceleration
        /science/LSAR/SLC/metadata/orbit/orbitType
        """
        orbit_group = self.METADATA_GROUP + "orbit/"
        if attrs:
            return (
                self._get_attrs(orbit_group + "time"),
                self._get_attrs(orbit_group + "position"),
                self._get_attrs(orbit_group + "velocity"),
            )
        if as_datetime:
            time = self._get_as_datetime(orbit_group + "time")
        else:
            time = self._get_data(orbit_group + "time")
        position = self._get_data(orbit_group + "position")
        velocity = self._get_data(orbit_group + "velocity")
        return time, position, velocity

    def _get_as_datetime(self, h5path):
        import numpy as np
        second_offsets = self._get_data(h5path)
        ref_time = self._get_ref_dt(h5path)
        # NOTE: it gives 10 decimals of precision after the second, but numpy picosecond
        # only allows [1969, 1970] year ranges. So truncate the 10th decimal
        ns_offsets = (1e9 * second_offsets).astype("timedelta64[ns]")
        return np.datetime64(ref_time) + ns_offsets

    def _get_ref_dt(self, h5path):
        """Parse the reference time from some HDF5 dataset"""
        ref_time_str = self._get_attrs(h5path)["units"].decode().replace("seconds since", "").strip()
        return datetime.datetime.strptime(ref_time_str, self.DT_FMT)

    def calibrate_slc(self, slc=None, to="gamma0", order=1, row_start=0, row_end=None):
        """Return the RSLC normalized to either gamma0 or beta0 amplitudes

        The LUTs are multiplicative factors that convert the nominally uncalibrated
        backscatter values to beta0, sigma0, or gamma0.

        Each quantity is in normalized power units, whereas the RSLC is complex amplitude.
        Thus, the RSLC will be multiplied by the sqrt of the gamma0 or beta0 values.

        beta0 = abs(RSLC)**2 * beta0_LUT
        sigma0 = abs(RSLC)**2 * sigma0_LUT
        gamma0 = abs(RSLC)**2 * gamma0_LUT

        See "Flattening gamma: Radiometric terrain correction for SAR imagery", Small, 2011.
        """
        import numpy as np

        if slc is None:
            slc = self.get_slc()
        cal_img = self._get_cal_slc(to=to, order=order)
        return np.sqrt(cal_img[row_start:row_end]) * slc[row_start:row_end]

    def get_cal_gamma0(self, attrs=False):
        """Get the array of gamma0 calibration values"""
        h5path = self.CAL_GROUP + "geometry/gamma0"
        return self._get_data(h5path) if not attrs else self._get_attrs(h5path)

    def get_cal_beta0(self, attrs=False):
        """Get the array of beta0 calibration values"""
        h5path = self.CAL_GROUP + "geometry/beta0"
        return self._get_data(h5path) if not attrs else self._get_attrs(h5path)

    def _get_cal_slc(self, to="gamma0", order=1):
        """Compute the gamma0/beta0 calibration values interpolated
        to be same size as the RSLC
        TODO: Do i need to try to adjust the start/stop times based on 
        how other SLCs are coregistered?
        """
        from scipy.interpolate import RectBivariateSpline

        slant_ranges_cal = self._get_data(self.CAL_GROUP + "slantRange")
        ztd_cal = self._get_data(self.CAL_GROUP + "zeroDopplerTime")
        if to == "gamma0":
            interp_vals = self.get_cal_gamma0()
        elif to == "beta0":
            interp_vals = self.get_cal_beta0()

        # TODO: get this for coregistered stuff....
        slant_ranges_slc = self.get_slant_ranges()
        ztd_slc = self.get_zero_doppler_times()

        interpolator = RectBivariateSpline(
            ztd_cal, slant_ranges_cal, interp_vals, kx=order, ky=order
        )
        return interpolator(ztd_slc, slant_ranges_slc)

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
