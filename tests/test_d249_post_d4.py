# SPDX-License-Identifier: GPL-2.0-or-later
import unittest

from core.post_d4 import *
from core.post_d4 import _checksum
from src.goodix5125_cleanroom import (
    crc32_mpeg2 as local_crc32,
    decode_crc_trailer,
    decode_group,
    decode_record as local_decode_record,
    encode_crc_trailer,
    encode_group,
    encode_synthetic_record,
)


def payload(control, data, checksum=None):
    size = len(data) + 1
    check = _checksum(control, data) if checksum is None else checksum
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((check,))


def outer(kind, body):
    return bytes((kind, len(body) & 0xFF, len(body) >> 8,
                  (kind + len(body)) & 0xFF)) + body


def ack(echo, status=1):
    return outer(PLAIN, payload(0xB0, bytes((echo, status))))


def af_response(pov=False):
    flags = 0x03 if pov else 0x02
    return outer(PLAIN, payload(0xAE, bytes((1, flags)) + bytes(14)))


def synthetic_raster():
    return tuple((index * 37 + index // 80 * 11) & 0xFFF for index in range(5120))


def image_payload(record=None):
    record = record if record is not None else encode_synthetic_record(synthetic_raster())
    return payload(0x20, b"\x01\x00\x00\x00\x00" + record)


def fdt_event(irq=2):
    return payload(0x30, irq.to_bytes(2, "little") + b"\x34\x12" + bytes(12))


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def exchange(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected transport exchange")
        return self.responses.pop(0)


class D249CodecEquivalenceTests(unittest.TestCase):
    def test_local_record_decodes_pixel_for_pixel(self):
        raster = synthetic_raster()
        record = encode_synthetic_record(raster)
        self.assertEqual(decode_image_record(record), local_decode_record(record))
        self.assertEqual(decode_image_record(record), raster)

    def test_real_crc_trailer_order_and_corruption(self):
        record = encode_synthetic_record(synthetic_raster())
        crc = local_crc32(record[:7680])
        self.assertEqual(record[7680:], encode_crc_trailer(crc))
        self.assertEqual(decode_crc_trailer(record[7680:]), crc)
        self.assertNotEqual(record[7680:], crc.to_bytes(4, "big"))
        damaged = bytearray(record)
        damaged[4097] ^= 0x04
        with self.assertRaises(ImageCrcError):
            decode_image_record(bytes(damaged))

    def test_six_byte_four_pixel_kat(self):
        samples = (0xFFF, 0xABC, 0x123, 0x456)
        packed = bytes.fromhex("cfff23ab4561")
        self.assertEqual(encode_group(samples), packed)
        self.assertEqual(decode_group(packed), samples)


class D249FirstImageClosureTests(unittest.TestCase):
    def test_fresh_fdt_path_reaches_first_image(self):
        transport = ScriptedTransport((
            [af_response(False)], [], [],
        ))
        machine = FirstImageMachine(transport)
        state = machine.query_state(0x1234)
        self.assertFalse(state.pov_valid)
        machine.begin_capture(bytes(range(12)), 0x2345)
        self.assertEqual(machine.phase, "WAIT_FDT_DOWN")
        self.assertIsNone(machine.receive_payload(fdt_event(2)))
        image = machine.receive_payload(image_payload())
        self.assertEqual(machine.phase, FIRST_IMAGE_RECEIVED)
        self.assertEqual(image, synthetic_raster())
        machine.eof()
        self.assertEqual(len(transport.requests), 3)

    def test_cached_pov_path_reaches_first_image(self):
        transport = ScriptedTransport(([af_response(True)], []))
        machine = FirstImageMachine(transport)
        self.assertTrue(machine.query_state(7).pov_valid)
        machine.begin_capture(bytes(12), 9)
        self.assertEqual(machine.phase, "WAIT_IMAGE")
        self.assertEqual(machine.receive_payload(image_payload()), synthetic_raster())
        self.assertEqual(machine.phase, FIRST_IMAGE_RECEIVED)

    def test_event_image_order_and_regression_fail_closed(self):
        transport = ScriptedTransport(([af_response(False)], [ack(0x32)]))
        machine = FirstImageMachine(transport)
        machine.query_state(1)
        machine.begin_capture(bytes(12), 2)
        with self.assertRaises(UnexpectedControl):
            machine.receive_payload(image_payload())
        with self.assertRaises(UnexpectedEvent):
            machine.receive_payload(fdt_event(0x200))
        with self.assertRaises(InvalidTransition):
            machine.query_state(3)

    def test_unexpected_duplicate_ack_and_eof(self):
        machine = FirstImageMachine(ScriptedTransport((
            [af_response(False)], [ack(0x32), ack(0x32)],
        )))
        machine.query_state(1)
        with self.assertRaises(UnexpectedAck):
            machine.begin_capture(bytes(12), 2)
        with self.assertRaises(StreamEnded):
            machine.eof()

    def test_bad_set_image_ack_is_terminal(self):
        machine = FirstImageMachine(ScriptedTransport((
            [af_response(False)], [ack(0x32)], [ack(0xD2)],
        )))
        machine.query_state(1)
        machine.begin_capture(bytes(12), 2)
        with self.assertRaises(UnexpectedAck):
            machine.receive_payload(fdt_event())

    def test_every_async_command_accepts_zero_or_one_valid_ack_only(self):
        table = bytes(range(12))
        commands = (
            (0x32, build_fdt_down(table, 1)),
            (0x20, build_set_image()),
            (0xD2, build_cached_image()),
            (0x36, build_fdt_manual(table)),
            (0x34, build_fdt_up(table)),
        )
        for echo, request in commands:
            with self.subTest(control=hex(echo), case="absent"):
                FirstImageMachine(ScriptedTransport(([],)))._send_async(request, echo)
            with self.subTest(control=hex(echo), case="valid"):
                FirstImageMachine(ScriptedTransport(([ack(echo)],)))._send_async(
                    request, echo
                )
            with self.subTest(control=hex(echo), case="wrong"):
                with self.assertRaises(UnexpectedAck):
                    FirstImageMachine(
                        ScriptedTransport(([ack(echo ^ 2)],))
                    )._send_async(request, echo)
            with self.subTest(control=hex(echo), case="duplicate"):
                with self.assertRaises(UnexpectedAck):
                    FirstImageMachine(
                        ScriptedTransport(([ack(echo), ack(echo)],))
                    )._send_async(request, echo)


class D249ParserPolicyTests(unittest.TestCase):
    def test_checksum_0x88_is_not_a_bypass(self):
        self.assertRaises(ChecksumMismatch, parse_payload, payload(0x30, b"bad", 0x88))
        # Positive case: 0x88 is accepted only when arithmetic makes it genuine.
        data = next(bytes((value,)) for value in range(256)
                    if _checksum(0x30, bytes((value,))) == 0x88)
        self.assertEqual(parse_payload(payload(0x30, data))[1], data)

    def test_builders_and_forbidden_allowlist(self):
        table = bytes(range(12))
        self.assertEqual(parse_payload(parse_outer(build_fdt_manual(table))[1])[1],
                         b"\x09\x01" + table)
        self.assertEqual(parse_payload(parse_outer(build_fdt_down(table, 0x1234))[1])[1][-2:],
                         b"\x34\x12")
        for frame in (build_fdt_up(table), build_set_image(), build_cached_image()):
            parse_payload(parse_outer(frame)[1])
        for forbidden in (0xE0, 0xA4, 0xF0, 0xF4):
            self.assertRaises(UnexpectedControl, build_command, forbidden, b"")

    def test_mixed_fragment_coalesce_interleave_and_eof(self):
        first = fdt_event(2)
        second = image_payload()
        demux = MixedDemux()
        self.assertEqual(demux.feed_outer(outer(TLS, b"x"), first[:2]), [])
        self.assertEqual(demux.feed_outer(outer(PLAIN, first)), [first])
        self.assertEqual(demux.feed_outer(outer(TLS, b"x"), first[2:] + second),
                         [first, second])
        demux.eof()
        partial = MixedDemux()
        partial.feed_outer(outer(TLS, b"x"), b"\x20")
        self.assertRaises(StreamEnded, partial.eof)

    def test_malformed_frames_payloads_and_af(self):
        good = af_response(False)
        cases = (
            (TruncatedFrame, b"\xa0"),
            (LengthMismatch, good[:-1]),
            (LengthMismatch, good + b"\x00"),
            (ChecksumMismatch, bytes((good[0], good[1], good[2], 0)) + good[4:]),
            (UnexpectedControl, bytes((0xC0, 0, 0, 0xC0))),
        )
        for error, frame in cases:
            self.assertRaises(error, parse_outer, frame)
        self.assertRaises(LengthMismatch, parse_af_response,
                          outer(PLAIN, payload(0xAE, bytes(15))))
        self.assertRaises(LengthMismatch, parse_af_response,
                          outer(PLAIN, payload(0xAE, bytes(17))))
        self.assertRaises(UnexpectedAck, parse_af_response, ack(0xAF))
        self.assertRaises(LengthMismatch, parse_image_payload, image_payload(b"x" * 7683))
        self.assertRaises(LengthMismatch, parse_image_payload, image_payload(b"x" * 7685))


if __name__ == "__main__":
    unittest.main()
