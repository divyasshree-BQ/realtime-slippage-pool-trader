"""
Price lookup utilities for DEX pool events.
"""

from typing import Dict, Optional


def get_best_slippage_bps(price_table: Dict, direction: str) -> Optional[int]:
    """
    Get the best (lowest) available slippage from price table.
    
    Args:
        price_table: PoolPriceTable dictionary
        direction: 'AtoB' or 'BtoA'
        
    Returns:
        Best slippage in basis points or None if not found
    """
    prices_key = f'{direction}Prices'
    if prices_key not in price_table:
        return None
        
    prices = price_table[prices_key]
    if not isinstance(prices, list) or len(prices) == 0:
        return None
    
    # Find the lowest slippage that has valid price data
    best_slippage = None
    for price_entry in prices:
        if isinstance(price_entry, dict):
            slippage = price_entry.get('SlippageBasisPoints')
            if slippage is not None:
                if best_slippage is None or slippage < best_slippage:
                    best_slippage = slippage
    
    return best_slippage


def get_median_slippage_bps(price_table: Dict, direction: str) -> Optional[int]:
    """
    Get the median available slippage from price table.
    
    Args:
        price_table: PoolPriceTable dictionary
        direction: 'AtoB' or 'BtoA'
        
    Returns:
        Median slippage in basis points or None if not found
    """
    prices_key = f'{direction}Prices'
    if prices_key not in price_table:
        return None
        
    prices = price_table[prices_key]
    if not isinstance(prices, list) or len(prices) == 0:
        return None
    
    # Collect all valid slippage values
    slippages = []
    for price_entry in prices:
        if isinstance(price_entry, dict):
            slippage = price_entry.get('SlippageBasisPoints')
            if slippage is not None:
                slippages.append(slippage)
    
    if not slippages:
        return None
    
    # Sort and get median
    slippages.sort()
    median_index = len(slippages) // 2
    return slippages[median_index]


def get_price_for_slippage(price_table: Dict, direction: str, slippage_bps: int) -> Optional[Dict]:
    """
    Get price entry for specific slippage from price table.
    
    Args:
        price_table: PoolPriceTable dictionary
        direction: 'AtoB' or 'BtoA'
        slippage_bps: Slippage in basis points (e.g., 10, 50, 100)
        
    Returns:
        Price entry dict or None if not found
    """
    prices_key = f'{direction}Prices'
    if prices_key not in price_table:
        return None
        
    prices = price_table[prices_key]
    if not isinstance(prices, list):
        return None
        
    for price_entry in prices:
        if isinstance(price_entry, dict) and price_entry.get('SlippageBasisPoints') == slippage_bps:
            return price_entry
            
    # Return first available if exact match not found
    if prices:
        return prices[0]
    return None


