from setuptools import setup

try:
    with open("README.rst", "r") as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = ""

setup(
    name="yace",
    version="0.5.4",
    author="Simon A. F. Lund",
    author_email="os@safl.dk",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/safl/yace",
    license="GPL-2.0",
    setup_requires=["wheel"],
    install_requires=[
        "jinja2",
        "pyyaml",
        "libclang",
        "setuptools>=60",
    ],
    python_requires=">=3.7",
    entry_points={"console_scripts": ["yace=yace.cli.yace:main"]},
    packages=[
        "yace",
        "yace.cli",
        "yace.idl",
        "yace.targets",
        "yace.targets.capi",
        "yace.targets.ctypes",
    ],
    package_dir={"": "src"},
    zip_safe=False,
    package_data={
        "": ["*.template", "*.clang-format"],
    },
    options={"bdist_wheel": {"universal": True}},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Framework :: Pytest",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Programming Language :: Python",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development",
        "Topic :: Text Processing",
        "Topic :: Utilities",
    ],
)
