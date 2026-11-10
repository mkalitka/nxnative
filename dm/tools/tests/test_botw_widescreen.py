"""BOTW's camera writer: run the emitted ARM64 body with synthetic game objects.

No game files. The test also checks the launcher offers one Picture shape setting,
and the shared UI math keeps physical HUD widths unchanged on an iPhone.
"""
import importlib.util
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'dm/tools'))
from nso_asm import ADRP, B


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


botw = load('botw_wide_patches', ROOT / 'dm/games/01007EF00011E000/patches.py')
settings = load('botw_wide_settings', ROOT / 'dm/games/settings.py')


class Widescreen(unittest.TestCase):
    def test_picture_shape_matches_screen_by_default(self):
        # One launcher setting for both shapes: Picture shape (DM_SCREEN_ASPECT), offered by the profile's screen_aspect; Match screen on the Mac too
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings.nacp, 'languages', return_value=['en-US']):
            (Path(tmp) / 'main.fixups.tsv').write_text('# WIDESCREEN\t1\n')
            for platform_name in ('ios', 'mac'):
                with patch.dict('os.environ', {'SETTINGS_PLATFORM': platform_name}):
                    rows = {s['env']: s for s in settings.build('01007EF00011E000', tmp, Path(tmp) / 'control.nacp')['settings']}
                self.assertNotIn('DM_WIDESCREEN', rows)
                self.assertEqual(rows['DM_SCREEN_ASPECT']['default'], 'auto')
                self.assertEqual(rows['DM_SCREEN_ASPECT']['options'], [['auto', 'Match screen'], ['1.43', 'iPhone Duo screen (1.43:1)'], ['0', '16:9 (Switch)']])

    @unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64' and shutil.which('clang'), 'native Apple ARM64 test')
    def test_camera_writer_and_ui_geometry(self):
        words, sites, puts = [], [], []
        ctx = types.SimpleNamespace(here=lambda: 0x3000000 + 4 * len(words), emit=words.append,
                                    site=lambda *v: sites.append(v), put=lambda *v: puts.append(v), state=0x4000000, capabilities=set())
        botw.widescreen(ctx)
        self.assertEqual(len(bytes.fromhex(sites[0][1])), 52)   # entire writer checked, not just the entry word
        self.assertEqual(puts[0][0], 0x10edae0)
        self.assertEqual(puts[0][1], [B(0x10edae0, 0x3000000)])
        self.assertEqual(words[-1], B(0x3000000 + 4 * (len(words) - 1), 0x10edb14))
        self.assertEqual(ctx.capabilities, {'WIDESCREEN'})
        # Relocate only the state-page ADRP and final return for this standalone native
        # function. All other instructions are exactly the words emitted by the profile.
        body = []
        for i, word in enumerate(words[:-1]):
            if word == ADRP(8, 0x3000000 + 4 * i, ctx.state):
                body += ['adrp x8, _wide_state@PAGE', 'add x8, x8, _wide_state@PAGEOFF']
            else:
                body.append(f'.long {word:#x}')
        asm = '''.text
.globl _camera_writer
.p2align 2
_camera_writer:
stp x19,x20,[sp,#-32]!
stp x21,x22,[sp,#16]
mov x19,x0
mov x20,x1
mov x21,x2
mov w22,#1
''' + '\n'.join(body) + '''
ldp x21,x22,[sp,#16]
ldp x19,x20,[sp],#32
ret
'''
        harness = '''#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "nvn_widescreen.h"
_Alignas(4096) float wide_state[16];
extern void camera_writer(void *, void *, void *);
static float get(const unsigned char *p, unsigned off) { float f; memcpy(&f,p+off,4); return f; }
static void put(unsigned char *p,unsigned off,float f) { memcpy(p+off,&f,4); }
int main(void) {
    unsigned char projection[256]={0}, planes[128]={0}, rect[128]={0};
    put(planes,0x6c,0.1f); put(planes,0x70,5000);
    put(rect,0x38,10); put(rect,0x3c,20); put(rect,0x40,1930); put(rect,0x44,1100);
    float phone=nvn_widescreen_ratio(2868,1320);
    assert(fabs(phone-2868.0/1320)<1e-6);
    assert(!nvn_widescreen_ratio(1920,1080)); assert(!nvn_widescreen_ratio(1952,1100));   // 16:9 within 1 %
    assert(!nvn_widescreen_ratio(2732,2048)); assert(!nvn_widescreen_ratio(1512,945));   // iPad, 16:10 MacBook: taller, the game's own rendering (DM_SCREEN_ASPECT)
    assert(!nvn_widescreen_ratio(0,0)); assert(!nvn_widescreen_ratio(INFINITY,1)); assert(!nvn_widescreen_ratio(1,3));
    float requests[]={0,phone,phone,0};
    for(unsigned i=0;i<4;i++) {
        wide_state[14]=requests[i]; wide_state[15]=-1; projection[0x18]=0;
        camera_writer(projection,planes,rect);
        assert(fabs(get(projection,0xc0)-(requests[i]>0?requests[i]:16.0/9))<1e-6);
        assert(projection[0x18]==1); assert(get(projection,0xa8)==0.1f); assert(get(projection,0xac)==5000);
        assert(wide_state[15]==requests[i]);
    }
    double factor=phone/(16.0/9), scale=2868.0/1920;
    double l=nvn_widescreen_x(0,1920,factor), r=nvn_widescreen_x(1920,1920,factor);
    assert(fabs((r-l)*scale-1320.0*16/9)<0.001); // centered physical 16:9 HUD
    assert(fabs((l+r)/2-960)<1e-6);
    double hud=nvn_widescreen_x(200,1920,factor)-nvn_widescreen_x(100,1920,factor);
    assert(fabs(hud*scale-100.0*1320/1080)<0.001);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); (d / 'writer.S').write_text(asm); (d / 'test.c').write_text(harness)
            subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'dm/gfx/nvn'),
                            str(d / 'test.c'), str(d / 'writer.S'), '-o', str(d / 'test')], check=True, capture_output=True)
            subprocess.run([str(d / 'test')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
