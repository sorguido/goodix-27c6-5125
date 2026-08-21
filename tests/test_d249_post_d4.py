# SPDX-License-Identifier: GPL-2.0-or-later
import unittest
from core.post_d4 import *
from core.post_d4 import _checksum

def payload(c,data):
    n=len(data)+1; return bytes((c,n&255,n>>8))+data+bytes((_checksum(c,data),))
def outer(k,p): return bytes((k,len(p)&255,len(p)>>8,(k+len(p))&255))+p

class Mock:
    def __init__(self, frames): self.frames=frames; self.requests=[]
    def exchange(self, request): self.requests.append(request); return self.frames

class D249(unittest.TestCase):
    def test_af_and_unknown_bits(self):
        state=bytes((1,0x8f))+bytes(14); f=outer(PLAIN,payload(0xAE,state))
        m=FirstImageMachine(Mock([f])); s=m.query_state(0x1234)
        self.assertEqual(m.transport.requests[0],build_af(0x1234)); self.assertTrue(s.pov_valid and s.tls_connected and s.locked); self.assertEqual(s.unknown_flag_bits,0x84)
    def test_builders_allowlist(self):
        t=bytes(range(12)); self.assertEqual(parse_payload(parse_outer(build_fdt_manual(t))[1])[1],b'\x09\x01'+t)
        self.assertEqual(parse_payload(parse_outer(build_fdt_down(t,0x1234))[1])[1][-2:],b'\x34\x12')
        for f in (build_fdt_up(t),build_set_image(),build_cached_image()): parse_payload(parse_outer(f)[1])
        for forbidden in (0xE0,0xA4,0xF0,0xF4): self.assertRaises(UnexpectedControl,build_command,forbidden,b'')
    def test_mixed_fragment_coalesce_interleave(self):
        p1=payload(0x30,b'\x02\x00'); p2=payload(0x20,b'\x01\x00'); d=MixedDemux()
        self.assertEqual(d.feed_outer(outer(TLS,b'x'),p1[:2]),[])
        self.assertEqual(d.feed_outer(outer(PLAIN,p1)),[p1])
        self.assertEqual(d.feed_outer(outer(TLS,b'x'),p1[2:]+p2),[p1,p2]); d.eof()
    def test_fdt(self):
        e=parse_fdt_event(payload(0x30,b'\x02\x00\x34\x12'+bytes(12))); self.assertEqual((e.irq,e.touch_flags),(2,0x1234))
    def test_image_synthetic(self):
        packed=bytes((i*17)&255 for i in range(7680)); rec=packed+crc32_mpeg2(packed).to_bytes(4,'big')
        self.assertEqual(len(decode_image_record(rec)),5120)
        self.assertRaises(ImageCrcError,decode_image_record,rec[:-1]+bytes((rec[-1]^1,)))
    def test_adversarial(self):
        good=outer(PLAIN,payload(0xAE,bytes(16)))
        cases=[(TruncatedFrame,b'\xa0'),(LengthMismatch,good[:-1]),(ChecksumMismatch,bytes((good[0],good[1],good[2],0))+good[4:]),(UnexpectedControl,bytes((0xC0,0,0,0xC0)))]
        for err,frame in cases: self.assertRaises(err,parse_outer,frame)
        self.assertRaises(LengthMismatch,parse_af_response,outer(PLAIN,payload(0xAE,bytes(15))))
        self.assertRaises(LengthMismatch,parse_af_response,outer(PLAIN,payload(0xAE,bytes(17))))
        self.assertRaises(UnexpectedAck,parse_af_response,outer(PLAIN,payload(0xB0,b'\xaf\x01')))
        d=MixedDemux(); d.feed_outer(outer(TLS,b'x'),b'\x20'); self.assertRaises(StreamEnded,d.eof)
    def test_duplicates_and_order(self):
        f=outer(PLAIN,payload(0xAE,bytes(16))); self.assertRaises(UnexpectedAck,FirstImageMachine(Mock([f,f])).query_state,1)

if __name__=='__main__': unittest.main()
