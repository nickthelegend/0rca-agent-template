from algosdk.v2client import algod
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer, 
    AccountTransactionSigner, 
    TransactionWithSigner
)
from algosdk.transaction import PaymentTxn
from algosdk.abi import Method
from algosdk import mnemonic
from algokit_utils.transactions.transaction_composer import populate_app_call_resources
from algokit_utils import PaymentParams, AlgoAmount
from algosdk import transaction
from algosdk.encoding import msgpack_encode

# Algod client (Testnet)
client = algod.AlgodClient("", "https://testnet-api.algonode.cloud")

# Account
mn = "announce feed swing base certain rib rose phrase crouch rotate voyage enroll same sort flush emotion pulp airport notice inject pelican zero blossom about honey"
private_key = mnemonic.to_private_key(mn)
sender = "NICKXD44FJQJZ2O5QLHS4FQSRX6WHHTSZG6HBQK4TJIOMHNVUSML33XITQ"

receiver = "WAKOSD5LW5FQ5LZZ5AXNWIKGS6QIDMJWCHAMSWV7YRLBD6NYZMLHVNVOOY"
app_id = 749378614

# Method definition (must match your contract exactly!)
method = Method.from_signature("pay(pay)void")

# Setup signer
signer = AccountTransactionSigner(private_key)

# Composer
atc = AtomicTransactionComposer()

# choose the index you want to reference

sp = client.suggested_params()
sp.flat_fee = True
sp.fee = 2000  # Set your desired static fee in microAlgos

atc.add_method_call(
    app_id=app_id,
    method=method,
    sender=sender,
    sp=sp,
    signer=signer,
    method_args=[
        TransactionWithSigner(
            PaymentTxn(
                sender=sender,
                sp=sp,
                receiver=receiver,
                amt=1000000,  # 1 Algo
            ),
            signer
        )
    ],
    
    
)



atc = populate_app_call_resources(atc, client)
group = atc.build_group()


# Extract the Transaction object and encode to msgpack
for tws in group:
    txn = tws.txn  # Get the Transaction object
    id = tws.txn.get_txid()  # Get the Transaction object
    print(id)  # This is the msgpack-encoded unsigned transaction

    unsigned_bytes = msgpack_encode(txn)
    print(unsigned_bytes)  # This is the msgpack-encoded unsigned transaction
# Execute
# result = atc.execute(client, 4)
# print("✅ Success in round:", result.confirmed_round)
# print("Txn ID:", result.tx_ids[0])
# group_id = transaction.calculate_group_id(result.tx_ids)  # txns is a list of unsigned Transaction objects
