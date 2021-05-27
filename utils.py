"""uavsar.py: utilities for manipulating uavsar images"""
from __future__ import division
import numpy as np
from scipy.ndimage.interpolation import shift

import sario


def split_array_into_blocks(data):
    """Takes a long rectangular array (like UAVSAR) and creates blocks

    Useful to look at small data pieces at a time in dismph

    Returns:
        blocks (list[np.ndarray])
    """
    rows, cols = data.shape
    blocks = np.array_split(data, np.ceil(rows / cols))
    return blocks


def split_and_save(filename):
    """Creates several files from one long data file

    Saves them with same filename with .1,.2,.3... at end before ext
    e.g. brazos_14937_17087-002_17088-003_0001d_s01_L090HH_01.int produces
    brazos_14937_17087-002_17088-003_0001d_s01_L090HH_01.1.int
    brazos_14937_17087-002_17088-003_0001d_s01_L090HH_01.2.int...

    Output:
        newpaths (list[str]): full paths to new files created
    """

    data = sario.load_file(filename)
    blocks = split_array_into_blocks(data)

    ext = sario.get_file_ext(filename)
    newpaths = []

    for ix_step, block in enumerate(blocks, start=1):
        fname = filename.replace(ext, ".{}{}".format(str(ix_step), ext))
        print("Saving {}".format(fname))
        sario.save(fname, block)
        newpaths.append(fname)

    return newpaths


def combine_cor_amp(corfilename, save=True):
    """Takes a .cor file from UAVSAR (which doesn't contain amplitude),
    and creates a new file with amplitude data interleaved for dishgt

    dishgt brazos_14937_17087-002_17088-003_0001d_s01_L090HH_01_withamp.cor 3300 1 5000 1
    where 3300 is number of columns/samples, and we want the first 5000 rows. the final
    1 is needed for the contour interval to set a max of 1 for .cor data

    Inputs:
        corfilename (str): string filename of the .cor from UAVSAR
        save (bool): True if you want to save the combined array

    Returns:
        cor_with_amp (np.ndarray) combined correlation + amplitude (as complex64)
        outfilename (str): same name as corfilename, but _withamp.cor
            Saves a new file under outfilename
    Note: .ann and .int files must be in same directory as .cor
    """
    ext = sario.get_file_ext(corfilename)
    assert ext == '.cor', 'corfilename must be a .cor file'

    intfilename = corfilename.replace('.cor', '.int')

    intdata = sario.load_file(intfilename)
    amp = np.abs(intdata)

    cordata = sario.load_file(corfilename)
    # For dishgt, it expects the two matrices stacked [[amp]; [cor]]
    cor_with_amp = np.vstack((amp, cordata))

    outfilename = corfilename.replace('.cor', '_withamp.cor')
    sario.save(outfilename, cor_with_amp)
    return cor_with_amp, outfilename


def crop_to_smallest(image_list):
    """Makes all images the smallest dimension so they are alignable

    Args:
        image_list (iterable[ndarray]): list of images, or 3D array
            with 1st axis as the image number
    Returns:
        list[ndarray]: images of all same size

    Example:
    >>> a = np.arange(10).reshape((5, 2))
    >>> b = np.arange(9).reshape((3, 3))
    >>> cropped = crop_to_smallest((a, b))
    >>> print(all(img.shape == (3, 2) for img in cropped))
    True
    """
    shapes = np.array([i.shape for i in image_list])
    min_rows, min_cols = np.min(shapes, axis=0)
    return [img[:min_rows, :min_cols] for img in image_list]


def offset(img_info1, img_info2, axis=None):
    """Calculates how many pixels two images are offset

    Finds offset FROM img_info2 TO img_info1

    If image2 is 3 pixels down and 2 left of image1, the returns would
    be offset(im1, image) = (3, 2), offset(im1, image, axis=1) = 2

    To align image2 with image1, you can do:
    offsets = offset(img_info1, img_info2)
    Examples:
    >>> fake_info1 = {'x_first': -155.0, 'x_step': 0.1, 'y_first': 19.5, 'y_step': -0.2}
    >>> fake_info1 = {'x_first': -155.0, 'x_step': 0.1, 'y_first': 19.5, 'y_step': -0.2}

    """
    if img_info1['y_step'] != img_info2['y_step']:
        raise ValueError("Step sizes must be the same for the two images")

    row_offset = (img_info2['y_first'] - img_info1['y_first']) / img_info1['y_step']
    col_offset = (img_info2['x_first'] - img_info1['x_first']) / img_info1['x_step']
    output_tuple = (row_offset, col_offset)
    if axis is None:
        return output_tuple
    else:
        if not isinstance(axis, int):
            raise ValueError("axis must be an int less than 2")
        return output_tuple[axis]


def align_image_pair(image_pair, info_list, verbose=True):
    """Takes two images, shifts the second to align with the first

    Args:
        image_pair (tuple[ndarray, ndarray]): two images to align
        info_list (tuple[dict, dict]): the associated rsc_data/ann_info
            for the two images

    Returns:
        ndarray: shifted version of the 2nd image of image_pair
    """

    cropped_images = crop_to_smallest(image_pair)
    img1, img2 = cropped_images
    img1_ann, img2_ann = info_list

    offset_tup = offset(img1_ann, img2_ann)
    if verbose:
        print("Offset (rows, cols): {}".format(offset_tup))
    # Note: we use order=1 since default order=3 spline was giving
    # negative values for images (leading to invalid nonsense)
    return shift(img2, offset_tup, order=1)
