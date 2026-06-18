"""Runtime configuration — maps to institutional node credentials and chain endpoints.

This file loads connection details (like server addresses and secret keys)
from a .env file so we don't hardcode them in the code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


# The Settings class holds all the configuration values our app needs.
# It reads them from an environment file (.env) which is like a checklist of settings.
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",          # Read from the .env file
        env_file_encoding="utf-8", # Standard text encoding
        extra="ignore",            # Ignore any extra settings we don't know about
    )

    besu_rpc_url: str = "http://localhost:8545"   # Address of the blockchain node
    chain_id: int = 1337                           # Which blockchain network to use
    bank_private_key: str = ""                     # The bank's secret key (like a password)
    alice_private_key: str = ""                    # Alice's secret key
    alice_onchain_address: str = ""                # Alice's account address on the blockchain
    bob_onchain_address: str = ""                  # Bob's account address on the blockchain
    contract_address_file: str = "deployed/contract_address.txt"  # Where to save the contract address
    contracts_dir: str = "contracts"               # Folder containing the smart contract files


# Create a single global settings object that all other files can use.
settings = Settings()
