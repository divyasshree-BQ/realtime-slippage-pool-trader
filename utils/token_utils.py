"""
Token utilities for address extraction and validation.
"""

from typing import Dict, Optional, TYPE_CHECKING
from eth_utils import to_checksum_address
from decimal import Decimal

if TYPE_CHECKING:
    from web3 import Web3

# Common token addresses
WETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'


def get_token_address(currency_info: Dict) -> Optional[str]:
    """
    Extract token address from currency info.
    
    Args:
        currency_info: Currency dictionary with 'SmartContract' field
        
    Returns:
        Checksummed token address or None if invalid
    """
    address = currency_info.get('SmartContract') 
    if not address or address == '0x':
        return None
    
    if address.startswith('0x'):
        try:
            return to_checksum_address(address)
        except:
            return None
    return None


def get_token_balance(token_info: Dict, w3: 'Web3', address: str) -> Optional[float]:
    """
    Get the token balance for a given address.
    
    Args:
        token_info: Currency dictionary with 'SmartContract' and 'Decimals' fields
        w3: Web3 instance
        address: Wallet address to check balance for
        
    Returns:
        Token balance as float (human-readable, adjusted for decimals) or None if unable to fetch
    """
    try:
        token_address = get_token_address(token_info)
        if not token_address:
            return None
        
        decimals = int(token_info.get('Decimals', 18))
        token_abi = get_token_abi()
        token_contract = w3.eth.contract(
            address=token_address,
            abi=token_abi
        )
        balance_wei = token_contract.functions.balanceOf(address).call()
        return float(Decimal(balance_wei) / (Decimal(10) ** decimals))
    except Exception:
        return None


def get_token_abi():
    """
    Get standard ERC20 token ABI for common operations.
    
    Returns:
        List of ABI entries for approve, allowance, and balanceOf
    """
    return [
        {
            "inputs": [
                {"internalType": "address", "name": "spender", "type": "address"},
                {"internalType": "uint256", "name": "amount", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"}
            ],
            "name": "allowance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]


def check_and_approve_token(
    token_address: str,
    router_address: str,
    amount: int,
    w3: 'Web3',
    account,
    address: str,
    gas_manager,
    stream_gas_price_wei: Optional[int] = None
) -> bool:
    """
    Check token balance and approve if needed.
    
    Args:
        token_address: Token contract address
        router_address: Router contract address to approve
        amount: Amount to approve
        w3: Web3 instance
        account: Account object for signing transactions
        address: Wallet address
        gas_manager: GasManager instance
        stream_gas_price_wei: Gas price from stream in Wei (optional)
        
    Returns:
        True if approved or already has sufficient allowance, False otherwise
    """
    print(f"  Checking token balance for address: {token_address}")
    token_abi = get_token_abi()
    token_contract = w3.eth.contract(
        address=to_checksum_address(token_address),
        abi=token_abi
    )
    
    # Check token balance
    try:
        token_balance = token_contract.functions.balanceOf(address).call()
        if token_balance < amount:
            print(f"  WARNING: Insufficient token balance. Need {amount}, have {token_balance}")
            print(f"  Token Address: {token_address}")
            return False
    except Exception as e:
        print(f"  WARNING: Error checking token balance: {str(e)}")
        return False
    
    # Check ETH balance for gas fees
    gas_price = gas_manager.get_gas_price(stream_gas_price_wei=stream_gas_price_wei)
    balance_wei = w3.eth.get_balance(address)
    estimated_gas_cost = gas_price * 300000
    if balance_wei < estimated_gas_cost:
        print(f"  WARNING: Insufficient ETH for gas fees. Need {w3.from_wei(estimated_gas_cost, 'ether'):.6f} ETH, have {w3.from_wei(balance_wei, 'ether'):.6f} ETH")
        return False
    
    # Check and approve if needed
    allowance = token_contract.functions.allowance(address, router_address).call()
    if allowance < amount:
        nonce = w3.eth.get_transaction_count(address)
        approve_txn = token_contract.functions.approve(
            router_address,
            2**256 - 1  # Max approval
        ).build_transaction({
            'from': address,
            'gas': 150000,
            'gasPrice': gas_price,
            'nonce': nonce
        })
        
        signed_approve = account.sign_transaction(approve_txn)
        approve_tx_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        print(f"  Approval tx: {approve_tx_hash.hex()}")
        
        # Wait for approval confirmation
        receipt = w3.eth.wait_for_transaction_receipt(approve_tx_hash, timeout=120)
        if receipt.status != 1:
            print(f"  ERROR: Approval transaction failed")
            return False
        print(f"  Approval confirmed, proceeding with swap...")
    
    return True

