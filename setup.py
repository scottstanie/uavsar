import setuptools


setuptools.setup(
    name="uavsar",
    version="0.1.0",
    author="Scott Staniewicz",
    author_email="scott.stanie@utexas.com",
    description="Query and download UAVSAR PolSAR products",
    url="https://github.com/scottstanie/uavsar",
    classifiers=[
        "Programming Language :: Python",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering",
        "Intended Audience :: Science/Research",
    ],
    install_requires=["requests"],
    extras_require={
        ':python_version == "2.7"': ["futures"],
        "geoslc": ["numpy", "h5py", "numba", "joblib"],
    },
    entry_points={
        "console_scripts": [
            "uaquery=uaquery.cli:cli",
            "uageocode=uageoslc.cli:cli",
        ],
    },
    packages=["uageoslc", "uaquery"],
    zip_safe=False,
)
