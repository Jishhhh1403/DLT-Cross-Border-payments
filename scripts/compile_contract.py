"""Compile DepositToken and write contracts/build/DepositToken.json"""

import json
from pathlib import Path

from solcx import compile_files, install_solc, set_solc_version

ROOT = Path(__file__).resolve().parents[1]
SOL = ROOT / "contracts" / "DepositToken.sol"
OUT = ROOT / "contracts" / "build" / "DepositToken.json"


def main() -> None:
    try:
        set_solc_version("0.8.24")
    except Exception:
        install_solc("0.8.24")
        set_solc_version("0.8.24")
    compiled = compile_files(
        [str(SOL)],
        output_values=["abi", "bin"],
        solc_version="0.8.24",
        evm_version="london",
    )
    key = next(k for k in compiled if k.endswith(":DepositToken"))
    artifact = compiled[key]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"abi": artifact["abi"], "bin": artifact["bin"]}, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
