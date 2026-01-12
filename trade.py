"""
Live Trading Script - Executes real trades on DEX based on stream data.
WARNING: This executes REAL trades with REAL funds. Use with caution!
"""

import time
from typing import Dict, Optional, List
from stream import BitqueryStream
from trader import DEXTrader
from utils.price_utils import get_median_slippage_bps, get_best_direction_by_liquidity


class TradingStrategy:
    """Trading strategy that decides when and how to trade."""
    
    def __init__(
        self,
        trader: DEXTrader,
        trade_amount: float = 100.0,
        slippage_bps: int = 50,
        min_profit_threshold: float = 0.0,
        trade_direction: Optional[str] = None,  # None for dynamic (default), 'AtoB' or 'BtoA' for fixed
        enabled: bool = False,
        close_blocks: int = 3  # Number of blocks to wait before closing position
    ):
        """
        Initialize trading strategy.
        
        Args:
            trader: DEXTrader instance
            trade_amount: Amount to trade per opportunity
            slippage_bps: Maximum slippage in basis points
            min_profit_threshold: Minimum profit threshold
            trade_direction: Trade direction (None for dynamic based on liquidity, 'AtoB' or 'BtoA' for fixed)
            enabled: Whether trading is enabled (safety flag)
            close_blocks: Number of blocks to wait before closing position (2 or 3)
        """
        self.trader = trader
        self.trade_amount = trade_amount
        self.slippage_bps = slippage_bps
        self.min_profit_threshold = min_profit_threshold
        self.trade_direction = trade_direction
        self.enabled = enabled
        self.last_trade_time = 0
        self.min_trade_interval = 5.0  # Minimum seconds between trades
        self.total_trades = 0
        self.successful_trades = 0
        self.failed_trades = 0
        self.close_blocks = close_blocks
        self.open_positions: List[Dict] = []  # Track positions that need to be closed
        
    def should_trade(self, pool_event: Dict) -> bool:
        """Determine if we should trade on this pool event."""
        if not self.enabled:
            return False
        
        # Don't open new trades if there are open positions - wait for them to close
        open_positions_count = len([p for p in self.open_positions if p.get('status') == 'open'])
        if open_positions_count > 0:
            return False
        
        current_time = time.time()
        if current_time - self.last_trade_time < self.min_trade_interval:
            # Silently skip - too frequent trades
            return False
        
        if not pool_event.get('PoolPriceTable'):
            return False
        
        liquidity = pool_event.get('Liquidity', {})
        if not liquidity.get('AmountCurrencyA') or not liquidity.get('AmountCurrencyB'):
            return False
        
        return True
    
    def execute_strategy(self, pool_event: Dict) -> Optional[Dict]:
        """Execute trading strategy on a pool event."""
        if not self.should_trade(pool_event):
            return None
        
        # Extract pool info for logging
        pool = pool_event.get('Pool', {})
        currency_a = pool.get('CurrencyA', {})
        currency_b = pool.get('CurrencyB', {})
        
        # Determine trade direction dynamically based on liquidity (default behavior)
        # Only use fixed direction if explicitly set to 'AtoB' or 'BtoA'
        if self.trade_direction is None:
            direction = get_best_direction_by_liquidity(pool_event, verbose=True)
            if direction is None:
                # Fallback to AtoB if cannot determine
                direction = 'AtoB'
                print(f"  WARNING: Could not determine direction from liquidity, defaulting to {direction}")
            else:
                print(f"  Final Direction: {direction}")
        else:
            direction = self.trade_direction
            print(f"  Using fixed direction: {direction}")
        
        # Get median slippage from stream, fallback to default if not available
        pool_price_table = pool_event.get('PoolPriceTable', {})
        median_slippage = get_median_slippage_bps(pool_price_table, direction)
        if median_slippage is None:
            median_slippage = self.slippage_bps  # Fallback to default
        print(f"Median slippage chosen: {median_slippage} bps")
        print(f"Direction chosen: {direction}")
        try:
            result = self.trader.execute_trade(
                pool_event=pool_event,
                direction=direction,
                amount_in=self.trade_amount,
                slippage_bps=median_slippage
            )
        except Exception as e:
            print(f"  ERROR: Error executing trade: {str(e)}")
            import traceback
            traceback.print_exc()
            result = None
        
        self.total_trades += 1
        self.last_trade_time = time.time()
        
        if result:
            if result.get('status') == 'confirmed':
                self.successful_trades += 1
                block_number = result.get('block_number')
                
                print(f"Trade #{self.total_trades}: {result.get('direction', direction)} | "
                      f"In: {result.get('amount_in', self.trade_amount):.6f} {result.get('currency_a', '')} | "
                      f"Out: {result.get('amount_out', 0):.6f} {result.get('currency_b', '')} | "
                      f"Price: {result.get('price', 0):.6f} |"
                      f"Slippage: {result.get('slippage_bps', self.slippage_bps)} bps |"
                      f"Pool ID: {result.get('pool_id', '')} |"
                      f"Currency A: {result.get('currency_a', '')} |"
                      f"Currency B: {result.get('currency_b', '')} |"
                      f"Protocol: {result.get('protocol', '')} |"
                      f"Block: {block_number} |"
                      f"TX: {result.get('tx_hash', 'N/A')}")
                
                # Store position for closing in opposite direction
                if block_number:
                    opposite_direction = 'BtoA' if direction == 'AtoB' else 'AtoB'
                    
                    # Get amount_out from result, with fallback calculation if needed
                    amount_out = result.get('amount_out', 0)
                    amount_in = result.get('amount_in', self.trade_amount)
                    price = result.get('price', 0)
                    
                    # If amount_out is 0 or invalid, calculate from price and amount_in
                    if amount_out is None or amount_out <= 0.000001:
                        if price > 0:
                            amount_out = amount_in * price
                            print(f"  WARNING: amount_out was invalid ({result.get('amount_out', 0):.6f}), calculated from price: {amount_out:.6f}")
                        else:
                            # Last resort: use trade_amount as fallback
                            amount_out = self.trade_amount
                            print(f"  WARNING: Could not determine amount_out, using trade_amount: {amount_out:.6f}")
                    
                    position = {
                        'open_block': block_number,
                        'direction': direction,
                        'opposite_direction': opposite_direction,
                        'pool_event': pool_event,
                        'amount_out': amount_out,  # Use validated output amount for closing
                        'pool_id': result.get('pool_id', ''),
                        'currency_a': result.get('currency_a', ''),
                        'currency_b': result.get('currency_b', ''),
                        'slippage_bps': result.get('slippage_bps', median_slippage),
                        'status': 'open'
                    }
                    self.open_positions.append(position)
                    print(f"  Position opened at block {block_number}, will close in {self.close_blocks} blocks (direction: {opposite_direction})")
            elif result.get('status') == 'failed':
                self.failed_trades += 1
        else:
            self.failed_trades += 1
            # Only print if we actually attempted a trade (to avoid spam)
            if self.total_trades > 0:
                print(f"  WARNING: Trade #{self.total_trades} failed (execute_trade returned None)")
        
        return result
    
    def check_and_close_positions(self, current_block: int) -> None:
        """Check for positions that need to be closed and execute opposite trades."""
        if not self.enabled:
            return
        
        positions_to_close = []
        for position in self.open_positions:
            if position.get('status') != 'open':
                continue
            
            open_block = position.get('open_block', 0)
            blocks_elapsed = current_block - open_block
            
            # Close position if we're within the close_blocks window (2 or 3 blocks)
            if blocks_elapsed >= self.close_blocks:
                positions_to_close.append(position)
        
        for position in positions_to_close:
            try:
                pool_event = position.get('pool_event')
                opposite_direction = position.get('opposite_direction')
                stored_amount_out = position.get('amount_out', self.trade_amount)
                slippage_bps = position.get('slippage_bps', self.slippage_bps)
                
                # Get actual token balance to ensure we don't try to swap more than we have
                pool = pool_event.get('Pool', {})
                currency_a = pool.get('CurrencyA', {})
                currency_b = pool.get('CurrencyB', {})
                
                # Determine which token we need to swap (the one we received from opening trade)
                if opposite_direction == 'BtoA':
                    token_to_swap = currency_b  # We received currency_b, now swap it back
                else:
                    token_to_swap = currency_a  # We received currency_a, now swap it back
                
                # Get actual balance
                from utils.token_utils import get_token_balance
                actual_balance = get_token_balance(token_to_swap, self.trader.w3, self.trader.address)
                
                # Determine amount to use for closing
                # If stored amount is 0 or very small (likely invalid/calculation failed), use actual balance
                # Otherwise, use minimum of stored and actual for safety
                if stored_amount_out is None or stored_amount_out <= 0.000001:
                    # Stored amount is invalid, use actual balance
                    if actual_balance is None or actual_balance <= 0:
                        print(f"\nClosing position opened at block {position.get('open_block')} (current: {current_block}, elapsed: {current_block - position.get('open_block')} blocks)")
                        print(f"   WARNING: Cannot close position - no valid amount. Stored: {stored_amount_out:.6f}, Actual: {actual_balance if actual_balance is not None else 'N/A'}")
                        position['status'] = 'close_failed'
                        print("--------------------------------")
                        continue
                    amount_out = actual_balance
                elif actual_balance is None:
                    # Can't get actual balance, use stored amount (but warn)
                    amount_out = stored_amount_out
                    print(f"   WARNING: Could not get actual balance, using stored amount")
                else:
                    # Both are valid, use minimum for safety
                    amount_out = min(stored_amount_out, actual_balance)
                
                # Final safety check - don't try to swap 0 or negative amounts
                if amount_out <= 0:
                    print(f"\nClosing position opened at block {position.get('open_block')} (current: {current_block}, elapsed: {current_block - position.get('open_block')} blocks)")
                    print(f"   WARNING: Cannot close position - amount is 0 or negative: {amount_out:.6f}")
                    position['status'] = 'close_failed'
                    print("--------------------------------")
                    continue
                
                print(f"\nClosing position opened at block {position.get('open_block')} (current: {current_block}, elapsed: {current_block - position.get('open_block')} blocks)")
                actual_balance_str = f"{actual_balance:.6f}" if actual_balance is not None else "N/A"
                print(f"   Direction: {opposite_direction} | Stored amount: {stored_amount_out:.6f} | Actual balance: {actual_balance_str} | Using: {amount_out:.6f}")
                
                # Execute opposite trade
                result = self.trader.execute_trade(
                    pool_event=pool_event,
                    direction=opposite_direction,
                    amount_in=amount_out,  # Use the actual available amount
                    slippage_bps=slippage_bps
                )
                
                if result:
                    if result.get('status') == 'confirmed':
                        position['status'] = 'closed'
                        position['close_tx'] = result.get('tx_hash')
                        position['close_block'] = result.get('block_number')
                        print(f"Position closed successfully | TX: {result.get('tx_hash', 'N/A')} | Block: {result.get('block_number', 'N/A')}")
                        print("--------------------------------")
                    elif result.get('status') == 'failed':
                        position['status'] = 'close_failed'
                        print(f"Failed to close position | TX: {result.get('tx_hash', 'N/A')}")
                        print("--------------------------------")
                else:
                    position['status'] = 'close_failed'
                    print(f"Failed to close position (no result)")
                    print("--------------------------------")
            except Exception as e:
                print(f"ERROR: Error closing position: {str(e)}")
                position['status'] = 'close_error'
                print("--------------------------------")
        # Remove closed positions from tracking (keep failed ones for debugging)
        self.open_positions = [p for p in self.open_positions if p.get('status') in ['open', 'close_failed', 'close_error']]
    
    def get_statistics(self) -> Dict:
        """Get trading statistics."""
        open_positions_count = len([p for p in self.open_positions if p.get('status') == 'open'])
        return {
            'total_trades': self.total_trades,
            'successful_trades': self.successful_trades,
            'failed_trades': self.failed_trades,
            'success_rate': (self.successful_trades / self.total_trades * 100) if self.total_trades > 0 else 0,
            'open_positions': open_positions_count
        }
    
    def print_statistics(self):
        """Print current trading statistics."""
        stats = self.get_statistics()
        print(f"\n=== Trading Statistics ===")
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Successful: {stats['successful_trades']}")
        print(f"Failed: {stats['failed_trades']}")
        print(f"Success Rate: {stats['success_rate']:.2f}%")
        print(f"Open Positions: {stats['open_positions']}")
        print("=" * 40)


