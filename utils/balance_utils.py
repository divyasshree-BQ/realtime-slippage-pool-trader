"""
Balance checking utilities.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from web3 import Web3
    from utils.gas_utils import GasManager


def check_eth_balance(
    amount_in: int,
    w3: 'Web3',
    address: str,
    gas_manager: 'GasManager',
    stream_gas_price_wei: Optional[int] = None
) -> bool:
    """
    Check if sufficient ETH balance for swap and gas.
    
    Args:
        amount_in: Amount of ETH needed for swap
        w3: Web3 instance
        address: Wallet address
        gas_manager: GasManager instance
        stream_gas_price_wei: Gas price from stream in Wei (optional)
        
    Returns:
        True if sufficient balance, False otherwise
    """
    gas_price = gas_manager.get_gas_price(stream_gas_price_wei=stream_gas_price_wei)
    balance_wei = w3.eth.get_balance(address)
    estimated_gas_cost = gas_price * 300000
    total_needed = amount_in + estimated_gas_cost
    if balance_wei < total_needed:
        print(f"  WARNING: Insufficient ETH balance. Need {w3.from_wei(total_needed, 'ether'):.6f} ETH, have {w3.from_wei(balance_wei, 'ether'):.6f} ETH")
        return False
    return True
