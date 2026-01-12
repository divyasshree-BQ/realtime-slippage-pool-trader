# Trading Bot using Real-time Slippage on Ethereum, Arbitrum, Base, BSC

An automated trading bot that executes real-time trades on Uniswap V2 and V3 DEX pools using live slippage data from Bitquery. The bot analyzes liquidity depth, determines optimal trade directions, and automatically opens and closes positions based on market conditions.

## ⚠️ WARNING

**This bot executes REAL trades with REAL funds on the Ethereum mainnet. Use at your own risk. Always test thoroughly and start with small amounts.**

## Features

- **Real-time DEX Pool Monitoring**: Subscribes to Bitquery Kafka stream for live DEX pool events
- **Dynamic Direction Selection**: Automatically determines optimal trade direction (AtoB or BtoA) based on liquidity depth analysis
- **Multi-Protocol Support**: Supports Uniswap V2 and V3 protocols
- **Intelligent Slippage Management**: Uses median slippage from stream data with configurable fallbacks
- **Automatic Position Management**: Opens positions and automatically closes them after a specified number of blocks
- **Gas Price Optimization**: Extracts gas prices from stream data for optimal transaction costs
- **Comprehensive Logging**: Detailed trade execution logs with transaction hashes, amounts, and prices

## Architecture

### Core Components

1. **BitqueryStream** (`stream.py`): Kafka consumer that subscribes to Bitquery DEX pool events
2. **DEXTrader** (`trader.py`): Handles trade execution on Uniswap V2/V3
3. **TradingStrategy** (`trade.py`): Implements trading logic, position management, and decision-making
4. **Uniswap Swappers** (`uniswap/`): Protocol-specific swap execution logic
5. **Utilities** (`utils/`): Helper functions for prices, gas, tokens, balances, and conversions

### Trading Flow

1. **Stream Processing**: Receives DEX pool events from Bitquery Kafka stream
2. **Liquidity Analysis**: Analyzes pool liquidity and determines best trade direction
3. **Trade Execution**: Executes swap on Uniswap with optimal slippage and gas settings
4. **Position Tracking**: Tracks open positions and automatically closes them after N blocks
5. **Statistics**: Maintains trade statistics and success rates

## Setup

### Prerequisites

