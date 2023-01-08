/**
 * Copyright (C) Simon A. F. Lund <os@safl.dk>
 * SPDX-License-Identifier: BSD-3-CLAUSE
 *
 * @file example_spec.c
 */
#include <inttypes.h>
#include <stdio.h>
#include <errno.h>
#include <libexample.h>
#include <libexample_pp.h>




static int
example_point_yaml(FILE *stream, const struct example_point *obj, int flags)
{
	int wrtn = 0;

	wrtn += fprintf(stream, "example_point:");

	if (!obj) {
		wrtn += fprintf(stream, " ~\n");
		return wrtn;
	}

	// TODO: implement the yaml-representation

	return wrtn;
}

int
example_point_fpr(FILE *stream, const struct example_point *obj, int flags)
{
	switch (flags) {
	case EXAMPLE_PR_DEF:
	case EXAMPLE_PR_YAML:
		return example_point_yaml(stream, obj, flags);
		break;

	case EXAMPLE_PR_JSON:
		return -ENOSYS;
	}

	return -ENOSYS;
}

int
example_point_pr(const struct example_point *obj, int flags)
{
	return example_point_fpr(stdout, obj, flags);
}