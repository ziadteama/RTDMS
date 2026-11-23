#!/usr/bin/env bash
# Deploy a clean checkout of main to the Pi over ssh (no rsync needed on the Pi), run from the dev
# machine inside the repo. Only changed files are sent; nothing on the Pi is ever deleted.
#   RTDMS_PI_HOST=user@host deploy.sh [--ref REF] [--install [install.sh flags]] [--no-restart]
#                                      [--dry-run] [--rollback]
#   --ref REF     what to deploy (default origin/main, fetched first); only committed files
#   --install     afterwards run pi/deploy/install.sh on the Pi; the rest of the arguments go to it
#                 (e.g. --install --open)
#   --rollback    restore the newest backup (~/rtdms-pi/.bak-*) and restart
# Before every deploy the files about to change are saved in ~/rtdms-pi/.bak-<stamp>/code.tgz
# (last 5 kept). Ends with check.sh --wait 120 on the Pi; its exit code is ours.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
HOST="${RTDMS_PI_HOST:-}"
REF=origin/main DRY=0 RESTART=1 INSTALL=0 ROLLBACK=0 INSTALL_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:?host}"; shift ;;
    --ref) REF="${2:?ref}"; shift ;;
    --dry-run) DRY=1 ;;
    --no-restart) RESTART=0 ;;
    --rollback) ROLLBACK=1 ;;
    --install) INSTALL=1; shift; INSTALL_ARGS=("$@"); break ;;
    *) echo "usage: RTDMS_PI_HOST=user@host $0 [--ref REF] [--install [flags]] [--no-restart] [--dry-run] [--rollback]" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$HOST" ] || { echo "deploy: set RTDMS_PI_HOST=user@host (or --host)" >&2; exit 2; }
SSH=(ssh -o BatchMode=yes "$HOST")
say() { echo "deploy: $*"; }
check() { "$HERE/check.sh" --ssh "$HOST" --wait "${1:-120}"; }

if [ "$ROLLBACK" = 1 ]; then
  say "rollback to the newest backup"
  # shellcheck disable=SC2016
  "${SSH[@]}" 'set -e; b=$(ls -d ~/rtdms-pi/.bak-* 2>/dev/null | sort | tail -1); [ -n "$b" ] && [ -f "$b/code.tgz" ] || { echo "no backup"; exit 1; }
    echo "restoring $b"; tar xzf "$b/code.tgz" -C ~; systemctl --user restart rtdms-pi-user'
  check 120; exit $?
fi

[ "$REF" != origin/main ] || git -C "$REPO" fetch -q origin main
SHA="$(git -C "$REPO" rev-parse --short "$REF")"
SRC="$(mktemp -d)"; trap 'rm -rf "$SRC"' EXIT
git -C "$REPO" archive "$REF" | tar x -C "$SRC"
say "ref $REF ($SHA) -> $HOST"

# NOT deployed: distraction configs/ (the Pi has its own Pi-bundle pipeline.yaml: INT8 detector, LiteRT
# face mesh, pose every 6th frame) and profiles/ (the driver's calibration).
# tree <remote base> <local base in the checkout> <path>...   (relative to the local base)
CHANGED_LIST="$(mktemp)"; trap 'rm -rf "$SRC" "$CHANGED_LIST"' EXIT
tree() {
  local rbase="$1" lbase="$2"; shift 2
  local list; list="$(cd "$SRC/$lbase" && find "$@" -type f ! -name '*.pyc' ! -path '*__pycache__*' | sort)"
  local lm rm
  lm="$(cd "$SRC/$lbase" && printf '%s\n' "$list" | xargs -d '\n' md5sum)"
  rm="$(printf '%s\n' "$list" | "${SSH[@]}" "cd $rbase 2>/dev/null && xargs -d '\n' md5sum 2>/dev/null" || true)"
  # differing or missing files -> relative path under the remote base
  { diff <(echo "$rm" | sort -k2) <(echo "$lm" | sort -k2) || true; } | sed -n 's/^> [0-9a-f]\{32\}  //p' |
    while read -r f; do echo "$rbase|$lbase|$f"; done >>"$CHANGED_LIST"
}
tree rtdms-pi . pi/src pi/pyproject.toml pi/deploy fusion/src fusion/pyproject.toml \
  models/physiology/src models/physiology/models models/physiology/pyproject.toml contracts
tree rtdms/distraction models/distraction src scripts/stream.py scripts/hybrid.py scripts/hybrid_alerts.py scripts/drowsiness.py scripts/run.py scripts/held_live.py pyproject.toml \
  models/action_v2 models/held_v1 models/det_v2d_ir_512_ncnn_model models/det_v2d_ir_512_det_aciq_mixed_ncnn_model \
  models/yolo26n_pose_320_ncnn_model
tree rtdms/face models/face src models/face_landmarker.task
N="$(wc -l <"$CHANGED_LIST")"
say "$N file(s) differ from the Pi"
if [ "$DRY" = 1 ]; then awk -F'|' '{print "  " $1 "/" $3}' "$CHANGED_LIST" | head -50; exit 0; fi

if [ "$N" -gt 0 ]; then
  STAMP="$(date +%Y%m%d-%H%M%S)"
  say "backup ~/rtdms-pi/.bak-$STAMP/code.tgz"
  "${SSH[@]}" "set -e; mkdir -p ~/rtdms-pi/.bak-$STAMP; cd ~; p=''
    for d in rtdms-pi/pi/src rtdms-pi/pi/deploy rtdms-pi/fusion/src rtdms-pi/models/physiology/src rtdms-pi/contracts \
             rtdms/distraction/src rtdms/distraction/scripts rtdms/face/src; do
      [ -e \$d ] && p=\"\$p \$d\"; done
    tar czf ~/rtdms-pi/.bak-$STAMP/code.tgz \$p
    ls -dt ~/rtdms-pi/.bak-* | tail -n +6 | xargs -r rm -rf"
  while IFS='|' read -r rbase lbase f; do
    printf '%s\0' "$rbase|$lbase|$f"
  done <"$CHANGED_LIST" | python3 -c '
import sys, subprocess, tarfile, io, os
src, host = sys.argv[1], sys.argv[2]
groups = {}
for rec in sys.stdin.buffer.read().split(b"\0"):
    if rec:
        rb, lb, f = rec.decode().split("|", 2)
        groups.setdefault((rb, lb), []).append(f)
for (rb, lb), files in groups.items():
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", host, f"mkdir -p {rb} && tar xzf - -C {rb}"], stdin=subprocess.PIPE)
    with tarfile.open(fileobj=p.stdin, mode="w|gz") as t:
        for f in files:
            t.add(os.path.join(src, lb, f), arcname=f)
    p.stdin.close()
    if p.wait():
        sys.exit("upload failed for " + rb)
    print(f"deploy: sent {len(files)} file(s) to {rb}")
' "$SRC" "$HOST"
fi

if [ "$INSTALL" = 1 ]; then
  say "install.sh ${INSTALL_ARGS[*]:-}"
  "${SSH[@]}" "bash ~/rtdms-pi/pi/deploy/install.sh ${INSTALL_ARGS[*]:-}"
elif [ "$RESTART" = 1 ] && [ "$N" -gt 0 ]; then
  say "restart rtdms-pi-user"
  "${SSH[@]}" 'systemctl --user restart rtdms-pi-user'
fi
check 120
