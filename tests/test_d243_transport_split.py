from __future__ import annotations

import unittest

from src.goodix5125_d232_offline import (
    EXACT_PHASE_ORDER,
    build_b0,
    expected_request_frames,
    parse_a0,
    parse_b0,
)
from src.goodix5125_d233_backend import (
    B0TlsBridge,
    ProductionUsbTransport,
    TLS_RECORD_PACING_MS,
    USB_MAX_PACKET,
    UsbAmbiguousCompletion,
    UsbFailure,
)
from tests.test_d233_backend import FakeUsbApi, synthetic_objects
from tests.test_d242_transport_fix import TwoRecordServerFlight


class RecordingTransport:
    def __init__(self):
        self.frames: list[bytes] = []

    def write_frame(self, frame, _timeout):
        self.frames.append(bytes(frame))


class D243TransportSplitTests(unittest.TestCase):
    def setUp(self):
        self.material, _responses = synthetic_objects()
        self.requests = expected_request_frames(self.material)

    def test_e4_exact_core_frame_uses_d241_short_out_without_zero_tail(self):
        e4 = self.requests["E4"]
        original = bytes(e4)
        parsed_before = parse_a0(e4)
        api = FakeUsbApi()
        transport = ProductionUsbTransport(api)
        transport.transport_open()
        transport.write_frame(e4, 1000)
        self.assertEqual(e4, original, "logical E4 frame changed")
        self.assertEqual(parse_a0(e4), parsed_before, "E4 header/checksum changed")
        self.assertEqual(len(api.outgoing), 1)
        self.assertEqual(api.outgoing[0], e4)
        self.assertEqual(len(api.outgoing[0]), len(e4))
        self.assertNotEqual(len(api.outgoing[0]), 64)
        self.assertEqual(transport.bulk_out_logical_chunk_lengths, [len(e4)])
        self.assertEqual(transport.bulk_out_wire_chunk_lengths, [len(e4)])

    def test_full_pre_d1_a0_sequence_uses_short_final_d241_semantics(self):
        api = FakeUsbApi()
        transport = ProductionUsbTransport(api)
        transport.transport_open()
        observed_phases = []
        for phase in EXACT_PHASE_ORDER[:-1]:
            frame = self.requests[phase]
            start = len(api.outgoing)
            transport.write_frame(frame, 1000)
            chunks = api.outgoing[start:]
            observed_phases.append(phase)
            self.assertEqual(b"".join(chunks), frame, phase)
            self.assertEqual(
                [len(chunk) for chunk in chunks],
                [
                    min(USB_MAX_PACKET, len(frame) - offset)
                    for offset in range(0, len(frame), USB_MAX_PACKET)
                ],
                phase,
            )
        self.assertEqual(tuple(observed_phases), EXACT_PHASE_ORDER[:-1])
        self.assertEqual(transport.command_count, 12)

    def test_b0_server_flight_is_fixed64_zero_filled_and_full_completion(self):
        records = TwoRecordServerFlight().drain()
        frames = [build_b0(record) for record in records]
        api = FakeUsbApi()
        transport = ProductionUsbTransport(api)
        transport.transport_open()
        transport.write_frame(frames[0], 1000)
        transport.write_frame(frames[1], 1000)
        self.assertEqual([len(chunk) for chunk in api.outgoing], [64, 64, 64])
        first_wire = b"".join(api.outgoing[:2])
        self.assertEqual(first_wire[: len(frames[0])], frames[0])
        self.assertEqual(first_wire[len(frames[0]) :], bytes(128 - len(frames[0])))
        self.assertEqual(api.outgoing[2][: len(frames[1])], frames[1])
        self.assertEqual(
            api.outgoing[2][len(frames[1]) :], bytes(64 - len(frames[1]))
        )
        self.assertEqual(parse_b0(frames[0]), records[0])
        self.assertEqual(parse_b0(frames[1]), records[1])

        partial = FakeUsbApi()
        partial_transport = ProductionUsbTransport(partial)
        partial_transport.transport_open()
        partial.partial_out = True
        with self.assertRaises(UsbAmbiguousCompletion):
            partial_transport.write_frame(frames[1], 1000)
        self.assertEqual(partial_transport.bulk_out_complete_count, 0)

    def test_tls_pacing_is_two_times_10ms_and_never_applies_to_a0(self):
        delays: list[float] = []
        api = FakeUsbApi()
        a0_transport = ProductionUsbTransport(api)
        a0_transport.transport_open()
        for frame in self.requests.values():
            a0_transport.write_frame(frame, 1000)
        self.assertEqual(delays, [])

        transport = RecordingTransport()
        bridge = B0TlsBridge(
            TwoRecordServerFlight(), transport, pacer=delays.append
        )
        client_body = b"\x03\x03" + bytes(32) + b"\x00\x00\x04\x00\xa8\x00\xff\x01\x00"
        client = (
            b"\x16\x03\x03"
            + (4 + len(client_body)).to_bytes(2, "big")
            + b"\x01"
            + len(client_body).to_bytes(3, "big")
            + client_body
        )
        bridge.accept_b0(build_b0(client), 1000, first_record=True)
        self.assertEqual(delays, [TLS_RECORD_PACING_MS / 1000] * 2)
        self.assertEqual(bridge.pacing_count, 2)

    def test_unclassified_or_malformed_wrapper_fails_closed_without_usb_out(self):
        for frame in (b"short", b"\xc0\x00\x00\xc0", b"\xa0\x01\x00\xa1"):
            with self.subTest(frame=frame.hex()):
                api = FakeUsbApi()
                transport = ProductionUsbTransport(api)
                transport.transport_open()
                with self.assertRaises(UsbFailure):
                    transport.write_frame(frame, 1000)
                self.assertEqual(api.outgoing, [])
                self.assertEqual(transport.command_count, 0)


if __name__ == "__main__":
    unittest.main()