def get_best_direction_by_liquidity(pool_event: Dict, slippage_bps: Optional[int] = None, verbose: bool = True) -> Optional[str]:
    """
    Determine the best trade direction based on available liquidity.
    
    Compares liquidity depth in both directions (AtoB and BtoA) and returns
    the direction with more available liquidity.
    
    Args:
        pool_event: Pool event dictionary containing Liquidity and PoolPriceTable
        slippage_bps: Optional slippage level to compare at (defaults to best available)
        verbose: Whether to print detailed decision information
        
    Returns:
        'AtoB' or 'BtoA' based on which has more liquidity, or None if cannot determine
    """
    liquidity = pool_event.get('Liquidity', {})
    price_table = pool_event.get('PoolPriceTable', {})
    
    if not liquidity or not price_table:
        if verbose:
            print("  WARNING: Missing liquidity or price table data")
        return None
    
    # Extract raw liquidity amounts for display
    amount_a = liquidity.get('AmountCurrencyA')
    amount_b = liquidity.get('AmountCurrencyB')
    
    if verbose:
        print("\nDirection Decision Analysis:")
        print(f"  Raw Liquidity - CurrencyA: {amount_a}, CurrencyB: {amount_b}")
    
    # Method 1: Compare MaxAmountIn at median slippage level for each direction
    atob_slippage = None
    btoa_slippage = None
    
    if slippage_bps is None:
        # Get median slippage for both directions
        atob_slippage = get_median_slippage_bps(price_table, 'AtoB')
        btoa_slippage = get_median_slippage_bps(price_table, 'BtoA')
        
        if verbose:
            print(f"  Median Slippage - AtoB: {atob_slippage} bps, BtoA: {btoa_slippage} bps")
        
        if atob_slippage is None or btoa_slippage is None:
            if verbose:
                print("  WARNING: Missing slippage data, falling back to raw liquidity comparison")
            # Fallback to liquidity amounts
            return _compare_liquidity_amounts(liquidity, verbose=verbose)
        
        # Use median slippage for each direction separately
        atob_price = get_price_for_slippage(price_table, 'AtoB', atob_slippage)
        btoa_price = get_price_for_slippage(price_table, 'BtoA', btoa_slippage)
        
        if verbose:
            print(f"  Using median slippage for each direction (AtoB: {atob_slippage} bps, BtoA: {btoa_slippage} bps)")
    else:
        # Get MaxAmountIn for both directions at the specified slippage
        atob_price = get_price_for_slippage(price_table, 'AtoB', slippage_bps)
        btoa_price = get_price_for_slippage(price_table, 'BtoA', slippage_bps)
    
    atob_max = atob_price.get('MaxAmountIn') if atob_price else None
    btoa_max = btoa_price.get('MaxAmountIn') if btoa_price else None
    
    # Determine which slippage was used for display
    if slippage_bps is not None:
        display_slippage = slippage_bps
    else:
        display_slippage = f"{atob_slippage}/{btoa_slippage}"
    if verbose:
        print(f"  MaxAmountIn at {display_slippage} bps - AtoB: {atob_max}, BtoA: {btoa_max}")
    
    # If we have MaxAmountIn values, use them
    if atob_max is not None and btoa_max is not None:
        # Compare as numbers (they should be integers after conversion)
        if isinstance(atob_max, (int, float)) and isinstance(btoa_max, (int, float)):
            # Normalize MaxAmountIn by available liquidity to get ratio
            # AtoB: MaxAmountIn is in CurrencyA, normalize by CurrencyA liquidity
            # BtoA: MaxAmountIn is in CurrencyB, normalize by CurrencyB liquidity
            try:
                amount_a_num = amount_a
                amount_b_num = amount_b
                
                # This normalizes by pool size, so a smaller pool with a higher utilization percentage can be chosen over a larger pool with lower utilization.
                # Calculate ratios (MaxAmountIn as percentage of available liquidity)
                if amount_a_num > 0 and amount_b_num > 0:
                    atob_ratio = atob_max / amount_a_num
                    btoa_ratio = btoa_max / amount_b_num
                    
                    direction = 'AtoB' if atob_ratio >= btoa_ratio else 'BtoA'
                    if verbose:
                        print(f"  Method: MaxAmountIn ratio comparison (normalized by liquidity)")
                        print(f"  AtoB Ratio: {atob_ratio:.6f} ({atob_max} / {amount_a_num})")
                        print(f"  BtoA Ratio: {btoa_ratio:.6f} ({btoa_max} / {amount_b_num})")
                        print(f"  Decision: {direction} (AtoB ratio: {atob_ratio:.6f} {'>=' if atob_ratio >= btoa_ratio else '<'} BtoA ratio: {btoa_ratio:.6f})")
                    return direction
                # else:
                #     # Fallback to absolute comparison if liquidity is zero
                #     if verbose:
                #         print(f"  WARNING: Zero liquidity detected, using absolute MaxAmountIn comparison")
                #     direction = 'AtoB' if atob_max >= btoa_max else 'BtoA'
                #     if verbose:
                #         print(f"  Method: MaxAmountIn comparison (absolute, fallback)")
                #         print(f"  Decision: {direction} (AtoB MaxAmountIn: {atob_max} {'>=' if atob_max >= btoa_max else '<'} BtoA MaxAmountIn: {btoa_max})")
                #     return direction
            except (ValueError, TypeError, ZeroDivisionError) as e:
                # Fallback to absolute comparison if ratio calculation fails
                if verbose:
                    print(f"  WARNING: Error calculating ratios: {e}, using absolute MaxAmountIn comparison")
                direction = 'AtoB' if atob_max >= btoa_max else 'BtoA'
                if verbose:
                    print(f"  Method: MaxAmountIn comparison (absolute, fallback)")
                    print(f"  Decision: {direction} (AtoB MaxAmountIn: {atob_max} {'>=' if atob_max >= btoa_max else '<'} BtoA MaxAmountIn: {btoa_max})")
                return direction
    
    # Fallback: Compare raw liquidity amounts
    if verbose:
        print(f"  WARNING: MaxAmountIn not available, using raw liquidity comparison")
    return _compare_liquidity_amounts(liquidity, verbose=verbose)


def _compare_liquidity_amounts(liquidity: Dict, verbose: bool = True) -> Optional[str]:
    """
    Compare raw liquidity amounts to determine direction.
    
    Args:
        liquidity: Liquidity dictionary with AmountCurrencyA and AmountCurrencyB
        verbose: Whether to print detailed decision information
        
    Returns:
        'AtoB' if CurrencyA has more liquidity, 'BtoA' if CurrencyB has more, or None
    """
    amount_a = liquidity.get('AmountCurrencyA')
    amount_b = liquidity.get('AmountCurrencyB')
    
    if amount_a is None or amount_b is None:
        if verbose:
            print("  WARNING: Missing liquidity amounts")
        return None
    
    # Convert to numbers if they're strings (should already be converted by protobuf_utils)
    try:
        amount_a_num = amount_a
        amount_b_num = amount_b
        
        if isinstance(amount_a, str):
            amount_a_num = int(amount_a, 16) if amount_a.startswith('0x') else int(amount_a)
        if isinstance(amount_b, str):
            amount_b_num = int(amount_b, 16) if amount_b.startswith('0x') else int(amount_b)
        
        # Compare amounts - choose direction with more liquidity
        if isinstance(amount_a_num, (int, float)) and isinstance(amount_b_num, (int, float)):
            direction = 'AtoB' if amount_a_num >= amount_b_num else 'BtoA'
            if verbose:
                print(f"  Method: Raw liquidity comparison")
                print(f"  Decision: {direction} (CurrencyA: {amount_a_num} {'>=' if amount_a_num >= amount_b_num else '<'} CurrencyB: {amount_b_num})")
            return direction
    except (ValueError, TypeError) as e:
        if verbose:
            print(f"  WARNING: Error comparing liquidity amounts: {e}")
        pass
    
    return None

