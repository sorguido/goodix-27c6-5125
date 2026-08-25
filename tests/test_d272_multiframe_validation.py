# SPDX-License-Identifier: GPL-2.0-or-later
import unittest

from core.multiframe_validation import (
    BoundedMultiFrameRunner,
    Input,
    InputKind,
    MultiFrameContract,
    MultiFrameError,
)
from core.post_d4 import parse_outer, parse_payload


RASTER = tuple(index % 4096 for index in range(5120))
UP = bytes.fromhex("808780948081807a807f8086")
DOWN = bytes.fromhex("80ac80bd80a380b180a680b2")


def cycle_inputs():
    return [
        Input(InputKind.ACK, control=0x34, status=1),
        Input(InputKind.IRQ, irq=0x0200),
        Input(InputKind.ACK, control=0x20, status=1),
        Input(InputKind.IMAGE, raster=RASTER),
        Input(InputKind.ACK, control=0x50, status=1),
        Input(InputKind.NAV_RESPONSE, control=0x50),
        Input(InputKind.ACK, control=0x32, status=1),
        Input(InputKind.IRQ, irq=0x0002),
        Input(InputKind.ACK, control=0x22, status=1),
        Input(InputKind.IMAGE, raster=RASTER),
    ]


class FakeSingleReader:
    def __init__(self, inputs):
        self.inputs = list(inputs)
        self.writes = []
        self.read_calls = 0

    def write(self, frame, timeout_ms):
        self.writes.append((frame, timeout_ms))

    def read_next(self, timeout_ms):
        self.read_calls += 1
        if not self.inputs:
            raise MultiFrameError("synthetic_timeout")
        return self.inputs.pop(0)


def controls(channel):
    result = []
    for frame, _timeout in channel.writes:
        kind, payload = parse_outer(frame)
        assert kind == 0xA0
        control, _data = parse_payload(payload)
        result.append(control)
    return result


class D272MultiFrameTests(unittest.TestCase):
    def contract(self, roles=("A1", "A2", "A3")):
        return MultiFrameContract(roles, UP, DOWN, 0x1234)

    def test_exact_bounded_order_and_terminal_last_image(self):
        retained = []

        def sink(role, raster):
            retained.append(raster)
            return {"role": role, "keypoints": 31}

        channel = FakeSingleReader(cycle_inputs() + cycle_inputs())
        result = BoundedMultiFrameRunner(channel, sink).run(
            self.contract(), RASTER
        )
        self.assertEqual([item["role"] for item in result], ["A1", "A2", "A3"])
        self.assertEqual(
            controls(channel),
            [0x34, 0x20, 0x50, 0x32, 0x22] * 2,
        )
        self.assertFalse(channel.inputs)
        self.assertTrue(all(all(value == 0 for value in item) for item in retained))

    def test_sample_bound_and_up_table_are_fail_closed(self):
        channel = FakeSingleReader([])
        runner = BoundedMultiFrameRunner(channel, lambda role, raster: {})
        with self.assertRaisesRegex(MultiFrameError, "sample_count_out_of_bounds"):
            runner.run(self.contract(("A1",)), RASTER)
        with self.assertRaisesRegex(MultiFrameError, "up_table_source_unresolved"):
            runner.run(MultiFrameContract(("A1", "A2"), b"", DOWN, 0), RASTER)
        self.assertEqual(channel.writes, [])

    def test_wrong_irq_stops_without_retry_or_extra_command(self):
        channel = FakeSingleReader([
            Input(InputKind.ACK, control=0x34, status=1),
            Input(InputKind.IRQ, irq=2),
        ])
        with self.assertRaisesRegex(MultiFrameError, "expected_irq_0x0200"):
            BoundedMultiFrameRunner(channel, lambda role, raster: {}).run(
                self.contract(("A1", "A2")), RASTER
            )
        self.assertEqual(controls(channel), [0x34])

    def test_duplicate_or_unexpected_input_stops(self):
        channel = FakeSingleReader([
            Input(InputKind.ACK, control=0x34, status=1),
            Input(InputKind.ACK, control=0x34, status=1),
        ])
        with self.assertRaisesRegex(MultiFrameError, "unexpected_input"):
            BoundedMultiFrameRunner(channel, lambda role, raster: {}).run(
                self.contract(("A1", "A2")), RASTER
            )
        self.assertEqual(controls(channel), [0x34])

        duplicate_image = FakeSingleReader([
            Input(InputKind.ACK, control=0x34, status=1),
            Input(InputKind.IMAGE, raster=RASTER),
        ])
        with self.assertRaisesRegex(MultiFrameError, "unexpected_input"):
            BoundedMultiFrameRunner(
                duplicate_image, lambda role, raster: {}
            ).run(self.contract(("A1", "A2")), RASTER)
        self.assertEqual(controls(duplicate_image), [0x34])

    def test_bad_ack_and_missing_response_stop(self):
        bad_ack = FakeSingleReader([Input(InputKind.ACK, control=0x34, status=0)])
        with self.assertRaisesRegex(MultiFrameError, "unexpected_ack"):
            BoundedMultiFrameRunner(bad_ack, lambda role, raster: {}).run(
                self.contract(("A1", "A2")), RASTER
            )
        missing = FakeSingleReader([])
        with self.assertRaisesRegex(MultiFrameError, "synthetic_timeout"):
            BoundedMultiFrameRunner(missing, lambda role, raster: {}).run(
                self.contract(("A1", "A2")), RASTER
            )
        self.assertEqual(controls(missing), [0x34])

    def test_metric_output_cannot_contain_biometric_material(self):
        runner = BoundedMultiFrameRunner(
            FakeSingleReader([]), lambda role, raster: {"pixels": raster}
        )
        with self.assertRaisesRegex(MultiFrameError, "biometric_material"):
            runner.run(self.contract(("A1", "A2")), RASTER)


if __name__ == "__main__":
    unittest.main()
