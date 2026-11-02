/**
 * Every construct of the C subset, each documented; parsing it must give no
 * diagnostics
 */
#ifndef VALID_H
#define VALID_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define VALID_NAME "valid" ///< A string constant
#define VALID_MAGIC 0xACDC ///< A hexadecimal constant
#define VALID_MAX 42       ///< A decimal constant
#define VALID_SHIFTED (1 << 4) ///< An integer constant expression
#define VALID_ALIAS VALID_MAX  ///< Another constant, by name

/**
 * Options, by name
 */
enum valid_opt {
	VALID_OPT_A = 0x1, ///< The first
	VALID_OPT_B = 0x2, ///< The second
	VALID_OPT_C = -1,  ///< A negative one
};

/**
 * An opaque handle; declared, never defined
 */
struct valid_handle;

/**
 * A point, contained by value in other records
 */
struct valid_point {
	int32_t x; ///< X
	int32_t y; ///< Y
};

/**
 * Called back with the argument given and a value
 *
 * @param arg The argument
 * @param value The value
 *
 * @return 0 to go on, otherwise stop
 */
typedef int (*valid_visit_cb)(void *arg, uint64_t value);

/**
 * Every kind of field
 */
struct valid_all {
	bool flag;                     ///< bool
	char letter;                   ///< char
	signed char schar;             ///< signed char
	unsigned char uchar;           ///< unsigned char
	short s;                       ///< short
	unsigned short us;             ///< unsigned short
	int i;                         ///< int
	unsigned int ui;               ///< unsigned int
	long l;                        ///< long
	unsigned long ul;              ///< unsigned long
	long long ll;                  ///< long long
	unsigned long long ull;        ///< unsigned long long
	float f;                       ///< float
	double d;                      ///< double
	int8_t i8;                     ///< int8_t
	uint16_t u16;                  ///< uint16_t
	int32_t i32;                   ///< int32_t
	uint64_t u64;                  ///< uint64_t
	size_t size;                   ///< size_t
	uintptr_t uptr;                ///< uintptr_t
	char name[16];                 ///< char array
	uint8_t bytes[4];              ///< array
	int32_t grid[2][3];            ///< two-dimensional array
	struct valid_point at;         ///< record by value
	struct valid_point path[2];    ///< array of records
	const char *label;             ///< string
	void *opaque;                  ///< void pointer
	struct valid_handle *handle;   ///< pointer to an opaque record
	const struct valid_point *ref; ///< pointer to const record
	valid_visit_cb visit;          ///< function pointer, by typedef
	uint32_t opt;                  ///< takes its values from enum valid_opt
};

/**
 * One of the two
 */
union valid_either {
	uint64_t number;         ///< a number
	struct valid_point point; ///< or a point
};

/**
 * Open a handle
 *
 * @param path What to open
 * @param handle Set to the handle opened
 *
 * @return 0 on success, negative errno on error
 */
int
valid_open(const char *path, struct valid_handle **handle);

/**
 * Close a handle
 *
 * @param handle The handle to close, NULL is ignored
 */
void
valid_close(struct valid_handle *handle);

/**
 * Visit every value
 *
 * @param handle The handle
 * @param visit Called for each value
 * @param arg Given to 'visit'
 *
 * @return The number of values visited, negative errno on error
 *
 * @lifetime visit call
 */
int64_t
valid_visit(struct valid_handle *handle, valid_visit_cb visit, void *arg);

/**
 * Fill in the record
 *
 * @param all The record to fill in
 * @param either The union to fill in
 *
 * @return The name of the handle, NULL when there is none
 */
const char *
valid_fill(struct valid_all *all, union valid_either *either);

#endif /* VALID_H */
