struct foo {
	int x; ///< Comment on the first member
	int y;
	int z;	
};

struct char_types {
	signed char name0;
	unsigned char name1;
	char name2;
};

struct short {
	short int name0;
	short name1;
	unsigned short int name2;
	unsigned short name3;
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

	struct example_payload_opts opts;
	
	uint64_t input_a; ///< Input operand a
	uint64_t input_b; ///< Input operand b
	uint64_t output;  ///< Output operand
};


struct signed_fixedwidth {
	int64_t i64;
	int32_t i32;
	int16_t i16;
	int8_t i8;
};


struct unsigned_syswidth {
	unsigned int u;
	unsigned long int ul;
	unsigned long long int ull;
};

struct signed_syswidth {
	int i;
	long int li;
	long long int ill;
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
 * Payload options
 *
 * @struct
 */
struct example_payload_opts {
	uint8_t pack : 1; ///< Pack stuff
	uint8_t foo  : 3; ///< Something foo
	uint8_t bar  : 4; ///< Something bar
};