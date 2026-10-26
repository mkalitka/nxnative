"""BOTW's camera writer: run the emitted ARM64 body with synthetic game objects.

No game files. The test also checks the launcher gates support on rewritten main,
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
    def test_only_patched_build_offers_automatic_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(settings.nacp, 'languages', return_value=['en-US']):
            main = Path(tmp) / 'main.fixups.tsv'
            for header, supported in [('', False), ('# RENDER_SCALE\t1\n', False), ('# WIDESCREEN\t1\n', True)]:
                main.write_text(header)
                rows = {s['env']: s for s in settings.build('01007EF00011E000', tmp, Path(tmp) / 'control.nacp')['settings']}
                self.assertEqual('DM_WIDESCREEN' in rows, supported)
                if supported:
                    self.assertEqual(rows['DM_WIDESCREEN']['default'], '2')
                    self.assertEqual(rows['DM_WIDESCREEN']['options'], [['2', 'Automatic'], ['1', 'Full screen'], ['0', '16:9']])

    @unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64' and shutil.which('clang'), 'native Apple ARM64 test')
    def test_camera_writer_and_ui_geometry(self):
        words, sites, puts = [], [], []
        ctx = types.SimpleNamespace(here=lambda: 0x3000000 + 4 * len(words), emit=words.append,
                                    site=lambda *v: sites.append(v), put=lambda *v: puts.append(v), state=0x4000000)
        botw.widescreen(ctx)
        self.assertEqual(len(bytes.fromhex(sites[0][1])), 52)   # entire writer checked, not just the entry word
        self.assertEqual(puts[0][0], 0x10edae0)
        self.assertEqual(puts[0][1], [B(0x10edae0, 0x3000000)])
        self.assertEqual(words[-1], B(0x3000000 + 4 * (len(words) - 1), 0x10edb14))
        self.assertEqual(ctx.widescreen, 1)
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
    assert(fabs(nvn_widescreen_ratio(2732,2048)-2732.0/2048)<1e-6);   // iPad
    assert(fabs(nvn_widescreen_ratio(1512,945)-1.6)<1e-6);   // MacBook below the notch: 16:10
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
    // 16:10 (2560x1600 shown from a 1920x1080 canvas): the HUD is flattened to a centred 16:9 band across the width
    double f10=(2560.0/1600)/(16.0/9), sx=2560.0/1920, sy=1600.0/1080;
    double t=nvn_widescreen_x(0,1080,1/f10), b=nvn_widescreen_x(1080,1080,1/f10);
    assert(fabs(1920*sx/((b-t)*sy)-16.0/9)<1e-6); assert(fabs((t+b)/2-540)<1e-6);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); (d / 'writer.S').write_text(asm); (d / 'test.c').write_text(harness)
            subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'dm/gfx/nvn'),
                            str(d / 'test.c'), str(d / 'writer.S'), '-o', str(d / 'test')], check=True, capture_output=True)
            subprocess.run([str(d / 'test')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
