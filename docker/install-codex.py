"""Install a pinned official Codex binary, verifying the published asset digest."""

import argparse
import hashlib
import json
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


def install(output: Path):
    release = json.loads(Path(__file__).with_name("codex-release.json").read_text())
    architecture = platform.machine()
    if architecture not in release["linux"]:
        raise ValueError(f"Unsupported Codex Linux architecture: {architecture}")
    executable = f"codex-{architecture}-unknown-linux-musl"
    url = (
        "https://github.com/openai/codex/releases/download/"
        f"rust-v{release['version']}/{executable}.tar.gz"
    )
    with tempfile.TemporaryDirectory(prefix="codex-install-") as directory:
        archive = Path(directory) / "codex.tar.gz"
        digest = hashlib.sha256()
        with (
            urllib.request.urlopen(url, timeout=120) as response,
            archive.open("wb") as target,
        ):
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != release["linux"][architecture]:
            raise ValueError("Codex release archive does not match its pinned digest")
        with tarfile.open(archive, "r:gz") as package:
            member = package.getmember(executable)
            if not member.isfile():
                raise ValueError("Codex release member is not a regular file")
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(".installing")
            with package.extractfile(member) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target)
            temporary.chmod(0o755)
            temporary.replace(output)
    print(f"Installed Codex {release['version']} ({architecture})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    install(arguments.output)
