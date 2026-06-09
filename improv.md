    1 # Architectural Remediation Plan
    2
    3 ## Objective
    4 Address critical architectural and security flaws identified in the `tokenized-deposit-poc`, specifically focusing
      on implementing atomic settlement via a Saga pattern, enhancing smart contract security, securing configuration
      secrets, and documenting the plan in a structured JSON format.
    5
    6 ## Key Files & Context
    7 - `backend/app/settlement.py`: Currently lacks atomicity; will be updated to use a state machine.
    8 - `backend/app/fiat_ledger.py`: Will be updated to track transaction states and support idempotency.
    9 - `backend/app/models.py`: Needs updates to include transaction state models.
   10 - `contracts/DepositToken.sol`: Single-admin setup; needs roles and circuit breakers.
   11 - `docker-compose.yml`: Contains hardcoded secrets; needs refactoring.
   12 - `improv/remediation_plan.json`: New file to be created containing a structured summary of this plan.
   13
   14 ## Proposed Solution & Implementation Steps
   15
   16 ### Phase 1: Structured Plan Documentation
   17 1.  **Create JSON Plan Summary**:
   18     -   Create a new directory named `improv/` at the project root.
   19     -   Inside it, create a `remediation_plan.json` file that programmatically describes the phases and tasks
      outlined in this remediation plan.
   20
   21 ### Phase 2: Smart Contract Security
   22 1.  **Refactor `DepositToken.sol`**:
   23     -   Replace the single `bankOperator` with a role-based access control system (`MINTER_ROLE`, `BURNER_ROLE`,
      `PAUSER_ROLE`, `ADMIN_ROLE`).
   24     -   Implement a `Pausable` mechanism to allow the `PAUSER_ROLE` to freeze token transfers and minting/burning
      in emergencies.
   25 2.  **Update Deployment**:
   26     -   Update `scripts/deploy_contract.py` to properly grant these roles during initialization.
   27
   28 ### Phase 3: Settlement Atomicity (Saga Pattern)
   29 1.  **Introduce State Tracking**:
   30     -   Update `backend/app/models.py` to include a `TransactionRecord` model with states (e.g., `PENDING`,
      `RESERVED`, `ONCHAIN_SUBMITTED`, `COMPLETED`, `FAILED`).
   31     -   Add an `idempotency_key` requirement to all settlement requests (`MintRequest`, `RedeemRequest`, etc.).
   32 2.  **Refactor `fiat_ledger.py`**:
   33     -   Implement a transaction registry to track the state of operations by their `idempotency_key`.
   34     -   Ensure operations check the registry first to prevent duplicate execution.
   35 3.  **Refactor `settlement.py` (The Saga Orchestrator)**:
   36     -   Implement the Saga flow for `mint`:
   37         1.  Record transaction as `PENDING`.
   38         2.  Attempt Fiat Reservation. If success, update to `RESERVED`; if fail, mark `FAILED` and abort.
   39         3.  Attempt On-chain Mint. If success, update to `ONCHAIN_SUBMITTED`. If fail, execute compensating
      transaction (un-reserve fiat) and mark `FAILED`.
   40         4.  Finalize Fiat Consumption and mark `COMPLETED`.
   41     -   Apply similar robust flows to `redeem` and `transfer`.
   42
   43 ### Phase 4: Infrastructure Security
   44 1.  **Secure Configurations**:
   45     -   Remove `BANK_PRIVATE_KEY` and other sensitive variables from `docker-compose.yml`.
   46     -   Introduce a `.env.example` file and update documentation to require creating a local `.env`.
   47     -   Ensure `besu/config/keys/validator.key` and any `.env` files are in `.gitignore`.
   48
   49 ## Verification
   50 -   Verify the `improv/remediation_plan.json` file exists and accurately reflects the work.
   51 -   Run the standard compilation and deployment scripts to ensure the contract updates are valid.
   52 -   Execute tests (or manual API calls via the `/docs` endpoint) simulating failed blockchain transactions to
      verify the Saga rollback logic functions correctly.
   53 -   Verify `.gitignore` prevents secrets from being tracked.