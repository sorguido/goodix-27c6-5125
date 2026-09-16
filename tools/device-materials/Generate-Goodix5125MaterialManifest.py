#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate the per-reader manifest after validating an offline material bundle."""
import argparse, hashlib, json, os, stat, struct, tempfile
from pathlib import Path

SCHEMA='goodix-5125-device-materials-v1'
def read(path, size):
    if not path.is_absolute(): raise ValueError('all input paths must be absolute')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0))
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size!=size: raise ValueError(f'{path.name}: regular {size}-byte file required')
        b=os.read(fd,size)
        if len(b)!=size or os.read(fd,1): raise ValueError(f'{path.name}: short or changing file')
        return b
    finally: os.close(fd)
def crc32_mpeg2(b):
    c=0xffffffff
    for x in b:
        c^=x<<24
        for _ in range(8): c=((c<<1)^(0x04c11db7 if c&0x80000000 else 0))&0xffffffff
    return c
def finalizer(b): return (-0xa5a5-sum(int.from_bytes(b[i:i+2],'little') for i in range(0,222,2)))&0xffff
def response(value,n,name):
    try: b=bytes.fromhex(value)
    except ValueError as e: raise ValueError(f'{name}: invalid hex') from e
    if len(b)!=n: raise ValueError(f'{name}: exactly {n} bytes required')
    return hashlib.sha256(b).hexdigest()
def atomic(path,data):
    if not path.is_absolute() or path.exists() or path.is_symlink(): raise ValueError('output must be a new absolute path')
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        os.fchmod(fd,0o600); os.write(fd,data); os.fsync(fd); os.close(fd); fd=-1; os.link(tmp,path,follow_symlinks=False); os.unlink(tmp); tmp=None
    finally:
        if fd>=0: os.close(fd)
        if tmp:
            try: os.unlink(tmp)
            except OSError: pass
def generate(a):
    t=read(a.transport,88); c=read(a.config90,224); f=read(a.fdt_cache,13520)
    header=struct.unpack_from('<8sHHHHHHHH',t)
    if header!=(b'G5125POC',1,24,0x27c6,0x5125,1,32,32,0): raise ValueError('transport header rejected')
    if int.from_bytes(c[-2:],'little')!=finalizer(c): raise ValueError('CONFIG90 finalizer rejected')
    if int.from_bytes(f[-4:],'little')!=crc32_mpeg2(f[:-4]): raise ValueError('FDT cache CRC rejected')
    m={'schema':SCHEMA,'vid':'27c6','pid':'5125','app':'GF_ST411SEC_APP_12509',
       'transport_sha256':hashlib.sha256(t).hexdigest(),'config90_sha256':hashlib.sha256(c).hexdigest(),
       'fdt_cache_sha256':hashlib.sha256(f).hexdigest(),'a2_response_sha256':response(a.a2,3,'A2'),
       'chip82_response_sha256':response(a.chip82,4,'chip82'),'otp_a6_response_sha256':response(a.otp,64,'OTP A6')}
    if m['otp_a6_response_sha256']!=hashlib.sha256(f[:64]).hexdigest(): raise ValueError('OTP A6 response does not match FDT cache OTP')
    atomic(a.output,(json.dumps(m,indent=2,sort_keys=True)+'\n').encode()); return m
def selftest():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d); t=struct.pack('<8sHHHHHHHH',b'G5125POC',1,24,0x27c6,0x5125,1,32,32,0)+bytes(range(64)); c=bytearray(224); c[-2:]=finalizer(c).to_bytes(2,'little'); f=bytearray(13520); f[:64]=bytes(range(64)); f[64:76]=b'nonzero-seed'; f[-4:]=crc32_mpeg2(f[:-4]).to_bytes(4,'little')
        for n,b in [('t',t),('c',c),('f',f)]: (p/n).write_bytes(b)
        a=argparse.Namespace(transport=(p/'t').absolute(),config90=(p/'c').absolute(),fdt_cache=(p/'f').absolute(),a2='010203',chip82='01020304',otp=bytes(range(64)).hex(),output=(p/'m').absolute()); generate(a); assert json.loads((p/'m').read_text())['schema']==SCHEMA
    print('GOODIX_MATERIAL_MANIFEST_SELFTEST=PASS')
def main():
    q=argparse.ArgumentParser(); q.add_argument('--self-test',action='store_true'); q.add_argument('--transport',type=Path); q.add_argument('--config90',type=Path); q.add_argument('--fdt-cache',type=Path); q.add_argument('--a2-response-hex',dest='a2'); q.add_argument('--chip82-response-hex',dest='chip82'); q.add_argument('--otp-a6-response-hex',dest='otp'); q.add_argument('--output',type=Path); a=q.parse_args()
    if a.self_test: selftest(); return
    try: generate(a)
    except (OSError,ValueError,TypeError) as e: raise SystemExit('GOODIX_MATERIAL_MANIFEST=FAIL: '+str(e))
    print('GOODIX_MATERIAL_MANIFEST=PASS')
if __name__=='__main__': main()
