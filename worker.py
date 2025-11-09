import time
import threading
from database import get_db, update_job_status, complete_job
from my_agent import process_job

def get_running_jobs():
    """Get jobs that are in running status"""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM jobs_local WHERE status = 'running' ORDER BY created_at"
        ).fetchall()

def execute_job(job_id):
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
        
        print(f"Processing job {job_id}: {job['job_input']}")
        
        # Process job using agent logic
        result = process_job(job['job_input'])
        
        # Complete the job
        complete_job(job_id, result)
        print(f"Job {job_id} completed successfully")
        
    except Exception as e:
        print(f"Job {job_id} failed: {str(e)}")
        update_job_status(job_id, "failed")

def run_worker():
    """Main worker loop - processes running jobs"""
    print("Worker started. Monitoring for running jobs...")
    
    while True:
        try:
            # Get all running jobs
            running_jobs = get_running_jobs()
            
            for job in running_jobs:
                job_id = job['job_id']
                
                # Execute job in separate thread to allow parallel processing
                thread = threading.Thread(target=execute_job, args=(job_id,))
                thread.daemon = True
                thread.start()
            
            # Wait before checking again
            time.sleep(5)
            
        except Exception as e:
            print(f"Worker error: {e}. Continuing...")
            time.sleep(10)

if __name__ == "__main__":
    run_worker()