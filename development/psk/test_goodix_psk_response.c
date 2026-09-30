// SPDX-License-Identifier: GPL-2.0-or-later

#include "goodix_psk_response.h"

#include <stdio.h>
#include <string.h>

static int failures;

static void expect(int condition, const char *name)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", name);
        failures++;
    }
}

static size_t make_a0(uint8_t control,
                      const uint8_t *body,
                      size_t body_len,
                      uint8_t *frame)
{
    uint16_t inner_len = (uint16_t)(body_len + 1u);
    uint16_t payload_len = (uint16_t)(body_len + 4u);
    unsigned int sum = control + (uint8_t)inner_len +
                       (uint8_t)(inner_len >> 8);

    frame[0] = 0xA0u;
    frame[1] = (uint8_t)payload_len;
    frame[2] = (uint8_t)(payload_len >> 8);
    frame[3] = (uint8_t)(frame[0] + frame[1] + frame[2]);
    frame[4] = control;
    frame[5] = (uint8_t)inner_len;
    frame[6] = (uint8_t)(inner_len >> 8);
    memcpy(frame + 7, body, body_len);

    for (size_t i = 0; i < body_len; ++i)
        sum += body[i];

    frame[7 + body_len] = (uint8_t)(0xAAu - sum);
    return body_len + 8u;
}

static size_t make_ack(uint8_t status, uint8_t *frame)
{
    const uint8_t body[2] = {0xE0u, status};
    return make_a0(0xB0u, body, sizeof(body), frame);
}

static size_t make_result(uint8_t control, uint8_t *frame)
{
    const uint8_t body[2] = {0x00u, 0x02u};
    return make_a0(control, body, sizeof(body), frame);
}

static void test_e2_fragmented_success(void)
{
    struct goodix_e0_response response;
    static const uint8_t ack[] = {
        0xA0u,0x06u,0x00u,0xA6u,0xB0u,
        0x03u,0x00u,0xE0u,0x01u,0x16u
    };
    static const uint8_t result[] = {
        0xA0u,0x06u,0x00u,0xA6u,0xE2u,
        0x03u,0x00u,0x00u,0x02u,0xC3u
    };

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, ack, 1) == 0,
           "fragmented ACK byte 1 waits");
    expect(goodix_e0_response_feed(&response, ack + 1, 3) == 0,
           "fragmented ACK header waits");
    expect(goodix_e0_response_feed(&response, ack + 4, sizeof(ack) - 4) == 0,
           "fragmented ACK completes");
    expect(response.ack_seen && response.ack_status == 0x01u,
           "ACK status recorded");
    expect(goodix_e0_response_feed(&response, result, 2) == 0,
           "fragmented E2 prefix waits");
    expect(goodix_e0_response_feed(&response, result + 2,
                                   sizeof(result) - 2) == 1,
           "E2 result accepted");
    expect(response.terminal == GOODIX_E0_ACCEPTED &&
           response.result_control == 0xE2u,
           "E2 terminal state");
}

static void test_observed_e0_success(void)
{
    struct goodix_e0_response response;
    static const uint8_t frames[] = {
        /* Literal frames from WINDOWS_A_RETURN_AFTER_B.pcapng. */
        0xA0u,0x06u,0x00u,0xA6u,0xB0u,
        0x03u,0x00u,0xE0u,0x01u,0x16u,
        0xA0u,0x06u,0x00u,0xA6u,0xE0u,
        0x03u,0x00u,0x00u,0x02u,0xC5u
    };

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, frames, sizeof(frames)) == 1,
           "captured E0 result accepted in one chunk");
    expect(response.result_control == 0xE0u,
           "captured E0 result recorded");
}

static void test_ack_status_07_and_duplicate_ack(void)
{
    struct goodix_e0_response response;
    uint8_t ack[16], result[16];
    size_t ack_len = make_ack(0x07u, ack);
    size_t result_len = make_result(0xE2u, result);

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "ACK status 07 accepted");
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "identical duplicate ACK tolerated");
    expect(goodix_e0_response_feed(&response, result, result_len) == 1,
           "result after duplicate ACK accepted");
}

static void test_unexpected_control_ignored(void)
{
    struct goodix_e0_response response;
    const uint8_t unrelated_body[1] = {0x42u};
    uint8_t unrelated[16], ack[16], result[16];
    size_t unrelated_len = make_a0(0xA8u, unrelated_body,
                                   sizeof(unrelated_body), unrelated);
    size_t ack_len = make_ack(0x01u, ack);
    size_t result_len = make_result(0xE2u, result);

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, unrelated, unrelated_len) == 0,
           "unexpected valid control ignored");
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "ACK after unexpected control accepted");
    expect(goodix_e0_response_feed(&response, result, result_len) == 1,
           "result after unexpected control accepted");
}

