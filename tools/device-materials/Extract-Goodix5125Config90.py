#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline extractor for Goodix 27c6:5125 CONFIG90 from USBPcap pcapng."""
from __future__ import annotations
import argparse, hashlib, json, sys, tempfile
from dataclasses import dataclass
from pathlib import Path
from _goodix5125_usbpcap import (
    A0, ExtractError, atomic_write_new_0600, iter_bulk_payloads, parse_a0,
    reassemble_frames, synthetic_a0_frame, synthetic_pcapng,
)

CONFIG90=0x90; CONFIG90_LEN=224; FINALIZER_OFF=222

@dataclass(frozen=True)
class Candidate:
    first_packet:int; last_packet:int; wire_control:int; body:bytes
    @property
    def sha256(self): return hashlib.sha256(self.body).hexdigest()

def expected_finalizer(body):
    if len(body)!=CONFIG90_LEN: raise ExtractError(f'CONFIG90 length {len(body)} != {CONFIG90_LEN}')
    total=sum(int.from_bytes(body[o:o+2],'little') for o in range(0,FINALIZER_OFF,2))&0xffff
    return (-0xa5a5-total)&0xffff

def validate_config90(body):
    exp=expected_finalizer(body); obs=int.from_bytes(body[-2:],'little')
    if obs!=exp: raise ExtractError(f'CONFIG90 finalizer mismatch: observed=0x{obs:04x}, expected=0x{exp:04x}')

def find_candidates(path):
    out=[]
    payloads=iter_bulk_payloads(path,device_to_host=False)
    for frame in reassemble_frames(payloads):
        if frame.raw[0]!=A0: continue
        try: wire,logical,body=parse_a0(frame.raw)
        except ExtractError: continue
        if logical!=CONFIG90 or len(body)!=CONFIG90_LEN: continue
        try: validate_config90(body)
        except ExtractError: continue
        out.append(Candidate(frame.first_packet,frame.last_packet,wire,body))
    return out

def choose(cands):
    if not cands: raise ExtractError('no valid 224-byte A0/0x90 CONFIG90 frame found')
    groups={}
    for c in cands: groups.setdefault(c.sha256,[]).append(c)
    if len(groups)!=1:
        s=', '.join(f'{h[:12]}… ({len(v)} occurrence(s))' for h,v in sorted(groups.items()))
        raise ExtractError('multiple distinct valid CONFIG90 bodies found: '+s)
    grp=next(iter(groups.values())); return grp[0].body,grp

def extract(pcap,output):
    body,occ=choose(find_candidates(pcap)); atomic_write_new_0600(output,body)
    return {'schema':'GOODIX5125_CONFIG90_EXTRACTION_V1','result':'PASS','source_capture':str(pcap),'output':str(output),'size':len(body),'sha256':hashlib.sha256(body).hexdigest(),'finalizer_le':body[-2:].hex(),'occurrence_count':len(occ),'occurrences':[{'first_packet_index':c.first_packet,'last_packet_index':c.last_packet,'wire_control':f'0x{c.wire_control:02x}'} for c in occ]}

# ---- synthetic self-test ----
def make_config(seed):
    b=bytearray(CONFIG90_LEN)
    for i in range(FINALIZER_OFF): b[i]=(i*37+seed*11)&0xff
    b[-2:]=expected_finalizer(bytes(b)).to_bytes(2,'little'); return bytes(b)
def build_frame(body):
    return synthetic_a0_frame(CONFIG90,body,wire_control=0x91)
def pcapng(chunks): return synthetic_pcapng((chunk,False) for chunk in chunks)
def selftest():
    with tempfile.TemporaryDirectory() as td:
        r=Path(td); b1=make_config(1); f1=build_frame(b1)
        p=r/'frag.pcapng'; p.write_bytes(pcapng([f1[:31],f1[31:117],f1[117:]])); body,occ=choose(find_candidates(p)); assert body==b1 and len(occ)==1
        p2=r/'dup.pcapng'; p2.write_bytes(pcapng([f1,f1])); body,occ=choose(find_candidates(p2)); assert body==b1 and len(occ)==2
        b2=make_config(2); p3=r/'amb.pcapng'; p3.write_bytes(pcapng([f1,build_frame(b2)]))
        try: choose(find_candidates(p3)); raise AssertionError('ambiguous capture accepted')
        except ExtractError: pass
        bad=bytearray(b1); bad[-1]^=1; p4=r/'bad.pcapng'; p4.write_bytes(pcapng([build_frame(bytes(bad))])); assert find_candidates(p4)==[]
        out=r/'target-config-90.bin'; rep=extract(p,out); assert out.read_bytes()==b1 and (out.stat().st_mode&0o777)==0o600 and rep['size']==224
    print('GOODIX_CONFIG90_SELFTEST=PASS')

def main():
    ap=argparse.ArgumentParser(description='Extract Goodix 27c6:5125 target-config-90.bin from an offline Windows USBPcap pcapng capture.')
    ap.add_argument('--pcap',type=Path); ap.add_argument('--output',type=Path); ap.add_argument('--json',action='store_true'); ap.add_argument('--self-test',action='store_true'); a=ap.parse_args()
    if a.self_test: selftest(); return 0
    if a.pcap is None or a.output is None: print('ERROR: --pcap and --output are required unless --self-test is used',file=sys.stderr); return 2
    try: rep=extract(a.pcap,a.output)
    except ExtractError as e: print(f'GOODIX_CONFIG90_EXTRACTION=FAIL: {e}',file=sys.stderr); return 1
    if a.json: print(json.dumps(rep,indent=2,sort_keys=True))
    else:
        print('GOODIX_CONFIG90_EXTRACTION=PASS'); print('output='+rep['output']); print('size='+str(rep['size'])); print('sha256='+rep['sha256']); print('finalizer_le='+rep['finalizer_le']); print('occurrence_count='+str(rep['occurrence_count']))
        for i,o in enumerate(rep['occurrences'],1): print(f"occurrence_{i}=packets:{o['first_packet_index']}-{o['last_packet_index']},wire_control:{o['wire_control']}")
    return 0
if __name__=='__main__': raise SystemExit(main())
