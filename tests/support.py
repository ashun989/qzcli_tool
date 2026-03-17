from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import qzcli.config as config


@contextmanager
def temporary_config_state():
    original_values = {
        "CONFIG_DIR": config.CONFIG_DIR,
        "CONFIG_FILE": config.CONFIG_FILE,
        "JOBS_FILE": config.JOBS_FILE,
        "JOBS_ARCHIVE_FILE": config.JOBS_ARCHIVE_FILE,
        "TOKEN_CACHE_FILE": config.TOKEN_CACHE_FILE,
        "COOKIE_FILE": config.COOKIE_FILE,
        "RESOURCES_FILE": config.RESOURCES_FILE,
    }

    with TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        config.CONFIG_DIR = base
        config.CONFIG_FILE = base / "config.json"
        config.JOBS_FILE = base / "jobs.json"
        config.JOBS_ARCHIVE_FILE = base / "jobs.archive.jsonl"
        config.TOKEN_CACHE_FILE = base / ".token_cache"
        config.COOKIE_FILE = base / ".cookie"
        config.RESOURCES_FILE = base / "resources.json"
        try:
            yield base
        finally:
            for name, value in original_values.items():
                setattr(config, name, value)
