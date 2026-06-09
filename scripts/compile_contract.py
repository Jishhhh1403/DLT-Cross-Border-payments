"""Compile DepositToken and write contracts/build/DepositToken.json"""

import json
from pathlib import Path

from solcx import compile_files, install_solc, set_solc_version

ROOT = Path(__file__).resolve().parents[1]
SOL = ROOT / "contracts" / "DepositToken.sol"
OUT = ROOT / "contracts" / "build" / "DepositToken.json"
NODE_MODULES = ROOT / "contracts" / "node_modules"


def main() -> None:
    try:
        set_solc_version("0.8.24")
    except Exception:
        install_solc("0.8.24")
        set_solc_version("0.8.24")

    allow_paths = str(ROOT / "contracts")
    if NODE_MODULES.exists():
        allow_paths += ";" + str(NODE_MODULES)

    base_path = str(ROOT / "contracts")
    include_path = str(NODE_MODULES)
    compiled = compile_files(
        [str(SOL)],
        output_values=["abi", "bin"],
        solc_version="0.8.24",
        evm_version="paris",
        base_path=base_path,
        include_path=include_path,
    )
    key = next(k for k in compiled if k.endswith(":DepositToken"))
    artifact = compiled[key]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"abi": artifact["abi"], "bin": artifact["bin"]}, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
