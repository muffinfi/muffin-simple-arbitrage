import json
import os
from os import path
from pathlib import Path
from typing import TypedDict
from dotenv import dotenv_values
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
from flashbots import Flashbots, flashbot
from web3 import Web3


class Env:
    """
    Get environment variables.
    Precendence:
    1.  os.environ
    2.  values from .env.production
    3.  values from .env
    """
    _root_dir = Path(__file__).parent.parent
    _env = dotenv_values(_root_dir / '.env')
    _env_prod = dotenv_values(_root_dir / '.env.production')

    @classmethod
    def get_env_nullable(cls, key: str):
        return os.environ.get(key, cls._env_prod.get(key, cls._env.get(key, None)))

    @classmethod
    def get_env(cls, key: str) -> str:
        value = cls.get_env_nullable(key)
        assert value is not None, f'Missing env var: {key}'
        return value


# ---------- network ----------

NETWORK = 'mainnet'


# ---------- rpc and account keys ----------

if NETWORK == 'mainnet':
    WEBSOCKET_PROVIDER_URI = Env.get_env('WEBSOCKET_PROVIDER_URI')
    ACCOUNT_TX_SENDER_KEY = Env.get_env('ACCOUNT_TX_SENDER_KEY')
    ACCOUNT_FLASHBOT_SIGNER_KEY = Env.get_env('ACCOUNT_FLASHBOT_SIGNER_KEY')
    USE_FLASH_BOT = True

elif NETWORK == 'goerli':
    WEBSOCKET_PROVIDER_URI = Env.get_env('GOERLI_WEBSOCKET_PROVIDER_URI')
    ACCOUNT_TX_SENDER_KEY = Env.get_env('GOERLI_ACCOUNT_TX_SENDER_KEY')
    ACCOUNT_FLASHBOT_SIGNER_KEY = Env.get_env('GOERLI_ACCOUNT_FLASHBOT_SIGNER_KEY')
    USE_FLASH_BOT = True

elif NETWORK == 'rinkeby':
    WEBSOCKET_PROVIDER_URI = Env.get_env('RINKEBY_WEBSOCKET_PROVIDER_URI')
    ACCOUNT_TX_SENDER_KEY = Env.get_env('RINKEBY_ACCOUNT_TX_SENDER_KEY')
    ACCOUNT_FLASHBOT_SIGNER_KEY = Env.get_env('RINKEBY_ACCOUNT_FLASHBOT_SIGNER_KEY')
    USE_FLASH_BOT = False

else:
    raise Exception('unknown network')


# ---------- contract addresses ----------

if NETWORK == 'mainnet':
    HUB_ADDRESS = '0x6690384822afF0B65fE0C21a809F187F5c3fcdd8'
    ARBITRAGEUR_ADDRESS = Env.get_env('ARBITRAGEUR_ADDRESS')

elif NETWORK == 'goerli':
    HUB_ADDRESS = '0xA06c455D19704E4871c547211504e17E2199308D'
    ARBITRAGEUR_ADDRESS = Env.get_env('GOERLI_ARBITRAGEUR_ADDRESS')

elif NETWORK == 'rinkeby':
    HUB_ADDRESS = '0x42789c4D6c5Cc9334fef4da662A57D78771Ce9E5'
    ARBITRAGEUR_ADDRESS = Env.get_env('RINKEBY_ARBITRAGEUR_ADDRESS')

else:
    raise Exception('unknown network')


# ---------- external markets ----------

class UniV2MarketInfo(TypedDict):
    factory_address:    str
    init_code_hash:     str
    name:               str  # used for logging


if NETWORK == 'mainnet':
    UNIV2_MARKETS: list[UniV2MarketInfo] = [{
        'name': 'UniswapV2',
        'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
        'init_code_hash': '96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f',
    }, {
        'name': 'SushiSwap',
        'factory_address': '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',
        'init_code_hash': 'e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303',
    }]

