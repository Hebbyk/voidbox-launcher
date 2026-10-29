"""
mc_launcher.forge_processors — STAGE 2: runs a Forge/NeoForge install_profile's
"processors" to actually patch together a working client jar.

This is the genuinely hard part: modern Forge/NeoForge don't ship a ready
client jar, they ship a RECIPE (install_profile.json) for building one by
running a handful of small Java tools in sequence (remap to SRG names,
extract Mojang's mappings, apply a binary patch, etc). This module runs
that recipe.

Verified against real install_profile.json dumps from both Forge 1.20.1 and
NeoForge 1.20.4 — the mechanism, and its three data-value conventions, are
identical between them:
    "[group:artifact:version[:classifier][@ext]]"  -> a library file path
    "/some/path"                                    -> extract from installer jar
    "'literal value'"                               -> the literal, quotes stripped
"""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

import core  # reuses get_os_name() and the shared cache dir convention


class ProcessorError(Exception):
    pass


# ---------------------------------------------------------------------------
# Maven coordinate resolution, extended for the "@extension" suffix used
# throughout install_profile.json — core.maven_coord_to_path() doesn't need
# this for Fabric/Quilt's plain coordinates, so it's separate here.
# ---------------------------------------------------------------------------

def maven_coord_to_path_ext(coord: str) -> str:
    """'de.oceanlabs.mcp:mcp_config:1.20.1-X@zip' ->
    'de/oceanlabs/mcp/mcp_config/1.20.1-X/mcp_config-1.20.1-X.zip'
    'net.minecraft:client:1.20.1-X:mappings@txt' ->
    'net/minecraft/client/1.20.1-X/client-1.20.1-X-mappings.txt'"""
    coord, _, ext = coord.partition("@")
    ext = ext or "jar"
    parts = coord.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + f".{ext}"
    return f"{group.replace('.', '/')}/{artifact}/{version}/{filename}"


# ---------------------------------------------------------------------------
# Resolving placeholders
# ---------------------------------------------------------------------------

class InstallContext:
    """Bundles everything needed to resolve a processor's placeholders for
    one side (client/server) of one Forge/NeoForge install."""

    def __init__(self, libraries_dir: Path, root: Path, installer_jar: Path,
                 minecraft_jar: Path, side: str):
        self.libraries_dir = Path(libraries_dir)
        self.root = Path(root)
        self.installer_jar = Path(installer_jar)
        self.minecraft_jar = Path(minecraft_jar)
        self.side = side
        self._extracted_cache = {}

    def resolve_data_value(self, raw: str) -> str:
        if raw.startswith("[") and raw.endswith("]"):
            rel = maven_coord_to_path_ext(raw[1:-1])
            return str(self.libraries_dir / rel)
        if raw.startswith("/"):
            return str(self._extract_from_installer(raw))
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1]
        return raw

    def _extract_from_installer(self, jar_internal_path: str) -> Path:
        if jar_internal_path in self._extracted_cache:
            return self._extracted_cache[jar_internal_path]
        internal = jar_internal_path.lstrip("/")
        dest = self.root / internal
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(self.installer_jar) as zf:
                dest.write_bytes(zf.read(internal))
        self._extracted_cache[jar_internal_path] = dest
        return dest

    def build_substitutions(self, install_profile: dict) -> dict:
        subs = {
            "SIDE": self.side,
            "MINECRAFT_JAR": str(self.minecraft_jar),
            "ROOT": str(self.root),
            "INSTALLER": str(self.installer_jar),
            "LIBRARY_DIR": str(self.libraries_dir),
        }
        for key, entry in install_profile.get("data", {}).items():
            raw = entry.get(self.side)
            if raw is not None:
                subs[key] = self.resolve_data_value(raw)
        return subs


_BRACE_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")
_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")


def substitute(s: str, subs: dict, libraries_dir: Path) -> str:
    s = _BRACE_RE.sub(lambda m: subs.get(m.group(1), m.group(0)), s)
    s = _BRACKET_RE.sub(lambda m: str(Path(libraries_dir) / maven_coord_to_path_ext(m.group(1))), s)
    return s


# ---------------------------------------------------------------------------
# Running processors
# ---------------------------------------------------------------------------

def _read_main_class(jar_path: Path) -> str:
    with zipfile.ZipFile(jar_path) as zf:
        manifest_text = zf.read("META-INF/MANIFEST.MF").decode("utf-8")
    # Java manifests wrap long lines with a leading space on the continuation
    # line — unfold those before parsing or a long value could get truncated.
    unfolded = re.sub(r"\r?\n ", "", manifest_text)
    for line in unfolded.splitlines():
        if line.startswith("Main-Class:"):
            return line.split(":", 1)[1].strip()
    raise ProcessorError(f"No Main-Class found in {jar_path}'s manifest")


def _outputs_already_satisfied(processor: dict, subs: dict, libraries_dir: Path) -> bool:
    """Best-effort skip check via the processor's own declared 'outputs'
    (resolved path -> expected sha1). Never blocks a run — any failure here
    just means the processor runs again, which is always safe, just slower."""
    outputs = processor.get("outputs")
    if not outputs:
        return False
    try:
        for path_tmpl, sha_tmpl in outputs.items():
            path = Path(substitute(path_tmpl, subs, libraries_dir))
            expected = substitute(sha_tmpl, subs, libraries_dir)
            if not path.exists():
                return False
            if hashlib.sha1(path.read_bytes()).hexdigest() != expected:
                return False
        return True
    except Exception:
        return False


def run_processor(processor: dict, subs: dict, libraries_dir: Path, java_path: str):
    sides = processor.get("sides")
    if sides and subs["SIDE"] not in sides:
        return  # not applicable to the side being installed

    if _outputs_already_satisfied(processor, subs, libraries_dir):
        print(f"[forge_processors] already done, skipping: {processor['jar']}")
        return

    jar_path = Path(libraries_dir) / maven_coord_to_path_ext(processor["jar"])
    if not jar_path.exists():
        raise ProcessorError(
            f"Processor jar missing: {jar_path}\n"
            f"(should have been downloaded as part of install_profile.json's own "
            f"'libraries' list before running processors)"
        )

    classpath_entries = [str(jar_path)] + [
        str(Path(libraries_dir) / maven_coord_to_path_ext(c)) for c in processor.get("classpath", [])
    ]
    missing = [e for e in classpath_entries if not Path(e).exists()]
    if missing:
        raise ProcessorError(f"Processor classpath entries missing: {missing}")

    main_class = _read_main_class(jar_path)
    args = [substitute(a, subs, libraries_dir) for a in processor.get("args", [])]

    sep = ";" if core.get_os_name() == "windows" else ":"
    cmd = [java_path, "-cp", sep.join(classpath_entries), main_class] + args
    print(f"[forge_processors] running {main_class}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProcessorError(
            f"Processor failed (exit {result.returncode}): {main_class}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )


def run_all_processors(install_profile: dict, context: InstallContext, java_path: str):
    subs = context.build_substitutions(install_profile)
    processors = install_profile.get("processors", [])
    applicable = [p for p in processors if not p.get("sides") or context.side in p["sides"]]
    print(f"[forge_processors] {len(applicable)}/{len(processors)} processors apply to "
          f"side='{context.side}'")
    for i, processor in enumerate(applicable, 1):
        print(f"[forge_processors] ({i}/{len(applicable)}) {processor['jar']}")
        run_processor(processor, subs, context.libraries_dir, java_path)
