"""Runtime configuration — maps to institutional node credentials and chain endpoints."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    besu_rpc_url: str = "http://localhost:8545"
    chain_id: int = 1337
    bank_private_key: str = ""
    alice_private_key: str = ""
    alice_onchain_address: str = ""
    bob_onchain_address: str = ""
    contract_address_file: str = "deployed/contract_address.txt"
    contracts_dir: str = "contracts"


settings = Settings()
