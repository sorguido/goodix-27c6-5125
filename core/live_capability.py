# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixed capability authority shared by D261 and the future first-image path."""

from __future__ import annotations


D261_LIVE_AUTHORIZATION_FLAG = "--i-authorize-one-d261-fdt-arm-live-attempt"
D265_FUTURE_LIVE_AUTHORIZATION_FLAG = "--i-authorize-one-future-d265-first-image-live-attempt"
D267_LIVE_AUTHORIZATION_FLAG = "--i-authorize-one-d267-first-image-live-attempt"


class CapabilityFailure(RuntimeError):
    pass


class CliIntentCapability:
    __slots__ = ("_nonce",)
    def __init__(self, nonce: object) -> None: self._nonce = nonce


class MarkerClaimCapability:
    __slots__ = ("_nonce",)
    def __init__(self, nonce: object) -> None: self._nonce = nonce


class LiveIoCapability:
    __slots__ = ("_nonce",)
    def __init__(self, nonce: object) -> None: self._nonce = nonce


class FutureIntentCapability:
    __slots__ = ("_nonce", "_used")
    def __init__(self, nonce: object) -> None: self._nonce, self._used = nonce, False


class FutureMarkerClaimCapability:
    __slots__ = ("_nonce", "_used")
    def __init__(self, nonce: object) -> None: self._nonce, self._used = nonce, False


class FutureLiveIoCapability:
    __slots__ = ("_nonce",)
    def __init__(self, nonce: object) -> None: self._nonce = nonce


class D267IntentCapability:
    __slots__ = ("_nonce", "_used")
    def __init__(self, nonce: object) -> None: self._nonce, self._used = nonce, False


class D267MarkerClaimCapability:
    __slots__ = ("_nonce", "_used")
    def __init__(self, nonce: object) -> None: self._nonce, self._used = nonce, False


class D267LiveIoCapability:
    __slots__ = ("_nonce",)
    def __init__(self, nonce: object) -> None: self._nonce = nonce


_D261_INTENT = object(); _D261_MARKER = object(); _D261_LIVE_IO = object()
_FUTURE_INTENT = object(); _FUTURE_MARKER = object(); _FUTURE_LIVE_IO = object()
_D267_INTENT = object(); _D267_MARKER = object(); _D267_LIVE_IO = object()


def _issue_d261_intent_after_exact_flag(exact_flag: str) -> CliIntentCapability:
    if exact_flag != D261_LIVE_AUTHORIZATION_FLAG: raise CapabilityFailure("explicit_live_authorization_required")
    return CliIntentCapability(_D261_INTENT)


def require_d261_intent(token: object) -> None:
    if not isinstance(token, CliIntentCapability) or token._nonce is not _D261_INTENT:
        raise CapabilityFailure("valid_cli_intent_capability_required")


def _issue_d261_marker_after_durable_claim(token: object) -> MarkerClaimCapability:
    require_d261_intent(token); return MarkerClaimCapability(_D261_MARKER)


def _issue_d261_live_io_after_marker(token: object, marker: object) -> LiveIoCapability:
    require_d261_intent(token)
    if not isinstance(marker, MarkerClaimCapability) or marker._nonce is not _D261_MARKER:
        raise CapabilityFailure("single_use_marker_required_before_live_io")
    return LiveIoCapability(_D261_LIVE_IO)


def issue_future_intent(exact_flag: str) -> FutureIntentCapability:
    if exact_flag != D265_FUTURE_LIVE_AUTHORIZATION_FLAG: raise CapabilityFailure("exact_future_operator_intent_required")
    return FutureIntentCapability(_FUTURE_INTENT)


def consume_future_intent(token: object) -> None:
    if not isinstance(token, FutureIntentCapability) or token._nonce is not _FUTURE_INTENT:
        raise CapabilityFailure("future_intent_capability_required")
    if token._used: raise CapabilityFailure("future_intent_capability_already_used")
    token._used = True


def _issue_future_marker_after_durable_claim(token: object) -> FutureMarkerClaimCapability:
    if not isinstance(token, FutureIntentCapability) or token._nonce is not _FUTURE_INTENT or not token._used:
        raise CapabilityFailure("consumed_future_intent_required_after_durable_marker")
    return FutureMarkerClaimCapability(_FUTURE_MARKER)


def issue_future_live_io(marker: object) -> FutureLiveIoCapability:
    if not isinstance(marker, FutureMarkerClaimCapability) or marker._nonce is not _FUTURE_MARKER:
        raise CapabilityFailure("valid_future_marker_claim_required")
    if marker._used: raise CapabilityFailure("future_marker_claim_capability_already_used")
    marker._used = True; return FutureLiveIoCapability(_FUTURE_LIVE_IO)


def issue_d267_intent(exact_flag: str) -> D267IntentCapability:
    if exact_flag != D267_LIVE_AUTHORIZATION_FLAG:
        raise CapabilityFailure("exact_d267_operator_intent_required")
    return D267IntentCapability(_D267_INTENT)


def consume_d267_intent(token: object) -> None:
    if not isinstance(token, D267IntentCapability) or token._nonce is not _D267_INTENT:
        raise CapabilityFailure("d267_intent_capability_required")
    if token._used:
        raise CapabilityFailure("d267_intent_capability_already_used")
    token._used = True


def _issue_d267_marker_after_durable_claim(token: object) -> D267MarkerClaimCapability:
    if (
        not isinstance(token, D267IntentCapability)
        or token._nonce is not _D267_INTENT
        or not token._used
    ):
        raise CapabilityFailure("consumed_d267_intent_required_after_durable_marker")
    return D267MarkerClaimCapability(_D267_MARKER)


def issue_d267_live_io(marker: object) -> D267LiveIoCapability:
    if not isinstance(marker, D267MarkerClaimCapability) or marker._nonce is not _D267_MARKER:
        raise CapabilityFailure("valid_d267_marker_claim_required")
    if marker._used:
        raise CapabilityFailure("d267_marker_claim_capability_already_used")
    marker._used = True
    return D267LiveIoCapability(_D267_LIVE_IO)


def require_known_material_intent(token: object) -> None:
    if isinstance(token, CliIntentCapability) and token._nonce is _D261_INTENT: return
    if isinstance(token, FutureIntentCapability) and token._nonce is _FUTURE_INTENT: return
    if isinstance(token, D267IntentCapability) and token._nonce is _D267_INTENT: return
    raise CapabilityFailure("known_material_intent_capability_required")


def require_known_live_io_capability(token: object) -> None:
    if isinstance(token, LiveIoCapability) and token._nonce is _D261_LIVE_IO: return
    if isinstance(token, FutureLiveIoCapability) and token._nonce is _FUTURE_LIVE_IO: return
    if isinstance(token, D267LiveIoCapability) and token._nonce is _D267_LIVE_IO: return
    raise CapabilityFailure("known_live_io_capability_required")


def require_root_with_nonroot_operator(euid: int, sudo_uid: str) -> None:
    """Shared D261/future operator-context policy; pure and offline-testable."""
    if euid != 0:
        raise CapabilityFailure("live_euid_root_required")
    if not sudo_uid.isdigit() or int(sudo_uid) == 0:
        raise CapabilityFailure("non_root_operator_context_required")
