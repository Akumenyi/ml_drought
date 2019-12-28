import shutil
from pathlib import Path


def get_data_path() -> Path:
    # if the working directory is alread ml_drought don't need ../data
    if Path(".").absolute().as_posix().split("/")[-1] == "ml_drought":
        data_path = Path("data")
    elif Path(".").absolute().as_posix().split("/")[-3] == "ml_drought":
        data_path = Path("../../data")
    else:
        data_path = Path("../data")
    return data_path


def _rename_directory(from_path: Path, to_path: Path) -> None:
    shutil.move(from_path, to_path)
    print(f"MOVED {from_path} to {to_path}")