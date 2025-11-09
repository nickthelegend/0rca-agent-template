from flask import Flask, request, jsonify
import json
import base64
from database import init_db, create_job, get_job, update_job_payment_processing
from algosdk.v2client import algod
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, AccountTransactionSigner, TransactionWithSigner
from algosdk.transaction import PaymentTxn
from algosdk.abi import Method
from algosdk import mnemonic
from algokit_utils.transactions.transaction_composer import populate_app_call_resources
from algosdk.encoding import msgpack_encode

app = Flask(__name__)

# Algorand configuration
client = algod.AlgodClient("", "https://testnet-api.algonode.cloud")
receiver = "WAKOSD5LW5FQ5LZZ5AXNWIKGS6QIDMJWCHAMSWV7YRLBD6NYZMLHVNVOOY"
app_id = 749378614
method = Method.from_signature("pay(pay)void")

def generate_unsigned_txns(sender_address, agent_id, job_id):
    """Generate real unsigned Algorand transactions"""
    # Create dummy signer for transaction building (won't be used for signing)
    dummy_private_key = mnemonic.to_private_key("announce feed swing base certain rib rose phrase crouch rotate voyage enroll same sort flush emotion pulp airport notice inject pelican zero blossom about honey")
    signer = AccountTransactionSigner(dummy_private_key)
    
    atc = AtomicTransactionComposer()
    sp = client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000
    
    atc.add_method_call(
        app_id=app_id,
        method=method,
        sender=sender_address,
        sp=sp,
        signer=signer,
        method_args=[
            TransactionWithSigner(
                PaymentTxn(
                    sender=sender_address,
                    sp=sp,
                    receiver=receiver,
                    amt=1000000
                ),
                signer
            )
        ]
    )
    
    atc = populate_app_call_resources(atc, client)
    group = atc.build_group()
    
    unsigned_txns = []
    txn_ids = []
    
    for tws in group:
        txn = tws.txn
        txn_id = txn.get_txid()
        txn_ids.append(txn_id)
        
        unsigned_bytes = msgpack_encode(txn)
        if isinstance(unsigned_bytes, str):
            unsigned_bytes = unsigned_bytes.encode()
        unsigned_txns.append(base64.b64encode(unsigned_bytes).decode())
    
    # Update job status to payment_processing with txn_ids
    update_job_payment_processing(job_id, txn_ids)
    
    return unsigned_txns

@app.route("/")
def hello():
    return "Agent Server Running"

@app.route("/start_job", methods=["POST"])
def start_job():
    """Start a new job and return job_id with unsigned transactions"""
    data = request.get_json()
    required_fields = ["sender_address", "job_input", "agent_id"]
    
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "sender_address, job_input, and agent_id required"}), 400
    
    sender_address = data["sender_address"]
    job_input = data["job_input"]
    agent_id = data["agent_id"]
    
    job_id, job_input_hash = create_job(job_input, sender_address)
    
    # Generate real unsigned group transactions
    unsigned_txns = generate_unsigned_txns(sender_address, agent_id, job_id)
    
    return jsonify({
        "job_id": job_id,
        "unsigned_group_txns": unsigned_txns,
        "payment_required": 1_000_000
    })

@app.route("/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    """Get job status and result"""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify({
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "output": job["output"]
    })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
