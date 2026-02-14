project(
  'libfoo',
  'c',
  version: '0.0.1',
  default_options: ['c_std=c11', 'warning_level=2'],
)

inc = include_directories('include')

libfoo = library(
  'foo',
  'src/foo.c',
  include_directories: inc,
  install: true,
)

install_headers('include/foo.h')

pkg_mod = import('pkgconfig')
pkg_mod.generate(
  libfoo,
  name: 'foo',
  description: 'Example library for yace',
)
