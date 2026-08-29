#!/usr/bin/env bash
# One-command hardware verification for the physiology subsystem.
#
#   tools/verify_on_pi.sh [host]
#
# Syncs this checkout to the Pi and runs every gate that needs real hardware.
# Everything it prints is hardware evidence; everything measured elsewhere is not.
set -uo pipefail

HOST="${1:-192.168.100.181}"
KEY="${PI_KEY:-$HOME/.ssh/id_ed25519}"
USER_NAME="${PI_USER:-khalifa}"
REMOTE="$USER_NAME@$HOST"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$REMOTE")
ENVV="export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1"

echo "== reachability =="
"${SSH[@]}" "echo ok" >/dev/null 2>&1 || {
  echo "UNREACHABLE at $HOST."
  echo "  Try the Tailscale address:  tools/verify_on_pi.sh 100.113.107.122"
  echo "  If ping works but port 22 does not, sshd is down - needs physical access."
  exit 1
}
echo "reachable"

echo "== environment (record with every result) =="
"${SSH[@]}" "hostname; uname -m; python3 --version; \
  echo -n 'governor: '; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor; \
  echo -n 'clock: '; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq; \
  echo -n 'temp: '; vcgencmd measure_temp; \
  echo -n 'throttled: '; vcgencmd get_throttled; \
  echo -n 'boot device: '; findmnt -no SOURCE /"

echo "== sync =="
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' -cf - \
    src tests tools configs pyproject.toml .data 2>/dev/null \
  | "${SSH[@]}" "rm -rf ~/dms/hil && mkdir -p ~/dms/hil && tar -xf - -C ~/dms/hil"

echo "== gate =="
"${SSH[@]}" "cd ~/dms/hil && $ENVV && export PYTHONPATH=\$HOME/dms/hil/src && \
  ~/dms/venv/bin/python -m pytest -q 2>&1 | tail -3 && \
  ~/dms/venv/bin/python -m ruff check . 2>&1 | tail -2 && \
  ~/dms/venv/bin/python -m mypy src 2>&1 | tail -2"

echo "== BIDMC (baseline 0.5082470420003504, 420 outputs) =="
"${SSH[@]}" "cd ~/dms/hil && $ENVV && export PYTHONPATH=\$HOME/dms/hil/src && \
  ~/dms/venv/bin/python tools/validate_bidmc.py .data/bidmc_01_Signals.csv .data/bidmc_01_Numerics.csv 2>&1 \
  | grep -E 'hr_mae|p95|evaluated'"

echo "== CPU and RSS, MTU sweep (the open question) =="
"${SSH[@]}" "cd ~/dms/hil && $ENVV && export PYTHONPATH=\$HOME/dms/hil/src && ~/dms/venv/bin/python - <<'PY'
import asyncio, time
from dms_physiology.acquisition import ReplaySource
from dms_physiology.fusion import InMemorySink
from dms_physiology.service import PhysiologyService
from dms_physiology.types import PpgFrame
from dms_physiology.waveform import WaveformConfig, generate_ppg

def rss():
    for l in open('/proc/self/status'):
        if l.startswith('VmRSS'): return int(l.split()[1])/1024
    return 0.0

async def main():
    print(f\"  {'config':<22}{'CPU %core':>10}{'peak RSS':>11}\")
    for b, label in ((3,'batch=3 (ATT MTU 23)'), (20,'batch=20'), (79,'batch=79 (MTU 247)')):
        cfg = WaveformConfig(seconds=120.0, batch_size=b, seed=5)
        frs = [PpgFrame(packet=p, sample_rate_hz=100, received_at_seconds=0.0)
               for p, _ in generate_ppg(cfg)]
        s = InMemorySink()
        t = time.process_time()
        await PhysiologyService(ReplaySource(frs), s).run()
        cpu = time.process_time() - t
        print(f'  {label:<22}{100*cpu/120:9.2f}%{rss():10.1f}MB')
    print()
    print('  gates: CPU <1% target / <2% hard, RSS 120MB target / 150MB hard')
asyncio.run(main())
PY"

echo "== thermal after load =="
"${SSH[@]}" "vcgencmd measure_temp; vcgencmd get_throttled; \
  echo -n 'clock: '; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
echo
echo "Non-zero 'throttled' invalidates the CPU numbers above (VALIDATION.md:122)."
