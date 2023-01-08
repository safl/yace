/**
 * yace example
 *
 * This example is intended for documentation as well as testing
 *
 * NOTE: This file is auto-generated using yace: https://github.com/safl/yace
 *
 * Copyright (C) Simon A. F. Lund <os@safl.dk>
 * SPDX-License-Identifier: BSD-3-CLAUSE
 *
 * @file example.h
 */
#ifndef EXAMPLE_H
#define EXAMPLE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <assert.h>
#include <stdint.h>
#include <sys/types.h>

#define MAX_X 128

#define MAX_Y 64

#define MAX_Z 64

/**
 * Point in three dimensional space
 *
 * @struct example_point
 */
struct example_point {
	int32_t x; ///< X Coordinate
	int32_t y; ///< Y Coordinate
	int32_t z; ///< Z Coordinate
};

#ifdef __cplusplus
}
#endif

#endif /* EXAMPLE_H */