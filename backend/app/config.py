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
    bob_private_key: str = ""
    alice_onchain_address: str = ""
    bob_onchain_address: str = ""
    contract_address_file: str = "deployed/contract_address.txt"
    contracts_dir: str = "contracts"

    db_user: str = "postgres"
    db_password: str = "postgres"
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "fiat_ledger"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def client_private_keys(self) -> dict[str, str]:
        keys = {}
        for field_name in self.model_fields:
            if field_name.endswith("_private_key") and field_name != "bank_private_key":
                client_id = field_name.removesuffix("_private_key").upper()
                val = getattr(self, field_name)
                if val:
                    keys[client_id] = val
        return keys


settings = Settings()
