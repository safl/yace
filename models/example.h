#define PLOT_SERIAL "WYRD1234"
#define PLOT_FOO 0xACDC
#define PLOT_VERSION_MAJOR 1
#define PLOT_VERSION_MINOR 2
#define PLOT_VERSION_PATCH 3

/**
 * Description of enum
 *
 * More stuff
 *
 * @enum plot_options
 */
enum plot_options {
  PLOT_OPTIONS_PNG = 0x1, ///< First thing
  PLOT_OPTIONS_PDF = 0x2, ///< Second thing
};

/**
 * Description of structure
 *
 * @struct coordinate
 */
struct coordinate {
  int32_t x; ///< X Coordinate
  int32_t y; ///< Y Coordinate
  int32_t z; ///< Z Coordinate
};

/**
 * Description of a feature...
 *
 * @union feature
 */
union feature {
  struct coordinate coord; ///< Coordinate
  uint32_t vector;         ///< Vector
};

/**
 * This is a function
 *
 * @param x The first thing
 * @param y The second thing
 *
 * @return Something on success, -1 on error.
 */
int foo(int x, int y);

typedef int (*binop_func)(int, int);