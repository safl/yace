#include <inttypes.h>
#include <stdio.h>

#define EXAMPLE_MAX_X 128
#define EXAMPLE_MAX_Y 64
#define EXAMPLE_MAX_Z 64
#define EXAMPLE_MIN_X 128
#define EXAMPLE_MIN_Y 64
#define EXAMPLE_MIN_Z 64

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

struct example_payload_opts {
  uint8_t pack : 1; ///< Pack stuff
  uint8_t foo : 3;  ///< Something foo
  uint8_t bar : 4;  ///< Something bar
};

/**
 * Instruction format for point operation processor
 *
 * @struct
 */
struct example_payload {
  uint8_t opc;      ///< Point Processing Opcode
  uint8_t tag;      ///< Instruction Tag
  uint8_t ecc;      ///< Error-correction Seed
  struct example_payload_opts opts;
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
 * @return On succes, 0 is returned. On error, -1 is returned and errno set to
 * indicate the error
 */
int example_hw(int argc, const char **argv);

/**
 * Print hello world
 *
 *
 * @return Nothing, void.
 */
void example_hw_void(uint32_t foo, size_t bar);

/**
 * Print hello world
 *
 * @param argc Number of command-line arguments
 * @param argv Number of command-line arguments
 *
 * @return On succes, 0 is returned. On error, -1 is returned and errno set to
 * indicate the error
 */
const char *example_hw_chp(int argc, const char **argv);

const char **example_hw_chp2(int argc, const char **argv);

struct foo example_hw_strct(int argc, const char **argv);

void *example_hw_void(int argc, const char **argv);