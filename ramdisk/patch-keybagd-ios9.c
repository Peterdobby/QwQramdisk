/* Fixed, fail-closed iOS 9 system-keybag patcher for known source hashes.
 * Compile once for the ramdisk; no compiler or signing runs during create.
 */
#include <CommonCrypto/CommonDigest.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

struct patch {
    size_t offset;
    unsigned char before[4];
    unsigned char after[4];
};

struct profile {
    const char *build;
    size_t size;
    unsigned paths;
    const char *source_sha256;
    const char *result_sha256;
    const struct patch *patches;
    size_t patch_count;
};

/* Generated from the reviewed source-hash registry before signing. */
#include "keybagd-profiles.h"

static int digest_matches(const unsigned char *data, size_t size, const char *hex)
{
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    char actual[CC_SHA256_DIGEST_LENGTH * 2 + 1];
    size_t i;
    CC_SHA256(data, (CC_LONG)size, digest);
    for (i = 0; i < sizeof(digest); ++i)
        snprintf(actual + i * 2, 3, "%02x", digest[i]);
    return strcmp(actual, hex) == 0;
}

int main(int argc, char **argv)
{
    static const char old_path[] = "/private/var";
    static const char new_path[] = "/mnt2//././.";
    FILE *input = NULL, *output = NULL;
    unsigned char *data = NULL;
    const struct profile *profile = NULL;
    long length;
    size_t size, i, j, paths = 0;
    int result = 1;
    int check_only = argc == 3 && !strcmp(argv[1], "--check");

    if (argc != 3 || (!check_only && !strcmp(argv[1], argv[2]))) {
        fprintf(stderr, "usage: patch-keybagd-ios9 SOURCE DESTINATION | --check SOURCE\n");
        return 1;
    }
    input = fopen(argv[check_only ? 2 : 1], "rb");
    if (!input || fseek(input, 0, SEEK_END) ||
        (length = ftell(input)) < 0 || fseek(input, 0, SEEK_SET)) {
        fprintf(stderr, "patch-keybagd-ios9: cannot read source\n");
        goto done;
    }
    size = (size_t)length;
    data = malloc(size);
    if (size < 8 || !data || fread(data, 1, size, input) != size ||
        memcmp(data, "\xcf\xfa\xed\xfe\x0c\0\0\x01", 8)) {
        fprintf(stderr, "patch-keybagd-ios9: cannot read source Mach-O\n");
        goto done;
    }
    for (i = 0; i < sizeof(profiles) / sizeof(profiles[0]); ++i)
        if (size == profiles[i].size &&
            digest_matches(data, size, profiles[i].source_sha256)) {
            profile = &profiles[i];
            break;
        }
    if (!profile) {
        fprintf(stderr, "patch-keybagd-ios9: unsupported source size or SHA-256\n");
        goto done;
    }
    for (i = 0; i + sizeof(old_path) - 1 <= size; ++i) {
        if (!memcmp(data + i, old_path, sizeof(old_path) - 1)) {
            memcpy(data + i, new_path, sizeof(new_path) - 1);
            ++paths;
            i += sizeof(old_path) - 2;
        }
    }
    if (paths != profile->paths) {
        fprintf(stderr, "patch-keybagd-ios9: unexpected Data path count %zu\n", paths);
        goto done;
    }
    for (j = 0; j < profile->patch_count; ++j) {
        const struct patch *p = &profile->patches[j];
        if (p->offset + 4 > size || memcmp(data + p->offset, p->before, 4)) {
            fprintf(stderr, "patch-keybagd-ios9: unexpected bytes at 0x%zx\n", p->offset);
            goto done;
        }
        memcpy(data + p->offset, p->after, 4);
    }
    if (!digest_matches(data, size, profile->result_sha256)) {
        fprintf(stderr, "patch-keybagd-ios9: output SHA-256 mismatch\n");
        goto done;
    }
    if (check_only) {
        fprintf(stderr, "patch-keybagd-ios9: matched %s by source SHA-256; validated %zu patches\n",
                profile->build, profile->patch_count);
        result = 0;
        goto done;
    }
    output = fopen(argv[2], "wb");
    if (!output || fwrite(data, 1, size, output) != size ||
        fflush(output) || chmod(argv[2], 0755)) {
        fprintf(stderr, "patch-keybagd-ios9: destination write failed\n");
        goto done;
    }
    fprintf(stderr, "patch-keybagd-ios9: %s relocated %zu paths and patched %zu instructions\n",
            profile->build, paths, profile->patch_count);
    result = 0;
done:
    if (output) fclose(output);
    if (input) fclose(input);
    free(data);
    return result;
}
