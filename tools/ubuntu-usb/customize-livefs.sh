#!/usr/bin/env bash
set -euo pipefail

mode="install"
assets_dir=""
manifest=""
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
packages_file="${PACKAGES_FILE:-$script_dir/packages.txt}"

usage() {
    cat <<'EOF'
Usage:
  customize-livefs.sh --check --assets-dir DIR --manifest FILE
  customize-livefs.sh --assets-dir DIR --manifest FILE

--check validates packages.txt and every local asset without changing files.
Normal mode is intended for Cubic's root-filesystem terminal and installs the
validated packages, official applications, and the local ICC profile.
EOF
}

while (($#)); do
    case "$1" in
        --check)
            mode="check"
            shift
            ;;
        --assets-dir)
            (($# >= 2)) || { usage >&2; exit 2; }
            assets_dir="$2"
            shift 2
            ;;
        --manifest)
            (($# >= 2)) || { usage >&2; exit 2; }
            manifest="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$assets_dir" || -z "$manifest" ]]; then
    usage >&2
    exit 2
fi

if [[ ! -f "$packages_file" ]]; then
    printf 'Package list is missing: %s\n' "$packages_file" >&2
    exit 1
fi

if [[ -n "${PYTHON:-}" ]]; then
    python_command="$PYTHON"
elif command -v python3 >/dev/null 2>&1; then
    python_command="python3"
elif command -v python >/dev/null 2>&1; then
    python_command="python"
else
    printf 'Python 3 is required to validate the local asset manifest.\n' >&2
    exit 1
fi

"$python_command" - "$assets_dir" "$manifest" "$packages_file" <<'PY'
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

assets_root = Path(sys.argv[1]).resolve()
manifest_path = Path(sys.argv[2])
packages_path = Path(sys.argv[3])
required_assets = {
    "antigravity_linux_x64",
    "chatgpt_linux_amd64",
    "ivo0536_icc_profile",
}
required_packages = {
    "git",
    "python3",
    "adb",
    "fastboot",
    "7zip",
    "e2fsprogs",
    "openjdk-21-jdk",
}
sha256_re = re.compile(r"^[0-9a-f]{64}$")
errors = []

try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as error:
    print(f"Invalid local asset manifest: {error}", file=sys.stderr)
    raise SystemExit(1)

try:
    package_lines = packages_path.read_text(encoding="utf-8").splitlines()
except OSError as error:
    print(f"Cannot read package list: {error}", file=sys.stderr)
    raise SystemExit(1)

package_names = []
for line_number, line in enumerate(package_lines, start=1):
    entry = line.split("#", 1)[0].strip()
    if not entry:
        continue
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", entry):
        errors.append(f"Invalid package name on line {line_number}: {entry!r}")
    else:
        package_names.append(entry)

missing_packages = required_packages - set(package_names)
if missing_packages:
    errors.append("Missing required packages: " + ", ".join(sorted(missing_packages)))
if len(package_names) != len(set(package_names)):
    errors.append("Package list contains duplicate package names")

assets = manifest.get("assets") if isinstance(manifest, dict) else None
if not isinstance(assets, list):
    errors.append("Local manifest must contain an assets list")
    assets = []

seen_ids = set()
for asset in assets:
    if not isinstance(asset, dict):
        errors.append("Every local asset entry must be an object")
        continue
    asset_id = asset.get("id")
    if not isinstance(asset_id, str) or not asset_id:
        errors.append("Every local asset must have an id")
        continue
    if asset_id in seen_ids:
        errors.append(f"Duplicate local asset id: {asset_id}")
        continue
    seen_ids.add(asset_id)

    relative_path = asset.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        errors.append(f"{asset_id}: missing relative path")
        continue
    posix_path = PurePosixPath(relative_path.replace("\\", "/"))
    if posix_path.is_absolute() or ".." in posix_path.parts:
        errors.append(f"{asset_id}: unsafe relative path")
        continue
    local_file = (assets_root / Path(*posix_path.parts)).resolve()
    try:
        local_file.relative_to(assets_root)
    except ValueError:
        errors.append(f"{asset_id}: asset path escapes the selected assets directory")
        continue
    if not local_file.is_file():
        errors.append(f"{asset_id}: missing local asset {relative_path}")
        continue

    version = asset.get("version")
    expected_digest = asset.get("sha256")
    if not isinstance(version, str) or not version.strip():
        errors.append(f"{asset_id}: exact version is required")
        continue
    if not isinstance(expected_digest, str) or not sha256_re.fullmatch(expected_digest):
        errors.append(f"{asset_id}: expected a 64-character lowercase SHA-256")
        continue

    digest = hashlib.sha256()
    with local_file.open("rb") as asset_file:
        for chunk in iter(lambda: asset_file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_digest:
        errors.append(f"{asset_id}: SHA-256 does not match the downloaded asset")

    if asset_id == "antigravity_linux_x64":
        try:
            with tarfile.open(local_file, mode="r:gz") as archive:
                has_launcher = any(
                    member.isfile()
                    and PurePosixPath(member.name).name.lower() == "antigravity"
                    and member.mode & 0o111
                    for member in archive.getmembers()
                )
            if not has_launcher:
                errors.append(f"{asset_id}: archive has no executable Antigravity launcher")
        except (OSError, tarfile.TarError) as error:
            errors.append(f"{asset_id}: invalid Antigravity tar.gz archive ({error})")

missing_assets = required_assets - seen_ids
if missing_assets:
    errors.append("Missing required assets: " + ", ".join(sorted(missing_assets)))

if errors:
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)

print("assets and package list verified")
PY

if [[ "$mode" == "check" ]]; then
    exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
    printf "Normal mode must run as root inside Cubic's root-filesystem terminal.\n" >&2
    exit 1
fi

brave_keyring="/usr/share/keyrings/brave-browser-archive-keyring.gpg"
install -d -m 0755 "$(dirname "$brave_keyring")"
curl -fsSLo "$brave_keyring" https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
curl -fsSLo /etc/apt/sources.list.d/brave-browser-release.sources https://brave-browser-apt-release.s3.brave.com/brave-browser.sources

mapfile -t package_names < <(sed 's/#.*//' "$packages_file" | awk 'NF {print $1}')
apt-get update
apt-get install -y --no-install-recommends "${package_names[@]}"
apt-get install -y --no-install-recommends "$assets_dir/chatgpt_amd64.deb"

install -d -m 0755 /opt/antigravity
tar -xzf "$assets_dir/Antigravity.tar.gz" -C /opt/antigravity
antigravity_binary="$(find /opt/antigravity -type f -iname antigravity -perm /111 -print -quit)"
if [[ -z "$antigravity_binary" ]]; then
    printf 'Official Antigravity archive did not contain an executable named Antigravity.\n' >&2
    exit 1
fi
cat > /usr/share/applications/antigravity.desktop <<EOF
[Desktop Entry]
Name=Google Antigravity
Comment=AI-assisted development environment
Exec=$antigravity_binary
Icon=applications-development
Terminal=false
Type=Application
Categories=Development;IDE;
EOF

install -D -m 0644 "$assets_dir/Dell_IVO0536_HDR_D65.icm" /usr/share/color/icc/Dell_IVO0536_HDR_D65.icm
apt-get clean
rm -rf /var/lib/apt/lists/*
printf 'Ubuntu workstation packages and local assets installed.\n'
