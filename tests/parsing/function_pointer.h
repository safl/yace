/**
 * Function pointer to a binary operator
 */
typedef int (*binop_func)(int, int);

/**
 * Function pointer utilization
 *
 * @param op Function pointer to a binary operator
 * @param a Left-hand input-argument to binary operator
 * @param b Right-hand input-argument to binary operator
 *
 * @result Returns result of applying the binary operator to the inputs.
 */
int
apply(binop_func op, int a, int b);
