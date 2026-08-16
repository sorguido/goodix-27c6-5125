from __future__ import annotations

import json
import unittest
from pathlib import Path

from analysis.D242.d242_capture_forensics import derive
from src.goodix5125_d232_offline import SecretBuffer, build_b0, parse_b0
from src.goodix5125_d233_backend import (
    B0TlsBridge,
    ProductionUsbTransport,
    TLS_RECORD_PACING_MS,
    UsbAmbiguousCompletion,
)
from tests.test_d233_backend import FakeUsbApi


REPOSITORY = Path(__file__).resolve().parents[1]
CAPTURE = REPOSITORY / "analysis/D230/work/GoodixExport/rilevamento.pcapng"


class TwoRecordServerFlight:
    complete = False
    closed = False
    handshake_count = 0

    def __init__(self):
        self._drained = False

    def feed(self, _payload):
        pass

    def advance(self):
        self.handshake_count = 1

    def drain(self):
        if self._drained:
            return ()
        self._drained = True
        return (
            b"\x16\x03\x03\x00\x51\x02\x00\x00\x4d" + bytes(77),
            b"\x16\x03\x03\x00\x04\x0e\x00\x00\x00",
        )


class RecordingTransport:
    def __init__(self):
        self.frames: list[bytes] = []

    def write_frame(self, frame, _timeout):
        self.frames.append(bytes(frame))


class D242TransportCorrectionTests(unittest.TestCase):
    def test_primary_capture_metadata_fixture_is_stable_and_redacted(self):
        report = derive(CAPTURE)
        self.assertEqual(report["capture_historical_classification"], "D175")
        self.assertEqual(report["d43_primary_capture"], "NOT_AVAILABLE")
        self.assertEqual(report["client_hello"]["record_payload_length"], 47)
        self.assertEqual(report["client_hello"]["cipher_suites"], ["0x00a8", "0x00ff"])
        self.assertEqual(report["server_hello"]["record_payload_length"], 81)
        self.assertEqual(report["server_hello"]["extensions"], [{"type": "0xff01", "length": 1}])
        self.assertEqual(report["server_hello_done"]["record_payload_length"], 4)
        self.assertEqual(report["client_key_exchange"]["identity_classification"], "Client_identity")
        self.assertEqual(report["server_flight_grouping"]["server_hello_usb_out_payload_lengths"], [64, 64])
        self.assertEqual(report["server_flight_grouping"]["server_hello_done_usb_out_payload_lengths"], [64])
        self.assertEqual(
            report["server_flight_grouping"]["server_hello_final_tail_class"],
            "NONZERO_REDACTED_OUTSIDE_DECLARED_B0",
        )
        self.assertFalse(any(report["redaction"].values()))

    def test_transport_zero_pads_every_final_out_to_oem_packet_size(self):
        api = FakeUsbApi()
        transport = ProductionUsbTransport(api)
        transport.transport_open()
        transport.write_frame(b"a" * 90, 1000)
        transport.write_frame(b"b" * 13, 1000)
        self.assertEqual([len(item) for item in api.outgoing], [64, 64, 64])
        self.assertEqual(api.outgoing[1][:26], b"a" * 26)
        self.assertEqual(api.outgoing[1][26:], bytes(38))
        self.assertEqual(api.outgoing[2][:13], b"b" * 13)
        self.assertEqual(api.outgoing[2][13:], bytes(51))
        self.assertEqual(transport.bulk_out_submit_count, 3)
        self.assertEqual(transport.bulk_out_complete_count, 3)

    def test_partial_padded_out_is_ambiguous_and_fails_closed(self):
        api = FakeUsbApi()
        transport = ProductionUsbTransport(api)
        transport.transport_open()
        api.partial_out = True
        with self.assertRaises(UsbAmbiguousCompletion):
            transport.write_frame(b"short", 1000)
        self.assertEqual(transport.bulk_out_submit_count, 1)
        self.assertEqual(transport.bulk_out_complete_count, 0)

    def test_server_flight_keeps_one_tls_record_per_b0_and_paces_each(self):
        transport = RecordingTransport()
        delays: list[float] = []
        bridge = B0TlsBridge(
            TwoRecordServerFlight(), transport, pacer=delays.append
        )
        client_body = b"\x03\x03" + bytes(32) + b"\x00\x00\x04\x00\xa8\x00\xff\x01\x00"
        client = b"\x16\x03\x03" + (4 + len(client_body)).to_bytes(2, "big") + b"\x01" + len(client_body).to_bytes(3, "big") + client_body
        bridge.accept_b0(build_b0(client), 1000, first_record=True)
        self.assertEqual(len(transport.frames), 2)
        self.assertEqual([len(parse_b0(frame)) for frame in transport.frames], [86, 9])
        self.assertEqual(delays, [TLS_RECORD_PACING_MS / 1000] * 2)
        self.assertEqual(bridge.pacing_count, 2)

    def test_d239_52_is_the_complete_tls_record_and_d241_47_its_payload(self):
        live = json.loads(
            (REPOSITORY / "analysis/D241/D241_operator_live_stdout.json").read_text()
        )
        d1 = live["protocol_observations"][-1]
        client = live["tls_trace_redacted"][0]
        self.assertEqual(d1["response_body_length"], 52)
        self.assertEqual(client["record_length"], 47)
        self.assertEqual(d1["response_body_length"], 5 + client["record_length"])


if __name__ == "__main__":
    unittest.main()
