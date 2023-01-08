from pathlib import Path

from setuptools import find_namespace_packages, setup

try:
    with open("README.rst", "r") as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = ""

setup(
    name="yace",
    version="0.3.0",
    author="Simon A. F. Lund",
    author_email="os@safl.dk",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/safl/yace",
    license="BSD",
    setup_requires=["wheel"],
    install_requires=[
        "jinja2",
        "pyyaml",
        "setuptools>=60",
    ],
    python_requires=">=3.7",
    entry_points={"console_scripts": ["yace=yace.cli:main"]},
    packages=[
        "yace",
        "yace.model",
        "yace.templates",
        "yace.templates.c",
        "yace.templates.ctypes",
    ],
    package_dir={"": "src"},
    zip_safe=False,
    package_data={
        "": ["*.template"],
    },
    options={"bdist_wheel": {"universal": True}},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Framework :: Pytest",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development",
        "Topic :: Text Processing",
        "Topic :: Utilities",
    ],
)
