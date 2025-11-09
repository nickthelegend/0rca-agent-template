from flask import Flask, request, jsonify
import json
import base64
import sys
from database import init_db, create_job, get_job, update_job_payment_processing, update_job_status, complete_job, create_access_token, verify_access_token, get_db
import threading
import time
from algosdk.v2client import algod, indexer
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, AccountTransactionSigner, TransactionWithSigner
from algosdk.transaction import PaymentTxn
from algosdk.abi import Method
from algosdk import mnemonic
from algokit_utils.transactions.transaction_composer import populate_app_call_resources
from algosdk.encoding import msgpack_encode
from my_agent import process_job

app = Flask(__name__)

# Algorand configuration
client = algod.AlgodClient("", "https://testnet-api.algonode.cloud")
indexer_client = indexer.IndexerClient("", "https://testnet-idx.algonode.cloud")
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
    """Execute the AI agent job using modular agent logic"""
    job = get_job(job_id)
    if not job:
        return
    
    try:
        # Use modular agent logic from my_agent.py
        output = process_job(job['job_input'])
        
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
        
        # Generate access token
        access_token = create_access_token(job_id, "agent_001")  # Use agent_id from job if stored
        
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
    
    # Validate Algorand address format
    if len(sender_address) != 58:
        return jsonify({"error": "Invalid sender_address: must be 58 characters"}), 400
    
    job_id, job_input_hash = create_job(job_input, sender_address)
    
    try:
        # Generate real unsigned group transactions
        unsigned_txns, txn_ids = generate_unsigned_txns(sender_address, agent_id, job_id)
        
        return jsonify({
            "job_id": job_id,
            "unsigned_group_txns": unsigned_txns,
            "txn_ids": txn_ids,
            "payment_required": 1_000_000
        })
    except Exception as e:
        return jsonify({"error": f"Failed to generate transactions: {str(e)}"}), 500

@app.route("/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    """Get job status and result"""
    # Check for access token
    access_token = request.args.get('access_token')
    
    if access_token:
        # Verify access token
        if not verify_access_token(job_id, access_token):
            return jsonify({"error": "Invalid or expired access token"}), 401
        
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

def get_running_jobs():
    """Get jobs that are in running status"""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM jobs_local WHERE status = 'running' ORDER BY created_at"
        ).fetchall()

def worker_execute_job(job_id):
    """Execute a single job using the agent logic"""
    try:
        # Get job details
        with get_db() as conn:
            job = conn.execute(
                "SELECT * FROM jobs_local WHERE job_id = ?", (job_id,)
            ).fetchone()
        
        if not job:
            print(f"Job {job_id} not found")
            return
        
        print(f"Worker processing job {job_id}: {job['job_input']}")
        
        # Process job using agent logic
        result = process_job(job['job_input'])
        
        # Complete the job
        complete_job(job_id, result)
        print(f"Worker completed job {job_id}")
        
    except Exception as e:
        print(f"Worker job {job_id} failed: {str(e)}")
        update_job_status(job_id, "failed")

def run_worker():
    """Background worker loop"""
    print("Background worker started...")
    
    while True:
        try:
            # Get all running jobs
            running_jobs = get_running_jobs()
            
            for job in running_jobs:
                job_id = job['job_id']
                
                # Execute job in separate thread
                thread = threading.Thread(target=worker_execute_job, args=(job_id,))
                thread.daemon = True
                thread.start()
            
            # Wait before checking again
            time.sleep(5)
            
        except Exception as e:
            print(f"Worker error: {e}. Continuing...")
            time.sleep(10)

if __name__ == "__main__":
    init_db()
    
    # Start background worker unless --web-only flag
    if "--web-only" not in sys.argv:
        print("Starting integrated background worker...")
        worker_thread = threading.Thread(target=run_worker, daemon=True)
        worker_thread.start()
    else:
        print("Running in web-only mode (no background worker)")
    
    print("Starting web server on http://localhost:8000")
    app.run(host="0.0.0.0", port=8000)
