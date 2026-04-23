import subprocess
import sys


def test_tasks_all_help_has_leverage_sweep_flag():
    cp = subprocess.run([sys.executable, "scripts/tasks.py", "all", "--help"], capture_output=True, text=True)
    assert cp.returncode == 0
    assert "--leverage-sweep" in cp.stdout
