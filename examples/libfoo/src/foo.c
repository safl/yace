/*
 * SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <foo.h>

struct foo_handle {
	char *name;
	struct foo_point points[FOO_POINTS_MAX];
	size_t npoints;
	foo_done_cb done;
	void *done_arg;
	foo_added_cb added;
	void *added_arg;
};

const char *
foo_version(void)
{
	return "1.2.3";
}

int
foo_open(const char *name, struct foo_handle **handle)
{
	struct foo_handle *opened;

	if (!name || !handle) {
		return -EINVAL;
	}

	opened = calloc(1, sizeof(*opened));
	if (!opened) {
		return -ENOMEM;
	}
	opened->name = malloc(strlen(name) + 1);
	if (!opened->name) {
		free(opened);
		return -ENOMEM;
	}
	strcpy(opened->name, name);

	*handle = opened;

	return 0;
}

void
foo_close(struct foo_handle *handle)
{
	if (!handle) {
		return;
	}
	free(handle->name);
	free(handle);
}

const char *
foo_name(const struct foo_handle *handle)
{
	return handle->name;
}

int
foo_point_add(struct foo_handle *handle, const struct foo_point *point)
{
	if (handle->npoints == FOO_POINTS_MAX) {
		return -ENOSPC;
	}
	handle->points[handle->npoints++] = *point;
	if (handle->added) {
		handle->added(handle->added_arg, point);
	}

	return 0;
}

ssize_t
foo_point_add_many(struct foo_handle *handle, const struct foo_point *points, size_t npoints)
{
	size_t added = 0;

	while (added < npoints && !foo_point_add(handle, &points[added])) {
		added += 1;
	}

	return added || !npoints ? (ssize_t)added : -ENOSPC;
}

size_t
foo_point_count(const struct foo_handle *handle)
{
	return handle->npoints;
}

const struct foo_point *
foo_point_get(const struct foo_handle *handle, size_t idx)
{
	return idx < handle->npoints ? &handle->points[idx] : NULL;
}

ssize_t
foo_point_copy(const struct foo_handle *handle, struct foo_point *points, size_t npoints)
{
	size_t copied = npoints < handle->npoints ? npoints : handle->npoints;

	memcpy(points, handle->points, copied * sizeof(*points));

	return (ssize_t)copied;
}

int
foo_point_watch(struct foo_handle *handle, foo_added_cb added, void *arg)
{
	if (handle->added) {
		return -EBUSY;
	}
	handle->added = added;
	handle->added_arg = arg;

	return 0;
}

ssize_t
foo_point_visit(struct foo_handle *handle, foo_visit_cb visit, void *arg)
{
	ssize_t visited = 0;

	if (!visit) {
		return -EINVAL;
	}

	for (size_t idx = 0; idx < handle->npoints; ++idx) {
		visited += 1;
		if (visit(arg, &handle->points[idx])) {
			break;
		}
	}

	return visited;
}

ssize_t
foo_point_visit_with(struct foo_handle *handle, const struct foo_visitor *visitor)
{
	return foo_point_visit(handle, visitor->visit, visitor->arg);
}

int
foo_count_submit(struct foo_handle *handle, foo_done_cb done, void *arg)
{
	if (handle->done) {
		return -EBUSY;
	}
	handle->done = done;
	handle->done_arg = arg;

	return 0;
}

size_t
foo_count_complete(struct foo_handle *handle)
{
	foo_done_cb done = handle->done;

	if (!done) {
		return 0;
	}
	handle->done = NULL;
	done(handle->done_arg, handle->npoints);

	return 1;
}

void
foo_status_get(const struct foo_handle *handle, struct foo_status *status)
{
	status->code = (uint16_t)((handle->done ? FOO_STATUS_CODE_PENDING : 0) |
				  ((handle->npoints << 4) & FOO_STATUS_CODE_POINTS) |
				  (handle->npoints == FOO_POINTS_MAX ? FOO_STATUS_CODE_FULL : 0));
	status->max = FOO_POINTS_MAX;
}

void
foo_scalars_fill(struct foo_scalars *scalars)
{
	memset(scalars, 0, sizeof(*scalars));

	scalars->flag = true;
	scalars->letter = 'y';
	scalars->schar = -2;
	scalars->uchar = 250;
	scalars->s = -300;
	scalars->us = 60000;
	scalars->i = -70000;
	scalars->ui = 4000000000u;
	scalars->l = -5;
	scalars->ul = 6;
	scalars->ll = -7;
	scalars->ull = 8;
	scalars->f = 0.5f;
	scalars->d = -2.25;
	scalars->i8 = INT8_MIN;
	scalars->i16 = INT16_MIN;
	scalars->i32 = INT32_MIN;
	scalars->i64 = INT64_MIN;
	scalars->u8 = UINT8_MAX;
	scalars->u16 = UINT16_MAX;
	scalars->u32 = UINT32_MAX;
	scalars->u64 = UINT64_MAX;
	scalars->iptr = -9;
	scalars->uptr = 10;
	scalars->size = 11;
	scalars->ssize = -12;
	scalars->diff = -13;
}

int
foo_figure_fill(struct foo_figure *figure, uint32_t shape)
{
	static const struct foo_point corners[] = {{0, 0}, {4, 0}, {4, 3}, {0, 3}};

	memset(figure, 0, sizeof(*figure));

	switch (shape) {
	case FOO_SHAPE_POINT:
		figure->ncorners = 1;
		strcpy(figure->name, "point");
		break;
	case FOO_SHAPE_LINE:
		figure->ncorners = 2;
		strcpy(figure->name, "line");
		break;
	case FOO_SHAPE_POLYGON:
		figure->ncorners = 4;
		figure->options = FOO_OPTION_CLOSED | FOO_OPTION_FILLED;
		figure->area = 12.0;
		strcpy(figure->name, "rectangle");
		break;
	default:
		return -EINVAL;
	}

	figure->shape = shape;
	figure->origin.x = -1;
	figure->origin.y = 2;
	memcpy(figure->corners, corners, figure->ncorners * sizeof(corners[0]));
	for (int row = 0; row < 2; ++row) {
		for (int col = 0; col < 3; ++col) {
			figure->grid[row][col] = (int16_t)(row * 3 + col - 2);
		}
	}
	figure->label = "say \"hi\"\tthen go";
	figure->scale = 1.5f;

	return 0;
}

void
foo_value_set(union foo_value *value, int32_t i)
{
	memset(value, 0, sizeof(*value));
	value->i = i;
}

void
foo_wire_fill(struct foo_wire *wire)
{
	memset(wire, 0, sizeof(*wire));
	wire->kind = FOO_SHAPE_LINE;
	wire->length = 4000000000u;
	wire->at.x = -3;
	wire->at.y = 4;
	wire->pair[0] = 1;
	wire->pair[1] = UINT16_MAX;
}
