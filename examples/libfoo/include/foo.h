/**
 * An example library, using every construct of the C subset of yace
 *
 * It is the fixture the targets are checked against: each target's check calls
 * it through the bindings generated from this header and prints what it got
 * back, which must be what 'expected.yaml' says.
 */
#ifndef FOO_H
#define FOO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#define FOO_NAME "foo"           ///< Name of the library
#define FOO_MAGIC 0xACDC         ///< A hexadecimal constant
#define FOO_VERSION_MAJOR 1      ///< Major version
#define FOO_VERSION_MINOR 2      ///< Minor version
#define FOO_VERSION_PATCH 3      ///< Patch version
#define FOO_POINTS_MAX (1 << 3)  ///< Points a handle holds at most
#define FOO_DEFAULT_SHAPE_SIDES FOO_POINTS_MAX ///< A constant, by name

/**
 * Kinds of figure
 */
enum foo_shape {
	FOO_SHAPE_NONE = -1,   ///< No figure
	FOO_SHAPE_POINT = 0,   ///< A single point
	FOO_SHAPE_LINE = 1,    ///< Two points
	FOO_SHAPE_POLYGON = 2, ///< Three points or more
};

/**
 * Options of a figure, combined as bits
 */
enum foo_option {
	FOO_OPTION_CLOSED = 0x1, ///< The last corner connects to the first
	FOO_OPTION_FILLED = 0x2, ///< The inside is filled
};

/**
 * A collection of points, opened with foo_open() and closed with foo_close()
 */
struct foo_handle;

/**
 * A point on the plane
 */
struct foo_point {
	int32_t x; ///< Horizontal position
	int32_t y; ///< Vertical position
};

/**
 * Called back with each point visited
 *
 * @param arg The argument given along with the callback
 * @param point The point visited
 *
 * @return 0 to go on, anything else to stop
 */
typedef int (*foo_visit_cb)(void *arg, const struct foo_point *point);

/**
 * A callback and its argument
 */
struct foo_visitor {
	foo_visit_cb visit; ///< Called for each point
	void *arg;          ///< Given to 'visit'
};

/**
 * A value of every kind of scalar
 */
struct foo_scalars {
	bool flag;              ///< bool
	char letter;            ///< char
	signed char schar;      ///< signed char
	unsigned char uchar;    ///< unsigned char
	short s;                ///< short
	unsigned short us;      ///< unsigned short
	int i;                  ///< int
	unsigned int ui;        ///< unsigned int
	long l;                 ///< long
	unsigned long ul;       ///< unsigned long
	long long ll;           ///< long long
	unsigned long long ull; ///< unsigned long long
	float f;                ///< float
	double d;               ///< double
	int8_t i8;              ///< int8_t
	int16_t i16;            ///< int16_t
	int32_t i32;            ///< int32_t
	int64_t i64;            ///< int64_t
	uint8_t u8;             ///< uint8_t
	uint16_t u16;           ///< uint16_t
	uint32_t u32;           ///< uint32_t
	uint64_t u64;           ///< uint64_t
	intptr_t iptr;          ///< intptr_t
	uintptr_t uptr;         ///< uintptr_t
	size_t size;            ///< size_t
	ssize_t ssize;          ///< ssize_t
	ptrdiff_t diff;         ///< ptrdiff_t
};

/**
 * A figure: its kind, where it is, and its corners
 */
struct foo_figure {
	uint32_t shape;               ///< One of enum foo_shape
	uint32_t options;             ///< Bits of enum foo_option
	struct foo_point origin;      ///< Where the figure is
	struct foo_point corners[4];  ///< The corners, relative to 'origin'
	uint8_t ncorners;             ///< How many of 'corners' are used
	char name[16];                ///< Name of the figure
	int16_t grid[2][3];           ///< A two-dimensional array
	const char *label;            ///< A string, NULL when there is none
	float scale;                  ///< Scale of the figure
	double area;                  ///< Area of the figure
};

/**
 * A 32-bit value, read as signed, as unsigned, or as the 'x' of a point
 */
union foo_value {
	int32_t i;              ///< Signed
	uint32_t u;             ///< Unsigned
	struct foo_point point; ///< A point, its 'x' sharing the bits of 'i'
};

/**
 * The version of the library
 *
 * @return The version, as "MAJOR.MINOR.PATCH"
 */
const char *
foo_version(void);

/**
 * Open a handle holding no points
 *
 * @param name Name of the handle, copied
 * @param handle Set to the handle opened
 *
 * @return 0 on success, -1 when 'name' or 'handle' is NULL or memory ran out
 */
int
foo_open(const char *name, struct foo_handle **handle);

/**
 * Close a handle
 *
 * @param handle The handle to close, NULL is ignored
 */
void
foo_close(struct foo_handle *handle);

/**
 * The name the handle was opened with
 *
 * @param handle The handle
 *
 * @return The name, owned by the handle
 */
const char *
foo_name(const struct foo_handle *handle);

/**
 * Add a point to the handle
 *
 * @param handle The handle
 * @param point The point to add, copied
 *
 * @return 0 on success, -1 when the handle holds FOO_POINTS_MAX points
 */
int
foo_add(struct foo_handle *handle, const struct foo_point *point);

/**
 * The number of points held
 *
 * @param handle The handle
 *
 * @return The number of points
 */
size_t
foo_count(const struct foo_handle *handle);

/**
 * A point held by the handle
 *
 * @param handle The handle
 * @param idx Index of the point
 *
 * @return The point, NULL when 'idx' is past the last one
 */
const struct foo_point *
foo_at(const struct foo_handle *handle, size_t idx);

/**
 * Visit the points in the order they were added
 *
 * @param handle The handle
 * @param visit Called for each point, until it returns non-zero
 * @param arg Given to 'visit'
 *
 * @return The number of points visited, -1 when 'visit' is NULL
 */
ssize_t
foo_visit(struct foo_handle *handle, foo_visit_cb visit, void *arg);

/**
 * Visit the points with a visitor; as foo_visit()
 *
 * @param handle The handle
 * @param visitor The callback and its argument
 *
 * @return The number of points visited, -1 when the callback is NULL
 */
ssize_t
foo_visit_with(struct foo_handle *handle, const struct foo_visitor *visitor);

/**
 * Fill in a value of every kind of scalar, the limits of the fixed-width ones
 *
 * @param scalars The values to fill in
 */
void
foo_scalars_fill(struct foo_scalars *scalars);

/**
 * Fill in a figure of the given shape
 *
 * @param figure The figure to fill in
 * @param shape One of enum foo_shape
 *
 * @return 0 on success, -1 when 'shape' is none of enum foo_shape
 */
int
foo_figure_fill(struct foo_figure *figure, uint32_t shape);

/**
 * Set a value, clearing the bits it does not use
 *
 * @param value The value to set
 * @param i What to set it to
 */
void
foo_value_set(union foo_value *value, int32_t i);

#endif /* FOO_H */
