/**
 * The plain C way of the benchmark: the x of every point of the handle, summed
 * 'rounds' times
 */
#include <stdint.h>
#include <libfoo.h>

int64_t
bench_sum(const struct foo_handle *handle, size_t rounds)
{
	size_t count = foo_count(handle);
	int64_t sum = 0;

	for (size_t round = 0; round < rounds; ++round) {
		for (size_t idx = 0; idx < count; ++idx) {
			sum += foo_at(handle, idx)->x;
		}
	}

	return sum;
}
