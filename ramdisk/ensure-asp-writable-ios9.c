/* Enable the A8 ASP write path before mounting System or Data.
 * nand-readonly=0 must already have published writable child media at boot.
 * This only sets the driver's ASPSetWritable property; it never formats media.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdio.h>

typedef mach_port_t io_object_t;
extern CFMutableDictionaryRef IOServiceMatching(const char *);
extern CFMutableDictionaryRef IOBSDNameMatching(mach_port_t, uint32_t, const char *);
extern io_object_t IOServiceGetMatchingService(mach_port_t, CFDictionaryRef);
extern kern_return_t IOServiceGetMatchingServices(mach_port_t, CFDictionaryRef, io_object_t *);
extern io_object_t IOIteratorNext(io_object_t);
extern kern_return_t IOObjectRelease(io_object_t);
extern CFTypeRef IORegistryEntryCreateCFProperty(io_object_t, CFStringRef, CFAllocatorRef, uint32_t);
extern kern_return_t IORegistryEntrySetCFProperty(io_object_t, CFStringRef, CFTypeRef);

static int data_is_writable(void)
{
    CFMutableDictionaryRef match = IOBSDNameMatching(0, 0, "disk0s1s2");
    if (!match) return 0;
    io_object_t media = IOServiceGetMatchingService(0, match);
    if (!media) return 0;
    CFTypeRef value = IORegistryEntryCreateCFProperty(media, CFSTR("Writable"),
                                                     kCFAllocatorDefault, 0);
    int writable = value && CFGetTypeID(value) == CFBooleanGetTypeID()
                   && CFBooleanGetValue(value);
    if (value) CFRelease(value);
    IOObjectRelease(media);
    return writable;
}

int main(void)
{
    if (!data_is_writable()) {
        fputs("ensure-asp-writable-ios9: Data media is read-only; recreate and boot "
              "the matching image with nand-readonly=0 before retrying\n", stderr);
        return 1;
    }
    CFMutableDictionaryRef match = IOServiceMatching("ASPStorage");
    io_object_t iterator = 0;
    if (!match || IOServiceGetMatchingServices(0, match, &iterator)) {
        fputs("ensure-asp-writable-ios9: cannot match ASPStorage\n", stderr);
        return 1;
    }
    io_object_t storage = IOIteratorNext(iterator);
    io_object_t other = IOIteratorNext(iterator);
    IOObjectRelease(iterator);
    if (!storage || other) {
        if (storage) IOObjectRelease(storage);
        if (other) IOObjectRelease(other);
        fputs("ensure-asp-writable-ios9: expected exactly one ASPStorage; stopped\n", stderr);
        return 1;
    }
    kern_return_t result = IORegistryEntrySetCFProperty(storage, CFSTR("ASPSetWritable"),
                                                       kCFBooleanTrue);
    IOObjectRelease(storage);
    if (result) {
        fprintf(stderr, "ensure-asp-writable-ios9: ASPSetWritable failed (0x%x)\n", result);
        return 1;
    }
    if (!data_is_writable()) {
        fputs("ensure-asp-writable-ios9: Data media is not writable after setup\n", stderr);
        return 1;
    }
    puts("ensure-asp-writable-ios9: ASP write path ready; Data media Writable=true");
    return 0;
}
