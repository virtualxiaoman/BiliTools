"""设置读写：JSON 持久化到 assets/ui_settings.json。"""
import json
from pathlib import Path

from src.config.path import ASSETS_DIR, VIDEO_OUTPUT_DIR

UI_SETTINGS_PATH = ASSETS_DIR / "ui_settings.json"

DEFAULTS = {
    "save_dir": str(VIDEO_OUTPUT_DIR),
    "quality": "HD4K",
    "media_type": "video_with_audio",  # 视频（含音频）/ 仅音频
    "theme": "light",                  # light / dark
    "log_max_lines": 1000,
    "log_timestamp": True,
}


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else UI_SETTINGS_PATH
        self.data = dict(DEFAULTS)
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.data.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass  # 损坏则回退默认

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self._save()

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
