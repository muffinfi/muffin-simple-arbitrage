# muffin-simple-arbitrage

An example of evaluating arbitrage opportunities between Muffin and other UNIv2 markets (e.g. UniswapV2, SushiSwap) and submitting arbitrage transactions using Flashbots.

This script is a simple and naive arbitrage bot that is meant to demostrate one of many ways to do arbitrage on Muffin. As this bot is publicly available to everyone, it is unlikely for this bot to stay competitive and profitable. We see this bot as a starter pack for searchers to reference or iterate on.

## Installation

1.  Install python >=3.9.
2.  Git-clone this project to your machine.
3.  Install dependencies.
    ```bash
    pip install -r requirements.txt
    ```

## Preparation

1.  Generate a private key for your bot wallet.
2.  Generate another private key for signing transaction for flashbots bundle.
3.  Prepare an Ethereum RPC endpoint from Alchemy.
4.  Prepare some ETH in your bot wallet to pay gas for deploying contract and for later doing arbitrage.
5.  Deploy the included Arbitrage4.sol to Ethereum.

    ```bash
    RPC_URL="https://..."       # Ethereum RPC endpoint
    OWNER_ADDRESS="0x..."       # your bot wallet address
    EXECUTOR_ADDRESS="0x..."    # your bot wallet address
    HUB_ADDRESS="0x6690384822afF0B65fE0C21a809F187F5c3fcdd8"
    WETH_ADDRESS="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

    forge create Arbitrageur4 \
        --root ./muffin_arb_contracts \
        --rpc-url=$RPC_URL \
        --constructor-args "$HUB_ADDRESS" "$WETH_ADDRESS" "$OWNER_ADDRESS" "$EXECUTOR_ADDRESS"
    ```

6.  Complete the .env file.
    - **WEBSOCKET_PROVIDER_URI:** Ethereum websocket RPC endpoint.
    - **ACCOUNT_TX_SENDER_KEY:** Your bot wallet private key.
    - **ACCOUNT_FLASHBOT_SIGNER_KEY:** Private key to sign flashbots transaction paylod.
    - **ARBITRAGEUR_ADDRESS:** The Arbitrage4.sol contract address you deployed.
    - **BRIBE_PERCENTAGE_POST_BASE_FEE:** Percentage of profit you'll give to miner.

## Usage

### Start the bot:

```bash
python main.py
```

### Take WETH from the Arbitrage4.sol contract

```python
from muffin_arb.arbitrage import take_token
take_token()
```

## What it does?

For every new block, the bot does:

1.  Fetch all specified ETH-token pairs from Muffin, UniswapV2 and SushiSwap (specified in settings.py).
2.  For each token pair, evaluate if there is an profitable arbitrage opportunity between Muffin and an UNIv2 market. The bot only takes profit in ETH.
3.  Sort the arb opportunities by their estimated profits.
4.  Submit the most profitable arb using Flashbots endpoint.
5.  After a successful arb, the profit (WETH) stays in the Arbitrage4.sol contract. You can take it to your own wallet anytime.

## Notable files

```bash
.
├── muffin_arb
│   ├── arbitrage.py                # Construct and send arbitrage transaction
│   ├── evaluate.py                 # Evaluate arbitrage opportunities
│   ├── main.py                     # Entry point. Run the whole arb process
│   ├── market.py                   # Fetch market's state and implement swap logics
│   ├── settings.py                 # Store constants and keys used in this project
│   ├── token.py                    # Fetch token's info
│   └── impl
│       └── int
│           └── pool_int.py         # Muffin's swap logic implementation
├── muffin_arb_contracts
│   ├── foundry.toml                # Foundry config
│   └── src
│       ├── Arbitrageur4.sol        # The contract we use to perform atomic arbitrage
│       ├── Auth.sol                # Abstract contract inherited by Arbitrageur4.sol
│       └── Multicall.sol           # Abstract contract inherited by Arbitrageur4.sol
├── .env                            # Keys for this project
├── main.py                         # Your cli entry point
└── requirements.txt                # This project's dependencies
```

## Possible improvement

Here are some ideas to improve the bot, but we do not have a roadmap to implement them.

- Implement arbitrage with UNIv3 and Curve
- Send more than one arb at once
- Specify which tiers to use when swapping on Muffin
- Gas-optimize the arbitrageur contract
- Take profits in other tokens besides ETH
- Implement triangular arbs
- Implement CEX-DEX arb


## Disclaimer

The smart contract and the scripts in this repository are not audited. Use at your own risk.
