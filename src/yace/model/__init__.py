#!/usr/bin/env python3
"""
The interface model was initially just a collection of YAML-files, globbed for
and merged together by the copiler using a YAML-parser. This left for two
things to be done:

* Documentation of the interface model
* Validation of the interface model

The path of least resistance seemed to then go forward with utilizing Python
data-classes for model-validation and using doc-strings which the **yace**
documentation could extract. Thus, the the interface model can be defined by
either writing yaml-files or fiddling with Python data-classes.

The former is currently the recommended approach as there is currently no
persistance of the Python representation.
...
"""
