"""Download WESAD wrist BVP + quest/tags from Hugging Face (no 2GB Sciebo zip)."""

from __future__ import annotations

from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "Rabbit-bot/prism_daatset"
SUBJECTS = [f"S{i}" for i in range(2, 18) if i != 12]
OUT = Path(__file__).resolve().parents[1] / "data" / "hf_wesad"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    import zipfile

    for sid in SUBJECTS:
        quest_rel = f"WESAD/{sid}/{sid}_quest.csv"
        zip_rel = f"WESAD/{sid}/{sid}_E4_Data.zip"
        quest = hf_hub_download(
            repo_id=REPO, repo_type="dataset", filename=quest_rel, local_dir=str(OUT)
        )
        zpath = hf_hub_download(
            repo_id=REPO, repo_type="dataset", filename=zip_rel, local_dir=str(OUT)
        )
        dest = OUT / "WESAD" / sid / f"{sid}_E4_Data"
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(dest)
        bvp = dest / "BVP.csv"
        if not bvp.exists():
            # some zips nest one extra folder
            matches = list(dest.rglob("BVP.csv"))
            if not matches:
                raise FileNotFoundError(f"no BVP.csv in {zpath}")
            bvp = matches[0]
        print(sid, Path(quest).stat().st_size, bvp.stat().st_size, bvp)
    print("done", OUT)


if __name__ == "__main__":
    main()
