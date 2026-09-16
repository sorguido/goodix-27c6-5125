#!/usr/bin/env python3
"""Build the mechanical D230 tables from the offline census.

This tool only consumes already extracted files below analysis/D230/work and
emits aggregate metadata/tables.  It has no hardware, USB or network access.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
D230 = ROOT / "analysis" / "D230"
WORK = D230 / "work"
CENSUS = json.loads((WORK / "offline_census.json").read_text())


def write_csv(name: str, fields: list[str], rows: list[dict[str, object]]) -> None:
    with (D230 / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def addr(value: str) -> str:
    return f"0x{int(value, 16):x}"


OBSERVED_NAMES = {
    "0x01": "NOP/state request (wire bit set)",
    "0x20": "sensor/mode family",
    "0x22": "sensor/mode family subtype",
    "0x32": "sensor/mode family",
    "0x34": "sensor/mode family subtype",
    "0x36": "sensor/mode family subtype",
    "0x50": "sensor/mode family",
    "0x70": "mode command; resident target unresolved",
    "0x80": "ChipRegWrite",
    "0x82": "ChipRegRead",
    "0x90": "DEVICE_CONFIG download",
    "0x97": "SetDriverState wire coordinate",
    "0xa2": "MCU/reset-family command",
    "0xa6": "OTP/fixed production read",
    "0xa8": "GetEvkVersion",
    "0xaf": "GetMcuState wire coordinate",
    "0xd1": "TLS server initialization / transition",
    "0xd4": "D-family state command",
    "0xd5": "D4-family wire coordinate",
    "0xe4": "production_read_mcu selector protocol",
}

STATIC_NAMES = {
    "0x40": "mode family",
    "0x60": "mode family",
    "0x70": "mode family",
    "0x80": "ChipRegWrite",
    "0x82": "ChipRegRead",
    "0x90": "DEVICE_CONFIG download",
    "0x92": "powerdown FDT scan frequency",
    "0x96": "SetDriverState",
    "0x98": "set DAC",
    "0x9a": "SPI communication test",
    "0xa0": "set/get SPI clock",
    "0xa2": "reset/MCU family",
    "0xa4": "erase APP / ClearApp",
    "0xa6": "OTP/fixed production read",
    "0xa8": "GetEvkVersion",
    "0xac": "mode family",
    "0xae": "GetMcuState",
    "0xd0": "TLS server init",
    "0xd2": "D-family state command",
    "0xd4": "D-family state command",
    "0xd8": "D-family state command",
    "0xe0": "production_write_mcu selector protocol",
    "0xe4": "production_read_mcu selector protocol",
    "0xe6": "E-family state command",
    "0xee": "E-family command",
    "0xf0": "firmware update frame",
    "0xf4": "firmware check/finalize/reset",
}


def build_known_baseline() -> None:
    observed = Counter(
        frame["wire_control"]
        for frame in CENSUS["host_to_device_frames"]
        if frame.get("outer_type") == "0xa0" and "wire_control" in frame
    )
    static = Counter(
        call["computed_opcode"]
        for call in CENSUS["builder_callsites"]
        if call["computed_opcode"] != "dynamic"
    )
    keys = sorted(set(observed) | set(static), key=lambda item: int(item, 16))
    rows = []
    for opcode in keys:
        name = OBSERVED_NAMES.get(opcode, STATIC_NAMES.get(opcode, "unlabelled family member"))
        read_class = "not_read"
        if opcode in {"0x82", "0xa6", "0xa8", "0xae", "0xaf", "0xe4"}:
            read_class = "bounded_or_selector_read"
        if opcode in {"0xa4", "0xf0", "0xf4"}:
            read_class = "maintenance_mutating"
        rows.append({
            "opcode_or_wire_control": opcode,
            "name_or_role": name,
            "observed_request_count": observed[opcode],
            "static_builder_callsite_count": static[opcode],
            "source": "recovered capture" if observed[opcode] else "gfusb static builder census",
            "read_boundary_class": read_class,
            "arbitrary_32bit_address": "no",
            "notes": "Wire value retained; pre-OR coordinate is not inferred by clearing bit 0.",
        })
    rows.append({
        "opcode_or_wire_control": "dynamic",
        "name_or_role": "runtime-computed subtype / generic no-ack / B0 TLS",
        "observed_request_count": 4,
        "static_builder_callsite_count": sum(c["computed_opcode"] == "dynamic" for c in CENSUS["builder_callsites"]),
        "source": "gfusb static builder census and recovered capture",
        "read_boundary_class": "bounded_by_callers_or_tls_transport",
        "arbitrary_32bit_address": "no",
        "notes": "Dynamic builders were classified by enclosing functions and callers.",
    })
    write_csv("D230_known_command_baseline.csv", list(rows[0]), rows)


def next_response(packet: int) -> str:
    candidates = [
        frame for frame in CENSUS["device_to_host_frames"]
        if frame["first_packet_index"] > packet
    ]
    if not candidates:
        return "none before capture end"
    frame = min(candidates, key=lambda item: item["first_packet_index"])
    if frame.get("outer_type") == "0xa0":
        return f"packet {frame['first_packet_index']}: A0 {frame.get('wire_control', 'unparsed')} len={frame['frame_length']}"
    return f"packet {frame['first_packet_index']}: {frame.get('outer_type')} len={frame['frame_length']}"


def capture_state(packet: int) -> str:
    if packet < 53:
        return "enumeration/initial queries"
    if packet < 114:
        return "normal APP cold-start pre-D1"
    if packet < 120:
        return "D1 transition"
    return "B0/TLS/application session"


def build_capture() -> None:
    rows = []
    counts = Counter(
        (frame.get("outer_type"), frame.get("wire_control", "n/a"))
        for frame in CENSUS["host_to_device_frames"]
    )
    for order, frame in enumerate(CENSUS["host_to_device_frames"], 1):
        packet = frame["first_packet_index"]
        outer = frame.get("outer_type", "unknown")
        wire = frame.get("wire_control", "n/a")
        if outer == "0xa0":
            candidates = frame.get("candidate_flash_addresses", [])
            candidate_text = ";".join(f"{v['value']}@inner+{v['offset']}" for v in candidates) or "none"
            shape = f"A0 inner={frame.get('inner_length')} payload={frame.get('payload_length')}; bounded prefix={frame.get('payload_prefix_hex','')[:32]}"
            length_fields = "outer LE16 + inner LE16; no proven host memory-read length"
            logical = {
                "0xd5": "0xd4 (builder-proven)",
                "0x97": "0x96 (builder-proven)",
                "0xaf": "0xae (builder-proven)",
                "0x01": "0x00 for bounded no-ack form",
            }.get(wire, wire)
        else:
            candidate_text = "not inspected as plaintext; TLS transport"
            shape = f"B0 TLS record wrapper, frame length={frame['frame_length']}"
            length_fields = "B0/TLS record length only"
            logical = "n/a"
        rows.append({
            "capture_id": "recovered-rilevamento-sha256-50071c0f",
            "order": order,
            "packet_index_zero_based": packet,
            "outer_type": outer,
            "wire_control_opcode": wire,
            "logical_pre_or_control_if_proven": logical,
            "payload_length": frame.get("payload_length", frame["frame_length"] - 4),
            "payload_shape": shape,
            "candidate_address_fields": candidate_text,
            "candidate_length_fields": length_fields,
            "preceding_mode_state": capture_state(packet),
            "following_response": next_response(packet),
            "repetition_count_in_capture": counts[(outer, wire)],
            "memory_read_candidate": (
                "false_positive_fixed_config_bytes"
                if outer == "0xa0" and candidates
                else "no"
            ),
        })
    write_csv("D230_windows_capture_opcode_census.csv", list(rows[0]), rows)


FUNCTION_LABELS = {
    0x18001C190: "E6 state command",
    0x18001C1F8: "D8 state command",
    0x18001C260: "D2 state command",
    0x18001C2C8: "SendSPICommunicationTestPackage",
    0x18001C46C: "D4 state command",
    0x18001C534: "TLSServerInit",
    0x180024C90: "ChicagoHUSetMode",
    0x180027ED0: "ChicagoHUsetDac",
    0x18002A540: "ChicagoTSetMode",
    0x18002D790: "ChicagoTsetDac",
    0x180030DF0: "milanGSetMode",
    0x1800345E0: "milanLSetMode",
    0x18003C7F4: "production_read_mcu",
    0x18003D8E0: "production_write_mcu",
    0x180058D50: "tls_callback_send",
    0x180059488: "ChipRegRead",
    0x180059610: "ChipRegWrite",
    0x180059B38: "GetEvkVersion",
    0x180059F98: "GetMcuState",
    0x18005A33C: "HardResetMCUWithCmd",
    0x18005B0C8: "E-family helper",
    0x18005B4BC: "ProductionOperateKey",
    0x18005C1D0: "SendNopCmd",
    0x18005C724: "SetDriverState",
    0x18005D598: "UsbSendDataToDeviceLock",
    0x180061550: "device_action_erase_app",
    0x1800655F8: "A6 fixed production/OTP read",
    0x1800656F4: "gfUpdatefirmware/ClearApp",
    0x180067244: "gf_do_communication_test",
    0x180067328: "gf_download_config",
    0x1800683DC: "gf_set_pwrdown_fdt_scanfreq",
    0x180069880: "gfresetMCUAndfingerprint",
    0x180069C20: "gfsetAndGetSPICLK",
    0x18006BB3C: "updatefirmware",
}


def builder_payload(label: str, opcode: str) -> tuple[str, str, str]:
    if label == "ChipRegRead":
        return ("fixed 5-byte body: selector byte + LE16 register + LE16 count", "typed response copied to caller", "no: 16-bit register namespace")
    if label == "production_read_mcu":
        return ("caller blob under E4 production selector protocol", "parsed status/length then bounded copy", "no: high-level callers constrain selectors; no address serializer")
    if label == "ProductionOperateKey":
        return ("operation enum and fixed key/state selector", "fixed PMK-hash/state/Pkey result", "no: enum, not address")
    if "firmware" in label.lower() or "erase" in label.lower():
        return ("firmware slices/control", "status/check result", "no readback; mutating maintenance path")
    if label == "tls_callback_send":
        return ("preformed TLS record", "transport completion", "not a device command builder")
    return ("fixed constants and/or caller-bounded command data", "ACK or typed operation response", "no host-controlled 32-bit MCU address proven")


def build_builders() -> None:
    observed_ops = {frame.get("wire_control") for frame in CENSUS["host_to_device_frames"]}
    rows = []
    for call in CENSUS["builder_callsites"]:
        function = int(call["function_start"], 16)
        label = FUNCTION_LABELS.get(function, "classified enclosing function")
        opcode = call["computed_opcode"]
        payload, consumer, arbitrary = builder_payload(label, opcode)
        rows.append({
            "function_address": f"0x{function:x}",
            "callsite": addr(call["callsite"]),
            "callers_or_enclosing_role": label,
            "transport_builder": call["transport_kind"],
            "opcode_control": opcode,
            "arguments": f"r8={call.get('r8_command','dynamic')};r9={call.get('r9_subcommand','dynamic')};rcx={call.get('rcx','dynamic')};rdx={call.get('rdx','dynamic')}",
            "payload_construction": payload,
            "constants": json.dumps(call.get("stack_constants", {}), sort_keys=True, separators=(",", ":")),
            "response_size": "operation-specific bounded output; no length-proportional arbitrary memory response",
            "consumer": consumer,
            "observed_in_recovered_capture": "yes" if opcode in observed_ops or call["transport_kind"] == "B0_TLS" else "no",
            "arbitrary_read_dataflow": arbitrary,
            "static_evidence": f"gfusb disassembly line {call['disasm_line']}; builder {call['transport_kind']}",
        })
    write_csv("D230_gfusb_command_builder_inventory.csv", list(rows[0]), rows)


def build_usb_surface() -> None:
    rows = [
        {"surface":"bulk OUT 0x01 / IN 0x81 A0","host_to_device":"yes","capture_count":"56 OUT submissions / 59 IN submissions","address_capable":"payload is generic but inventoried builders expose no arbitrary 32-bit MCU read","memory_read":"bounded typed reads only","classification":"fully inventoried core command transport"},
        {"surface":"bulk OUT 0x01 / IN 0x81 B0","host_to_device":"yes","capture_count":"4 host B0 frames","address_capable":"TLS application data, not an APP command escape in classified gfusb paths","memory_read":"no memory-read builder/dispatcher found","classification":"TLS record transport"},
        {"surface":"interrupt IN 0x82","host_to_device":"no","capture_count":"2 submissions + 2 completions","address_capable":"no OUT direction","memory_read":"no command payload observed","classification":"zero-length/polling only in recovered capture"},
        {"surface":"standard control EP0","host_to_device":"descriptor/configuration only","capture_count":"4 OUT + 7 IN submissions","address_capable":"USB setup values only","memory_read":"no vendor/class memory request","classification":"enumeration surface"},
        {"surface":"vendor/class control transfer","host_to_device":"not found","capture_count":"0","address_capable":"no","memory_read":"no","classification":"absent from capture and classified UMDF send paths"},
        {"surface":"alternate interface/CDC/raw non-A0 bulk","host_to_device":"not found","capture_count":"0","address_capable":"no evidence","memory_read":"no","classification":"no descriptor, capture, import or send-path evidence"},
        {"surface":"UMDF IOCTL to USB indirection 0x18005ddcc","host_to_device":"yes via the above pipes","capture_count":"covered by A0/B0 counts","address_capable":"does not synthesize a separate USB request type","memory_read":"no alternate backend found","classification":"transport indirection, not extra wire surface"},
    ]
    write_csv("D230_usb_transport_surface.csv", list(rows[0]), rows)


def build_dispatcher() -> None:
    handlers = {
        0:("resident/indirect","resident_unknown","unresolved family; no host arbitrary-read builder"),
        1:("resident/indirect","resident_unknown","unresolved family; no host arbitrary-read builder"),
        2:("0x20006d4c + slot 0","indirect","mode callback"),
        3:("0x20006d4c + slot 8","indirect","mode callback"),
        4:("0x20006d4c + slot 12","indirect","mode callback"),
        5:("0x20006d4c + slot 4","indirect","mode callback"),
        6:("0x20006d4c + slot 20","indirect","mode callback"),
        7:("0x20006d4c + slot 16 -> 0x0802b8f5","resident_unknown","0x70 semantics unavailable below APP start"),
        8:("0x0803356c","yes","0x80/0x82 register family; LE16 register fields"),
        9:("0x080367d4","yes","0x90/0x92/0x96/0x98/0x9a config/state family"),
        10:("0x08033188","yes","A-family switch; A2 subtype 2 -> 0x080272e1 resident; A6/A8 bounded"),
        11:("default","yes","no separate handler in 16-way dispatcher"),
        12:("default","yes","no separate handler in 16-way dispatcher"),
        13:("0x080396b0","yes","D-family TLS/state handling"),
        14:("0x08033b3c","yes","E-family production selector protocols"),
        15:("0x08033c4c","yes","F-family firmware update/check handling"),
    }
    observed = Counter(int(f["wire_control"],16) >> 4 for f in CENSUS["host_to_device_frames"] if f.get("outer_type") == "0xa0")
    rows = []
    for family in range(16):
        handler, present, note = handlers[family]
        rows.append({
            "wire_opcode_family": f"0x{family:x}x",
            "dispatcher_slot": family,
            "dispatcher_entry_address": "0x08035e3c jump table / state switch",
            "handler_address_or_slot": handler,
            "handler_present_in_app": present,
            "input_length_checks": "family/subtype-specific bounded parser" if present == "yes" else "not recoverable without resident body",
            "payload_fields": note,
            "reply_path": "0x08032f94 typed A0 reply or family callback" if present == "yes" else "unknown resident/indirect",
            "observed_requests_in_recovered_capture": observed[family],
            "arbitrary_address_length_interpretation": "not found in APP-present handlers",
            "question_relevant_unresolved": "no" if family not in {7,10} else "resident body absent, but no matching host arbitrary-read builder/request",
        })
    write_csv("D230_app12509_dispatcher_census.csv", list(rows[0]), rows)


def build_primitive_map() -> None:
    rows = [
        {"primitive_or_function":"ordinary CPU loads/copy loops","address":"multiple APP functions","source_address_domain":"APP literals/SRAM/caller-internal pointers","length_constraints":"call-site fixed/bounded","side_effects":"none inherent","caller_set":"internal APP","host_reachable":"not as host-controlled source pointer","normal_mode":"yes internally","iap_only":"no","class":"PRIMITIVE_EXISTS_BUT_NOT_EXPOSED"},
        {"primitive_or_function":"ChipRegRead handler","address":"gfusb 0x180059488; APP family 8 at 0x0803356c","source_address_domain":"16-bit chip/sensor register namespace","length_constraints":"LE16 count and typed response","side_effects":"read-like register access","caller_set":"normal Windows stack","host_reachable":"yes, bounded namespace","normal_mode":"yes","iap_only":"no","class":"BOUNDED_REGISTER_READ_NOT_MCU_MEMORY"},
        {"primitive_or_function":"production_read_mcu","address":"gfusb 0x18003c7f4; APP E family 0x08033b3c","source_address_domain":"production selector namespace","length_constraints":"selector-defined response","side_effects":"selector dependent","caller_set":"production wrappers","host_reachable":"yes through constrained callers","normal_mode":"yes","iap_only":"no","class":"FIXED_SELECTOR_READ_NOT_ARBITRARY"},
        {"primitive_or_function":"A6 production/OTP read","address":"gfusb 0x1800655f8; APP A family 0x08033188","source_address_domain":"OTP/factory selector","length_constraints":"fixed protocol result","side_effects":"none proven for read","caller_set":"firmware/version initialization","host_reachable":"yes","normal_mode":"yes","iap_only":"no","class":"FIXED_OTP_READ_NOT_FLASH"},
        {"primitive_or_function":"A8 firmware version","address":"gfusb 0x180059b38; APP A family 0x08033188","source_address_domain":"fixed firmware identity","length_constraints":"fixed string response","side_effects":"none","caller_set":"initial query","host_reachable":"yes","normal_mode":"yes","iap_only":"no","class":"FIXED_METADATA_READ"},
        {"primitive_or_function":"AE/AF MCU state","address":"gfusb 0x180059f98; APP A family 0x08033188","source_address_domain":"fixed state structure","length_constraints":"fixed state response","side_effects":"none proven","caller_set":"normal Windows stack","host_reachable":"yes","normal_mode":"yes","iap_only":"no","class":"FIXED_STATE_READ"},
        {"primitive_or_function":"F0/F4 firmware programming/check","address":"gfusb 0x18006bb3c; APP F family 0x08033c4c","source_address_domain":"update image/status, not raw flash return","length_constraints":"sliced firmware input; status response","side_effects":"erase/program/reset possible","caller_set":"firmware update","host_reachable":"maintenance only","normal_mode":"requires transition/update flow","iap_only":"yes/maintenance","class":"MUTATING_NO_READBACK_FOUND"},
        {"primitive_or_function":"flash controller program control","address":"APP 0x0802d874 / peripheral 0x40023c00","source_address_domain":"flash program/erase control","length_constraints":"program path","side_effects":"persistent mutation","caller_set":"firmware maintenance","host_reachable":"only through mutating maintenance flow","normal_mode":"no safe use","iap_only":"maintenance","class":"WRITE_PRIMITIVE_NOT_READ_PATH"},
        {"primitive_or_function":"A2 / 0x70 resident handlers","address":"0x080272e1 / 0x0802b8f5","source_address_domain":"body absent","length_constraints":"unknown","side_effects":"unknown","caller_set":"normal cold-start","host_reachable":"yes for the exact fixed captured requests","normal_mode":"yes","iap_only":"unknown","class":"RESIDENT_UNKNOWN_NO_ARBITRARY_HOST_DATAFLOW"},
    ]
    write_csv("D230_memory_read_primitive_map.csv", list(rows[0]), rows)


def build_read_boundaries() -> None:
    rows = [
        {"operation":"E4","host_controls":"production selector/request blob through constrained API","address_namespace":"production MCU service selectors","address_fixed_or_arbitrary":"selector, not proven address","length_fixed_or_arbitrary":"selector-defined bounded output","maximum_read":"not a caller-selected MCU span","memory_domain":"fixed production data","side_effects":"selector-dependent; studied read path","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"no 32-bit address+length serializer or matching handler"},
        {"operation":"0x82 ChipRegRead","host_controls":"LE16 register + LE16 count","address_namespace":"chip/sensor registers","address_fixed_or_arbitrary":"arbitrary only inside 16-bit register namespace","length_fixed_or_arbitrary":"LE16 typed count","maximum_read":"operation bounded; not MCU flash span","memory_domain":"registers","side_effects":"read-like","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"cannot encode either 32-bit MCU address"},
        {"operation":"A6 / OTP","host_controls":"fixed selector/shape","address_namespace":"OTP/factory data","address_fixed_or_arbitrary":"fixed/selective","length_fixed_or_arbitrary":"fixed","maximum_read":"fixed response","memory_domain":"OTP/factory","side_effects":"none proven for read","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"different namespace and no raw address"},
        {"operation":"A8","host_controls":"query only","address_namespace":"firmware version metadata","address_fixed_or_arbitrary":"fixed","length_fixed_or_arbitrary":"fixed string","maximum_read":"firmware name","memory_domain":"metadata","side_effects":"none","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"fixed metadata handler"},
        {"operation":"AE / wire AF","host_controls":"query only","address_namespace":"MCU state structure","address_fixed_or_arbitrary":"fixed","length_fixed_or_arbitrary":"fixed","maximum_read":"fixed state","memory_domain":"runtime state","side_effects":"none proven","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"fixed state response"},
        {"operation":"ProductionOperateKey","host_controls":"operation enum","address_namespace":"PMK hash / MCU state / Pkey selectors","address_fixed_or_arbitrary":"fixed enum","length_fixed_or_arbitrary":"fixed per enum","maximum_read":"operation-specific","memory_domain":"secure/factory typed data","side_effects":"operation-dependent","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"no pointer/address input"},
        {"operation":"0x90 DEVICE_CONFIG","host_controls":"224-byte configuration body","address_namespace":"configuration destination selected by handler","address_fixed_or_arbitrary":"not an address read","length_fixed_or_arbitrary":"fixed 224-byte download in capture","maximum_read":"none","memory_domain":"volatile configuration write","side_effects":"volatile write","can_reach_0x080272e0":"no","can_reach_0x0802b8f4":"no","reason":"download/write path; candidate address byte windows are coincidences"},
        {"operation":"F0/F4 update/check","host_controls":"firmware input slices/update control","address_namespace":"firmware update state","address_fixed_or_arbitrary":"not exposed as read address","length_fixed_or_arbitrary":"input slice lengths","maximum_read":"status only","memory_domain":"IAP/APP flash maintenance","side_effects":"erase/program/reset possible","can_reach_0x080272e0":"no safe read","can_reach_0x0802b8f4":"no safe read","reason":"no returned raw flash; path is mutating"},
    ]
    write_csv("D230_known_read_operations_boundary.csv", list(rows[0]), rows)


def build_falsification() -> None:
    rows = [
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"hidden opcode in recovered capture","SEARCH_METHOD":"enumerate every host A0/B0 frame and correlate next IN frame","SEARCH_BOUNDARY":"255 USB packets; 52 host framed requests","RESULT":"not found; 20 distinct A0 wire controls, no address+length request"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"32-bit flash address embedded in request","SEARCH_METHOD":"sliding LE32 scan for 0x08000000..0x080fffff plus structural review","SEARCH_BOUNDARY":"all recovered A0 request bodies","RESULT":"three windows only inside fixed 0x90 config; no field boundary, increment or proportional response"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"unused gfusb builder","SEARCH_METHOD":"classify all calls to A0 generic/no-ack and B0 builders by PE function ranges","SEARCH_BOUNDARY":"65 call-sites in gfusb .text","RESULT":"none serializes host-controlled 32-bit MCU address into a typed read"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"alternate USB request surface","SEARCH_METHOD":"capture transfer census, descriptors, imports and 0x18005ddcc IO indirection","SEARCH_BOUNDARY":"control, interrupt and bulk paths in recovered corpus","RESULT":"no vendor/class/debug/raw alternate path"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"APP handler copies from host pointer","SEARCH_METHOD":"16-family dispatcher census and present-handler dataflow review","SEARCH_BOUNDARY":"mapped APP families 8,9,A,D,E,F plus indirect slots","RESULT":"no APP-present arbitrary address+length response path"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"flash verify returns bytes","SEARCH_METHOD":"F0/F4 builder, strings and APP F-family review","SEARCH_BOUNDARY":"firmware update/check flow","RESULT":"status/check/reset only; no raw flash response and mutating preconditions"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"E4 is a generic memory peek","SEARCH_METHOD":"host serialization/consumer and E-family selector review","SEARCH_BOUNDARY":"production_read_mcu and its classified callers","RESULT":"selector protocol with parsed typed result; no MCU address serializer"},
        {"CLAIM":"no safe arbitrary resident read path","FALSIFIER":"0x82 register address aliases MCU flash","SEARCH_METHOD":"reconstruct exact LE16 register+count payload and APP family","SEARCH_BOUNDARY":"ChipRegRead 0x180059488 / family 8","RESULT":"16-bit register namespace cannot encode 0x080272e0 or 0x0802b8f4"},
        {"CLAIM":"negative proof coverage sufficient for inventoried corpus","FALSIFIER":"question-relevant unclassified host builder","SEARCH_METHOD":"function-range census around all known transport builders","SEARCH_BOUNDARY":"gfusb static corpus","RESULT":"none; dynamic subtypes classified by enclosing API role"},
        {"CLAIM":"negative proof coverage sufficient for inventoried corpus","FALSIFIER":"lost capture contains unique opcode","SEARCH_METHOD":"cannot inspect definitively lost operator-designated first capture","SEARCH_BOUNDARY":"one recovered capture only; historical metadata is not substituted for packet census","RESULT":"unresolvable coverage limitation; does not alter local-corpus claim, and is an explicit reopening condition"},
        {"CLAIM":"device can never expose arbitrary read","FALSIFIER":"resident code has undocumented command","SEARCH_METHOD":"scope check","SEARCH_BOUNDARY":"resident bodies below 0x0802c000 absent","RESULT":"claim rejected as too broad; D230 conclusion is explicitly corpus-bounded"},
    ]
    write_csv("D230_falsification_matrix.csv", list(rows[0]), rows)


def main() -> None:
    D230.mkdir(parents=True, exist_ok=True)
    build_known_baseline()
    build_capture()
    build_builders()
    build_usb_surface()
    build_dispatcher()
    build_primitive_map()
    build_read_boundaries()
    build_falsification()


if __name__ == "__main__":
    main()
