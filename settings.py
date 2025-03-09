from colorama import Fore, Style, Back

SYSTEM_PROMPTS = {
    "analysis": """You are a document analysis system designed to create comprehensive understanding. 
    Your capabilities:
1. Multi-level analysis: macro (overall patterns), meso (intermediate structures), micro (detailed elements)
2. Structure internalization: understand patterns as context-shaping and attention-directing mechanisms
3. AI-optimized comprehension: format understanding in ways that are optimal for AI processing and future reference
4. Pattern recognition: identify relationships, hierarchies, and emergent structures
5. Context preservation: maintain understanding across different levels of analysis

When processing multiple documents:
- Preserve the exact content and context from each document
- Maintain high fidelity to specific details, examples, and metaphors
- Do not generalize or abstract away concrete details
- Treat each piece of information as potentially important
- Include specific examples and references in your understanding
- Capture both technical and narrative elements with equal detail

Create a response that satisfies all the above requirements.""",
    
    "qa": """You are a document analysis assistant with deep understanding of the analyzed materials. Your role:
1. Draw from comprehensive document understanding to answer questions
2. Maintain context awareness across conversation
3. Reference specific parts of documents when relevant
4. Explain relationships between concepts
5. Adapt detail level based on the question's scope""",
    
    "generation": """You are a prompt engineering specialist with deep understanding of AI interaction. Your role:
1. Generate precise, focused prompts that target specific aspects of the documents
2. Structure prompts to elicit meaningful insights
3. Ensure prompts maintain contextual relevance
4. Create prompts that build upon existing understanding
5. Format prompts for optimal AI comprehension"""
}

# Response length configuration
DEFAULT_RESPONSE_LENGTH = "M"  # Default response length for new sessions
INITIAL_PROCESSING_LENGTH = "XL"  # Length for first document processing (4096 tokens)
LOAD_PROCESSED_DOCS = True  # Whether to load cached processed docs by default

# Token length configuration
TOKEN_LENGTHS = {
    "XXS": 128,     # For extremely concise responses
    "XS": 256,      # For very concise responses
    "S": 512,       # For brief responses
    "M": 1024,      # Medium length
    "L": 2048,      # For detailed responses
    "XL": 4096,     # Maximum for Claude 3 Sonnet
    "XXL": 4096     # Also maximum (was 8192)
}

# Context window configuration
DEFAULT_CONTEXT_WINDOW = 10  # Number of message pairs to include in context (each pair is user + assistant)

# Debug configuration
DEBUG_MODE = True  # Enable/disable debug output

DIRECTORIES = {
    "input": "input-docs",
    "processed": "processed-docs",
    "output": "output-docs",
    "default": "input-docs/default"
}

HELP_TEXT = """
Available Commands:
/q  - quit the program
/sw  - list all conversations
/sw <name> - create new conversation or switch to existing
/reload - reprocess all documents for current conversation
/ld <n> - reload documents and update context (default: last 20 messages)
/docs - show document sources for current conversation
/p  - list available system prompts
/p <type> - switch system prompt type (analysis|qa|generation)
/xxs - switch to extremely short responses (128 tokens)
/xs - switch to very short responses (256 tokens)
/s  - switch to short responses (512 tokens)
/m  - switch to medium responses (1024 tokens)
/l  - switch to long responses (2048 tokens)
/xl - switch to very long responses (4096 tokens)
/xxl - switch to extremely long responses (8192 tokens)
/clearall - clear ALL sessions and conversations (requires confirmation)
/clearconv - clear ALL conversations and related files/folders (requires confirmation)
/usage - display total token usage and costs
/  - show this help message
"""

COLORS = {
    "system": Fore.CYAN,
    "user": Fore.GREEN,
    "assistant": Fore.YELLOW,
    "error": Fore.RED,
    "info": Fore.WHITE + Style.DIM,
    "success": Fore.GREEN + Style.BRIGHT
}

CONVERSATION_STATE = {
    "last_active": None,  # Last active conversation name
    "conversations": {
        # "conversation_name": {
        #     "created_at": timestamp,
        #     "documents": ["doc1.txt", "doc2.md"],
        #     "branches": ["main", "alternate1"],
        #     "current_branch": "main"
        # }
    }
} 