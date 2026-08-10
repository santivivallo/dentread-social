#!/usr/bin/env python3
"""
Busca secretos en los archivos versionados antes de exponer el repo.

Existe por un caso real: `SETUP-CREDENCIALES.md` traía la clave Fernet
escrita en texto plano y estuvo a un comando de quedar pública. Un secreto
en un `.md` no lo atrapa `.gitignore`, que solo protege `.env`.

    python -m tools.scan_secrets          # antes de cada push importante

Devuelve 1 si encuentra algo. Pensado para correr también en CI.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Cada patrón describe una credencial concreta, no "algo que parece random":
# un umbral genérico de entropía marca hashes, IDs y rutas, y a los tres
# falsos positivos nadie vuelve a mirar la salida.
PATTERNS: list[tuple[str, str]] = [
    ("clave Fernet", r"\b[A-Za-z0-9_-]{43}=(?![A-Za-z0-9_=-])"),
    ("token de Meta", r"\bEAA[A-Za-z0-9]{40,}"),
    ("access key de AWS/R2", r"\bAKIA[0-9A-Z]{16}\b"),
    ("secret de 32 hex (app secret)", r"(?i)secret\S{0,20}[=:]\s*[0-9a-f]{32}\b"),
    ("clave privada", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("token de GitHub", r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    ("URL con credenciales", r"://[^/\s:@]+:[^/\s:@]+@"),
]

# `.env.example` documenta los nombres de las variables, no sus valores.
SKIP = {".env.example"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return [Path(p) for p in out.stdout.split("\n") if p]


def main() -> int:
    hits: list[str] = []
    for path in tracked_files():
        if path.name in SKIP or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                      # binarios: logos, fuentes
        for label, pattern in PATTERNS:
            for m in re.finditer(pattern, text):
                line = text[:m.start()].count("\n") + 1
                hits.append(f"  {path}:{line}  {label}")

    if hits:
        print(f"✗ {len(hits)} posible(s) secreto(s) en archivos versionados:\n")
        print("\n".join(hits))
        print("\nSacalos antes de hacer público el repo. Si alguno ya se pusheó,"
              "\nno alcanza con borrarlo: rotá la credencial.")
        return 1

    print(f"✓ sin secretos en {len(tracked_files())} archivos versionados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
