/**
 * The check of the C API of libfoo: calls the library through the generated
 * header and prints what it got back, as YAML documents, or with argument
 * "json" as JSON objects, each holding what 'expected.yaml' says
 */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <libfoo.h>

static int json;
static int nkeys;

static void
doc_begin(const char *name)
{
	nkeys = 0;
	printf(json ? "{\"%s\": {" : "---\n%s:\n", name);
}

static void
doc_end(void)
{
	printf(json ? "}}\n" : "");
}

static void
key(const char *name)
{
	if (json) {
		printf("%s\"%s\": ", nkeys ? ", " : "", name);
	} else {
		printf("  %s: ", name);
	}
	nkeys += 1;
}

static void
int_value(const char *name, intmax_t value)
{
	key(name);
	printf("%jd%s", value, json ? "" : "\n");
}

/* Only for strings needing no escapes; the pretty-printers handle those */
static void
str_value(const char *name, const char *value)
{
	key(name);
	printf("\"%s\"%s", value, json ? "" : "\n");
}

static void
names_value(const char *name, const char *(*str)(int), const int *values, size_t len)
{
	key(name);
	printf("[");
	for (size_t idx = 0; idx < len; ++idx) {
		printf("%s\"%s\"", idx ? ", " : "", str(values[idx]));
	}
	printf("]%s", json ? "" : "\n");
}

static void
record_begin(const char *name)
{
	printf(json ? "{\"%s\": " : "---\n", name);
}

static void
record_end(void)
{
	printf(json ? "}\n" : "");
}

struct sum {
	int64_t x;
	int64_t y;
	size_t stop_after;
	size_t visited;
};

static int
summarize(void *arg, const struct foo_point *point)
{
	struct sum *sum = arg;

	sum->x += point->x;
	sum->y += point->y;
	sum->visited += 1;

	return sum->visited == sum->stop_after;
}

static void
count_done(void *arg, size_t count)
{
	*(size_t *)arg = count;
}

int
main(int argc, char **argv)
{
	int flags = FOO_PR_YAML;
	static const int shapes[] = {FOO_SHAPE_NONE, FOO_SHAPE_POINT, FOO_SHAPE_LINE,
				     FOO_SHAPE_POLYGON, 3};
	static const int options[] = {FOO_OPTION_CLOSED, FOO_OPTION_FILLED, 3};
	struct foo_handle *handle = NULL;
	struct foo_point copied[4];
	int64_t sum_x = 0;
	size_t done_count = 0;
	struct foo_point points[] = {{1, 2}, {3, 4}, {5, 6}};
	struct sum all = {0}, first_two = {0, 0, 2, 0}, with = {0};
	struct foo_visitor visitor = {summarize, &with};
	struct foo_scalars scalars;
	struct foo_figure figure;
	struct foo_status status;
	union foo_value value;
	int added = 0;

	if (argc > 1 && !strcmp(argv[1], "json")) {
		json = 1;
		flags = FOO_PR_JSON;
	}

	doc_begin("defines");
	str_value("FOO_NAME", FOO_NAME);
	int_value("FOO_MAGIC", FOO_MAGIC);
	int_value("FOO_VERSION_MAJOR", FOO_VERSION_MAJOR);
	int_value("FOO_VERSION_MINOR", FOO_VERSION_MINOR);
	int_value("FOO_VERSION_PATCH", FOO_VERSION_PATCH);
	int_value("FOO_POINTS_MAX", FOO_POINTS_MAX);
	int_value("FOO_DEFAULT_SHAPE_SIDES", FOO_DEFAULT_SHAPE_SIDES);
	doc_end();

	doc_begin("enums");
	names_value("foo_shape", foo_shape_str, shapes, sizeof(shapes) / sizeof(*shapes));
	names_value("foo_option", foo_option_str, options, sizeof(options) / sizeof(*options));
	doc_end();

	doc_begin("calls");
	str_value("version", foo_version());
	int_value("open", foo_open("points", &handle));
	if (!handle) {
		return 1;
	}
	int_value("open_without_name", foo_open(NULL, &handle));
	str_value("name", foo_name(handle));
	for (size_t idx = 0; idx < sizeof(points) / sizeof(*points); ++idx) {
		added += !foo_add(handle, &points[idx]);
	}
	int_value("added", added);
	int_value("count", (intmax_t)foo_count(handle));
	int_value("visit", foo_visit(handle, summarize, &all));
	int_value("visit_sum_x", all.x);
	int_value("visit_sum_y", all.y);
	int_value("visit_stopped", foo_visit(handle, summarize, &first_two));
	int_value("visit_without_callback", foo_visit(handle, NULL, NULL));
	int_value("visit_with", foo_visit_with(handle, &visitor));
	int_value("visit_with_sum_x", with.x);
	int_value("figure_of_unknown_shape", foo_figure_fill(&figure, 3));
	int_value("add_many", foo_add_many(handle, points, sizeof(points) / sizeof(*points)));
	int_value("count_after_add_many", (intmax_t)foo_count(handle));
	int_value("points_copied", foo_points(handle, copied, 4));
	for (size_t idx = 0; idx < 4; ++idx) {
		sum_x += copied[idx].x;
	}
	int_value("points_sum_x", sum_x);
	int_value("submit", foo_submit(handle, count_done, &done_count));
	int_value("submit_busy", foo_submit(handle, count_done, &done_count));
	int_value("poke", (intmax_t)foo_poke(handle));
	int_value("done_count", (intmax_t)done_count);
	int_value("poke_again", (intmax_t)foo_poke(handle));
	doc_end();

	record_begin("foo_point");
	foo_point_fpr(stdout, foo_at(handle, 1), flags);
	record_end();

	record_begin("foo_point");
	foo_point_fpr(stdout, foo_at(handle, 6), flags);
	record_end();

	while (!foo_add(handle, &points[0])) {
		;
	}
	doc_begin("full");
	int_value("count", (intmax_t)foo_count(handle));
	int_value("add", foo_add(handle, &points[0]));
	int_value("add_many", foo_add_many(handle, points, 1));
	doc_end();

	foo_status_get(handle, &status);
	record_begin("foo_status");
	foo_status_fpr(stdout, &status, flags);
	record_end();
	doc_begin("status");
	int_value("pending", (status.code & FOO_STATUS_CODE_PENDING) >> 0);
	int_value("points", (status.code & FOO_STATUS_CODE_POINTS) >> 4);
	int_value("full", (status.code & FOO_STATUS_CODE_FULL) >> 15);
	doc_end();
	memset(&status, 0, sizeof(status));
	status.code |= (5 << 4) & FOO_STATUS_CODE_POINTS;
	status.code |= FOO_STATUS_CODE_PENDING;
	status.max = FOO_POINTS_MAX;
	record_begin("foo_status");
	foo_status_fpr(stdout, &status, flags);
	record_end();
	foo_close(handle);
	foo_close(NULL);

	foo_scalars_fill(&scalars);
	record_begin("foo_scalars");
	foo_scalars_fpr(stdout, &scalars, flags);
	record_end();

	for (uint32_t shape = FOO_SHAPE_POINT; shape <= FOO_SHAPE_POLYGON; ++shape) {
		if (foo_figure_fill(&figure, shape)) {
			return 1;
		}
		record_begin("foo_figure");
		foo_figure_fpr(stdout, &figure, flags);
		record_end();
	}

	foo_value_set(&value, -1);
	record_begin("foo_value");
	foo_value_fpr(stdout, &value, flags);
	record_end();

	return 0;
}
