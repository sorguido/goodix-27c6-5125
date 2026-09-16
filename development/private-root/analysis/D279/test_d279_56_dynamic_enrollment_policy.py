#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import unittest

from d279_56_dynamic_enrollment_policy import PIXELS, replay_dynamic_policy


def frame(value: int) -> bytearray:
    return bytearray([value] * PIXELS)


class DynamicEnrollmentPolicyTests(unittest.TestCase):
    def test_converges_after_three_distinct_and_two_consecutive_duplicates(self):
        frames = [frame(0), frame(30), frame(60), frame(0), frame(30)]
        result = replay_dynamic_policy(frames)
        self.assertEqual([item["classification"] for item in result["per_stage"]],
                         ["ACCEPT", "ACCEPT", "ACCEPT", "DUPLICATE", "CONVERGE"])
        self.assertEqual(result["distinct_sample_accept_count"], 3)
        self.assertEqual(result["first_possible_convergence_stage"], 5)
        self.assertEqual(result["final_selected_stage_count"], 4)
        self.assertEqual(result["duplicate_reject_count"], 1)
        self.assertFalse(result["max_stage_reached"])

    def test_duplicate_streak_resets_on_distinct_frame(self):
        frames = [frame(0), frame(30), frame(60), frame(0), frame(90),
                  frame(30), frame(60)]
        result = replay_dynamic_policy(frames)
        self.assertEqual(result["terminal_reason"],
                         "DUPLICATE_STREAK_CONVERGENCE")
        self.assertEqual(result["first_possible_convergence_stage"], 7)
        self.assertEqual(result["distinct_sample_accept_count"], 4)
        self.assertEqual(result["final_selected_stage_count"], 5)

    def test_maximum_eight_distinct_samples(self):
        result = replay_dynamic_policy([frame(index * 20) for index in range(8)])
        self.assertEqual(result["evaluated_stage_count"], 8)
        self.assertEqual(result["distinct_sample_accept_count"], 8)
        self.assertEqual(result["final_selected_stage_count"], 8)
        self.assertTrue(result["max_stage_reached"])
        self.assertIsNone(result["first_possible_convergence_stage"])

    def test_mad_threshold_is_strictly_less_than_eight(self):
        base = frame(0)
        below = frame(8)
        below[0] = 7
        at = frame(8)
        converged = replay_dynamic_policy(
            [base, frame(30), frame(60), below, below])
        self.assertEqual(converged["terminal_reason"],
                         "DUPLICATE_STREAK_CONVERGENCE")
        distinct = replay_dynamic_policy([base, at, frame(30), frame(60),
                                          frame(90), frame(120), frame(150),
                                          frame(180)])
        self.assertTrue(distinct["max_stage_reached"])
        self.assertEqual(distinct["distinct_sample_accept_count"], 8)

    def test_duplicates_before_three_distinct_do_not_converge(self):
        result = replay_dynamic_policy([frame(0), frame(0), frame(0),
                                        frame(30), frame(60)])
        self.assertEqual(result["terminal_reason"],
                         "INPUT_EXHAUSTED_WITHOUT_COMPLETION")
        self.assertEqual(result["duplicate_reject_count"], 2)
        self.assertEqual(result["distinct_sample_accept_count"], 3)
        self.assertIsNone(result["final_selected_stage_count"])


if __name__ == "__main__":
    unittest.main()
