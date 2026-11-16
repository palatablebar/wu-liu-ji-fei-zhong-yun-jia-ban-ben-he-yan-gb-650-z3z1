"""测试夹具：临时库、样例主流程、固定时区。

环境变量必须在导入 app 之前设好，config 在导入时读取。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TMP = Path(tempfile.mkdtemp(prefix="gb650-tests-"))

os.environ["FREIGHTRATE_DATA"] = str(_TMP)
os.environ["FREIGHTRATE_DB"] = str(_TMP / "test.db")
os.environ["FREIGHTRATE_SAMPLE"] = str(ROOT / "sample_data")
os.environ["FREIGHTRATE_RULES"] = "fr-2026.11.15-b1"
os.environ["TZ"] = "Asia/Shanghai"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from app import config, store  # noqa: E402
from app.modules.m1_waybill import service as waybill_service  # noqa: E402
from app.modules.m2_rates import service as rate_service  # noqa: E402
from app.modules.m4_weights import service as weight_service  # noqa: E402
from app.modules.m5_charges import service as charge_service  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    store.init_db()
    rate_service.seed_sample(force=True)
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def pipeline(database):
    """把样例脏运单跑完整条流水线，返回各阶段结果。"""
    ingest = waybill_service.import_sample()
    run_id = ingest["run_id"]
    weights = weight_service.compute_weights(run_id)
    charges = charge_service.compute_charges(run_id)
    return {
        "run_id": run_id,
        "ingest": ingest,
        "weights": weights,
        "charges": charges,
    }


@pytest.fixture(scope="session")
def run_id(pipeline):
    return pipeline["run_id"]


@pytest.fixture(scope="session")
def sample_bytes():
    def load(name: str) -> bytes:
        path = config.SAMPLE_DIR / name
        assert path.exists(), f"样例缺失：{name}"
        return path.read_bytes()

    return load
