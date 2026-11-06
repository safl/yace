/**
 * The benchmark in plain C, the baseline the targets are compared to
 *
 * Fills a handle with FOO_POINTS_MAX points, then sums the x of every point,
 * ROUNDS times over, by a call of foo_point_get() per point, "calls", and by
 * foo_point_visit() with a callback, "callback". Prints, for each way, the
 * time per point of the best of REPEAT runs, and the sum, as a JSON line.
 *
 * Usage: bench ROUNDS REPEAT
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include <libfoo.h>

static int64_t
now_ns(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}

static int64_t
calls(struct foo_handle *handle, size_t rounds)
{
	size_t count = foo_point_count(handle);
	int64_t sum = 0;

	for (size_t round = 0; round < rounds; ++round) {
		for (size_t idx = 0; idx < count; ++idx) {
			sum += foo_point_get(handle, idx)->x;
		}
	}

	return sum;
}

static int
add_x(void *arg, const struct foo_point *point)
{
	*(int64_t *)arg += point->x;
	return 0;
}

static int64_t
callback(struct foo_handle *handle, size_t rounds)
{
	int64_t sum = 0;

	for (size_t round = 0; round < rounds; ++round) {
		foo_point_visit(handle, add_x, &sum);
	}

	return sum;
}

static void
run(struct foo_handle *handle, const char *way,
    int64_t (*sum_of)(struct foo_handle *, size_t), size_t rounds, size_t repeat)
{
	int64_t best = INT64_MAX;
	int64_t sum = 0;

	for (size_t each = 0; each < repeat; ++each) {
		int64_t start = now_ns();

		sum = sum_of(handle, rounds);
		int64_t elapsed = now_ns() - start;
		if (elapsed < best) {
			best = elapsed;
		}
	}

	printf("{\"target\": \"c\", \"way\": \"%s\", \"ns\": %.3f, \"sum\": %lld}\n", way,
	       (double)best / (double)(rounds * foo_point_count(handle)), (long long)sum);
}

int
main(int argc, char **argv)
{
	struct foo_point points[FOO_POINTS_MAX];
	struct foo_handle *handle = NULL;

	if (argc != 3) {
		fprintf(stderr, "usage: %s ROUNDS REPEAT\n", argv[0]);
		return 1;
	}
	size_t rounds = strtoull(argv[1], NULL, 10);
	size_t repeat = strtoull(argv[2], NULL, 10);

	if (foo_open("bench", &handle)) {
		fprintf(stderr, "foo_open() failed\n");
		return 1;
	}
	for (int idx = 0; idx < FOO_POINTS_MAX; ++idx) {
		points[idx] = (struct foo_point){.x = idx, .y = -idx};
	}
	if (foo_point_add_many(handle, points, FOO_POINTS_MAX) != FOO_POINTS_MAX) {
		fprintf(stderr, "foo_point_add_many() failed\n");
		return 1;
	}

	run(handle, "calls", calls, rounds, repeat);
	run(handle, "callback", callback, rounds, repeat);

	foo_close(handle);

	return 0;
}
