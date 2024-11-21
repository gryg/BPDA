from multiversx_sdk import (
    Address,
    ContractQuery,
    ProxyNetworkProvider,
    SmartContractTransactionsFactory,
    TokenPayment,
    Transaction,
    TransactionsFactoryConfig,
    TransactionComputer,
    UserSigner
)
import base64
from pathlib import Path
import time

NETWORK_URL = "https://devnet-api.multiversx.com"
CONTRACT_ADDRESS = "erd1qqqqqqqqqqqqqpgqrqz7r8yl5dav2z0fgnn302l2w7xynygruvaq76m26j"
CHAIN_ID = "D"

provider = ProxyNetworkProvider(NETWORK_URL)
network_config = provider.get_network_config()
config = TransactionsFactoryConfig(CHAIN_ID)
factory = SmartContractTransactionsFactory(config)
transaction_computer = TransactionComputer()

def load_wallet():
    pem_path = Path("wallet.pem")
    return UserSigner.from_pem_file(pem_path)

def decode_card_properties(hex_props):
    props = bytes.fromhex(hex_props)
    if len(props) != 3:
        raise ValueError("Invalid properties length")
        
    classes = ["Warrior", "Mage", "Rogue", "Priest", "Hunter", "Warlock", "Shaman", "Druid", "Paladin"]
    rarities = ["Common", "Rare", "Epic", "Legendary"]
    powers = ["Low", "Medium", "High"]
    
    return {
        "class": classes[props[0]],
        "rarity": rarities[props[1]],
        "power": powers[props[2]]
    }

def encode_card_properties(props):
    classes = ["Warrior", "Mage", "Rogue", "Priest", "Hunter", "Warlock", "Shaman", "Druid", "Paladin"]
    rarities = ["Common", "Rare", "Epic", "Legendary"]
    powers = ["Low", "Medium", "High"]
    
    class_idx = classes.index(props['class'])
    rarity_idx = rarities.index(props['rarity'])
    power_idx = powers.index(props['power'])
    
    return bytes([class_idx, rarity_idx, power_idx]).hex()

def query_available_nfts():
    query = ContractQuery(
        contract=Address.from_bech32(CONTRACT_ADDRESS),
        function="nftSupply",
        arguments=[]
    )
    
    query_response = provider.query_contract(query)
    nfts = []
    for i, nft_data in enumerate(query_response.return_data, start=1):
        attributes = base64.b64decode(nft_data).hex()
        props = decode_card_properties(attributes)
        nfts.append({
            'nonce': i,
            'properties': props
        })
    return nfts

def get_assigned_nft_properties(signer):
    sender_address = signer.get_pubkey().to_address(hrp="erd")
    account = provider.get_account(sender_address)
    print(f"Account balance: {account.balance}")
    
    tx = Transaction(
        chain_id=network_config.chain_id,
        sender=sender_address.to_bech32(),
        receiver=CONTRACT_ADDRESS,
        gas_limit=20000000,  # Increased gas limit
        nonce=account.nonce,
        value="0",
        data=b"getYourNftCardProperties",
        version=1,
        gas_price=network_config.min_gas_price
    )
    
    tx.signature = signer.sign(transaction_computer.compute_bytes_for_signing(tx))
    tx_hash = provider.send_transaction(tx)
    print(f"Properties request hash: {tx_hash}")
    
    for i in range(30):
        time.sleep(1)
        tx_info = provider.get_transaction(tx_hash)
        print(f"Transaction status after {i+1}s:", tx_info.status if hasattr(tx_info, 'status') else 'No status')
        if hasattr(tx_info, 'smart_contract_results') and tx_info.smart_contract_results:
            for scr in tx_info.smart_contract_results:
                print("SCR data:", scr.data)
                if scr.data.startswith('@6f6b@'):
                    result_hex = scr.data.replace('@6f6b@', '')
                    return decode_card_properties(result_hex)
                    
    raise Exception("Transaction timeout - no results received")

