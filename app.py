from flask import Flask, request, jsonify
import json
import base64
from database import init_db, create_job, get_job, update_job_payment_processing, update_job_status, complete_job, create_access_token, verify_access_token
import threading
import time
from algosdk.v2client import algod, indexer
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, AccountTransactionSigner, TransactionWithSigner, TransactionSigner
from algosdk.transaction import PaymentTxn
from algosdk.abi import Method
from algosdk import mnemonic
from algokit_utils.transactions.transaction_composer import populate_app_call_resources
from algosdk.encoding import msgpack_encode

app = Flask(__name__)

# Algorand configuration
client = algod.AlgodClient("", "https://testnet-api.algonode.cloud")
indexer_client = indexer.IndexerClient("", "https://testnet-idx.algonode.cloud")
receiver = "WAKOSD5LW5FQ5LZZ5AXNWIKGS6QIDMJWCHAMSWV7YRLBD6NYZMLHVNVOOY"
app_id = 749378614
method = Method.from_signature("pay(pay)void")

def generate_unsigned_txns(sender_address, agent_id, job_id):
    """Generate real unsigned Algorand transactions"""
    class NoOpSigner(TransactionSigner):
        def sign(self, txn_group):
            # Never signs anything
            raise Exception("Unsigned transaction composer")
            # Some versions call this internally
        def sign_transactions(self, txns):
            raise Exception("This signer does not sign transactions.")

    signer = NoOpSigner()

    atc = AtomicTransactionComposer()
    sp = client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2000

    # Add method call
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

    # Skip populate_app_call_resources to avoid simulation
    group = atc.build_group()

    unsigned_txns = []
    txn_ids = []

    for tws in group:
        txn = tws.txn
        txn_ids.append(txn.get_txid())

        packed = msgpack_encode(txn)

        # <-- Fix here
        if isinstance(packed, str):
            packed = packed.encode()

        unsigned_txns.append(base64.b64encode(packed).decode())

    update_job_payment_processing(job_id, txn_ids)
    return unsigned_txns, txn_ids

def verify_transactions(job_id, submitted_txids):
    """Verify submitted transactions match job requirements"""
    job = get_job(job_id)
    if not job:
        return False, "Job not found"
    
    expected_txids = job["txn_ids"].split(',') if job["txn_ids"] else []
    
    if set(submitted_txids) != set(expected_txids):
        return False, "Transaction IDs don't match expected"
    
    # Verify each transaction on chain
    for txid in submitted_txids:
        try:
            txn_info = indexer_client.transaction(txid)
            txn = txn_info['transaction']
            
            # Verify sender matches job sender
            if txn['sender'] != job['sender_address']:
                return False, f"Sender mismatch for txn {txid}"
            
            # Verify transaction type and details
            if txn['tx-type'] == 'pay':
                if txn['payment-transaction']['receiver'] != receiver:
                    return False, f"Payment receiver mismatch for txn {txid}"
                if txn['payment-transaction']['amount'] != 1000000:
                    return False, f"Payment amount mismatch for txn {txid}"
            
            elif txn['tx-type'] == 'appl':
                if txn['application-transaction']['application-id'] != app_id:
                    return False, f"App ID mismatch for txn {txid}"
                
                # Verify ABI method selector
                app_args = txn['application-transaction'].get('application-args', [])
                if app_args:
                    method_selector = base64.b64decode(app_args[0])
                    expected_selector = method.get_selector()
                    if method_selector != expected_selector:
                        return False, f"Method selector mismatch for txn {txid}"
        
        except Exception as e:
            return False, f"Failed to verify txn {txid}: {str(e)}"
    
    return True, "All transactions verified"

def execute_job(job_id):
    """Execute the AI agent job"""
    job = get_job(job_id)
    if not job:
        return
    
    try:
        # Simulate AI processing time
        time.sleep(2)
        
        job_input = job['job_input']
        
        # Simple AI agent logic based on input
        if 'translate' in job_input.lower():
            if 'spanish' in job_input.lower():
                output = "Hola (Hello in Spanish)"
            elif 'french' in job_input.lower():
                output = "Au revoir (Goodbye in French)"
            else:
                output = "Translation completed"
        else:
            output = f"Processed: {job_input}"
        
        # Complete the job
        complete_job(job_id, output)
        
    except Exception as e:
        update_job_status(job_id, "failed")

@app.route("/submit_payment", methods=["POST"])
def submit_payment():
    """Verify submitted payment transactions"""
    data = request.get_json()
    
    if not data or "job_id" not in data or "txid" not in data:
        return jsonify({"error": "job_id and txid required"}), 400
    
    job_id = data["job_id"]
    submitted_txids = data["txid"]
    
    if not isinstance(submitted_txids, list):
        return jsonify({"error": "txid must be an array"}), 400
    
    # Verify transactions
    success, message = verify_transactions(job_id, submitted_txids)
    
    if success:
        update_job_status(job_id, "running")
        
        # Get job details for agent_id
        job = get_job(job_id)
        
        # Generate access token with security context
        ip_address = request.environ.get('REMOTE_ADDR')
        user_agent = request.headers.get('User-Agent')
        access_token = create_access_token(job_id, "agent_001", job['sender_address'], ip_address, user_agent)
        
        # Start job execution in background thread
        thread = threading.Thread(target=execute_job, args=(job_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "success", 
            "message": "Payment verified, job started",
            "access_token": access_token
        })
    else:
        return jsonify({
            "status": "error", 
            "message": message
        }), 400

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
    unsigned_txns, txn_ids = generate_unsigned_txns(sender_address, agent_id, job_id)
    
    return jsonify({
        "job_id": job_id,
        "unsigned_group_txns": unsigned_txns,
        "txn_ids": txn_ids,
        "payment_required": 1_000_000
    })

@app.route("/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    """Get job status and result"""
    # Check for access token
    access_token = request.args.get('access_token')
    
    if access_token:
        # Verify access token with security checks
        ip_address = request.environ.get('REMOTE_ADDR')
        user_agent = request.headers.get('User-Agent')
        
        valid, message = verify_access_token(job_id, access_token, ip_address, user_agent)
        if not valid:
            return jsonify({"error": message}), 401
        
        # Return full job details including output
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        
        return jsonify({
            "job_id": job["job_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "output": job["output"]
        })
    else:
        # Without access token, return limited info
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        
        return jsonify({
            "job_id": job["job_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "output": None  # Hide output without access token
        })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
