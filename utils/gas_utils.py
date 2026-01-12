"""
Gas price management utilities.
"""

from typing import Dict, Optional
from web3 import Web3


class GasManager:
    """Manages gas price calculations and limits."""
    
    def __init__(
        self,
        w3: Web3,
        gas_price_gwei: Optional[float] = None,
        max_gas_price_gwei: float = 200
    ):
        """
        Initialize gas manager.
        
        Args:
            w3: Web3 instance
            gas_price_gwei: Fixed gas price in Gwei (None to use network price)
            max_gas_price_gwei: Maximum gas price in Gwei
        """
        self.w3 = w3
        self.gas_price_gwei = gas_price_gwei
        self.max_gas_price_gwei = max_gas_price_gwei
    
    def get_gas_price(self, stream_gas_price_wei: Optional[int] = None) -> int:
        """
        Get current gas price in Wei.
        
        Args:
            stream_gas_price_wei: Gas price from stream in Wei (optional, takes priority)
        
        Returns:
            Gas price in Wei
        """
        # Priority 1: Use gas price from stream if provided
        if stream_gas_price_wei is not None:
            max_gas_price = self.w3.to_wei(self.max_gas_price_gwei, 'gwei')
            if stream_gas_price_wei > max_gas_price:
                print(f"[GAS] Using stream gas price (capped): {stream_gas_price_wei / 1e9:.2f} Gwei -> {self.max_gas_price_gwei} Gwei (exceeded max)")
                return max_gas_price
            print(f"[GAS] Using gas price from STREAM: {stream_gas_price_wei / 1e9:.2f} Gwei")
            return stream_gas_price_wei
        
        # Priority 2: Use fixed gas price if set
        if self.gas_price_gwei:
            fixed_gas_wei = self.w3.to_wei(self.gas_price_gwei, 'gwei')
            print(f"[GAS] Using FIXED gas price: {self.gas_price_gwei} Gwei ({fixed_gas_wei / 1e9:.2f} Gwei)")
            return fixed_gas_wei
        
        # Priority 3: Fetch from network via RPC
        try:
            gas_price = self.w3.eth.gas_price
            max_gas_price = self.w3.to_wei(self.max_gas_price_gwei, 'gwei')
            if gas_price > max_gas_price:
                print(f"[GAS] Using RPC gas price (capped): {gas_price / 1e9:.2f} Gwei -> {self.max_gas_price_gwei} Gwei (exceeded max)")
                return max_gas_price
            print(f"[GAS] Using gas price from RPC: {gas_price / 1e9:.2f} Gwei")
            return gas_price
        except Exception as e:
            # Fallback to default if gas estimation fails
            fallback_gas = self.w3.to_wei(30, 'gwei')
            print(f"[GAS] Using FALLBACK gas price: 30 Gwei (RPC fetch failed: {str(e)})")
            return fallback_gas


def extract_gas_from_stream(pool_event: Dict) -> Optional[int]:
    """
    Extract gas price from stream data.
    
    Priority:
    1. TransactionHeader.GasPrice (if available in pool event)
    2. Header.BaseFee (from parent block data)
    
    Args:
        pool_event: Pool event dictionary from stream
        
    Returns:
        Gas price in Wei, or None if not available
    """
    # Try to get GasPrice from TransactionHeader (most accurate for the specific transaction)
    transaction_header = pool_event.get('TransactionHeader', {})
    if transaction_header:
        gas_price = transaction_header.get('GasPrice')
        if gas_price is not None and isinstance(gas_price, int):
            print(f"[GAS] Extracted from stream TransactionHeader.GasPrice: {gas_price / 1e9:.2f} Gwei")
            return gas_price
    
    # Fallback to BaseFee from Header (block base fee)
    # Note: pool_event might be nested in a parent structure with Header
    # Check if Header is at the same level as PoolEvents
    header = pool_event.get('Header', {})
    if header:
        base_fee = header.get('BaseFee')
        if base_fee is not None and isinstance(base_fee, int):
            # BaseFee is the base fee per gas, we can use it as gas price
            # For EIP-1559 transactions, actual gas price = baseFee + priorityFee
            # But for legacy transactions, we can use baseFee as minimum
            print(f"[GAS] Extracted from stream Header.BaseFee: {base_fee / 1e9:.2f} Gwei")
            return base_fee
    
    print(f"[GAS] No gas price found in stream data, will use fallback (RPC/fixed/default)")
    return None

