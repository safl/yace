/**
 * Prints the given backend attribute to the given output stream
 *
 * @param stream output stream used for printing
 * @param attr Pointer to the ::example_be_attr to print
 * @param opts printer options, see ::example_pr
 *
 * @return On success, the number of characters printed is returned.
 */
int
example_be_attr_fpr(FILE *stream, const struct example_be_attr *attr, int flags);

/**
 * Prints the given backend attribute to stdout
 *
 * @param attr Pointer to the ::example_be_attr to print
 * @param opts printer options, see ::example_pr
 *
 * @return On success, the number of characters printed is returned.
 */
int
example_be_attr_pr(const struct example_be_attr *attr, int flags);
