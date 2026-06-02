"""Runtime configuration — maps to institutional node credentials and chain endpoints."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    besu_rpc_url: str = "http://localhost:8545"
    chain_id: int = 1337
    bank_private_key: str = "0x1111111111111111111111111111111111111111111111111111111111111111"
    alice_onchain_address: str = "0x1563915e194D8CfBA1943570603F7606A3115508"
    bob_onchain_address: str = "0x5CbDd86a2FA8Dc4bDdd8a8f69dBa48572EeC07FB"
    contract_address_file: str = "deployed/contract_address.txt"
    contracts_dir: str = "contracts"


settings = Settings()
