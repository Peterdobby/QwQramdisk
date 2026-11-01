import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.ios9_pattern import BOOTARGS, bootargs_for_profile, patch_stage

ROOT = Path(__file__).resolve().parents[1]
N61_IBEC = Path(os.environ.get('QWQ_N61_IBEC', ROOT / 'cache/n61-13F69/decrypted/iBEC.raw'))


class StorageBootChecks(unittest.TestCase):
    def test_other_profiles_keep_existing_bootargs(self):
        for profile in ('n66m-13F69', 'n71m-13B143', 'n71m-13A452', 'n51-13F69'):
            self.assertEqual(bootargs_for_profile(profile), BOOTARGS)

    @unittest.skipUnless(N61_IBEC.is_file(), 'local n61 13F69 iBEC sample unavailable')
    def test_generated_ibec_contains_n61_storage_argument(self):
        with tempfile.TemporaryDirectory() as d:
            output, report = Path(d) / 'iBEC', Path(d) / 'patch.json'
            args = bootargs_for_profile('n61-13F69')
            self.assertIn(b' nand-readonly=0\0', args)
            patch_stage(N61_IBEC, output, 'iBEC', report, bootargs=args)
            self.assertIn(args, output.read_bytes())
            plan = json.loads(report.read_text())
            self.assertTrue(any(p['note'] == 'relocate ramdisk boot arguments'
                                and p['after'] == args.hex() for p in plan['patches']))


MOCK = r'''
#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static int has(const char *s){const char *c=getenv("QWQ_STORAGE_CASE");return c&&!strcmp(c,s);}
CFMutableDictionaryRef IOServiceMatching(const char *c){return CFDictionaryCreateMutable(0,0,0,0);}
CFMutableDictionaryRef IOBSDNameMatching(mach_port_t p,uint32_t o,const char *n){
 if(strcmp(n,"disk0s1s2"))abort();return IOServiceMatching(n);
}
mach_port_t IOServiceGetMatchingService(mach_port_t p,CFDictionaryRef d){CFRelease(d);return 1;}
kern_return_t IOServiceGetMatchingServices(mach_port_t p,CFDictionaryRef d,mach_port_t *i){
 CFRelease(d);*i=2;return KERN_SUCCESS;
}
mach_port_t IOIteratorNext(mach_port_t i){static int count=0;++count;if(has("missing"))return 0;
 return count==1?3:(count==2&&has("ambiguous")?4:0);
}
kern_return_t IOObjectRelease(mach_port_t o){return KERN_SUCCESS;}
CFTypeRef IORegistryEntryCreateCFProperty(mach_port_t o,CFStringRef k,CFAllocatorRef a,uint32_t f){
 static int reads=0;++reads;if(!CFEqual(k,CFSTR("Writable")))abort();
 return has("readonly")||(has("after-readonly")&&reads>1)?kCFBooleanFalse:kCFBooleanTrue;
}
kern_return_t IORegistryEntrySetCFProperty(mach_port_t o,CFStringRef k,CFTypeRef v){
 if(o!=3||!CFEqual(k,CFSTR("ASPSetWritable"))||v!=kCFBooleanTrue)abort();
 puts("SET ASPSetWritable true");return has("setfail")?KERN_FAILURE:KERN_SUCCESS;
}
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS compiler required')
class StorageHelperChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        directory = Path(cls.directory.name)
        mock = directory / 'mock.c'
        mock.write_text(MOCK)
        cls.binary = directory / 'helper'
        subprocess.run(['xcrun', '--sdk', 'macosx', 'clang',
                        str(ROOT / 'ramdisk/ensure-asp-writable-ios9.c'), str(mock),
                        '-framework', 'CoreFoundation', '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_case(self, case):
        return subprocess.run([str(self.binary)], env={**os.environ, 'QWQ_STORAGE_CASE': case},
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_readonly_media_fails_before_enabling_writes(self):
        r = self.run_case('readonly')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('SET ASPSetWritable', r.stdout)

    def test_missing_or_ambiguous_controller_never_changes_properties(self):
        for case in ('missing', 'ambiguous'):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn('SET ASPSetWritable', r.stdout)

    def test_controller_failure_is_not_reported_ready(self):
        r = self.run_case('setfail')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('write path ready', r.stdout)

    def test_writable_media_and_successful_property_are_required(self):
        for case in ('ready', 'after-readonly'):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertEqual(r.stdout.count('SET ASPSetWritable true'), 1)
                self.assertEqual(r.returncode == 0, case == 'ready')
