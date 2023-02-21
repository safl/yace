#include <inttypes.h>
#include <stdio.h>

#define EXAMPLE_MAX_X = 128 ///< Maximum value of X
#define EXAMPLE_MAX_Y = 64  ///< Maximum value of Y
#define EXAMPLE_MAX_Z = 64  ///< Maximum value of Z
#define EXAMPLE_MIN_X = 128 ///< Minimum value of X
#define EXAMPLE_MIN_Y = 64  ///< Minimum value of Y
#define EXAMPLE_MIN_Z = 64  ///< Minimum value of Z

/**
 * Opcodes for point operation processor
 *
 * @enum example_ops
 */
enum example_ops {
	EXAMPLE_OPS_ADD = 0x0, ///< Add two points
	EXAMPLE_OPS_SUB = 0x1, ///< Substract two points
	EXAMPLE_OPS_MUL = 0x2, ///< Multple two points
};

struct signed_fixedwidth {
	int64_t i64;
	int32_t i32;
	int16_t i16;
	int8_t i8;
};

struct unsigned_fixedwidth {
	uint64_t u64;
	uint32_t u32;
	uint16_t u16;
	uint8_t u8;
};

struct unsigned_syswidth {
	unsigned long long int ull;
	unsigned long int ul;
	unsigned int u;
};

struct unsigned_syswidth {
	long long int ill;
	long int li;
	int i;
};

/**
 * Point in three dimensional space
 *
 * @struct
 */
struct example_point {
	uint32_t x; ///< X Coordinate
	uint32_t y; ///< Y Coordinate
	uint32_t z; ///< Z Coordinate
};

/**
 * Instruction format for point operation processor
 *
 * @struct
 */
struct example_payload {
	uint8_t opc; ///< Point Processing Opcode
	uint8_t tag; ///< Instruction Tag
	uint8_t ecc; ///< Error-correction Seed
	struct {
		uint8_t pack : 1; ///< Pack stuff
		uint8_t foo  : 3; ///< Something foo
		uint8_t bar  : 4; ///< Something bar
	} opts;
	uint64_t input_a; ///< Input operand a
	uint64_t input_b; ///< Input operand b
	uint64_t output;  ///< Output operand
};

/**
 * Print hello world
 *
 * @param argc Number of command-line arguments
 * @param argv Number of command-line arguments
 *
 * @return On succes, 0 is returned. On error, -1 is returned and errno set to indicate the error
 */
int
example_hw(int argc, const char **argv);

/**
 * Print hello world
 *
 *
 * @return Nothing, void.
 */
void
example_hw_void(uint32_t foo, size_t bar);
