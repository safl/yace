#include <stdint.h>

/**
 * A sample, as a device reports it
 */
struct pad_sample {
	uint8_t kind;   ///< What was sampled
	uint32_t value; ///< The value sampled
	uint16_t count; ///< How many samples the value is the sum of
};
