import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from core.settings import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    s = Settings(user_path=tmp_path / "user.json")
    s.set("paths.output_dir", str(tmp_path / "out"))
    s.set("obs.enabled", False)
    s.set("beamng.steer_sign", 0)
    return s


needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="нужен ffmpeg")
