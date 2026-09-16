#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline extractor for Goodix 27c6:5125 CONFIG90 from USBPcap pcapng."""
from __future__ import annotations
import argparse, hashlib, json, os, struct, sys, tempfile
from dataclasses import dataclass
from pathlib import Path

SHB=0x0A0D0D0A; IDB=1; EPB=6
USBPCAP_MIN_HEADER=27; BULK=3; HOST_TO_DEVICE=0; EP_OUT=0x01
A0=0xA0; B0=0xB0; CONFIG90=0x90; CONFIG90_LEN=224; FINALIZER_OFF=222

class ExtractError(RuntimeError): pass

@dataclass(frozen=True)
class Candidate:
    first_packet:int; last_packet:int; wire_control:int; body:bytes
    @property
    def sha256(self): return hashlib.sha256(self.body).hexdigest()

def u32(data,off,endian): return struct.unpack_from(endian+'I',data,off)[0]

def iter_pcapng(path:Path):
    try: data=path.read_bytes()
    except OSError as e: raise ExtractError(f'cannot read capture: {e}') from e
    if len(data)<12: raise ExtractError('capture is too short to be pcapng')
    off=0; endian='<'; interfaces=[]; packet_index=0; saw_shb=False
    while off+12<=len(data):
        if data[off:off+4]==struct.pack('<I',SHB):
            bom=data[off+8:off+12]
            if bom==b'\x4d\x3c\x2b\x1a': endian='<'
            elif bom==b'\x1a\x2b\x3c\x4d': endian='>'
            else: raise ExtractError(f'invalid pcapng byte-order magic at {off:#x}')
            block_type=SHB; saw_shb=True; interfaces=[]
        else:
            if not saw_shb: raise ExtractError('pcapng does not start with a Section Header Block')
            block_type=u32(data,off,endian)
        blen=u32(data,off+4,endian)
        if blen<12 or blen%4 or off+blen>len(data): raise ExtractError(f'invalid/truncated pcapng block at {off:#x}')
        if u32(data,off+blen-4,endian)!=blen: raise ExtractError(f'pcapng trailing length mismatch at {off:#x}')
        body=data[off+8:off+blen-4]
        if block_type==IDB:
            if len(body)<8: raise ExtractError(f'short IDB at {off:#x}')
            interfaces.append(struct.unpack_from(endian+'H',body,0)[0])
        elif block_type==EPB:
            if len(body)<20: raise ExtractError(f'short EPB at {off:#x}')
            iid,_,_,caplen,origlen=struct.unpack_from(endian+'IIIII',body,0)
            if iid>=len(interfaces): raise ExtractError(f'unknown interface at packet {packet_index}')
            if caplen>origlen or 20+caplen>len(body): raise ExtractError(f'invalid captured length at packet {packet_index}')
            yield packet_index,interfaces[iid],body[20:20+caplen]
            packet_index+=1
        off+=blen
    if not saw_shb: raise ExtractError('no pcapng Section Header Block found')
    if off!=len(data): raise ExtractError(f'unexpected trailing bytes after {off:#x}')

def decode_usbpcap(packet_index,linktype,raw):
    if len(raw)<USBPCAP_MIN_HEADER: return None
    hlen=struct.unpack_from('<H',raw,0)[0]
    if hlen<USBPCAP_MIN_HEADER or hlen>len(raw): return None
    info=raw[16]; endpoint=raw[21]; transfer=raw[22]; dlen=struct.unpack_from('<I',raw,23)[0]
    if hlen+dlen>len(raw): return None
    return info,endpoint,transfer,raw[hlen:hlen+dlen]

def iter_bulk_out(path):
    decoded=False
    for idx,linktype,raw in iter_pcapng(path):
        pkt=decode_usbpcap(idx,linktype,raw)
        if pkt is None: continue
        decoded=True
        info,ep,transfer,payload=pkt
        if transfer==BULK and ep==EP_OUT and info==HOST_TO_DEVICE and payload:
            yield idx,payload
    if not decoded: raise ExtractError('no decodable USBPcap packets found')

def reassemble(payloads):
    pending=bytearray(); first=None; last=None; expected=None
    for idx,payload in payloads:
        cur=0
        while cur<len(payload):
            if not pending:
                if payload[cur] not in (A0,B0): break
                if len(payload)-cur<4:
                    pending.extend(payload[cur:]); first=last=idx; expected=None; break
                plen=int.from_bytes(payload[cur+1:cur+3],'little'); flen=4+plen
                if flen<8 or flen>65539: break
                first=last=idx; expected=flen
            if expected is None:
                pending.extend(payload[cur:]); last=idx; cur=len(payload)
                if len(pending)>=4:
                    if pending[0] not in (A0,B0): pending.clear(); first=last=expected=None; break
                    flen=4+int.from_bytes(pending[1:3],'little')
                    if flen<8 or flen>65539: pending.clear(); first=last=expected=None; break
                    expected=flen
                continue
            need=expected-len(pending); take=min(need,len(payload)-cur)
            pending.extend(payload[cur:cur+take]); last=idx; cur+=take
            if len(pending)==expected:
                yield first,last,bytes(pending)
                pending.clear(); first=last=expected=None

