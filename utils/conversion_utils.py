"""
Amount conversion utilities for token amounts and slippage calculations.
"""

from typing import Dict
from decimal import Decimal


def convert_amount_to_smallest_unit(amount: float, decimals: int) -> int:
    """
    Convert human-readable amount to token's smallest unit.
    
    Args:
        amount: Amount in human-readable units
        decimals: Number of decimals for the token
        
    Returns:
        Amount in smallest unit (wei/smallest denomination)
    """
    return int(Decimal(str(amount)) * (Decimal(10) ** decimals))


def calculate_amount_out_min(
    amount_in: float,
    price: Decimal,
    decimals_out: int,
    slippage_bps: int
) -> int:
    """
    Calculate minimum amount out with slippage applied.
    
    Args:
        amount_in: Input amount in human-readable units
        price: Price from price table
        decimals_out: Number of decimals for output token
        slippage_bps: Slippage tolerance in basis points
        
    Returns:
        Minimum amount out in smallest unit
    """
    expected_out = Decimal(str(amount_in)) * price
    slippage_multiplier = Decimal('1') - (Decimal(str(slippage_bps)) / Decimal('10000'))
    amount_out_min = expected_out * slippage_multiplier
    return int(amount_out_min * (Decimal(10) ** decimals_out))


def convert_amount_from_smallest_unit(amount_wei: int, decimals: int) -> float:
    """
    Convert amount from token's smallest unit to human-readable format.
    
    Args:
        amount_wei: Amount in smallest unit
        decimals: Number of decimals for the token
        
    Returns:
        Amount in human-readable units
    """
    return float(Decimal(amount_wei) / (Decimal(10) ** decimals))
