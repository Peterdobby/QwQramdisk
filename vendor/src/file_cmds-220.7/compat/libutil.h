#include <stddef.h>
#include <stdint.h>
#define HN_DECIMAL 0x01
#define HN_NOSPACE 0x02
#define HN_B 0x04
#define HN_DIVISOR_1000 0x08
#define HN_IEC_PREFIXES 0x10
#define HN_GETSCALE 0x10
#define HN_AUTOSCALE 0x20
int humanize_number(char *, size_t, int64_t, const char *, int, int);
