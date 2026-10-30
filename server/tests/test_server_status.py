from __future__ import annotations

import time

import pytest

from biony.tools.server_status import ServerStatusTool, _duration

pytestmark = pytest.mark.anyio


def fake_system(root):
    proc, sys = root / "proc", root / "sys"
    proc.mkdir()
    (proc / "uptime").write_text("273600.5 500000.0\n")  # 3 dias e 4 h
    (proc / "loadavg").write_text("1.00 0.80 0.70 1/300 1234\n")
    (proc / "meminfo").write_text("MemTotal:  8000000 kB\nMemFree: 100 kB\nMemAvailable:  6000000 kB\n")
    other = sys / "class" / "hwmon" / "hwmon0"
    other.mkdir(parents=True)
    (other / "name").write_text("nvme\n")
    (other / "temp1_input").write_text("70000\n")
    cpu = sys / "class" / "hwmon" / "hwmon1"
    cpu.mkdir()
    (cpu / "name").write_text("k10temp\n")
    (cpu / "temp1_input").write_text("51250\n")
    (cpu / "temp2_input").write_text("48000\n")
    return proc, sys


async def test_status_reads_proc_and_sys(tmp_path):
    proc, sys = fake_system(tmp_path)
    tool = ServerStatusTool(disk_path=tmp_path, proc=proc, sys=sys, started_at=time.time() - 3600)

    status = (await tool.execute({})).content

    assert "Servidor ligado há 3 dia(s) e 4 h" in status
    assert "Carga da CPU: 1.00" in status
    assert "Temperatura da CPU: 51 °C" in status  # o sensor da CPU, não o do SSD
    assert "RAM: 1.9 GB de 7.6 GB em uso (25%)" in status
    assert "Disco:" in status and "livres" in status
    assert "Biony rodando há 1 h e 0 min" in status


async def test_missing_files_are_reported_not_raised(tmp_path):
    tool = ServerStatusTool(disk_path=tmp_path / "nada", proc=tmp_path / "proc", sys=tmp_path / "sys")

    result = await tool.execute({})

    assert result.ok
    for item in ("Tempo ligado", "Carga da CPU", "Temperatura da CPU: sem sensor", "RAM", "Disco"):
        assert item in result.content


def test_duration():
    assert _duration(59) == "0 min"
    assert _duration(3 * 3600 + 120) == "3 h e 2 min"
    assert _duration(2 * 86400 + 5 * 3600) == "2 dia(s) e 5 h"
