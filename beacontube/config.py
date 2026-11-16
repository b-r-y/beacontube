"""Settings, from the environment."""

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path
    name: str
    # Required on every request Beacon passes on to /v1 and /ui/ when set.
    token: str
    # Signs audio and cover addresses, which Beacon and the speakers fetch
    # without any header.
    secret: bytes
    host: str
    port: int
    # How long a song's audio stays after it left the history and the most
    # played list, in hours. Set in days (KEEP_DAYS): Beacon asks for a day at
    # least, so hours would only invite a value below it.
    keep_hours: float = 24


MIN_KEEP_DAYS = 1


def _secret(data_dir: Path) -> bytes:
    """SECRET if set, otherwise one made on first start and kept: a new one
    would change every song's address, and Beacon would treat them as new
    songs."""
    explicit = os.environ.get("SECRET", "")
    if explicit:
        return explicit.encode()
    path = data_dir / "secret"
    try:
        return path.read_bytes().strip()
    except FileNotFoundError:
        value = secrets.token_urlsafe(32).encode()
        path.write_bytes(value)
        path.chmod(0o600)
        return value


def _keep_hours() -> float:
    """KEEP_DAYS, in hours: a whole or a part day, one at least."""
    raw = os.environ.get("KEEP_DAYS", "")
    if not raw:
        return MIN_KEEP_DAYS * 24
    try:
        days = float(raw)
    except ValueError:
        raise SystemExit(f"KEEP_DAYS has to be a number of days, not {raw!r}.") from None
    if days < MIN_KEEP_DAYS:
        logging.getLogger("beacontube").warning(
            f"KEEP_DAYS={raw} is less than a day; keeping files for a day,"
            " since Beacon may ask for a song again within one."
        )
        return MIN_KEEP_DAYS * 24
    return days * 24


def load() -> Config:
    data_dir = Path(os.environ.get("DATA_DIR", "data")).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(data_dir, os.W_OK):
        raise SystemExit(f"Cannot write to {data_dir} as uid {os.getuid()}.")
    return Config(
        data_dir=data_dir,
        name=os.environ.get("SOURCE_NAME", "BeaconTube"),
        token=os.environ.get("TOKEN", ""),
        secret=_secret(data_dir),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8802")),
        keep_hours=_keep_hours(),
    )
