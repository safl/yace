/**
 * The check of the C++ layer of libfoo: calls the library through foo.hpp, its
 * handle, exceptions and returned values, and prints what it got back, as YAML
 * documents, or with argument "json" as JSON objects, each holding what
 * 'expected.yaml' says. An error is printed as the negative errno the C
 * function returned. The raw layer of C++ is the C API, checked by the C check;
 * what the layer does not take, a NULL where none is allowed, is called raw.
 */
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include <foo.hpp>

namespace {

bool as_json = false;

struct field {
	std::string key;
	std::string value; // as JSON, which is also YAML
};

std::string
quoted(const std::string &text)
{
	return "\"" + text + "\"";
}

std::string
num(std::int64_t value)
{
	return std::to_string(value);
}

void
document(const std::string &name, const std::vector<field> &fields)
{
	if (as_json) {
		std::cout << "{\"" << name << "\": {";
		for (std::size_t idx = 0; idx < fields.size(); ++idx) {
			std::cout << (idx ? ", " : "") << "\"" << fields[idx].key
				  << "\": " << fields[idx].value;
		}
		std::cout << "}}\n";
		return;
	}
	std::cout << "---\n" << name << ":\n";
	for (const auto &f : fields) {
		std::cout << "  " << f.key << ": " << f.value << "\n";
	}
}

/// Print a record, or none, with the printers of the C++ layer
template <class T>
void
record(const std::string &name, const std::optional<T> &obj)
{
	if (as_json) {
		std::cout << "{\"" << name << "\": ";
		if (obj) {
			std::cout << foo::json(*obj);
		} else {
			std::cout << "null\n";
		}
		std::cout << "}\n";
		return;
	}
	std::cout << "---\n";
	if (obj) {
		std::cout << *obj;
	} else {
		std::cout << name << ": ~\n";
	}
}

/// What 'call' returns, 0 for nothing, or the negative errno it throws
template <class F>
std::int64_t
errno_of(F &&call)
{
	try {
		if constexpr (std::is_void_v<decltype(call())>) {
			call();
			return 0;
		} else {
			return static_cast<std::int64_t>(call());
		}
	} catch (const std::system_error &err) {
		return -err.code().value();
	}
}

std::string
names(const std::vector<int> &values, const char *(*str)(int))
{
	std::string text = "[";
	for (std::size_t idx = 0; idx < values.size(); ++idx) {
		text += (idx ? ", " : "") + quoted(str(values[idx]));
	}
	return text + "]";
}

} // namespace

