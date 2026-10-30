"""Status do servidor, lido de /proc e /sys (de dentro do container também funciona).

Não precisa de acesso ao host: o kernel é compartilhado, então /proc/uptime, /proc/meminfo e
os sensores em /sys mostram o Debian inteiro. O disco é o do volume de dados (/data).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import time
from typing import Any, Mapping

from biony.core.tools import Tool, ToolDefinition, ToolResult

# Sensores de temperatura de CPU mais comuns (AMD, Intel, Raspberry Pi), em ordem de preferência.
CPU_SENSORS = ("k10temp", "zenpower", "coretemp", "cpu_thermal", "acpitz")


class ServerStatusTool(Tool):
    def __init__(self, *, disk_path: Path, proc: Path = Path("/proc"), sys: Path = Path("/sys"), started_at: float | None = None) -> None:
        self._disk = disk_path
        self._proc = proc
        self._sys = sys
        self._started_at = started_at if started_at is not None else time.time()
        self.definition = ToolDefinition(
            name="servidor_status",
            description=(
                "Mostra como está o servidor onde o Biony roda: há quanto tempo está ligado, carga da CPU, "
                "temperatura, RAM e disco. Só leitura."
            ),
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        lines = [
            self._uptime(),
            self._load(),
            self._temperature(),
            self._memory(),
            self._disk_usage(),
            f"Biony rodando há {_duration(time.time() - self._started_at)}",
        ]
        return ToolResult(True, "\n".join(lines))

    def _uptime(self) -> str:
        try:
            seconds = float(self._read(self._proc / "uptime").split()[0])
        except (OSError, ValueError, IndexError):
            return "Tempo ligado: não disponível"
        return f"Servidor ligado há {_duration(seconds)}"

    def _load(self) -> str:
        try:
            load = float(self._read(self._proc / "loadavg").split()[0])
        except (OSError, ValueError, IndexError):
            return "Carga da CPU: não disponível"
        cores = os.cpu_count() or 1
        return f"Carga da CPU: {load:.2f} em {cores} núcleo(s) (~{min(load / cores, 9.99) * 100:.0f}% ocupada, média de 1 min)"

    def _temperature(self) -> str:
        for sensor in CPU_SENSORS:
            for hwmon in sorted((self._sys / "class" / "hwmon").glob("hwmon*")):
                try:
                    if self._read(hwmon / "name").strip() != sensor:
                        continue
                    readings = [int(self._read(path)) / 1000 for path in sorted(hwmon.glob("temp*_input"))]
                except (OSError, ValueError):
                    continue
                if readings:
                    return f"Temperatura da CPU: {max(readings):.0f} °C"
        for zone in sorted((self._sys / "class" / "thermal").glob("thermal_zone*")):
            try:
                return f"Temperatura: {int(self._read(zone / 'temp')) / 1000:.0f} °C"
            except (OSError, ValueError):
                continue
        return "Temperatura da CPU: sem sensor disponível"

    def _memory(self) -> str:
        try:
            info = {}
            for line in self._read(self._proc / "meminfo").splitlines():
                key, _, value = line.partition(":")
                info[key] = int(value.split()[0]) * 1024
            total, available = info["MemTotal"], info["MemAvailable"]
        except (OSError, ValueError, KeyError, IndexError):
            return "RAM: não disponível"
        used = total - available
        return f"RAM: {_gb(used)} de {_gb(total)} em uso ({used / total * 100:.0f}%)"

    def _disk_usage(self) -> str:
        try:
            usage = shutil.disk_usage(self._disk)
        except OSError:
            return "Disco: não disponível"
        return f"Disco: {_gb(usage.used)} de {_gb(usage.total)} em uso ({usage.used / usage.total * 100:.0f}%), {_gb(usage.free)} livres"

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8")


def _gb(size: float) -> str:
    return f"{size / 1024**3:.1f} GB"


def _duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days} dia(s) e {hours} h"
    if hours:
        return f"{hours} h e {minutes} min"
    return f"{minutes} min"
