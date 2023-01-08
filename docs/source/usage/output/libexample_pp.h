/**
 * Pretty-printers for the enums and structs
 *
 * NOTE: This file is auto-generated using yace: https://github.com/safl/yace
 *
 * Copyright (C) Simon A. F. Lund <os@safl.dk>
 * SPDX-License-Identifier: BSD-3-CLAUSE
 *
 * @file libexample_pp.h
 */

/**
 * Options for pretty-printer (``*_pr``, ``*_fpr``) functions
 *
 * Options determines the format the pretty-printer uses, e.g. Yaml or JSON
 *
 * @enum example_pr
 */
enum example_pr {
	EXAMPLE_PR_DEF  = 0x0,
	EXAMPLE_PR_YAML = 0x1,
	EXAMPLE_PR_JSON = 0x2,
};

/**
 * Prints the given ::example_point 'obj' to the given output 'stream'
 *
 * @param stream output stream used for printing
 * @param obj Pointer to the ::example_point to print
 * @param flags Pretty-printer flags
 *
 * @return On success, the number of characters printed is returned.
 */
int
example_point_fpr(FILE *stream, const struct example_point *obj, int flags);

/**
 * Prints the given ::example_point 'obj' to stdout
 *
 * @param obj Pointer to the ::example_point to print
 * @param flags Pretty-printer flags
 *
 * @return On success, the number of characters printed is returned.
 */
int
example_point_pr(const struct example_point *obj, int flags);