def run_trading(
    topic: str = 'eth.dexpools.proto',
    trade_amount: float = 100.0,
    slippage_bps: int = 50,
    min_profit_threshold: float = 0.0,
    trade_direction: Optional[str] = None,    
    max_trades: Optional[int] = None,
    stats_interval: int = 100,
    close_blocks: int = 3  # Number of blocks to wait before closing position (2 or 3)
):
    """
    Run live trading on stream.
    
    WARNING: This executes REAL trades with REAL funds!
    
    Args:
        topic: Kafka topic to subscribe to
        trade_amount: Amount to trade per opportunity
        slippage_bps: Maximum slippage in basis points
        min_profit_threshold: Minimum profit threshold
        trade_direction: Trade direction (None for dynamic based on liquidity, 'AtoB' or 'BtoA' for fixed)
        max_trades: Maximum number of trades to execute (None for unlimited)
        stats_interval: Print statistics every N events
        close_blocks: Number of blocks to wait before closing position (2 or 3)
    """
    # Initialize trader (reads from .env file automatically)
    try:
        trader = DEXTrader(slippage_bps=slippage_bps)
    except ValueError as e:
        print(f"ERROR: {str(e)}")
        print("   Please ensure your .env file has PRIVATE_KEY set")
        return
    except Exception as e:
        print(f"ERROR: Error initializing trader: {str(e)}")
        return
    
    # Initialize strategy
    strategy = TradingStrategy(
        trader=trader,
        trade_amount=trade_amount,
        slippage_bps=slippage_bps,
        min_profit_threshold=min_profit_threshold,
        trade_direction=trade_direction,
        enabled=True,  # Always enabled for real trading
        close_blocks=close_blocks
    )
    
    # Initialize stream
    stream = BitqueryStream(topic=topic)
    
    print(f"Starting live trading...")
    print(f"Trade Amount: {trade_amount}")
    print(f"Slippage: {slippage_bps} bps")
    print(f"Trade Direction: {trade_direction}")
    print(f"Close Position After: {close_blocks} blocks")
    print(f"\nNote: Consumer is set to 'latest' offset - waiting for NEW messages only")
    print(f"Press Ctrl+C to stop\n")
    print("Waiting for messages from Kafka stream...")
    
    event_count = 0
    
    def process_event(pool_event: Dict):
        nonlocal event_count
        event_count += 1
        
        # Get current block number to check for positions that need closing
        try:
            current_block = trader.w3.eth.block_number
            # Check and close positions that are ready
            strategy.check_and_close_positions(current_block)
        except Exception:
            # If we can't get block number, skip position closing for this event
            pass
        
        try:
            pool_events = pool_event.get('PoolEvents', [])
            if not pool_events:
                return
            
            # Extract Header (with BaseFee) from block-level data for gas price fallback
            block_header = pool_event.get('Header', {})
            
            for event in pool_events:
                if not isinstance(event, dict):
                    continue
                
                if 'PoolPriceTable' not in event or 'Pool' not in event:
                    continue
                
                # Add Header to event for gas extraction (if not already present)
                if block_header and 'Header' not in event:
                    event['Header'] = block_header
                
                try:
                    result = strategy.execute_strategy(event)
                    
                    if max_trades and strategy.total_trades >= max_trades:
                        print(f"\nReached maximum trades limit: {max_trades}")
                        stream.close()
                        return
                except Exception as e:
                    continue
            
        except Exception as e:
            return
        
        if event_count % stats_interval == 0:
            strategy.print_statistics()
    
    try:
        while True:
            data_dict = stream.poll(timeout=1.0)
            
            # Always check for positions that need closing, even if no new event
            try:
                current_block = trader.w3.eth.block_number
                strategy.check_and_close_positions(current_block)
            except Exception:
                # If we can't get block number, skip position closing
                pass
            
            if data_dict is not None:
                process_event(data_dict)
                
                if max_trades and strategy.total_trades >= max_trades:
                    print(f"\nReached maximum trades limit: {max_trades}")
                    break
            
    except KeyboardInterrupt:
        print("\nTrading stopped by user")
    finally:
        stream.close()
        strategy.print_statistics()
        print("\nTrading complete!")


if __name__ == '__main__':
    # Execute live trades on Ethereum
    run_trading(
        topic='eth.dexpools.proto',
        trade_amount=0.0001,
        slippage_bps=50,
        min_profit_threshold=0.0,
        max_trades=None,
        stats_interval=100,
        close_blocks=3  # Close position after 3 blocks (can be set to 2 or 3)
    )

