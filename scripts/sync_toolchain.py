#!/usr/bin/env python3
import argparse
import bz2
import fnmatch
import gzip
import io
import json
import lzma
import os
import pathlib
import shutil
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request


def parse_args():
    parser = argparse.ArgumentParser(description="Sync curated Termux toolchain files into a local staging folder.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--abi", required=True, help="Target ABI label for metadata.")
    parser.add_argument("--cache-dir", default=None, help="Optional cache directory.")
    parser.add_argument("--timeout", type=int, default=30, help="Download timeout in seconds per attempt (default: 30).")
    parser.add_argument("--retries", type=int, default=3, help="Number of retries per download (default: 3).")
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# #region debug-point A:server-reporting
def _debug_event(hypothesis_id, location, msg, data=None):
    env_path = os.path.join(os.getcwd(), ".dbg", "extension-build-hang.env")
    debug_url = "http://127.0.0.1:7777/event"
    session_id = "extension-build-hang"
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if line.startswith("DEBUG_SERVER_URL="):
                    debug_url = line.split("=", 1)[1]
                elif line.startswith("DEBUG_SESSION_ID="):
                    session_id = line.split("=", 1)[1]
    except OSError:
        pass
    payload = {
        "sessionId": session_id,
        "runId": "pre-fix",
        "hypothesisId": hypothesis_id,
        "location": location,
        "msg": f"[DEBUG] {msg}",
        "data": data or {},
        "ts": int(time.time() * 1000),
    }
    try:
        request = urllib.request.Request(
            debug_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=2).read()
    except Exception:
        pass


# #endregion


def download_bytes_with_progress(url, timeout, retries):
    for attempt in range(retries):
        try:
            # #region debug-point C:download-start
            _debug_event(
                "C",
                "sync_toolchain.py:download_bytes_with_progress",
                "start download",
                {"url": url, "attempt": attempt + 1, "timeout": timeout, "retries": retries},
            )
            # #endregion
            with urllib.request.urlopen(url, timeout=timeout) as response:
                total_size = response.getheader("Content-Length")
                if total_size:
                    total_size = int(total_size)
                    downloaded = 0
                    block_size = 8192
                    buffer = io.BytesIO()
                    first_chunk_reported = False
                    while True:
                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        if not first_chunk_reported:
                            # #region debug-point C:first-chunk
                            _debug_event(
                                "C",
                                "sync_toolchain.py:download_bytes_with_progress",
                                "received first download chunk",
                                {"url": url, "chunk_bytes": len(chunk), "total_size": total_size},
                            )
                            # #endregion
                            first_chunk_reported = True
                        buffer.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r  {percent:.1f}% ({downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB", end="", flush=True)
                    print()
                    # #region debug-point C:download-done
                    _debug_event(
                        "C",
                        "sync_toolchain.py:download_bytes_with_progress",
                        "download completed with content-length",
                        {"url": url, "bytes": downloaded, "total_size": total_size},
                    )
                    # #endregion
                    return buffer.getvalue()
                else:
                    payload = response.read()
                    # #region debug-point C:download-done-no-length
                    _debug_event(
                        "C",
                        "sync_toolchain.py:download_bytes_with_progress",
                        "download completed without content-length",
                        {"url": url, "bytes": len(payload)},
                    )
                    # #endregion
                    return payload
        except Exception as exc:
            # #region debug-point C:download-error
            _debug_event(
                "C",
                "sync_toolchain.py:download_bytes_with_progress",
                "download attempt failed",
                {"url": url, "attempt": attempt + 1, "error": str(exc)},
            )
            # #endregion
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                raise
            if attempt < retries - 1:
                wait = (attempt + 1) * 2
                print(f"\r  Retry {attempt + 1}/{retries} in {wait}s...", flush=True)
                time.sleep(wait)
            else:
                raise


def iter_repo_index_candidates(repo_index_url):
    seen = set()

    def add(url):
        if url not in seen:
            seen.add(url)
            yield url

    yield from add(repo_index_url)
    for suffix in (".xz", ".gz", ".bz2"):
        if repo_index_url.endswith(suffix):
            base = repo_index_url[: -len(suffix)]
            yield from add(base)
            yield from add(base + ".gz")
            yield from add(base + ".bz2")
            yield from add(base + ".xz")
            return
    yield from add(repo_index_url + ".gz")
    yield from add(repo_index_url + ".bz2")
    yield from add(repo_index_url + ".xz")


def decode_repo_index(raw_bytes, source_url):
    if source_url.endswith(".xz"):
        return lzma.decompress(raw_bytes).decode("utf-8")
    if source_url.endswith(".gz"):
        return gzip.decompress(raw_bytes).decode("utf-8")
    if source_url.endswith(".bz2"):
        return bz2.decompress(raw_bytes).decode("utf-8")
    return raw_bytes.decode("utf-8")


def download_repo_index_text(repo_index_url, timeout, retries):
    errors = []
    for candidate in iter_repo_index_candidates(repo_index_url):
        try:
            print(f"Trying index: {candidate}")
            raw_bytes = download_bytes_with_progress(candidate, timeout, retries)
            return decode_repo_index(raw_bytes, candidate)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, EOFError, lzma.LZMAError) as exc:
            errors.append(f"{candidate}: {exc}")
    joined = "\n".join(errors)
    raise RuntimeError(f"Unable to fetch Termux package index from any known variant:\n{joined}")


def parse_control_stanzas(text):
    packages = {}
    current = {}
    current_key = None
    for line in text.splitlines():
        if not line.strip():
            if "Package" in current:
                packages[current["Package"]] = current
            current = {}
            current_key = None
            continue
        if line.startswith(" ") and current_key:
            current[current_key] += " " + line.strip()
            continue
        key, _, value = line.partition(":")
        current_key = key.strip()
        current[current_key] = value.strip()
    if "Package" in current:
        packages[current["Package"]] = current
    return packages


def normalize_dep_name(raw):
    item = raw.strip()
    if not item:
        return None
    item = item.split("|", 1)[0].strip()
    item = item.split("(", 1)[0].strip()
    item = item.split(":", 1)[0].strip()
    return item or None


def resolve_dependencies(packages, roots):
    resolved = []
    queue = list(roots)
    seen = set()
    while queue:
        package_name = queue.pop(0)
        if package_name in seen:
            continue
        meta = packages.get(package_name)
        if meta is None:
            raise RuntimeError(f"Package '{package_name}' not found in Termux index.")
        seen.add(package_name)
        resolved.append(package_name)
        depends_field = meta.get("Depends", "")
        for raw_dep in depends_field.split(","):
            dep_name = normalize_dep_name(raw_dep)
            if dep_name and dep_name not in seen:
                queue.append(dep_name)
    return resolved


def ensure_dir(path):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def cached_download(url, cache_dir, timeout, retries):
    filename = urllib.parse.urlparse(url).path.split("/")[-1]
    target = os.path.join(cache_dir, filename)
    if os.path.exists(target):
        print(f"  Using cached: {filename}")
        return target
    print(f"  Downloading: {filename}")
    data = download_bytes_with_progress(url, timeout, retries)
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def read_ar_member(archive_path, member_prefix):
    with open(archive_path, "rb") as handle:
        if handle.read(8) != b"!<arch>\n":
            raise RuntimeError(f"{archive_path} is not a valid ar archive.")
        while True:
            header = handle.read(60)
            if not header:
                break
            name = header[:16].decode("utf-8").strip()
            size = int(header[48:58].decode("utf-8").strip())
            data = handle.read(size)
            if size % 2 == 1:
                handle.read(1)
            clean_name = name.rstrip("/")
            if clean_name.startswith(member_prefix):
                return clean_name, data
    raise RuntimeError(f"{member_prefix}* not found in {archive_path}.")


def should_exclude(relative_path, exclude_globs):
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in exclude_globs)


