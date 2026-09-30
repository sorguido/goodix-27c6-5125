// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef GOODIX_PSK_RESPONSE_H
#define GOODIX_PSK_RESPONSE_H

#include <stddef.h>
#include <stdint.h>

#define GOODIX_PSK_MAX_FRAME 2048u

enum goodix_e0_terminal {
    GOODIX_E0_WAITING = 0,
    GOODIX_E0_ACCEPTED,
    GOODIX_E0_REJECTED,
};

enum goodix_e0_error {
    GOODIX_E0_ERROR_NONE = 0,
    GOODIX_E0_ERROR_MALFORMED_FRAME,
    GOODIX_E0_ERROR_BAD_ACK,
    GOODIX_E0_ERROR_RESULT_BEFORE_ACK,
    GOODIX_E0_ERROR_BAD_RESULT,
    GOODIX_E0_ERROR_TIMEOUT,
    GOODIX_E0_ERROR_IO,
};

enum goodix_e0_feed_result {
    GOODIX_E0_FEED_REJECTED = -1,
    GOODIX_E0_FEED_WAITING = 0,
    GOODIX_E0_FEED_ACCEPTED = 1,
    GOODIX_E0_FEED_ALREADY_TERMINAL = 2,
};

struct goodix_e0_response {
    uint8_t frame[GOODIX_PSK_MAX_FRAME];
    size_t have;
    size_t expected;
    enum goodix_e0_terminal terminal;
    enum goodix_e0_error error;
    unsigned int terminal_transitions;
    int ack_seen;
    uint8_t ack_status;
    uint8_t result_control;
};

struct goodix_e0_write_guard {
    unsigned int logical_attempts;
};

void goodix_e0_response_init(struct goodix_e0_response *response);

int goodix_e0_response_feed(struct goodix_e0_response *response,
                            const uint8_t *data,
                            size_t len);

int goodix_e0_response_timeout(struct goodix_e0_response *response);
int goodix_e0_response_io_error(struct goodix_e0_response *response);

const char *goodix_e0_error_name(enum goodix_e0_error error);

void goodix_e0_write_guard_init(struct goodix_e0_write_guard *guard);
int goodix_e0_write_guard_begin(struct goodix_e0_write_guard *guard);

#endif
