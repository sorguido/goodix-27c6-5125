# SPDX-License-Identifier: GPL-2.0-or-later
import ssl
import tempfile
from pathlib import Path
import unittest

from core.fdt_lifecycle import ExactFreshFdtBootstrapMachine, FdtLifecycle
from core.fdt_seed import CACHE_SIZE, provide_fdt12
from core.post_d4 import InvalidTransition, PLAIN, TLS, _checksum
from core.tls_b0 import (
    B0ApplicationConsumer,
    Tls12PskServerSession,
    TlsB0ConsumptionError,
)
from src.goodix5125_cleanroom import crc32_mpeg2


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(kind: int, body: bytes) -> bytes:
    lo, hi = len(body) & 0xFF, len(body) >> 8
    return bytes((kind, lo, hi, (kind + lo + hi) & 0xFF)) + body


def ack(echo: int) -> bytes:
    return outer(PLAIN, payload(0xB0, bytes((echo, 1))))


def nav_response() -> bytes:
    data = b"\x50\x01" + bytes(2407)
    return outer(PLAIN, bytes((0x50, 0x6A, 0x09)) + data + b"\x88")


def delta_response() -> bytes:
    return outer(PLAIN, payload(0x82, b"\x80\x1d"))


def irq100(words: tuple[int, ...]) -> bytes:
    raw = b"".join(word.to_bytes(2, "little") for word in words)
    return payload(0x36, b"\x00\x01\x00\x00" + raw)


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[bytes] = []
        self.timeouts: list[int | None] = []

    def exchange(self, request: bytes, *, timeout_ms: int | None = None):
        self.requests.append(request)
        self.timeouts.append(timeout_ms)
        if not self.responses:
            raise AssertionError("unexpected_exchange")
        return self.responses.pop(0)


class D259MinimalDeviceContractTests(unittest.TestCase):
    SECRET = bytes(range(1, 33))

    def _client(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers("PSK-AES128-GCM-SHA256")
        context.options |= ssl.OP_NO_TICKET
        context.set_psk_client_callback(lambda _hint: ("Client_identity", self.SECRET))
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        client = context.wrap_bio(incoming, outgoing, server_side=False)
        return client, incoming, outgoing

    def _active_tls(self):
        server = Tls12PskServerSession(self.SECRET)
        client, client_in, client_out = self._client()
        client_done = False
        for _ in range(100):
            try:
                client.do_handshake()
                client_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            outgoing = client_out.read()
            if outgoing:
                server.feed_handshake_bytes(outgoing)
                server.advance_handshake()
            for record in server.drain_encrypted_output():
                client_in.write(record)
            if client_done and server.handshake_complete:
                return server, client, client_out
        server.close()
        raise AssertionError("synthetic_tls_handshake_did_not_converge")

    @staticmethod
    def _encrypted_application_b0(client, client_out, plaintext: bytes) -> bytes:
        written = client.write(plaintext)
        if written != len(plaintext):
            raise AssertionError("short_synthetic_tls_write")
        record = client_out.read()
        if len(record) < 6 or record[0] != 0x17:
            raise AssertionError("synthetic_tls_application_record_missing")
        return outer(TLS, record)

    def test_b0_is_authenticated_decrypted_zeroized_and_discarded(self):
        server, client, client_out = self._active_tls()
        consumer = B0ApplicationConsumer(server)
        result = consumer.consume(
            self._encrypted_application_b0(client, client_out, b"synthetic-non-biometric-baseline")
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.plaintext_length, 32)
        self.assertEqual(consumer.consumption_count, 1)
        server.close()
        self.assertTrue(server.secret_zeroized)

    def test_ciphertext_discard_without_active_tls_is_rejected(self):
        class InactiveSession:
            handshake_complete = False

            def consume_application_record(self, _record):
                raise AssertionError("must_not_be_called")

        consumer = B0ApplicationConsumer(InactiveSession())
        with self.assertRaisesRegex(TlsB0ConsumptionError, "active_tls_session_required"):
            consumer.consume(outer(TLS, b"ciphertext-discard-is-not-consumption"))

    def _seed(self, directory: Path):
        otp = bytes(range(64))
        body = otp + bytes(range(1, 13)) + bytes(3200) + bytes(10240)
        path = directory / "cache.bin"
        path.write_bytes(body + crc32_mpeg2(body).to_bytes(4, "little"))
        self.assertEqual(path.stat().st_size, CACHE_SIZE)
        return provide_fdt12(path, otp)

    def test_minimal_path_omits_classifier_raster_cache_and_arms_once(self):
        server, client, client_out = self._active_tls()
        # TLS 1.2 AES-GCM adds 29 bytes here (5-byte record header, explicit
        # nonce and tag), yielding the target-observed 7,722-byte TLS record.
        b0 = self._encrypted_application_b0(client, client_out, bytes(7693))
        self.assertEqual(len(b0), 7726)
        responses = (
            [ack(0x36)], [ack(0x50), nav_response()], [ack(0x36)],
            [ack(0x82), delta_response()], [ack(0x20), b0], [ack(0x36)],
            [ack(0x32)],
        )
        transport = ScriptedTransport(responses)
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        machine = ExactFreshFdtBootstrapMachine(transport, lifecycle)
        with tempfile.TemporaryDirectory() as temporary:
            machine.begin(self._seed(Path(temporary)))
            samples = (
                (348, 382, 327, 356, 333, 357),
                (347, 381, 328, 356, 334, 358),
                (346, 380, 327, 356, 333, 357),
            )
            machine.manual_sample(irq100(samples[0]))
            machine.nav_interstage()
            machine.manual_sample(irq100(samples[1]))
            machine.delta_and_baseline_interstage()
            machine.manual_sample(irq100(samples[2]))
            machine.finalize_minimal_device_contract(B0ApplicationConsumer(server))
            machine.arm(0x1234)
        self.assertTrue(machine.second_delta_gate_passed)
        self.assertTrue(machine.baseline_b0_tls_consumed)
        self.assertEqual(machine.semantic_classifier_call_count, 0)
        self.assertEqual(machine.raster_decode_count, 0)
        self.assertEqual(machine.host_cache_write_count, 0)
        self.assertEqual(lifecycle.device_command_trace, (0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32))
        self.assertEqual(transport.timeouts, [500, 500, 500, 500, 2000, 500, 100])
        self.assertEqual(lifecycle.retry_count, 0)
        self.assertEqual(lifecycle.persistent_write_family_count, 0)
        server.close()

    def test_minimal_path_refuses_raw_ciphertext_discard_callback(self):
        responses = (
            [ack(0x36)], [ack(0x50), nav_response()], [ack(0x36)],
            [ack(0x82), delta_response()], [ack(0x20), outer(TLS, bytes(7722))],
            [ack(0x36)],
        )
        transport = ScriptedTransport(responses)
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        machine = ExactFreshFdtBootstrapMachine(transport, lifecycle)
        with tempfile.TemporaryDirectory() as temporary:
            machine.begin(self._seed(Path(temporary)))
            sample = irq100((100, 100, 100, 100, 100, 100))
            machine.manual_sample(sample)
            machine.nav_interstage()
            machine.manual_sample(sample)
            machine.delta_and_baseline_interstage()
            machine.manual_sample(sample)
            with self.assertRaises(AttributeError):
                machine.finalize_minimal_device_contract(lambda _frame: None)  # type: ignore[arg-type]
        self.assertEqual(lifecycle.state.value, "FAILED_CLOSED")


if __name__ == "__main__":
    unittest.main()