def create_nft(signer, properties):
    sender_address = signer.get_pubkey().to_address(hrp="erd")
    account = provider.get_account(sender_address)
    
    encoded_name = "filoftei.grigore".encode().hex()
    encoded_props = encode_card_properties(properties)
    
    tx = Transaction(
        chain_id=network_config.chain_id,
        sender=sender_address.to_bech32(),
        receiver=CONTRACT_ADDRESS,
        gas_limit=60000000,
        nonce=account.nonce,
        value="0",
        data=f"issueNft@{encoded_name}@{encoded_props}".encode(),
        version=1,
        gas_price=network_config.min_gas_price
    )
    
    tx.signature = signer.sign(transaction_computer.compute_bytes_for_signing(tx))
    tx_hash = provider.send_transaction(tx)
    print(f"NFT creation hash: {tx_hash}")
    
    for _ in range(30):
        time.sleep(1)
        tx_info = provider.get_transaction(tx_hash)
        if hasattr(tx_info, 'status'):
            if tx_info.status == "success":
                if hasattr(tx_info, 'smart_contract_results'):
                    for scr in tx_info.smart_contract_results:
                        if scr.data.startswith('@6f6b@'):
                            return tx_hash
            elif tx_info.status == "fail":
                raise Exception("NFT creation failed")
    
    raise Exception("Transaction timeout")

def exchange_nft(signer, nonce, student_nft_id, student_nft_nonce):
    sender_address = signer.get_pubkey().to_address(hrp="erd")
    account = provider.get_account(sender_address)
    
    payment = TokenPayment(
        token_identifier=student_nft_id,
        nonce=student_nft_nonce,
        amount=str(1)
    )
    
    tx = Transaction(
        chain_id=network_config.chain_id,
        sender=sender_address.to_bech32(),
        receiver=CONTRACT_ADDRESS,
        gas_limit=10000000,
        nonce=account.nonce,
        value="0",
        data=f"exchangeNft@{nonce}".encode(),
        version=1,
        gas_price=network_config.min_gas_price,
        esdt_value=payment
    )
    
    tx.signature = signer.sign(transaction_computer.compute_bytes_for_signing(tx))
    tx_hash = provider.send_transaction(tx)
    print(f"Exchange hash: {tx_hash}")
    
    for _ in range(30):
        time.sleep(1)
        tx_info = provider.get_transaction(tx_hash)
        if tx_info.status == "success":
            return tx_hash
        elif tx_info.status == "fail":
            raise Exception("Exchange failed")
            
    raise Exception("Transaction timeout")

def wait_for_transaction(tx_hash, timeout=30):
    for _ in range(timeout):
        time.sleep(1)
        tx_info = provider.get_transaction(tx_hash)
        if hasattr(tx_info, 'status'):
            if tx_info.status == "success":
                return tx_info
            elif tx_info.status == "fail":
                raise Exception(f"Transaction failed: {tx_info.smart_contract_results[0].data if hasattr(tx_info, 'smart_contract_results') else 'Unknown error'}")
    raise Exception("Transaction timeout")

def main():
    signer = load_wallet()
    
    try:
        print("Getting assigned NFT properties...")
        my_props = get_assigned_nft_properties(signer)
        print("Assigned NFT properties:", my_props)
        
        print("\nCreating NFT with matching properties...")
        nft_hash = create_nft(signer, my_props)
        nft_tx = wait_for_transaction(nft_hash)
        
        if not hasattr(nft_tx, 'tokens') or not nft_tx.tokens:
            print("No token information in transaction")
            return
            
        nft_id = nft_tx.tokens[0].identifier
        nft_nonce = nft_tx.tokens[0].nonce
        print(f"Created NFT - ID: {nft_id}, nonce: {nft_nonce}")
        
        print("\nQuerying available NFTs...")
        nfts = query_available_nfts()
        print("Available NFTs:")
        for nft in nfts:
            print(f"Nonce: {nft['nonce']}")
            print(f"Properties: {nft['properties']}\n")
        
        matching_nft = next((nft for nft in nfts 
                            if nft['properties'] == my_props), None)
        
        if matching_nft:
            print(f"Found matching NFT with nonce: {matching_nft['nonce']}")
            print("Initiating exchange...")
            exchange_hash = exchange_nft(signer, matching_nft['nonce'], nft_id, nft_nonce)
            wait_for_transaction(exchange_hash)
            print("Exchange successful!")
        else:
            print("No matching NFT found")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()