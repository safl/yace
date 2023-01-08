from pathlib import Path

from setuptools import find_namespace_packages, setup

setup(
    name="yace",
    version="0.2.0",
    author="Simon A. F. Lund",
    author_email="os@safl.dk",
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
    #include_package_data=True,
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
