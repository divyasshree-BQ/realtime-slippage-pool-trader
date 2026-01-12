"""
Uniswap V3 swap execution logic.
"""

import time
import traceback
from typing import Optional
from web3 import Web3
from eth_utils import to_checksum_address
from utils.gas_utils import GasManager
from utils.token_utils import WETH_ADDRESS, get_token_abi, check_and_approve_token
from utils.balance_utils import check_eth_balance


class UniswapV3Swapper:
    """Handles Uniswap V3 swap execution."""
    
    UNISWAP_V3_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'
    
    def __init__(self, w3: Web3, account, address: str, gas_manager: GasManager):
        """
        Initialize Uniswap V3 swapper.
        
        Args:
            w3: Web3 instance
            account: Account object for signing transactions
            address: Wallet address
            gas_manager: GasManager instance
        """
        self.w3 = w3
        self.account = account
        self.address = address
        self.gas_manager = gas_manager
        
        router_address = to_checksum_address(self.UNISWAP_V3_ROUTER)
        router_abi = self._get_router_abi()
        self.router_contract = self.w3.eth.contract(
            address=router_address,
            abi=router_abi
        )
        self.router_address = router_address
    
    def _get_router_abi(self):
        """Get Uniswap V3 router ABI (exactInputSingle)."""
        return [
            {
                "inputs": [
                    {
                        "components": [
                            {"internalType": "address", "name": "tokenIn", "type": "address"},
                            {"internalType": "address", "name": "tokenOut", "type": "address"},
                            {"internalType": "uint24", "name": "fee", "type": "uint24"},
                            {"internalType": "address", "name": "recipient", "type": "address"},
                            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                            {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                        ],
                        "internalType": "struct ISwapRouter.ExactInputSingleParams",
                        "name": "params",
                        "type": "tuple"
                    }
                ],
                "name": "exactInputSingle",
                "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
                "stateMutability": "payable",
                "type": "function"
            }
        ]
    
    
    def execute_swap(
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
            
        Returns:
            Transaction hash or None if failed
        """
        if deadline is None:
            deadline = int(time.time()) + 1200  # 20 minutes
        
        try:
            gas_price = self.gas_manager.get_gas_price(stream_gas_price_wei=stream_gas_price_wei)
            
            # Print token addresses for debugging
            print(f"  Executing swap - Token In: {token_in_address}, Token Out: {token_out_address}")
            
            # Check balances and approve if needed
            is_eth_in = token_in_address.lower() == WETH_ADDRESS.lower()
            if is_eth_in:
                print(f"  Token In is WETH/ETH")
                if not check_eth_balance(amount_in, self.w3, self.address, self.gas_manager, stream_gas_price_wei):
                    return None
            else:
                print(f"  Token In is ERC20 token")
                if not check_and_approve_token(token_in_address, self.router_address, amount_in, self.w3, self.account, self.address, self.gas_manager, stream_gas_price_wei):
                    return None
            
            # Get fresh nonce for swap transaction
            nonce = self.w3.eth.get_transaction_count(self.address)
            
            params = {
                'tokenIn': to_checksum_address(token_in_address),
                'tokenOut': to_checksum_address(token_out_address),
                'fee': fee,
                'recipient': self.address,
                'deadline': deadline,
                'amountIn': amount_in,
                'amountOutMinimum': amount_out_min,
                'sqrtPriceLimitX96': 0
            }
            
            transaction = self.router_contract.functions.exactInputSingle(params).build_transaction({
                'from': self.address,
                'gas': 300000,
                'gasPrice': gas_price,
                'nonce': nonce,
                'value': amount_in if is_eth_in else 0
            })
            
            signed_txn = self.account.sign_transaction(transaction)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"  Swap tx: {tx_hash.hex()}")
            
            return tx_hash.hex()
            
        except Exception as e:
            print(f"  ERROR: Error executing V3 swap: {str(e)}")
            print(f"  Traceback: {traceback.format_exc()}")
            return None

