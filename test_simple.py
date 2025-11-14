#!/usr/bin/env python3
import requests
import json

# Test the start_job endpoint
url = "http://localhost:8000/start_job"
data = {
    "sender_address": "NICKXD44FJQJZ2O5QLHS4FQSRX6WHHTSZG6HBQK4TJIOMHNVUSML33XITQ",
    "job_input": "Translate hello to Spanish", 
    "agent_id": "agent_001"
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")