elif NETWORK == 'goerli':
    UNIV2_MARKETS: list[UniV2MarketInfo] = [{
        'name': 'UniswapV2',
        'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
        'init_code_hash': '96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f',
    }]

elif NETWORK == 'rinkeby':
    UNIV2_MARKETS: list[UniV2MarketInfo] = [{
        'name': 'UniswapV2',
        'factory_address': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
        'init_code_hash': '96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f',
    }]

else:
    raise Exception('unknown network')


# ---------- token addresses ----------


if NETWORK == 'mainnet':
    ETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
    USDC_ADDRESS = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
    TOKEN_ADDRESSES = [
        ETH_ADDRESS,
        USDC_ADDRESS,
        '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',  # WBTC
        '0xdAC17F958D2ee523a2206206994597C13D831ec7',  # USDT
    ]

elif NETWORK == 'goerli':
    ETH_ADDRESS = '0x2C03fF2a384b5CbB93998be296adE0Ed2d9E60f9'  # teth
    USDC_ADDRESS = '0xb6136C36610d4d5374030AC0Ec0021fB1F04aaAa'
    TOKEN_ADDRESSES = [
        ETH_ADDRESS,
        USDC_ADDRESS,
    ]

elif NETWORK == 'rinkeby':
    ETH_ADDRESS = '0x15e4F1fc9a02e36039554531cDdF1C70F0B05364'  # teth
    USDC_ADDRESS = '0xC6399e9E8D6d70A2aA1fc6ade21F56567f6c7862'
    TOKEN_ADDRESSES = [
        ETH_ADDRESS,
        USDC_ADDRESS,
        '0x0C58e68883E8c6390255A83a73dfA42b56EC6400',  # WBTC
        '0xC6399e9E8D6d70A2aA1fc6ade21F56567f6c7862',  # USDC
        '0x7C4e4edc8Cda71DfaB107a1A44f6858f36857cA8',  # DAI
    ]

else:
    raise Exception('unknown network')


# ---------- miscellaneous ----------

BRIBE_PERCENTAGE_POST_BASE_FEE = int(Env.get_env_nullable('BRIBE_PERCENTAGE_POST_BASE_FEE') or 80)
CMC_PRO_API_KEY = Env.get_env_nullable('CMC_PRO_API_KEY') or ''

ERROR_LOG_FILE = Env._root_dir / 'error.log'


# ---------- construct w3 ----------

tx_sender: LocalAccount = Account.from_key(ACCOUNT_TX_SENDER_KEY)
flashbot_signer: LocalAccount = Account.from_key(ACCOUNT_FLASHBOT_SIGNER_KEY)

# web3 provider for normal tx
w3 = Web3(Web3.WebsocketProvider(WEBSOCKET_PROVIDER_URI))

# inject flashbots module to w3
if NETWORK == 'mainnet':
    flashbot(w3, flashbot_signer)
else:
    flashbot(w3, flashbot_signer, "https://relay-goerli.flashbots.net")


w3_flashbots: Flashbots
w3_flashbots = w3.flashbots  # type: ignore


# ---------- contracts and interfaces ----------


with open(path.join(path.dirname(__file__), './artifacts/IMuffinHubCombined.json'), 'r') as f:
    hub_contract = w3.eth.contract(
        address=Web3.toChecksumAddress(HUB_ADDRESS),
        abi=json.load(f)['abi'],
    )


with open(path.join(path.dirname(__file__), './artifacts/Arbitrageur4.json'), 'r') as f:
    arber_contract = w3.eth.contract(
        address=Web3.toChecksumAddress(ARBITRAGEUR_ADDRESS),
        abi=json.load(f)['abi'],
    )


with open(path.join(path.dirname(__file__), './artifacts/IUniswapV2Pair.json'), 'r') as f:
    univ2_interface = w3.eth.contract(
        address=None,
        abi=json.load(f)['abi'],
    )


with open(path.join(path.dirname(__file__), './artifacts/IERC20.json'), 'r') as f:
    erc20_interface = w3.eth.contract(
        address=None,
        abi=json.load(f)['abi'],
    )