static void test_rejections(void)
{
    struct goodix_e0_response response;
    uint8_t ack[16], result[16];
    size_t ack_len = make_ack(0x01u, ack);
    size_t result_len = make_result(0xE2u, result);

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, result, result_len) == -1,
           "result before ACK rejected");
    expect(response.error == GOODIX_E0_ERROR_RESULT_BEFORE_ACK,
           "missing ACK reason");

    goodix_e0_response_init(&response);
    make_ack(0x03u, ack);
    expect(goodix_e0_response_feed(&response, ack, ack_len) == -1,
           "unknown ACK status rejected");
    expect(response.error == GOODIX_E0_ERROR_BAD_ACK,
           "bad ACK reason");

    goodix_e0_response_init(&response);
    make_ack(0x01u, ack);
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "valid ACK before malformed result");
    result[result_len - 1u] ^= 0x01u;
    expect(goodix_e0_response_feed(&response, result, result_len) == -1,
           "bad checksum rejected");
    expect(response.error == GOODIX_E0_ERROR_MALFORMED_FRAME,
           "malformed frame reason");

    goodix_e0_response_init(&response);
    make_ack(0x01u, ack);
    make_result(0xE2u, result);
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "valid ACK before bad body");
    result[8] = 0x03u;
    result[result_len - 1u]--;
    expect(goodix_e0_response_feed(&response, result, result_len) == -1,
           "wrong result body rejected");
    expect(response.error == GOODIX_E0_ERROR_BAD_RESULT,
           "bad result reason");
}

static void test_timeout_and_late_result(void)
{
    struct goodix_e0_response response;
    uint8_t ack[16], result[16];
    size_t ack_len = make_ack(0x01u, ack);
    size_t result_len = make_result(0xE2u, result);

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "ACK before timeout");
    expect(goodix_e0_response_timeout(&response) == -1,
           "timeout rejects once");
    expect(response.error == GOODIX_E0_ERROR_TIMEOUT,
           "timeout reason");
    expect(goodix_e0_response_feed(&response, result, result_len) == 2,
           "late result cannot change terminal state");
    expect(response.terminal == GOODIX_E0_REJECTED &&
           response.terminal_transitions == 1u,
           "timeout remains the single terminal result");
}

static void test_duplicate_result_is_terminal(void)
{
    struct goodix_e0_response response;
    uint8_t ack[16], result[16];
    size_t ack_len = make_ack(0x01u, ack);
    size_t result_len = make_result(0xE2u, result);

    goodix_e0_response_init(&response);
    expect(goodix_e0_response_feed(&response, ack, ack_len) == 0,
           "ACK before duplicate test");
    expect(goodix_e0_response_feed(&response, result, result_len) == 1,
           "first result accepted");
    expect(goodix_e0_response_feed(&response, result, result_len) == 2,
           "duplicate result cannot emit another terminal result");
    expect(response.terminal_transitions == 1u,
           "exactly one terminal transition");
}

static void test_single_write_guard(void)
{
    struct goodix_e0_write_guard guard;

    goodix_e0_write_guard_init(&guard);
    expect(goodix_e0_write_guard_begin(&guard) == 0,
           "first logical E0 allowed");
    expect(goodix_e0_write_guard_begin(&guard) != 0,
           "second logical E0 forbidden");
    expect(guard.logical_attempts == 1u,
           "logical E0 counter remains one");
}

int main(void)
{
    test_e2_fragmented_success();
    test_observed_e0_success();
    test_ack_status_07_and_duplicate_ack();
    test_unexpected_control_ignored();
    test_rejections();
    test_timeout_and_late_result();
    test_duplicate_result_is_terminal();
    test_single_write_guard();

    if (failures != 0) {
        fprintf(stderr, "OFFLINE_TESTS=FAIL failures=%d\n", failures);
        return 1;
    }

    printf("E2_PARSER=PASS\n");
    printf("CAPTURED_E0_COMPATIBILITY=PASS\n");
    printf("ACK_HANDLING=PASS\n");
    printf("FRAME_FRAGMENTATION_REASSEMBLY=PASS\n");
    printf("TIMEOUTS=PASS\n");
    printf("UNEXPECTED_CONTROLS=PASS\n");
    printf("MALFORMED_FRAMES=PASS\n");
    printf("DUPLICATE_LATE_RESPONSE=PASS\n");
    printf("SINGLE_TERMINAL_RESULT=PASS\n");
    printf("NO_AUTO_RETRY_GUARD=PASS\n");
    printf("OFFLINE_TESTS=PASS\n");
    return 0;
}
