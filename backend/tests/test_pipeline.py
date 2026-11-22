import sys

import pytest

from app import pipeline


def test_run_times_out_as_runtime_error():  # 리뷰 #4
    with pytest.raises(RuntimeError, match="시간 초과"):
        pipeline._run([sys.executable, "-c", "import time; time.sleep(5)"], "캡처", timeout=0.2)
