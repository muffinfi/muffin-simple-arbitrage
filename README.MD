# muffin-simple-arbitrage

An example of evaluating arbitrage opportunities between Muffin and UNI v2, and submitting arbitrage transactions using Flashbots.

This script is a simple, non-production-grade arbitrage bot, which is meant to showcase one of many ways to do arbitrage on Muffin.

## Installation

1.  Install python >=3.9.
2.  Install this project's dependencies.
    ```bash
    gh repo clone muffinfi/muffin-simple-arbitrage
    cd muffin-simple-arbitrage
    pip install -r requirements.txt
    ```

## Preparation

1.  Generate a private key for your bot wallet.
2.  Generate another private key for signing transaction for flashbots bundle.
3.  Deploy the included Arbitrage4.sol to Ethereum.
    ```bash
    forge create Arbitrageur4 \
        --root ./muffin_arb_contracts \
        --constructor-args "$HUB_ADDRESS" "$WETH_ADDRESS" "$OWNER_ADDRESS" "$EXECUTOR_ADDRESS"
    ```
4.  Complete the .env file.
    - **WEBSOCKET_PROVIDER_URI:** Ethereum websocket RPC endpoint.
    - **ACCOUNT_TX_SENDER_KEY:** Bot wallet private key.
    - **ACCOUNT_FLASHBOT_SIGNER_KEY:** Private key to sign flashbots transaction paylod.
    - **ARBITRAGEUR_ADDRESS:** The Arbitrage4.sol contract address you deployed.
    - **BRIBE_PERCENTAGE_POST_BASE_FEE:** Percentage of profit you'll give to miner.

## Usage

```bash
python main.py
```

## What it does?

For every new block, the bot does:

1.  Fetch all specified ETH pairs from Muffin and UNI v2 (specified in settings.py).
2.  For each token pair, evaluate if there is an atomic arb opportunity between Muffin and UNI v2.
3.  Sort the arb opportunities by their estimated profits.
4.  Submit the most profitable arb using Flashbots endpoint.
