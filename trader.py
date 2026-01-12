"""
DEX Trader - Executes real trades on Uniswap and other DEX protocols.
"""

import os
from typing import Dict, Optional
from decimal import Decimal
from web3 import Web3
from dotenv import load_dotenv

from utils.token_utils import get_token_address, WETH_ADDRESS
from utils.price_utils import get_price_for_slippage
from utils.gas_utils import GasManager, extract_gas_from_stream
from utils.conversion_utils import convert_amount_to_smallest_unit, calculate_amount_out_min
from utils.transaction_utils import calculate_actual_amount_out
from uniswap.uniswap_v2 import UniswapV2Swapper
from uniswap.uniswap_v3 import UniswapV3Swapper
from eth_utils import to_checksum_address

# Load environment variables from .env file
load_dotenv()


class DEXTrader:
    """Executes real trades on DEX protocols."""
    
    def __init__(
        self,
        private_key: str = None,
        rpc_url: str = None,
        gas_price_gwei: float = None,
        max_gas_price_gwei: float = None,
        slippage_bps: int = 50
    ):
        """
        Initialize DEX trader.
        Reads configuration from .env file if parameters are not provided.
        
        Args:
            private_key: Private key of the trading wallet (loads from PRIVATE_KEY env var if None)
            rpc_url: Ethereum RPC URL (loads from RPC_URL env var if None)
            gas_price_gwei: Fixed gas price in Gwei (None to use network price)
            max_gas_price_gwei: Maximum gas price in Gwei (default: 200)
            slippage_bps: Default slippage tolerance in basis points
        """
        # Load from environment variables if not provided
        if private_key is None:
            private_key = os.getenv("PRIVATE_KEY", "")
            if not private_key:
                raise ValueError("PRIVATE_KEY not found in .env file and not provided as parameter")
        
        if rpc_url is None:
            rpc_url = os.getenv("RPC_URL", None)
        
        # Set default for max_gas_price_gwei if not provided
        if max_gas_price_gwei is None:
            max_gas_price_gwei = 200
        
        # Setup Web3
        if rpc_url:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Ethereum node")
        
        # Setup wallet
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        self.account = self.w3.eth.account.from_key(private_key)
        self.address = self.account.address
        
        # Setup gas manager
        self.gas_manager = GasManager(
            w3=self.w3,
            gas_price_gwei=gas_price_gwei,
            max_gas_price_gwei=max_gas_price_gwei
        )
        
        # Setup Uniswap swappers
        self.uniswap_v2 = UniswapV2Swapper(
            w3=self.w3,
            account=self.account,
            address=self.address,
            gas_manager=self.gas_manager
        )
        self.uniswap_v3 = UniswapV3Swapper(
            w3=self.w3,
            account=self.account,
            address=self.address,
            gas_manager=self.gas_manager
        )
        
        self.default_slippage_bps = slippage_bps
        
        # Check balance
        balance_wei = self.w3.eth.get_balance(self.address)
        balance_eth = self.w3.from_wei(balance_wei, 'ether')
        print(f"Wallet Address: {self.address}")
        print(f"ETH Balance: {balance_eth:.6f} ETH")
        
        if balance_eth < 0.01:
            print("WARNING: Low ETH balance. You may not have enough for gas fees.")
    
    
    def execute_swap_uniswap_v2(
        self,
        token_in_address: str,
        token_out_address: str,
        amount_in: int,
        amount_out_min: int,
        deadline: int = None,
        stream_gas_price_wei: Optional[int] = None
    ) -> Optional[str]:
        """
        Execute swap on Uniswap V2.
        
        Args:
            token_in_address: Token to swap from
            token_out_address: Token to swap to
            amount_in: Amount to swap (in token's smallest unit)
            amount_out_min: Minimum amount out (in token's smallest unit)
            deadline: Transaction deadline timestamp (None for 20 minutes from now)
            stream_gas_price_wei: Gas price from stream in Wei (optional)
            
        Returns:
            Transaction hash or None if failed
        """
        return self.uniswap_v2.execute_swap(
            token_in_address=token_in_address,
            token_out_address=token_out_address,
            amount_in=amount_in,
            amount_out_min=amount_out_min,
            deadline=deadline,
            stream_gas_price_wei=stream_gas_price_wei
        )
    
    def execute_swap_uniswap_v3(
        self,
        token_in_address: str,
        token_out_address: str,
        amount_in: int,
        amount_out_min: int,
        fee: int = 3000,
        deadline: int = None,
        stream_gas_price_wei: Optional[int] = None
    ) -> Optional[str]:
        """
        Execute swap on Uniswap V3.
        
        Args:
            token_in_address: Token to swap from
            token_out_address: Token to swap to
            amount_in: Amount to swap (in token's smallest unit)
            amount_out_min: Minimum amount out (in token's smallest unit)
            fee: Pool fee in basis points (3000 = 0.3%)
            deadline: Transaction deadline timestamp
            stream_gas_price_wei: Gas price from stream in Wei (optional)
            
        Returns:
            Transaction hash or None if failed
        """
        return self.uniswap_v3.execute_swap(
            token_in_address=token_in_address,
            token_out_address=token_out_address,
            amount_in=amount_in,
            amount_out_min=amount_out_min,
            fee=fee,
            deadline=deadline,
            stream_gas_price_wei=stream_gas_price_wei
        )
    
    def execute_trade(
        self,
        pool_event: Dict,
        direction: str,
        amount_in: float,
        slippage_bps: int = None
    ) -> Optional[Dict]:
        """
        Execute a real trade based on pool event.
        
        Args:
            pool_event: Pool event dictionary from stream
            direction: 'AtoB' or 'BtoA'
            amount_in: Amount to trade (in human-readable units)
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Trade result dictionary with tx_hash or None if failed
        """
        if slippage_bps is None:
            slippage_bps = self.default_slippage_bps
        
        # Extract pool and currency info
        pool = pool_event.get('Pool', {})
        if not pool:
            print(f"  WARNING: Missing pool data, skipping trade")
            return None
        
        currency_a = pool.get('CurrencyA', {})
        currency_b = pool.get('CurrencyB', {})
        if not currency_a or not currency_b:
            print(f"  WARNING: Missing currency data (A: {bool(currency_a)}, B: {bool(currency_b)}), skipping trade")
            return None
        
        # Get token addresses
        if direction == 'AtoB':
            token_in_info = currency_a
            token_out_info = currency_b
        else:
            token_in_info = currency_b
            token_out_info = currency_a
        token_in_address = get_token_address(token_in_info)
        token_out_address = get_token_address(token_out_info)
        
        # Print token addresses for debugging
        print(f"  Token In Address: {token_in_address}")
        print(f"  Token Out Address: {token_out_address}")
        print(f"  Token In Symbol: {token_in_info.get('Symbol', 'N/A')}")
        print(f"  Token Out Symbol: {token_out_info.get('Symbol', 'N/A')}")
        
        if not token_in_address or not token_out_address:
            print(f"  WARNING: Missing token address, skipping trade")
            return None
        
        # Get decimals
        try:
            decimals_in = int(token_in_info.get('Decimals', 18))
            decimals_out = int(token_out_info.get('Decimals', 18))
        except:
            decimals_in = 18
            decimals_out = 18
        
        # Convert amount to smallest unit
        amount_in_smallest = convert_amount_to_smallest_unit(amount_in, decimals_in)
        
        # Get expected output from price table
        pool_price_table = pool_event.get('PoolPriceTable', {})
        price_entry = get_price_for_slippage(pool_price_table, direction, slippage_bps)
        
        if not price_entry:
            print(f"  WARNING: No price data available for slippage {slippage_bps} bps")
            return None
        
        # Calculate expected output
        price = Decimal(str(price_entry.get('Price', 0)))
        expected_out = Decimal(str(amount_in)) * price
        
        # Calculate minimum amount out with slippage
        amount_out_min_smallest = calculate_amount_out_min(amount_in, price, decimals_out, slippage_bps)
        
        # Extract gas price from stream
        stream_gas_price_wei = extract_gas_from_stream(pool_event)
        
        # Determine protocol and execute
        protocol = pool_event.get('Dex', {}).get('ProtocolName', '').lower()
        
        # Get pool fee for V3 (default 0.3%)
        fee = 3000  # Could extract from pool info if available
        
        if 'uniswap_v2' in protocol or 'v2' in protocol:
            tx_hash = self.execute_swap_uniswap_v2(
                token_in_address,
                token_out_address,
                amount_in_smallest,
                amount_out_min_smallest,
                deadline=None,
                stream_gas_price_wei=stream_gas_price_wei
            )
        elif 'uniswap_v3' in protocol or 'v3' in protocol:
            tx_hash = self.execute_swap_uniswap_v3(
                token_in_address,
                token_out_address,
                amount_in_smallest,
                amount_out_min_smallest,
                fee,
                deadline=None,
                stream_gas_price_wei=stream_gas_price_wei
            )
        else:
            print(f"  WARNING: Protocol {protocol} not supported, skipping")
            return None
        
        if tx_hash:
            # Wait for confirmation (optional)
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    # Get actual amount received by checking token balance
                    actual_amount_out = calculate_actual_amount_out(
                        receipt,
                        token_out_address,
                        decimals_out,
                        self.w3,
                        self.address,
                        float(expected_out)
                    )
                    
                    return {
                        'tx_hash': tx_hash,
                        'status': 'confirmed',
                        'block_number': receipt.blockNumber,
                        'gas_used': receipt.gasUsed,
                        'direction': direction,
                        'amount_in': float(amount_in),
                        'amount_out': actual_amount_out,  # Use actual amount received
                        'price': float(price),
                        'currency_a': token_in_info.get('Symbol', ''),
                        'currency_b': token_out_info.get('Symbol', ''),
                        'pool_id': pool.get('PoolId', ''),
                        'protocol': pool_event.get('Dex', {}).get('ProtocolName', ''),
                        'slippage_bps': slippage_bps
                    }
                else:
                    print(f"  WARNING: Transaction failed (status: {receipt.status})")
                    return {'tx_hash': tx_hash, 'status': 'failed'}
            except Exception as e:
                print(f"  WARNING: Error waiting for transaction receipt: {str(e)}")
                return {'tx_hash': tx_hash, 'status': 'pending'}
        
        return None

