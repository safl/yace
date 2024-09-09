#define PLOT_SERIAL "WYRD1234"
#define PLOT_FOO 0xACDC
#define PLOT_VERSION_MAJOR 1
#define PLOT_VERSION_MINOR 2
#define PLOT_VERSION_PATCH 3

/**
 * Description of enum
 *
 * Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pellentesque accumsan massa est,
 * ut ullamcorper lectus malesuada sit amet. Donec gravida nibh aliquam mattis rhoncus. Quisque
 * sollicitudin ultricies orci, condimentum blandit lorem feugiat at. Aliquam tempus metus et nulla
 * eleifend, eu dapibus risus pellentesque. Duis fermentum bibendum ligula in pharetra. Curabitur
 * eget urna tempus, tempor dui sed, tempus lorem. Phasellus eu aliquam neque.
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