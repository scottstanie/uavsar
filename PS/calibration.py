from scipy.interpolate import RectBivariateSpline
from geoslc.parsers import UavsarHDF5
cal_group = "/science/LSAR/SLC/metadata/calibrationInformation/"
gamma_dset = cal_group + "geometry/gamma0"
beta_dset = cal_group + "geometry/beta0"
sr_dset = cal_group + "slantRange"
ztd_dset = cal_group + "zeroDopplerTime"

def load_cal_file(h5file, dset, print_description=False):
    with h5py.File(h5file) as hf:
        ds = hf[dset]
        if print_description:
            print(ds.attrs["description"].decode())
        return ds[()]
    
gamma0 = load_cal_file(h5files[0], gamma_dset, print_description=True)
beta0 = load_cal_file(h5files[0], beta_dset, print_description=True)
slant_ranges_cal = load_cal_file(h5files[0], sr_dset, print_description=True)
ztd_cal = load_cal_file(h5files[0], ztd_dset, print_description=True)
uav = UavsarHDF5(h5files[0])
slant_ranges_slc = uav.get_slant_ranges()
ztd_slc = uav.get_zero_doppler_times()
print(slant_ranges_slc.shape, ztd_slc.shape)

interp_gamma0 = RectBivariateSpline(ztd_cal, slant_ranges_cal, gamma0, kx=1, ky=1)
gamma0_slc = interp_gamma0(ztd_slc, slant_ranges_slc)

interp_beta0 = RectBivariateSpline(ztd_cal, slant_ranges_cal, beta0, kx=1, ky=1)
beta0_slc = interp_beta0(ztd_slc, slant_ranges_slc)