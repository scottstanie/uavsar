import numpy as np
import collections

RSC_KEY_TYPES = [
    ("width", int),
    ("file_length", int),
    ("x_first", float),
    ("y_first", float),
    ("x_step", float),
    ("y_step", float),
    ("x_unit", str),
    ("y_unit", str),
    ("z_offset", int),
    ("z_scale", int),
    ("projection", str),
]


def load_rsc(filename, lower=False, **kwargs):
    """Loads and parses the .dem.rsc file

    Args:
        filename (str) path to either the .dem or .dem.rsc file.
            Function will add .rsc to path if passed .dem file
        lower (bool): make keys of the dict lowercase

    Returns:
        dict: dem.rsc file parsed out, keys are all caps

    example file:
    WIDTH         10801
    FILE_LENGTH   7201
    X_FIRST       -157.0
    Y_FIRST       21.0
    X_STEP        0.000277777777
    Y_STEP        -0.000277777777
    X_UNIT        degrees
    Y_UNIT        degrees
    Z_OFFSET      0
    Z_SCALE       1
    PROJECTION    LL
    """

    # Use OrderedDict so that upsample_dem_rsc creates with same ordering as old
    output_data = collections.OrderedDict()
    # Second part in tuple is used to cast string to correct type

    rsc_filename = (
        "{}.rsc".format(filename) if not filename.endswith(".rsc") else filename
    )
    with open(rsc_filename, "r") as f:
        for line in f.readlines():
            for field, num_type in RSC_KEY_TYPES:
                if line.startswith(field.upper()):
                    output_data[field] = num_type(line.split()[1])

    if lower:
        output_data = {k.lower(): d for k, d in output_data.items()}
    return output_data


def load_dem(filename):
    """Loads a digital elevation map from .dem (e.g. produced by sardem)

    dem format is litte-endian int16 binary data
    """
    data = np.fromfile(filename, dtype="int16")

    # get info from .dem.rsc, reshape to correct size.
    info = load_rsc(filename)
    dem_img = data.reshape((info["file_length"], info["width"]))

    return dem_img


def get_latlon_arrs(rsc_file=None):
    """Get two 1D arrays of latitude and longitude from a .rsc file"""
    rsc_data = load_rsc(rsc_file)
    return _rsc_to_grid(**rsc_data)


def _rsc_to_grid(
    rows=None,
    cols=None,
    y_step=None,
    x_step=None,
    y_first=None,
    x_first=None,
    width=None,
    file_length=None,
    **kwargs,
):
    rows = rows or file_length
    cols = cols or width
    lon_arr = np.linspace(x_first, x_first + (cols - 1) * x_step, cols)
    lat_arr = np.linspace(y_first, y_first + (rows - 1) * y_step, rows)
    return lon_arr, lat_arr
