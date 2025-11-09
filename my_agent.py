import openai
import os

# Set OpenAI API key from environment
openai.api_key = os.getenv("OPENAI_API_KEY", "")

def process_job(job_input):
    """
    AI Agent powered by OpenAI GPT-4o-mini
    
    This agent can handle:
    - Text generation and creative writing
    - Translation between languages
    - Code generation and explanation
    - Analysis and summarization
    - Question answering
    - And much more!
    """
    
    try:
        # Use OpenAI's most cost-effective model
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful AI agent. Provide concise, accurate, and useful responses."
                },
                {
                    "role": "user", 
                    "content": job_input
                }
            ],
            max_tokens=500,  # Reasonable limit for cost control
            temperature=0.7  # Balanced creativity
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        # Fallback to simple processing if OpenAI fails
        return f"AI processing failed, fallback result: {job_input} (Error: {str(e)})"