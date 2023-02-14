#include <stdio.h>
#include <inttypes.h>

int
main(int argc, const char *argv[])
{
	printf("sizeof(uint8_t) = %lu\n", sizeof(uint8_t));
	printf("sizeof(uint16_t) = %lu\n", sizeof(uint16_t));
	printf("sizeof(uint32_t) = %lu\n", sizeof(uint32_t));
	printf("sizeof(uint64_t) = %lu\n", sizeof(uint64_t));

	printf("sizeof(int8_t) = %lu\n", sizeof(int8_t));
	printf("sizeof(int16_t) = %lu\n", sizeof(int16_t));
	printf("sizeof(int32_t) = %lu\n", sizeof(int32_t));
	printf("sizeof(int64_t) = %lu\n", sizeof(int64_t));

	printf("sizeof(char) = %lu\n", sizeof(char));
	printf("sizeof(unsigned char) = %lu\n", sizeof(unsigned char));
	printf("sizeof(signed char) = %lu\n", sizeof(signed char));

	printf("sizeof(short int) = %lu\n", sizeof(short int));
	printf("sizeof(unsigned short int) = %lu\n", sizeof(unsigned short int));
	printf("sizeof(signed short int) = %lu\n", sizeof(signed short int));

	printf("sizeof(int) = %lu\n", sizeof(int));
	printf("sizeof(unsigned int) = %lu\n", sizeof(unsigned int));
	printf("sizeof(signed int) = %lu\n", sizeof(signed int));

	printf("sizeof(long int) = %lu\n", sizeof(long int));
	printf("sizeof(unsigned long int) = %lu\n", sizeof(unsigned long int));
	printf("sizeof(signed long int) = %lu\n", sizeof(signed long int));

	printf("sizeof(long long int) = %lu\n", sizeof(long long int));
	printf("sizeof(unsigned long long int) = %lu\n", sizeof(unsigned long long int));
	printf("sizeof(signed long long int) = %lu\n", sizeof(signed long long int));

	return 0;
}
