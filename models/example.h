#define PLOT_SERIAL "WYRD1234"
#define PLOT_VERSION_MAJOR 1
#define PLOT_VERSION_MINOR 2
#define PLOT_VERSION_PATCH 3

enum plot_options {
  PLOT_OPTIONS_PNG = 0x1,
  PLOT_OPTIONS_PDF = 0x2,
};

struct coordinate {
  int32_t x;
  int32_t y;
  int32_t z;
};
