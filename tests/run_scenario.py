import os
import sys
import time

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document_processor import DocumentProcessor
from dotenv import load_dotenv

def print_doc_contents(docs, conversation_name):
    print(f"\nDocuments loaded for {conversation_name}:")
    for filename, content in docs.items():
        print(f"\n=== {filename} ===")
        print(content[:200] + "..." if len(content) > 200 else content)

def run_scenario():
    # Load environment variables
    load_dotenv()
    
    # Initialize processor
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    processor = DocumentProcessor(api_key=api_key)
    
    # Main conversation - will automatically load default + main docs
    print("\n=== Main Conversation ===")
    processor.create_conversation("main")
    
    tech_response = processor.ask_question("Tell me exactly what specifically the Temporal-Adaptive Mesh Hybrid is")
    time.sleep(1)
    
    metaphor_response = processor.ask_question("Tell me specifically about the wizard and balding man metaphor i provided you, and also tell me about the crown and gems metaphor I provided you")
    time.sleep(1)
    
    # Switch to test conversation - will automatically load default + test docs
    print("\n=== Test Conversation ===")
    processor.switch_conversation("test")
    
    tech_response = processor.ask_question("Tell me exactly what specifically the Temporal-Adaptive Mesh Hybrid is")
    time.sleep(1)
    
    metaphor_response = processor.ask_question("Tell me specifically about the wizard and balding man metaphor i provided you, and also tell me about the crown and gems metaphor I provided you")
    
    print("\n=== Scenario Complete ===")

if __name__ == "__main__":
    run_scenario() 