- Python 3.8+
- Ethereum wallet with ETH for gas fees
- [Bitquery](https://bitquery.io/) stream credentials. Contact team via their telegram or fill the form on their website.
- Ethereum RPC endpoint (Infura, Alchemy, etc.)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/divyasshree-BQ/realtime-slippage-pool-trader
cd realtime-slippage-pool-trader
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root:
```env
PRIVATE_KEY=your_private_key_here
RPC_URL=https://mainnet.infura.io/v3/your_project_id
```

4. Configure Bitquery credentials in `config.py`:
```python
eth_username = "your_bitquery_username"
eth_password = "your_bitquery_password"
```

## Configuration

### Environment Variables

- `PRIVATE_KEY`: Your Ethereum wallet private key (required)
- `RPC_URL`: Ethereum RPC endpoint URL (optional, but recommended)

### Trading Parameters

Edit `trade.py` to customize trading behavior:

```python
run_trading(
    topic='eth.dexpools.proto',      # Kafka topic
    trade_amount=0.0001,              # Amount per trade (in ETH/token units)
    slippage_bps=50,                  # Default slippage in basis points
    min_profit_threshold=0.0,         # Minimum profit threshold
    max_trades=None,                  # Maximum trades (None for unlimited)
    stats_interval=100,               # Print stats every N events
    close_blocks=3                    # Blocks to wait before closing position
)
```

### Trading Strategy Options

- **Dynamic Direction** (default): Automatically selects best direction based on liquidity
- **Fixed Direction**: Set `trade_direction='AtoB'` or `'BtoA'` for fixed direction
- **Position Closing**: Configure `close_blocks` (2 or 3) to control when positions are closed

## Usage

### Running the Trading Bot

```bash
python trade.py
```

The bot will:
1. Connect to Bitquery Kafka stream
2. Monitor DEX pool events
3. Execute trades based on configured strategy
4. Automatically close positions after specified blocks
5. Print statistics periodically

### Example Trade Execution

Based on `successful3.log`, here's an example trade flow:

```
Direction Decision Analysis:
  Raw Liquidity - CurrencyA: 3892.646240234375, CurrencyB: 227.53297424316406
  Median Slippage - AtoB: 200 bps, BtoA: 200 bps
  MaxAmountIn at 200/200 bps - AtoB: 844.4736328125, BtoA: 64.1043930053711
  Method: MaxAmountIn ratio comparison (normalized by liquidity)
  AtoB Ratio: 0.216941 (844.4736328125 / 3892.646240234375)
  BtoA Ratio: 0.281737 (64.1043930053711 / 227.53297424316406)
  Decision: BtoA (AtoB ratio: 0.216941 < BtoA ratio: 0.281737)
  Final Direction: BtoA

Trade #4: BtoA | In: 0.000100 WETH | Out: 0.001101 wTAO | Price: 10.557847
  | Slippage: 200 bps | Pool ID: 0x | Currency A: WETH | Currency B: wTAO
  | Protocol: uniswap_v3 | Block: 24218037 | TX: e717e6b663b87c0af7ffe2bd1d564581123cdb4a47427981eb5227759e0d5655

Closing position opened at block 24218037 (current: 24218040, elapsed: 3 blocks)
   Direction: AtoB | Stored amount: 0.001101 | Actual balance: 0.001101 | Using: 0.001101
Position closed successfully | TX: a184310ba9f2ad0d254dc52a8048db6e9910fbd2cd4a478a0a351ff2667dc4b8 | Block: 24218042
```

## Trading Strategy Details

### Direction Selection Algorithm

The bot uses determines the optimal trade direction by:

1. **Liquidity Analysis**: Compares available liquidity in both directions (AtoB and BtoA)
2. **MaxAmountIn Comparison**: Uses `MaxAmountIn` values from price tables at median slippage
3. **Normalized Ratio**: Calculates ratios normalized by available liquidity to find best utilization
4. **Decision**: Selects direction with higher normalized ratio (better liquidity utilization)

### Slippage Management

- **Primary**: Uses median slippage from stream data for each direction
- **Fallback**: Uses configured default slippage if stream data unavailable
- **Dynamic**: Adapts to market conditions based on real-time price tables

### Gas Price Optimization

The bot prioritizes gas prices in this order:
1. **Stream Gas Price**: Extracted from `TransactionHeader.GasPrice` in stream data
2. **Base Fee**: Falls back to `Header.BaseFee` from block data
3. **Network Gas Price**: Uses RPC gas price estimation
4. **Fixed/Default**: Uses configured fixed price or 30 Gwei fallback

### Position Management

- **Opening**: Tracks block number when position is opened
- **Closing**: Automatically closes position after N blocks (default: 3)
- **Balance Validation**: Verifies actual token balance before closing
- **Safety Checks**: Prevents closing with invalid amounts or zero balances

## Project Structure

```
trade-strategy-dexpool/
├── config.py                 # Bitquery credentials
├── stream.py                 # Kafka stream consumer
├── trade.py                  # Main trading strategy and execution
├── trader.py                 # DEX trader implementation
├── uniswap/
│   ├── __init__.py
│   ├── uniswap_v2.py        # Uniswap V2 swap logic
│   └── uniswap_v3.py        # Uniswap V3 swap logic
└── utils/
    ├── __init__.py
    ├── balance_utils.py     # Balance checking utilities
    ├── conversion_utils.py  # Amount conversion utilities
    ├── gas_utils.py         # Gas price management
    ├── price_utils.py       # Price and slippage utilities
    ├── protobuf_utils.py    # Protobuf message parsing
    ├── token_utils.py       # Token address and ABI utilities
    └── transaction_utils.py # Transaction result utilities
```

## Safety Features

- **Balance Checks**: Validates sufficient balance before executing trades
- **Gas Limits**: Maximum gas price cap (default: 200 Gwei)
- **Slippage Protection**: Configurable slippage tolerance
- **Transaction Confirmation**: Waits for transaction receipts before proceeding
- **Error Handling**: Comprehensive error handling and logging
- **Position Tracking**: Prevents opening new positions while others are open

## Logging

The bot provides detailed logging including:
- Trade execution details (amounts, prices, slippage)
- Transaction hashes and block numbers
- Direction decision analysis
- Gas price information
- Position opening/closing events
- Error messages and warnings
- Trading statistics

## Statistics

The bot tracks and reports:
- Total trades executed
- Successful trades
- Failed trades
- Success rate percentage
- Open positions count

## Disclaimer

This software is provided "as is" without warranty of any kind. Trading cryptocurrencies involves substantial risk of loss. The authors and contributors are not responsible for any financial losses incurred from using this software. Always:

- Test thoroughly with small amounts
- Understand the code before running
- Monitor your trades closely
- Keep your private keys secure
- Use at your own risk