int
main(int argc, char **argv)
{
	as_json = argc > 1 && !std::strcmp(argv[1], "json");

	document("defines", {
				    {"FOO_NAME", quoted(FOO_NAME)},
				    {"FOO_MAGIC", num(FOO_MAGIC)},
				    {"FOO_VERSION_MAJOR", num(FOO_VERSION_MAJOR)},
				    {"FOO_VERSION_MINOR", num(FOO_VERSION_MINOR)},
				    {"FOO_VERSION_PATCH", num(FOO_VERSION_PATCH)},
				    {"FOO_POINTS_MAX", num(FOO_POINTS_MAX)},
				    {"FOO_DEFAULT_SHAPE_SIDES", num(FOO_DEFAULT_SHAPE_SIDES)},
			    });

	auto shape_name = [](int value) -> const char * {
		auto found = foo::name(static_cast<foo::shape>(value));
		return found ? found->data() : "UNKNOWN";
	};
	auto option_name = [](int value) -> const char * {
		auto found = foo::name(static_cast<foo::option>(value));
		return found ? found->data() : "UNKNOWN";
	};
	document("enums", {
				  {"foo_shape", names({-1, 0, 1, 2, 3}, shape_name)},
				  {"foo_option", names({1, 2, 3}, option_name)},
			  });

	std::vector<foo::point> points = {{1, 2}, {3, 4}, {5, 6}};
	auto handle = foo::open("points");
	::foo_handle *unopened = nullptr;
	std::int64_t open_without_name = ::foo_open(nullptr, &unopened);

	std::int64_t added = 0;
	for (const auto &point : points) {
		added += errno_of([&] { handle.add(point); }) == 0;
	}
	std::int64_t count = static_cast<std::int64_t>(handle.count());

	std::int64_t sum_x = 0, sum_y = 0, seen = 0, with_x = 0;
	std::int64_t visit = static_cast<std::int64_t>(handle.visit([&](const foo::point &p) {
		sum_x += p.x;
		sum_y += p.y;
		return 0;
	}));
	std::int64_t stopped = static_cast<std::int64_t>(
		handle.visit([&](const foo::point &) { return ++seen == 2 ? 1 : 0; }));
	std::int64_t without = ::foo_visit(handle.native_handle(), nullptr, nullptr);
	foo::visitor visitor = {
		[](void *arg, const ::foo_point *p) -> int {
			*static_cast<std::int64_t *>(arg) += p->x;
			return 0;
		},
		&with_x,
	};
	std::int64_t visit_with = static_cast<std::int64_t>(handle.visit_with(visitor));
	std::int64_t unknown = errno_of([] { foo::figure_fill(3); });
	std::int64_t add_many = static_cast<std::int64_t>(handle.add_many(points));
	std::int64_t count_after = static_cast<std::int64_t>(handle.count());
	auto copied = handle.points(4);
	std::int64_t copied_x = 0;
	for (const auto &p : copied) {
		copied_x += p.x;
	}
	std::size_t done_count = 0;
	auto counter = [&done_count](std::size_t n) { done_count = n; };
	std::int64_t submit = errno_of([&] { handle.submit(counter); });
	std::int64_t submit_busy = errno_of([&] { handle.submit(counter); });
	std::int64_t poke = static_cast<std::int64_t>(handle.poke());
	std::int64_t poke_again = static_cast<std::int64_t>(handle.poke());

	document("calls", {
				  {"version", quoted(std::string(foo::version()))},
				  {"open", num(0)},
				  {"open_without_name", num(open_without_name)},
				  {"name", quoted(std::string(handle.name()))},
				  {"added", num(added)},
				  {"count", num(count)},
				  {"visit", num(visit)},
				  {"visit_sum_x", num(sum_x)},
				  {"visit_sum_y", num(sum_y)},
				  {"visit_stopped", num(stopped)},
				  {"visit_without_callback", num(without)},
				  {"visit_with", num(visit_with)},
				  {"visit_with_sum_x", num(with_x)},
				  {"figure_of_unknown_shape", num(unknown)},
				  {"add_many", num(add_many)},
				  {"count_after_add_many", num(count_after)},
				  {"points_copied", num(static_cast<std::int64_t>(copied.size()))},
				  {"points_sum_x", num(copied_x)},
				  {"submit", num(submit)},
				  {"submit_busy", num(submit_busy)},
				  {"poke", num(poke)},
				  {"done_count", num(static_cast<std::int64_t>(done_count))},
				  {"poke_again", num(poke_again)},
			  });

	record("foo_point", handle.at(1));
	record("foo_point", handle.at(6));

	while (errno_of([&] { handle.add(points[0]); }) == 0) {
	}
	document("full", {
				 {"count", num(static_cast<std::int64_t>(handle.count()))},
				 {"add", num(errno_of([&] { handle.add(points[0]); }))},
				 {"add_many",
				  num(errno_of([&] {
					  return handle.add_many(std::span(points).first(1));
				  }))},
			 });
	auto status = handle.status_get();
	record("foo_status", std::optional(status));
	document("status", {
				   {"pending", num(foo::code_pending(status))},
				   {"points", num(foo::code_points(status))},
				   {"full", num(foo::code_full(status))},
			   });
	foo::status made = {};
	made.max = FOO_POINTS_MAX;
	foo::set_code_points(made, 5);
	foo::set_code_pending(made, 1);
	record("foo_status", std::optional(made));
	handle.close();

	record("foo_scalars", std::optional(foo::scalars_fill()));
	for (auto shape : {foo::shape::point, foo::shape::line, foo::shape::polygon}) {
		record("foo_figure", std::optional(foo::figure_fill(static_cast<std::uint32_t>(shape))));
	}
	record("foo_value", std::optional(foo::value_set(-1)));
	record("foo_packed", std::optional(foo::packed_fill()));

	return 0;
}