def copy_tar_member(member, handle, output_root, symlink_jobs, executable_paths):
    output_path = os.path.join(output_root, member["relative"])
    parent = os.path.dirname(output_path)
    ensure_dir(parent)
    if member["type"] == "file":
        with open(output_path, "wb") as target:
            shutil.copyfileobj(handle, target)
        file_mode = 0o755 if member["executable"] else 0o644
        os.chmod(output_path, file_mode)
        if member["executable"]:
            executable_paths.add(member["relative"])
    elif member["type"] == "symlink":
        symlink_jobs.append(
            {
                "path": member["relative"],
                "target": member["target"],
            }
        )


def write_layout_metadata(output_root, symlink_jobs, executable_paths):
    metadata_dir = os.path.join(output_root, "metadata")
    ensure_dir(metadata_dir)
    payload = {
        "symlinks": sorted(symlink_jobs, key=lambda item: item["path"]),
        "executables": sorted(executable_paths),
    }
    with open(os.path.join(metadata_dir, "toolchain-layout.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def extract_package(deb_path, root_prefix, exclude_globs, output_root):
    member_name, data_bytes = read_ar_member(deb_path, "data.tar")
    mode = "r:*"
    symlink_jobs = []
    executable_paths = set()
    with tarfile.open(fileobj=io.BytesIO(data_bytes), mode=mode) as tar:
        for entry in tar.getmembers():
            if not (entry.isfile() or entry.issym() or entry.islnk()):
                continue
            normalized = entry.name.lstrip("./")
            if not normalized.startswith(root_prefix):
                continue
            relative = normalized[len(root_prefix):]
            if not relative or should_exclude(relative, exclude_globs):
                continue
            if entry.isfile():
                extracted = tar.extractfile(entry)
                if extracted is None:
                    continue
                copy_tar_member(
                    {
                        "relative": relative,
                        "type": "file",
                        "executable": bool(entry.mode & 0o111),
                    },
                    extracted,
                    output_root,
                    symlink_jobs,
                    executable_paths,
                )
            elif entry.issym() or entry.islnk():
                copy_tar_member(
                    {"relative": relative, "type": "symlink", "target": entry.linkname},
                    None,
                    output_root,
                    symlink_jobs,
                    executable_paths,
                )
    return symlink_jobs, executable_paths


def write_metadata(output_root, abi, top_level, resolved, package_index):
    metadata_dir = os.path.join(output_root, "metadata")
    ensure_dir(metadata_dir)
    payload = {
        "abi": abi,
        "topLevelPackages": top_level,
        "resolvedPackages": [
            {
                "name": name,
                "version": package_index[name].get("Version", ""),
                "filename": package_index[name].get("Filename", "")
            }
            for name in resolved
        ]
    }
    with open(os.path.join(metadata_dir, "toolchain-metadata.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main():
    args = parse_args()
    config = load_json(args.config)
    output_root = os.path.abspath(args.output)
    cache_dir = os.path.abspath(args.cache_dir or os.path.join(os.path.dirname(args.config), "..", "toolchain-cache"))
    ensure_dir(cache_dir)
    if os.path.exists(output_root):
        shutil.rmtree(output_root)
    ensure_dir(output_root)

    # #region debug-point A:main-start
    _debug_event(
        "A",
        "sync_toolchain.py:main",
        "toolchain sync started",
        {
            "config": os.path.abspath(args.config),
            "output_root": output_root,
            "cache_dir": cache_dir,
            "abi": args.abi,
            "timeout": args.timeout,
            "retries": args.retries,
            "top_level_count": len(config.get("topLevelPackages", [])),
        },
    )
    # #endregion

    print("Downloading Termux package index...")
    # #region debug-point B:index-start
    _debug_event(
        "B",
        "sync_toolchain.py:main",
        "start fetching package index",
        {"repo_index_url": config["repoIndexUrl"]},
    )
    # #endregion
    index_text = download_repo_index_text(config["repoIndexUrl"], args.timeout, args.retries)
    package_index = parse_control_stanzas(index_text)
    resolved_packages = resolve_dependencies(package_index, config["topLevelPackages"])
    # #region debug-point B:index-done
    _debug_event(
        "B",
        "sync_toolchain.py:main",
        "package index resolved",
        {
            "package_index_count": len(package_index),
            "resolved_packages_count": len(resolved_packages),
            "first_packages": resolved_packages[:5],
        },
    )
    # #endregion
    print(f"Resolved {len(resolved_packages)} packages.")

    package_base_url = config["packageBaseUrl"]
    root_prefix = config["rootPrefix"]
    exclude_globs = config.get("excludeGlobs", [])

    all_symlink_jobs = []
    all_executable_paths = set()

    for idx, package_name in enumerate(resolved_packages, 1):
        print(f"[{idx}/{len(resolved_packages)} {package_name}")
        filename = package_index[package_name].get("Filename")
        if not filename:
            raise RuntimeError(f"Package '{package_name}' has no Filename in the index.")
        url = urllib.parse.urljoin(package_base_url, filename)
        # #region debug-point D:package-stage
        _debug_event(
            "D",
            "sync_toolchain.py:main",
            "processing package",
            {
                "index": idx,
                "total": len(resolved_packages),
                "package_name": package_name,
                "filename": filename,
                "url": url,
            },
        )
        # #endregion
        deb_path = cached_download(url, cache_dir, args.timeout, args.retries)
        # #region debug-point E:extract-start
        _debug_event(
            "E",
            "sync_toolchain.py:main",
            "start extract package",
            {"package_name": package_name, "deb_path": deb_path},
        )
        # #endregion
        symlink_jobs, executable_paths = extract_package(deb_path, root_prefix, exclude_globs, output_root)
        all_symlink_jobs.extend(symlink_jobs)
        all_executable_paths.update(executable_paths)
        # #region debug-point E:extract-done
        _debug_event(
            "E",
            "sync_toolchain.py:main",
            "finished extract package",
            {"package_name": package_name},
        )
        # #endregion

    write_layout_metadata(output_root, all_symlink_jobs, all_executable_paths)
    write_metadata(output_root, args.abi, config["topLevelPackages"], resolved_packages, package_index)
    # #region debug-point A:main-done
    _debug_event(
        "A",
        "sync_toolchain.py:main",
        "toolchain sync finished",
        {"output_root": output_root, "resolved_packages_count": len(resolved_packages)},
    )
    # #endregion
    print(f"Toolchain staged at {output_root}")


if __name__ == "__main__":
    main()
