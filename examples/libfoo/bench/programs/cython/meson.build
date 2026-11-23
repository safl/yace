# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# 'fast' calls C through foo.pxd; 'foo' is the module of the bindings
project('foo-bench', 'c', 'cython', meson_version: '>= 1.12')

fs = import('fs')
py = import('python').find_installation(pure: false)

bindings = get_option('bindings')
library = get_option('library')
foo = declare_dependency(
  include_directories: include_directories(bindings),
  link_args: [library, '-Wl,-rpath,' + fs.parent(library)],
)

foreach name, source : {'fast': 'fast.pyx', 'foo': bindings / 'foo.pyx'}
  py.extension_module(
    name,
    source,
    dependencies: foo,
    cython_args: ['-I', bindings],
    install: true,
  )
endforeach
