// SPDX-License-Identifier: GPL-2.0-or-later

#include "goodix_psk_response.h"

#include <string.h>

#define CTRL_E0  0xE0u
#define CTRL_E2  0xE2u
#define CTRL_ACK 0xB0u

static uint16_t get_le16(const uint8_t *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint8_t a0_checksum(uint8_t control,
                           const uint8_t *body,
                           size_t body_len)
{
    uint16_t inner_len = (uint16_t)(body_len + 1u);
    unsigned int sum = control + (uint8_t)inner_len +
                       (uint8_t)(inner_len >> 8);

    for (size_t i = 0; i < body_len; ++i)
        sum += body[i];

    return (uint8_t)(0xAAu - sum);
}

static int validate_a0_frame(const uint8_t *frame, size_t len)
{
    uint16_t payload_len;
    uint16_t inner_len;
    size_t body_len;

    if (!frame || len < 8u || frame[0] != 0xA0u)
        return -1;

    payload_len = get_le16(frame + 1);
    if ((size_t)payload_len + 4u != len)
        return -1;

    if (frame[3] != (uint8_t)(frame[0] + frame[1] + frame[2]))
        return -1;

    inner_len = get_le16(frame + 5);
    if (inner_len == 0u || (size_t)inner_len + 3u != payload_len)
        return -1;

    body_len = (size_t)inner_len - 1u;
    if (frame[len - 1u] != a0_checksum(frame[4], frame + 7, body_len))
        return -1;

    return 0;
}

static int transition(struct goodix_e0_response *response,
                      enum goodix_e0_terminal terminal,
                      enum goodix_e0_error error)
{
    if (response->terminal != GOODIX_E0_WAITING)
        return GOODIX_E0_FEED_ALREADY_TERMINAL;

    response->terminal = terminal;
    response->error = error;
    response->terminal_transitions++;

    return terminal == GOODIX_E0_ACCEPTED ?
        GOODIX_E0_FEED_ACCEPTED : GOODIX_E0_FEED_REJECTED;
}

static int handle_a0_frame(struct goodix_e0_response *response,
                           const uint8_t *frame,
                           size_t len)
{
    const uint8_t *body;
    size_t body_len;
    uint8_t control;

    if (validate_a0_frame(frame, len) != 0)
        return transition(response, GOODIX_E0_REJECTED,
                          GOODIX_E0_ERROR_MALFORMED_FRAME);

    control = frame[4];
    body_len = (size_t)get_le16(frame + 5) - 1u;
    body = frame + 7;

    if (control == CTRL_ACK) {
        if (body_len != 2u)
            return transition(response, GOODIX_E0_REJECTED,
                              GOODIX_E0_ERROR_BAD_ACK);

        /* ACKs for unrelated commands may be late and are ignored. */
        if (body[0] != CTRL_E0)
            return GOODIX_E0_FEED_WAITING;

        if (body[1] != 0x01u && body[1] != 0x07u)
            return transition(response, GOODIX_E0_REJECTED,
                              GOODIX_E0_ERROR_BAD_ACK);

        if (response->ack_seen && response->ack_status != body[1])
            return transition(response, GOODIX_E0_REJECTED,
                              GOODIX_E0_ERROR_BAD_ACK);

        response->ack_seen = 1;
        response->ack_status = body[1];
        return GOODIX_E0_FEED_WAITING;
    }

    if (control != CTRL_E0 && control != CTRL_E2)
        return GOODIX_E0_FEED_WAITING;

    if (!response->ack_seen)
        return transition(response, GOODIX_E0_REJECTED,
                          GOODIX_E0_ERROR_RESULT_BEFORE_ACK);

    /*
     * 00 02 is the Windows-observed completion. 00 03 was returned by the
     * target after a Linux E0 whose BB010003 digest was then proven by E4
     * readback. Neither result bypasses the independent readback/TLS gates.
     */
    if (body_len != 2u || body[0] != 0x00u ||
        (body[1] != 0x02u && body[1] != 0x03u))
        return transition(response, GOODIX_E0_REJECTED,
                          GOODIX_E0_ERROR_BAD_RESULT);

    response->result_control = control;
    response->result_code = body[1];
    return transition(response, GOODIX_E0_ACCEPTED,
                      GOODIX_E0_ERROR_NONE);
}

void goodix_e0_response_init(struct goodix_e0_response *response)
{
    if (response)
        memset(response, 0, sizeof(*response));
}

int goodix_e0_response_feed(struct goodix_e0_response *response,
                            const uint8_t *data,
                            size_t len)
{
    size_t offset = 0;

    if (!response || (!data && len != 0u))
        return GOODIX_E0_FEED_REJECTED;

    if (response->terminal != GOODIX_E0_WAITING)
        return GOODIX_E0_FEED_ALREADY_TERMINAL;

    while (offset < len) {
        size_t target = response->expected ? response->expected : 4u;
        size_t need = target - response->have;
        size_t take = len - offset;

        if (take > need)
            take = need;

        memcpy(response->frame + response->have, data + offset, take);
        response->have += take;
        offset += take;

        if (response->have == 4u && response->expected == 0u) {
            size_t total;
            uint8_t family = response->frame[0] & 0xF0u;

            if ((family != 0xA0u && family != 0xB0u && family != 0xC0u) ||
                response->frame[3] !=
                    (uint8_t)(response->frame[0] + response->frame[1] +
                              response->frame[2]))
                return transition(response, GOODIX_E0_REJECTED,
                                  GOODIX_E0_ERROR_MALFORMED_FRAME);

            total = (size_t)get_le16(response->frame + 1) + 4u;
            if (total < 4u || total > sizeof(response->frame) ||
                (family == 0xA0u && total < 8u))
                return transition(response, GOODIX_E0_REJECTED,
                                  GOODIX_E0_ERROR_MALFORMED_FRAME);

            response->expected = total;
        }

        if (response->expected != 0u &&
            response->have == response->expected) {
            int result = GOODIX_E0_FEED_WAITING;

            if ((response->frame[0] & 0xF0u) == 0xA0u)
                result = handle_a0_frame(response, response->frame,
                                         response->expected);

            response->have = 0;
            response->expected = 0;

            if (result != GOODIX_E0_FEED_WAITING)
                return result;
        }
    }

    return GOODIX_E0_FEED_WAITING;
}

int goodix_e0_response_timeout(struct goodix_e0_response *response)
{
    if (!response)
        return GOODIX_E0_FEED_REJECTED;

    return transition(response, GOODIX_E0_REJECTED,
                      GOODIX_E0_ERROR_TIMEOUT);
}

int goodix_e0_response_io_error(struct goodix_e0_response *response)
{
    if (!response)
        return GOODIX_E0_FEED_REJECTED;

    return transition(response, GOODIX_E0_REJECTED,
                      GOODIX_E0_ERROR_IO);
}

const char *goodix_e0_error_name(enum goodix_e0_error error)
{
    switch (error) {
    case GOODIX_E0_ERROR_NONE:
        return "NONE";
    case GOODIX_E0_ERROR_MALFORMED_FRAME:
        return "MALFORMED_FRAME";
    case GOODIX_E0_ERROR_BAD_ACK:
        return "BAD_ACK";
    case GOODIX_E0_ERROR_RESULT_BEFORE_ACK:
        return "RESULT_BEFORE_ACK";
    case GOODIX_E0_ERROR_BAD_RESULT:
        return "BAD_RESULT";
    case GOODIX_E0_ERROR_TIMEOUT:
        return "TIMEOUT";
    case GOODIX_E0_ERROR_IO:
        return "IO";
    }

    return "UNKNOWN";
}

void goodix_e0_write_guard_init(struct goodix_e0_write_guard *guard)
{
    if (guard)
        guard->logical_attempts = 0;
}

int goodix_e0_write_guard_begin(struct goodix_e0_write_guard *guard)
{
    if (!guard || guard->logical_attempts != 0u)
        return -1;

    guard->logical_attempts = 1u;
    return 0;
}
