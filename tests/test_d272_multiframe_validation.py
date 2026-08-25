# SPDX-License-Identifier: GPL-2.0-or-later
import inspect
import unittest

from core.multiframe_validation import (
    EXPECTED_ACK_STATUS,
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

# Exact target-observed ACK order of one post-first-image cycle (D263 primary
# evidence, packets 235, 241, 247, 253 and the pre-first-image 229).
CYCLE_ACK_CONTROLS = (0x34, 0x20, 0x50, 0x32, 0x22)


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


def cycle_prefix_with_ack_status(ack_ordinal, status):
    """Inputs up to the Nth ACK of the cycle, with that ACK's status replaced.

    The prefix stops at the ACK under test so that any command emitted after a
    rejected ACK is directly observable in ``controls()``.
    """
    inputs = cycle_inputs()
    positions = [
        index
        for index, item in enumerate(inputs)
        if item.kind is InputKind.ACK
    ]
    target = positions[ack_ordinal]
    replaced = Input(
        InputKind.ACK,
        control=inputs[target].control,
        status=status,
    )
    return inputs[:target] + [replaced]


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

    # --- D272/01 corrective: exact ACK status, fail-closed -----------------

    def test_expected_ack_status_is_exactly_0x01(self):
        self.assertEqual(EXPECTED_ACK_STATUS, 0x01)

    def test_every_cycle_ack_accepts_only_status_0x01(self):
        """0x07 and any other status are fail-closed at every ACK stage.

        0x07 is target-observed only in the cold-start/pre-TLS phases; the
        post-arm cycle observed in D263 is exclusively status 0x01.
        """
        rejected = (0x00, 0x02, 0x03, 0x07, 0x10, 0x81, 0xFF)
        for ordinal, control in enumerate(CYCLE_ACK_CONTROLS):
            for status in rejected:
                with self.subTest(control=hex(control), status=hex(status)):
                    channel = FakeSingleReader(
                        cycle_prefix_with_ack_status(ordinal, status)
                    )
                    runner = BoundedMultiFrameRunner(
                        channel, lambda role, raster: {}
                    )
                    with self.assertRaisesRegex(
                        MultiFrameError, f"unexpected_ack:0x{control:02x}"
                    ):
                        runner.run(self.contract(("A1", "A2")), RASTER)
                    # No command is emitted after the rejected ACK.
                    self.assertEqual(
                        controls(channel),
                        list(CYCLE_ACK_CONTROLS[: ordinal + 1]),
                    )

    def test_every_cycle_ack_passes_on_status_0x01(self):
        """The same stages still accept the exact target-observed status."""
        for ordinal, control in enumerate(CYCLE_ACK_CONTROLS):
            with self.subTest(control=hex(control)):
                channel = FakeSingleReader(
                    cycle_prefix_with_ack_status(ordinal, EXPECTED_ACK_STATUS)
                )
                runner = BoundedMultiFrameRunner(channel, lambda role, raster: {})
                # The prefix ends at this ACK, so the run stops on the missing
                # next input, never on the ACK itself.
                with self.assertRaisesRegex(MultiFrameError, "synthetic_timeout"):
                    runner.run(self.contract(("A1", "A2")), RASTER)

    def test_wrong_echo_is_rejected_even_with_status_0x01(self):
        channel = FakeSingleReader(
            [Input(InputKind.ACK, control=0x20, status=EXPECTED_ACK_STATUS)]
        )
        with self.assertRaisesRegex(MultiFrameError, "unexpected_ack:0x34"):
            BoundedMultiFrameRunner(channel, lambda role, raster: {}).run(
                self.contract(("A1", "A2")), RASTER
            )
        self.assertEqual(controls(channel), [0x34])

    def test_ack_policy_has_no_permissive_membership_test(self):
        """Structural guard against reintroducing a multi-status ACK table."""
        source = inspect.getsource(BoundedMultiFrameRunner._command_ack)
        self.assertIn("EXPECTED_ACK_STATUS", source)
        self.assertNotIn("0x07", source)
        self.assertNotIn(" in (", source)


if __name__ == "__main__":
    unittest.main()
