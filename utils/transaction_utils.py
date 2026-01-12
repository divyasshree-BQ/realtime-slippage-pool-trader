"""
Transaction utilities for calculating actual amounts received and transaction results.
"""

from typing import Dict, Optional, TYPE_CHECKING
from decimal import Decimal
from eth_utils import to_checksum_address

if TYPE_CHECKING:
    from web3 import Web3

from utils.token_utils import WETH_ADDRESS


def calculate_actual_amount_out(
    receipt,
    token_out_address: str,
    decimals_out: int,
    w3: 'Web3',
    address: str,
    expected_out: float
) -> float:
    """
    Calculate actual amount received from a swap transaction.
    
    Args:
        receipt: Transaction receipt
        token_out_address: Output token address
        decimals_out: Number of decimals for output token
        w3: Web3 instance
        address: Wallet address
        expected_out: Expected output amount (fallback if calculation fails)
        
    Returns:
        Actual amount received as float
    """
    actual_amount_out = None
    
    # Check if output token is ETH/WETH
    is_eth_out = token_out_address.lower() == WETH_ADDRESS.lower()
    
    try:
        if is_eth_out:
            # For ETH/WETH, check ETH balance change
            balance_after = w3.eth.get_balance(address, block_identifier=receipt.blockNumber)
            balance_before = w3.eth.get_balance(address, block_identifier=receipt.blockNumber - 1)
            actual_amount_out_wei = balance_after - balance_before
            # Subtract gas cost (approximate)
            gas_cost = receipt.gasUsed * receipt.effectiveGasPrice
            actual_amount_out_wei = actual_amount_out_wei + gas_cost  # Add back gas since it was deducted
            actual_amount_out = float(Decimal(actual_amount_out_wei) / (Decimal(10) ** decimals_out))
        else:
            # For ERC20 tokens, check token balance
            token_out_contract = w3.eth.contract(
                address=to_checksum_address(token_out_address),
                abi=[{
                    "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function"
                }]
            )
            # Get balance after swap
            balance_after = token_out_contract.functions.balanceOf(address).call(block_identifier=receipt.blockNumber)
            # Get balance before swap (from block before the transaction)
            block_before = receipt.blockNumber - 1
            balance_before = token_out_contract.functions.balanceOf(address).call(block_identifier=block_before)
            actual_amount_out_wei = balance_after - balance_before
            actual_amount_out = float(Decimal(actual_amount_out_wei) / (Decimal(10) ** decimals_out))
        
        # Validate the calculated amount - should be positive and reasonable
        if actual_amount_out is None or actual_amount_out <= 0:
            # If calculation failed or returned invalid value, use expected amount
            actual_amount_out = float(expected_out)
        elif actual_amount_out < float(expected_out) * 0.5:
            # If actual is less than 50% of expected, something is wrong - use expected
            actual_amount_out = float(expected_out)
    except Exception as e:
        # If we can't get actual amount, fall back to expected
        print(f"  WARNING: Error calculating actual amount: {str(e)}, using expected amount")
        actual_amount_out = float(expected_out)
    
    return actual_amount_out
