"""Public synthetic D190 inputs and OEM-oracle validators recovered from D190."""

VECTORS = {
    "V0": bytes(32),
    "V1": bytes([1]) * 32,
    "V2": bytes(range(32)),
    "V3": bytes([0xAA, 0x55]) * 16,
    "V4": bytes.fromhex("31dc314296631fa52db5a09e625f74d43f5420455a214272ab444f84393e8d5a"),
}

EXPECTED_VALIDATORS = {
    "V0": "b5e0beeb94c84eb99b883abd5c251073c56b91035c562a91a46c7f3349c36c89",
    "V1": "e51d069d67065a052307d3bd6dd8edf377e8b2389dc309475891e415e5f2148c",
    "V2": "d1ba9a4790f8d47ba8b50043d72b577cdc2d1b701d466197aa741a94fd0f1ec4",
    "V3": "ea43b0f9a2eae84d55fa9b0a961c35b7dd8e5c2594e5e4562c92c3f198a19209",
    "V4": "af13a21ec8f8250b47da268f32ef74cd0ff5dbc0f8b48b93ee5411e422e8a9b4",
}
