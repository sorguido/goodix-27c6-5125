# SPDX-License-Identifier: GPL-2.0-or-later
"""Run one production service tick with a deterministic host-only driver."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from goodix_orchestrator.cli import _service_tick
from goodix_orchestrator.persistence import SQLiteStateStore
from tests.test_o003_coordinator import FakeDriver


repository = Path(sys.argv[1]).resolve(strict=True)
state_path = Path(sys.argv[2])
store = SQLiteStateStore(state_path)
store.initialize()
config = {
    "github_repository": "owner/private",
    "authorized_github_user_id": 1,
    "authorized_github_login": "authority",
    "reprobe_seconds": 900,
}

with patch(
    "goodix_orchestrator.cli.CodexCoordinatorDriver",
    side_effect=lambda *args, **kwargs: FakeDriver(),
):
    tick, close, engine = _service_tick(store, config, repository)
    try:
        tick()
        operator = store.load_operator_state()
        runtime = store.load_runtime()
        print(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "run_id": None if runtime is None else runtime.run_id,
                    "state": None if runtime is None else runtime.current_state.value,
                    "operator_paused": operator.operator_paused,
                    "error_class": operator.last_error_class,
                },
                sort_keys=True,
            )
        )
        if operator.operator_paused:
            raise SystemExit(3)
    finally:
        close()
