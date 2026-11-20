# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# check, cimporting foo.pxd, linked to the library
project('foo-check', 'c', 'cython', meson_version: '>= 1.12')

fs = import('fs')
py = import('python').find_installation(pure: false)

bindings = get_option('bindings')
library = get_option('library')
py.extension_module(
  'check',
  'check.pyx',
  include_directories: include_directories(bindings),
  cython_args: ['-I', bindings],
  link_args: [library, '-Wl,-rpath,' + fs.parent(library)],
  install: true,
)
