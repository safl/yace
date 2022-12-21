# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "yace"
copyright = "2022-2023, Simon A. F. Lund"
author = "Simon A. F. Lund"
release = "0.0.1"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.githubpages",
    "sphinx.ext.extlinks",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_logo = "_static/yace-text.png"
html_theme = "furo"
html_theme_options = {
    "sidebar_hide_name": True,
}
html_static_path = ["_static"]

extlinks = {
    "autopxd2": ("https://github.com/elijahr/python-autopxd2%s", None),
    "ctypeslib2": ("https://github.com/trolldbois/ctypeslib%s", None),
    "doxygen": ("https://www.doxygen.nl/%s", None),
    "rust-bindgen": ("https://github.com/rust-lang/rust-bindgen%s", None),
    "swig": ("https://www.swig.org/%s", None),
}