def parse_a0(raw):
    if len(raw)<8 or raw[0]!=A0: raise ExtractError('not A0')
    plen=int.from_bytes(raw[1:3],'little')
    if plen+4!=len(raw): raise ExtractError('A0 outer length mismatch')
    tag=(raw[0]+(plen&0xff)+((plen>>8)&0xff))&0xff
    if raw[3]!=tag: raise ExtractError('A0 outer tag mismatch')
    wire=raw[4]; logical=wire&0xfe; ilen=int.from_bytes(raw[5:7],'little')
    if ilen==0 or ilen+3!=plen: raise ExtractError('A0 inner length mismatch')
    body=raw[7:7+ilen-1]
    if len(body)!=ilen-1: raise ExtractError('A0 body truncated')
    checksum=(logical+len(body)+1+sum(body)+raw[-1])&0xff
    if checksum!=0xaa: raise ExtractError('A0 inner checksum mismatch')
    return wire,logical,body

def expected_finalizer(body):
    if len(body)!=CONFIG90_LEN: raise ExtractError(f'CONFIG90 length {len(body)} != {CONFIG90_LEN}')
    total=sum(int.from_bytes(body[o:o+2],'little') for o in range(0,FINALIZER_OFF,2))&0xffff
    return (-0xa5a5-total)&0xffff

def validate_config90(body):
    exp=expected_finalizer(body); obs=int.from_bytes(body[-2:],'little')
    if obs!=exp: raise ExtractError(f'CONFIG90 finalizer mismatch: observed=0x{obs:04x}, expected=0x{exp:04x}')

def find_candidates(path):
    out=[]
    for first,last,raw in reassemble(iter_bulk_out(path)):
        if raw[0]!=A0: continue
        try: wire,logical,body=parse_a0(raw)
        except ExtractError: continue
        if logical!=CONFIG90 or len(body)!=CONFIG90_LEN: continue
        try: validate_config90(body)
        except ExtractError: continue
        out.append(Candidate(first,last,wire,body))
    return out

def choose(cands):
    if not cands: raise ExtractError('no valid 224-byte A0/0x90 CONFIG90 frame found')
    groups={}
    for c in cands: groups.setdefault(c.sha256,[]).append(c)
    if len(groups)!=1:
        s=', '.join(f'{h[:12]}… ({len(v)} occurrence(s))' for h,v in sorted(groups.items()))
        raise ExtractError('multiple distinct valid CONFIG90 bodies found: '+s)
    grp=next(iter(groups.values())); return grp[0].body,grp

def atomic_write_0600(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() or path.is_symlink(): raise ExtractError(f'refusing to overwrite existing output: {path}')
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=str(path.parent))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f:
            fd=None; f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path); tmp=None; os.chmod(path,0o600)
    except OSError as e: raise ExtractError(f'cannot write output atomically: {e}') from e
    finally:
        if fd is not None: os.close(fd)
        if tmp is not None:
            try: os.unlink(tmp)
            except OSError: pass

def extract(pcap,output):
    body,occ=choose(find_candidates(pcap)); atomic_write_0600(output,body)
    return {'schema':'GOODIX5125_CONFIG90_EXTRACTION_V1','result':'PASS','source_capture':str(pcap),'output':str(output),'size':len(body),'sha256':hashlib.sha256(body).hexdigest(),'finalizer_le':body[-2:].hex(),'occurrence_count':len(occ),'occurrences':[{'first_packet_index':c.first_packet,'last_packet_index':c.last_packet,'wire_control':f'0x{c.wire_control:02x}'} for c in occ]}

# ---- synthetic self-test ----
def make_config(seed):
    b=bytearray(CONFIG90_LEN)
    for i in range(FINALIZER_OFF): b[i]=(i*37+seed*11)&0xff
    b[-2:]=expected_finalizer(bytes(b)).to_bytes(2,'little'); return bytes(b)
def build_frame(body):
    wire=0x91; logical=0x90; ilen=len(body)+1; plen=len(body)+4
    tag=(A0+(plen&0xff)+((plen>>8)&0xff))&0xff
    chk=(0xaa-(logical+len(body)+1+sum(body)))&0xff
    return bytes([A0,plen&0xff,(plen>>8)&0xff,tag,wire,ilen&0xff,(ilen>>8)&0xff])+body+bytes([chk])
def usbpcap(payload,irp=1):
    h=bytearray(27); struct.pack_into('<H',h,0,27); struct.pack_into('<Q',h,2,irp); struct.pack_into('<I',h,10,0); struct.pack_into('<H',h,14,0); h[16]=0; struct.pack_into('<H',h,17,1); struct.pack_into('<H',h,19,2); h[21]=1; h[22]=3; struct.pack_into('<I',h,23,len(payload)); return bytes(h)+payload
def block(t,body):
    body+=b'\0'*((-len(body))%4); total=12+len(body); return struct.pack('<II',t,total)+body+struct.pack('<I',total)
def pcapng(chunks):
    shb=struct.pack('<I',0x1A2B3C4D)+struct.pack('<HHq',1,0,-1); idb=struct.pack('<HHI',249,0,65535); out=bytearray(block(SHB,shb)+block(IDB,idb))
    for i,ch in enumerate(chunks,1):
        p=usbpcap(ch,i); out+=block(EPB,struct.pack('<IIIII',0,0,i,len(p),len(p))+p)
    return bytes(out)
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
