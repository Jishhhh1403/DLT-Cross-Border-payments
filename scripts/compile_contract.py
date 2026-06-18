"""
Compile the DepositToken smart contract and save the result as a JSON file.

This takes the human-readable Solidity code (DepositToken.sol) and compiles it
into something the blockchain can understand: the ABI (interface description)
and the bytecode (machine-readable code). The output is saved to contracts/build/DepositToken.json.
"""

import json
from pathlib import Path

from solcx import compile_files, install_solc, set_solc_version

ROOT = Path(__file__).resolve().parents[1]   # The project root folder
SOL = ROOT / "contracts" / "DepositToken.sol"                    # The input Solidity source file
OUT = ROOT / "contracts" / "build" / "DepositToken.json"         # Where to save the compiled output
NODE_MODULES = ROOT / "contracts" / "node_modules"               # OpenZeppelin library files


# The main compilation process.
def main() -> None:
    # Make sure we have the right Solidity compiler version (0.8.24).
    try:
        set_solc_version("0.8.24")
    except Exception:
        install_solc("0.8.24")
        set_solc_version("0.8.24")

    # Tell the compiler where to find imported files (like OpenZeppelin).
    allow_paths = str(ROOT / "contracts")
    if NODE_MODULES.exists():
        allow_paths += ";" + str(NODE_MODULES)

    base_path = str(ROOT / "contracts")
    include_path = str(NODE_MODULES)
    # Run the compiler.
    compiled = compile_files(
        [str(SOL)],
        output_values=["abi", "bin"],
        solc_version="0.8.24",
        evm_version="paris",
        base_path=base_path,
        include_path=include_path,
    )
    # Find the DepositToken contract in the compiled output.
    key = next(k for k in compiled if k.endswith(":DepositToken"))
    artifact = compiled[key]
    # Create the output folder if needed and save the compiled contract.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"abi": artifact["abi"], "bin": artifact["bin"]}, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
