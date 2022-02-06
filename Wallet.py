import hashlib
import json
from collections import namedtuple
from Block import ClsEncoder
import random

import binascii
import mnemonic
import bip32utils
import hmac


Transaction = namedtuple('Transaction', ['ver', 'sender', 'receivers',
                                         'outputs', 'proof'])
"""Transaction namedtuple. It's a namedtuple named to store all the information
related to the trasaction
Args:
    ver (str): The transaction version. Used to add support to the variety of 
    versions that might come later without making older version invalid.

    sender (str): The sender's address
    
    receivers (tuple): The receivers addresses. correct format for each address
    ([addr],[amount in string]). to add fees change addr to 'FEES'
    
    outputs (tuple): Unspent transaction outputs. Correct format for each output
    is ([block_id], [transaction_id], [output_id]) all in type string

    proof (tuple): A proof that ensures the sender is the owner of this address 
    and its outputs. It consists of a tuple with the public key of the sender
    and the signature of the transaction. 
    
"""
    


class Wallet:

    def __init__(self, mnemonic_words=None):
        """Class for handling the hd wallet. Currently uses bip39 standard with
        only 1 account and no categories.
        generates an hd wallet with on the coin's network

        Args:
            mnemonic_words (str): mnomic words to make the keys from
        """
        
        mnemo = mnemonic.Mnemonic("english")

        if mnemonic_words is None:
            mnemonic_words = mnemo.generate(strength=256)

        
        seed = mnemo.to_seed(mnemonic_words)

        # DO NOT share this key
        master_key = bip32utils.BIP32Key.fromEntropy(seed) 
        
        # This is the master key in path m/44'/69420'/0'/0
        master_coin_key = master_key.ChildKey(
            44 + bip32utils.BIP32_HARDEN
        ).ChildKey(
            69420 + bip32utils.BIP32_HARDEN
        ).ChildKey(
            0 + bip32utils.BIP32_HARDEN
        ).ChildKey(0).ChildKey(0)
   
        self.words = mnemonic_words
        self.addr = master_coin_key.Address()
        self.pub_k = binascii.hexlify(master_coin_key.PublicKey()).decode()
        # Private key is in wif (Wallet import format)
        self.priv_k = master_coin_key.PrivateKey()
        self.wif = master_coin_key.WalletImportFormat()
        
        self.utxos = list()
    
    
    def __repr__(self):
        return f'Wallet({self.words}, {self.addr}, {self.pub_k}, {self.priv_k})'
    
    def __str__(self):
        return json.dumps(self, ensure_ascii=False, indent=4, cls=ClsEncoder)
    
    def update_utxo(self, blockchain):
        """Get all the unspent transaction token from the blockchain.
        WARNING: might be very slow when the blockchain gets big. It is 
        recommended to use it only once when you reuse a wallet's 
        private key/mnemonic words

        Args:
            blockchain (Blockchain): The blockchain to retrieve the utxos from
        """
        utxo = blockchain.find_txns(self.addr)
        
    def sign(self, data):
        """Sign the given data using the wallet's private key. meant to be an
        internal function


        Args:
            data (str): the data to be signed

        Returns:
            string: the signature of the given data in hexadecimal format
        """
        return hmac.new(self.priv_k, data.encode(), hashlib.sha256).hexdigest()
    
    def send(self, fee, *recv_addrs):
        """Creates a new transaction to send other nodes. If the outputs are
        bigger than the value to be send, the change is sent back to the wallet
        as a new output

        Args:
            fee (int): the amount of coins to leave as a fee
            
            *recv_addrs (tuple): tuples containing addresses to send to with 
            the amount specified
            

        Raises:
            NotEnoughFundsError: This means the user tried to send more funds 
            than he has in his wallet
        
        Returns:
            namedtuple(Transaction): The newly created transaction
        """
        
        # Check if user has enough balance
        total = 0
        for addr in recv_addrs:
            total += addr[1]
        
        if total > self.get_balance():
            raise NotEnoughFundsError
        
        ver = '0.1'
        
        #TODO: Create better algorithm for choosing the right utxos
        outputs = []
        utxo_val = 0
        
        
        utxos_temp = self.utxos.copy()
        for i, utxo in enumerate(utxos_temp):
             
            utxo_val += utxo[3]
            # Create a list of outputs that will be used
            outputs.append((utxo[:-1]))
            self.utxos.pop(0)
            i -= 1
            
            if utxo_val > total + fee:
                # Add the remainder as a new output
                recv_addrs += ((self.addr, utxo_val - total - fee), )
                break
            elif utxo_val == total + fee: 
                break
            
        # To keep transaction signature consistent, we add fees even if its 0
        signature = self.sign(f"{ver}{self.addr}{recv_addrs}{('FEES', fee)}")
        proof = (self.pub_k, signature)
        
        if fee > 0:
                recv_addrs += recv_addrs + (('FEES', fee), )
                
        txn = Transaction(ver, self.addr, str(recv_addrs), str(outputs), proof)
        
        return txn
    
    
    def debug_send(self, fee, *recv_addrs):
        """same as send but for debugging purposes. Generates Transactions with
        no outputs and therefore will not be accepted in the network

        Args:
            fee (int): the amount of coins to leave as a fee
            
            *recv_addrs (tuple): tuples containing addresses to send to with 
            the amount specified
        
        Returns:
            namedtuple(Transaction): The newly created transaction
        """
        
        ver = '0.1'
        
        signature = self.sign(f"{ver}{self.addr}{recv_addrs}{('FEES', fee)}")
        proof = (self.pub_k, signature)
            
        txn = Transaction(ver, self.addr, recv_addrs + (('FEES', fee), ),
                          [], proof)
        
        return txn
    
    
    def debug_generate_outputs(self, amount, outputs):
        """Generates fake outputs. do not use in a real wallet. Created for
        debugging purposes

        Args:
            amount (int): total amount of money
            outputs (int): number of outputs to divide to
        """
        
        # Remainder
        if not amount % outputs == 0:
            block = random.randint(0, 100)
            txn_id = random.randint(0, 100)
            output_id = random.randint(0, 100)
            self.utxos.append((block, txn_id, output_id, amount % outputs))
            amount -= amount % outputs
            outputs -= 1

        
        
        for _ in range(outputs):
            block = random.randint(0, 100)
            txn_id = random.randint(0, 100)
            output_id = random.randint(0, 100)
            self.utxos.append((block, txn_id, output_id, int(amount / outputs)))
        

        
        
    def get_balance(self):
        """Sums all the Unspent transaction token to check the wallet's balance

        Returns:
            int: The account balance
        """
        
        bal = 0
        for txn in self.utxos:
            bal += txn[3]
        return bal
    


class NotEnoughFundsError(Exception):
    
    def __init__(self, message="Target wallet doesnt have enough funds"):
        super().__init__(message)
        
    