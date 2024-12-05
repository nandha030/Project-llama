from llama_cpp import Llama
import os
import time
from datetime import datetime

def log_progress(message, level="INFO"):
    """Logs progress with timestamp and level."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def test_model():
    """Test the LLaMA GGUF model using the llama-cpp integration."""
    try:
        log_progress("=== Starting Model Test Process ===")
        
        # Stage 1: Model Location
        log_progress("Stage 1: Locating GGUF model file")
        model_path = "/home/nandha/llama_models/llama-2-13b-chat.Q4_K_M.gguf"
        
        if not os.path.exists(model_path):
            log_progress("Model file not found - cannot proceed", "ERROR")
            input("Press Enter to exit...")
            return False
        
        log_progress(f"Model file found at: {model_path}", "SUCCESS")
        
        # Stage 2: Model Loading
        log_progress("Stage 2: Initializing model")
        log_progress(f"Configuring model with parameters: n_ctx=2048, n_batch=512, n_threads=6")
        
        start_time = time.time()
        llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_batch=512,
            n_threads=6
        )
        load_time = time.time() - start_time
        log_progress(f"Model initialized successfully in {load_time:.2f} seconds", "SUCCESS")
        
        # Stage 3: Model Testing
        log_progress("Stage 3: Testing model with sample prompt")
        prompt = "Hello, how are you?"
        log_progress(f"Test prompt: '{prompt}'")
        
        start_time = time.time()
        response = llm.create_completion(
            prompt,
            max_tokens=128,
            temperature=0.7
        )
        inference_time = time.time() - start_time
        
        log_progress(f"Response generated in {inference_time:.2f} seconds", "SUCCESS")
        log_progress("Model response:")
        print("-" * 50)
        print(response["choices"][0]["text"])
        print("-" * 50)
        
        # Stage 4: Performance Summary
        log_progress("Stage 4: Generating performance summary")
        print("\nPerformance Summary:")
        print(f"- Model size: {os.path.getsize(model_path) / (1024*1024*1024):.2f} GB")
        print(f"- Load time: {load_time:.2f} seconds")
        print(f"- Inference time: {inference_time:.2f} seconds")
        
        log_progress("=== Model Test Process Completed Successfully ===", "SUCCESS")
        
        input("\nPress Enter to exit...")
        return True
        
    except Exception as e:
        log_progress(f"Critical error occurred: {str(e)}", "ERROR")
        log_progress("Stack trace:", "DEBUG")
        import traceback
        print(traceback.format_exc())
        input("\nPress Enter to exit...")
        return False

if __name__ == "__main__":
    log_progress("=== Starting GGUF Model Test Application ===")
    test_model()
