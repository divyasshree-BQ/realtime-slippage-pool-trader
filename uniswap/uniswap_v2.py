"""
Uniswap V2 swap execution logic.
"""

import time
import traceback
from typing import Optional
from web3 import Web3
from eth_utils import to_checksum_address
from utils.gas_utils import GasManager
from utils.token_utils import WETH_ADDRESS, get_token_abi, check_and_approve_token
from utils.balance_utils import check_eth_balance


class UniswapV2Swapper:
    """Handles Uniswap V2 swap execution."""
    
    UNISWAP_V2_ROUTER = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    
    def __init__(self, w3: Web3, account, address: str, gas_manager: GasManager):
        """
        Initialize Uniswap V2 swapper.
        
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
        
        router_address = to_checksum_address(self.UNISWAP_V2_ROUTER)
        router_abi = self._get_router_abi()
        self.router_contract = self.w3.eth.contract(
            address=router_address,
            abi=router_abi
        )
        self.router_address = router_address
    
    def _get_router_abi(self):
        """Get Uniswap V2 router ABI."""
        return [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactETHForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForETH",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
    
    
    def execute_swap(
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
            
        Returns:
            Transaction hash or None if failed
        """
        if deadline is None:
            deadline = int(time.time()) + 1200  # 20 minutes
        
        path = [to_checksum_address(token_in_address), to_checksum_address(token_out_address)]
        
        # Determine swap function based on ETH involvement
        is_eth_in = token_in_address.lower() == WETH_ADDRESS.lower()
        is_eth_out = token_out_address.lower() == WETH_ADDRESS.lower()
        
        if is_eth_in:
            function_name = 'swapExactETHForTokens'
        elif is_eth_out:
            function_name = 'swapExactTokensForETH'
        else:
            function_name = 'swapExactTokensForTokens'
        
        try:
            gas_price = self.gas_manager.get_gas_price(stream_gas_price_wei=stream_gas_price_wei)
            
            # Check balances and approve if needed
            if function_name == 'swapExactETHForTokens':
                if not check_eth_balance(amount_in, self.w3, self.address, self.gas_manager, stream_gas_price_wei):
                    return None
            else:
                if not check_and_approve_token(token_in_address, self.router_address, amount_in, self.w3, self.account, self.address, self.gas_manager, stream_gas_price_wei):
                    return None
            
            # Get fresh nonce for swap transaction
            nonce = self.w3.eth.get_transaction_count(self.address)
            
            # Build swap transaction
            if function_name == 'swapExactETHForTokens':
                transaction = self.router_contract.functions.swapExactETHForTokens(
                    amount_out_min,
                    path,
                    self.address,
                    deadline
                ).build_transaction({
                    'from': self.address,
                    'value': amount_in,
                    'gas': 300000,
                    'gasPrice': gas_price,
                    'nonce': nonce
                })
            elif function_name == 'swapExactTokensForETH':
                transaction = self.router_contract.functions.swapExactTokensForETH(
                    amount_in,
                    amount_out_min,
                    path,
                    self.address,
                    deadline
                ).build_transaction({
                    'from': self.address,
                    'gas': 300000,
                    'gasPrice': gas_price,
                    'nonce': nonce
                })
            else:
                transaction = self.router_contract.functions.swapExactTokensForTokens(
                    amount_in,
                    amount_out_min,
                    path,
                    self.address,
                    deadline
                ).build_transaction({
                    'from': self.address,
                    'gas': 300000,
                    'gasPrice': gas_price,
                    'nonce': nonce
                })
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(transaction)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"  Swap tx: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            print(f"  ERROR: Error executing swap: {str(e)}")
            print(f"  Traceback: {traceback.format_exc()}")
            return None

