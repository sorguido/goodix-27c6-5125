CC ?= cc
CFLAGS ?= -O2 -g
CPPFLAGS ?=

WARNINGS = -std=c11 -Wall -Wextra -Werror -pedantic
WRITER_CFLAGS = $(shell pkg-config --cflags libusb-1.0 openssl)
WRITER_LIBS = $(shell pkg-config --libs libusb-1.0 openssl)

.PHONY: all test clean

all: goodix_psk_poc_writer goodix_psk_response_test

goodix_psk_response_test: goodix_psk_response.c test_goodix_psk_response.c goodix_psk_response.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARNINGS) -o $@ goodix_psk_response.c test_goodix_psk_response.c

goodix_psk_poc_writer: goodix_psk_poc_writer.c goodix_psk_response.c goodix_psk_response.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARNINGS) $(WRITER_CFLAGS) -o $@ goodix_psk_poc_writer.c goodix_psk_response.c $(WRITER_LIBS)

test: goodix_psk_response_test goodix_psk_poc_writer
	./goodix_psk_response_test

clean:
	$(RM) goodix_psk_response_test goodix_psk_poc_writer
