from anthropic import Anthropic, InternalServerError, RateLimitError
from instructor import Instructor, Mode, patch
from pydantic import BaseModel
import os
from typing import List, Optional
import json
from datetime import datetime
from settings import (
    SYSTEM_PROMPTS, TOKEN_LENGTHS, HELP_TEXT, COLORS, 
    DEFAULT_CONTEXT_WINDOW, DIRECTORIES, DEFAULT_RESPONSE_LENGTH, 
    INITIAL_PROCESSING_LENGTH, LOAD_PROCESSED_DOCS, DEBUG_MODE
)
from colorama import init, Fore, Style
from session_manager import Session, SessionManager
import time
from functools import wraps
import random

def retry_with_exponential_backoff(max_retries=5, initial_delay=1, max_delay=32):
    """Retry decorator with exponential backoff for rate limits and overload errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for retry in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not isinstance(e, (RateLimitError, InternalServerError)):
                        raise e
                    
                    if retry == max_retries - 1:
                        raise e
                    
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0, 0.1) * delay
                    sleep_time = delay + jitter
                    error_type = "rate limit" if isinstance(e, RateLimitError) else "server overload"
                    print(f"{COLORS['info']}API {error_type} hit. Retrying in {sleep_time:.1f} seconds...{Style.RESET_ALL}")
                    time.sleep(sleep_time)
                    delay = min(delay * 2, max_delay)
            return None
        return wrapper
    return decorator

class Document(BaseModel):
    name: str
    content: str

class DocumentUnderstanding(BaseModel):
    documents: List[Document]
    summary: str

class Message(BaseModel):
    role: str
    content: str
    prompt_id: Optional[str] = None

class DocumentProcessor:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with optional API key. If not provided, will try to get from environment"""
        init()  # Initialize colorama
        # Add debug logging
        env_key = os.getenv('ANTHROPIC_API_KEY')
        print(f"Environment API key found: {'Yes' if env_key else 'No'}")
        
        self.api_key = api_key or env_key
        if not self.api_key:
            raise ValueError("API key must be provided either through constructor or ANTHROPIC_API_KEY environment variable")
            
        # Initialize Anthropic client
        self.anthropic = Anthropic(api_key=self.api_key)
        
        # Initialize usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0  # Cost in USD
        # Claude 3 Sonnet pricing per 1K tokens
        self.input_token_price = 0.003  # $0.003 per 1K input tokens
        self.output_token_price = 0.015  # $0.015 per 1K output tokens
        
        self.documents = {}
        self.output_dir = "output-docs"
        self.conversation_history = []
        self.ensure_output_dir()
        self.system_prompts = SYSTEM_PROMPTS
        self.max_tokens = TOKEN_LENGTHS[DEFAULT_RESPONSE_LENGTH]  # Use configured default
        self.message_window = []
        self.document_summary = None
        self.window_size = DEFAULT_CONTEXT_WINDOW
        self.session_manager = SessionManager()
        self.current_session: Optional[Session] = None
        self.current_system_prompt = "analysis"
        
        # Clear and initialize debug log
        if DEBUG_MODE:
            debug_dir = "debug"
            if os.path.exists(debug_dir):
                for f in os.listdir(debug_dir):
                    os.remove(os.path.join(debug_dir, f))
            os.makedirs(debug_dir, exist_ok=True)
            
            self.debug_file = os.path.join(debug_dir, f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
        
    def ensure_output_dir(self):
        """Create output directory if it doesn't exist"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def load_documents_from_directory(self, input_dir: str) -> dict:
        """Load all documents from the specified directory"""
        if not os.path.exists(input_dir):
            raise ValueError(f"Input directory '{input_dir}' does not exist")
            
        documents = {}
        print(f"{COLORS['info']}Loading documents:{Style.RESET_ALL}")
        for filename in os.listdir(input_dir):
            if filename.endswith(('.txt', '.md', '.doc', '.docx', '.pdf')):
                file_path = os.path.join(input_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        print(f"{COLORS['info']}  • Reading {filename}...{Style.RESET_ALL}")
                        documents[filename] = file.read()
                except Exception as e:
                    print(f"{COLORS['error']}Error loading {file_path}: {str(e)}{Style.RESET_ALL}")
                    
        if not documents:
            print(f"{COLORS['error']}Warning: No documents were loaded from the input directory{Style.RESET_ALL}")
        else:
            print(f"{COLORS['success']}Loaded {len(documents)} documents{Style.RESET_ALL}")
        
        return documents

    def set_response_length(self, length: str) -> str:
        """Set the response length and return confirmation message"""
        # Convert input to uppercase to match new keys
        length = length.upper()
        if length not in TOKEN_LENGTHS:
            return f"Invalid length. Available options: {', '.join(TOKEN_LENGTHS.keys())}"
        
        self.max_tokens = TOKEN_LENGTHS[length]
        return f"Response length set to {length} ({self.max_tokens} tokens)"

    @retry_with_exponential_backoff()
    def process_documents(self, docs: dict, name: str) -> str:
        """Initial document processing with session creation"""
        print(f"\n{COLORS['info']}Document Processing Flow:{Style.RESET_ALL}")
        
        # Check for existing processed documents
        processed_dir = os.path.join(DIRECTORIES['processed'], name)
        understanding_path = os.path.join(processed_dir, 'understanding.md')
        
        if os.path.exists(understanding_path) and LOAD_PROCESSED_DOCS:
            print(f"{COLORS['info']}Loading existing document understanding...{Style.RESET_ALL}")
            with open(understanding_path, 'r') as f:
                content = f.read()
                # Extract summary from the markdown file (skip the header and system prompt)
                summary_start = content.find("\n\n", content.find("```\n\n")) + 2
                summary = content[summary_start:]
                
                # Create document models for session
                documents = [
                    Document(name=filename, content=content)
                    for filename, content in docs.items()
                ]
                
                # Create understanding object
                understanding = DocumentUnderstanding(
                    documents=documents,
                    summary=summary
                )
                
                # Create new session
                self.current_session = Session.create_new(name, json.dumps(understanding.model_dump()))
                self.session_manager.save_session(self.current_session)
                
                print(f"{COLORS['success']}✓ Loaded from: {understanding_path}{Style.RESET_ALL}")
                return summary
        
        # If no existing documents or forced reprocessing, continue with processing
        print(f"{COLORS['info']}Processing documents...{Style.RESET_ALL}")
        
        # Create document models
        documents = [
            Document(name=filename, content=content)
            for filename, content in docs.items()
        ]
        
        # Create system content with proper structure
        system = [
            {
                "type": "text",
                "text": self.system_prompts['analysis']
            },
            {
                "type": "text",
                "text": f"<conversation id='{name}'>\n" + json.dumps([doc.model_dump() for doc in documents]) + "\n</conversation>",
                "cache_control": {"type": "ephemeral"}
            }
        ]
        
        print(f"1. Using Analysis System Prompt:")
        print(f"{COLORS['system']}{self.system_prompts['analysis']}{Style.RESET_ALL}\n")
        
        print(f"2. Processing {len(docs)} documents with {INITIAL_PROCESSING_LENGTH} context...")
        
        # Debug before API call
        self._save_debug_output("process_documents_request", {
            "max_tokens": TOKEN_LENGTHS[INITIAL_PROCESSING_LENGTH],
            "model": "claude-3-5-sonnet-20241022",
            "system": system,
            "messages": [{
                "role": "user",
                "content": "Create a comprehensive analysis and understanding of these documents that can serve as a foundation for future interactions."
            }]
        })
        
        response = self.anthropic.messages.create(
            max_tokens=TOKEN_LENGTHS[INITIAL_PROCESSING_LENGTH],
            model="claude-3-5-sonnet-20241022",
            system=system,
            messages=[{
                "role": "user",
                "content": "Create a comprehensive analysis and understanding of these documents that can serve as a foundation for future interactions."
            }],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        
        # Track usage
        self._track_usage(response)
        
        # Debug after API call
        self._save_debug_output("process_documents_response", {
            "response": response.content[0].text
        })
        
        summary = response.content[0].text
        
        # Create and save document understanding
        understanding = DocumentUnderstanding(
            documents=documents,
            summary=summary
        )
        
        print(f"3. Saving processed understanding:")
        processed_dir = os.path.join(DIRECTORIES['processed'], name)
        os.makedirs(processed_dir, exist_ok=True)
        
        understanding_path = os.path.join(processed_dir, 'understanding.md')
        with open(understanding_path, 'w') as f:
            f.write(f"# Document Understanding\n\nGenerated using system prompt:\n```\n{self.system_prompts['analysis']}\n```\n\n{summary}")
        
        print(f"{COLORS['success']}✓ Saved to: {understanding_path}{Style.RESET_ALL}")
        
        # Create new session
        self.current_session = Session.create_new(name, json.dumps(understanding.model_dump()))
        self.session_manager.save_session(self.current_session)
        
        return summary

    @retry_with_exponential_backoff()
    def ask_question(self, question: str) -> tuple[str, str]:
        if not self.current_session:
            raise ValueError("No active session. Process documents first.")
            
        print(f"\n{COLORS['info']}Question Processing Flow:{Style.RESET_ALL}")
        print(f"1. Using {self.current_system_prompt.upper()} System Prompt with Document Understanding")
        
        # Show conversation context with dimmed paths
        print(f"{COLORS['info']}Active files:{Style.RESET_ALL}")
        print(f"  • System: {COLORS['info']}processed-docs/{self.current_session.name}/{Style.RESET_ALL}understanding.md")
        print(f"  • Conversation: {COLORS['info']}output-docs/{self.current_session.name}/{Style.RESET_ALL}conversation.md")
        print(f"  • Session ID: {self.current_session.session_id}")
        print(f"  • Conversation ID: {self.current_session.conversation_id}")
        
        # Show branch info if it exists
        if self.current_session.branch_info:
            print(f"  • Branch: {self.current_session.branch_info.branch_name} (Parent: {self.current_session.branch_info.parent_id})")
        
        # Load document understanding from session
        understanding = DocumentUnderstanding.model_validate_json(self.current_session.document_summary)
        
        # Create system prompt with document understanding
        system = [
            {
                "type": "text",
                "text": self.system_prompts[self.current_system_prompt]
            },
            {
                "type": "text",
                "text": f"<conversation id='{self.current_session.conversation_id}'>\n" + json.dumps(understanding.model_dump()) + "\n</conversation>",
                "cache_control": {"type": "ephemeral"}
            }
        ]
        
        # Create messages array using models
        messages = []
        for msg in self.current_session.message_window[-self.current_session.window_size:]:
            message = Message(
                role=msg["role"],
                content=msg["content"],
                prompt_id=msg.get("prompt_id")
            )
            messages.append({
                "role": message.role,
                "content": [
                    {
                        "type": "text",
                        "text": message.content
                    }
                ]
            })
        
        # Add current question
        messages.append({
            "role": "user", 
            "content": [
                {
                    "type": "text",
                    "text": question
                }
            ]
        })
        
        # Count previous user messages
        prev_user_messages = len([m for m in self.current_session.message_window if m["role"] == "user"])
        print(f"2. Including {prev_user_messages} recent messages for context")
        
        # Show previous prompt IDs from user messages only
        if self.current_session.message_window:
            user_prompts = [msg["prompt_id"] for msg in self.current_session.message_window 
                           if msg["role"] == "user"][-self.current_session.window_size:]
            if user_prompts:
                print(f"{COLORS['info']}Previous IDs: {', '.join(user_prompts)}{Style.RESET_ALL}")
        
        print(f"{COLORS['info']}Calling Claude API...{Style.RESET_ALL}")
        
        # Debug before API call
        self._save_debug_output("ask_question_request", {
            "max_tokens": self.max_tokens,
            "model": "claude-3-5-sonnet-20241022",
            "system": system,
            "messages": messages
        })
        
        response = self.anthropic.messages.create(
            max_tokens=self.max_tokens,
            model="claude-3-5-sonnet-20241022",
            system=system,
            messages=messages,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        
        # Track usage
        self._track_usage(response)
        
        # Debug after API call
        self._save_debug_output("ask_question_response", {
            "response": response.content[0].text
        })
        
        answer = response.content[0].text
        prompt_id = self.current_session.get_next_prompt_id()
        
        # Create and save messages
        user_message = Message(role="user", content=question, prompt_id=prompt_id)
        assistant_message = Message(role="assistant", content=answer, prompt_id=prompt_id)
        
        # Update session and save file
        self.current_session.message_window.append(user_message.model_dump())
        self.current_session.message_window.append(assistant_message.model_dump())
        self.session_manager.save_session(self.current_session)
        self._save_conversation_output(question, answer, prompt_id)
        
        return answer, prompt_id

    def _save_conversation_output(self, question: str, answer: str, prompt_id: str) -> None:
        """Save conversation to output directory without printing status"""
        if not self.current_session:
            return
            
        output_dir = os.path.join(self.output_dir, self.current_session.name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Use fixed filename instead of date-based
        filename = "conversation.md"
        filepath = os.path.join(output_dir, filename)
        
        branch_info = f":{self.current_session.branch_info.branch_name}" if self.current_session.branch_info else ""
        header = f"# Conversation: [{self.current_session.name}{branch_info}] [{self.current_system_prompt}] [{self.max_tokens}] [Conversation ID: {self.current_session.conversation_id}]"
        
        mode = 'a' if os.path.exists(filepath) else 'w'
        with open(filepath, mode, encoding='utf-8') as f:
            if mode == 'w':
                f.write(f"{header}\n\n")
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"## ID: {prompt_id}  {timestamp}\n\n")
            f.write(f"**Q:** {question}\n\n")
            f.write(f"**A:** {answer}\n\n---\n\n")

    def save_conversation_output(self, question: str, answer: str, prompt_id: str) -> None:
        """Save conversation to output directory"""
        if not self.current_session:
            return
            
        # Create conversation output directory
        output_dir = os.path.join(self.output_dir, self.current_session.name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Use the passed prompt_id instead of generating a new one
        filename = f"conversation_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = os.path.join(output_dir, filename)
        
        # Format conversation header
        branch_info = f":{self.current_session.branch_info.branch_name}" if self.current_session.branch_info else ""
        header = f"# Conversation: [{self.current_session.name}{branch_info}] [{self.current_system_prompt}] [{self.max_tokens}] [Conversation ID: {self.current_session.conversation_id}]"
        
        # Write or append to file
        mode = 'a' if os.path.exists(filepath) else 'w'
        with open(filepath, mode, encoding='utf-8') as f:
            if mode == 'w':
                f.write(f"{header}\n\n")
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"## ID: {prompt_id}  {timestamp}\n\n")
            f.write(f"**Q:** {question}\n\n")
            f.write(f"**A:** {answer}\n\n---\n\n")
        
        # Show processing info
        print(f"{COLORS['info']}Conversation ID: {self.current_session.conversation_id}")
        print(f"File: {filename}")
        if self.current_session.message_window:
            print(f"Previous IDs: {', '.join(msg.get('prompt_id', 'unknown') for msg in self.current_session.message_window[-3:])}{Style.RESET_ALL}")

    def save_conversation(self) -> str:
        """Save the entire conversation history to a file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"conversation_{timestamp}.md"  # Changed to .md extension
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write("# Document Analysis Conversation\n\n")
            for entry in self.conversation_history:
                if entry["role"] == "system":
                    if entry["content"] == "Initial Document Analysis":
                        file.write(f"## Initial Analysis\n\n{entry['text']}\n\n")
                    else:
                        file.write(f"### Generated Prompt\n\n{entry['text']}\n\n")
                elif entry["role"] == "user":
                    if entry["content"].startswith("/p "):
                        file.write(f"## Prompt Request: {entry['content'][3:]}\n\n")
                    else:
                        file.write(f"## Question\n\n**Q:** {entry['content']}\n\n")
                else:  # assistant
                    file.write(f"### Answer\n\n{entry['content']}\n\n---\n\n")
        
        return filepath

    @retry_with_exponential_backoff()
    def generate_and_run_prompt(self, user_input: str) -> str:
        """Generate a new prompt from Claude and then execute it"""
        if not self.current_session:
            raise ValueError("No active conversation")
        
        # First, get Claude to generate a prompt
        response = self.anthropic.messages.create(
            max_tokens=TOKEN_LENGTHS[DEFAULT_RESPONSE_LENGTH],
            model="claude-3-5-sonnet-20241022",
            system=self.system_prompts["prompt_generation"],
            messages=[{
                "role": "user",
                "content": f"Generate a detailed prompt for the following request: {user_input}"
            }],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        
        # Track usage
        self._track_usage(response)
        
        generated_prompt = response.content[0].text
        
        # Now execute the generated prompt
        response = self.anthropic.messages.create(
            max_tokens=TOKEN_LENGTHS[DEFAULT_RESPONSE_LENGTH],
            model="claude-3-5-sonnet-20241022",
            system=f"You have the following document understanding:\n\n{self.current_session.document_summary}\n\nUse this as context for the conversation.",
            messages=[{
                "role": "user",
                "content": generated_prompt
            }],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        
        # Track usage for second call
        self._track_usage(response)
        
        answer = response.content[0].text
        
        # Update session
        self.current_session.message_window.append({"role": "user", "content": f"[Generated Prompt] {generated_prompt}"})
        self.current_session.message_window.append({"role": "assistant", "content": answer})
        self.session_manager.save_session(self.current_session)
        
        return f"Generated Prompt: {generated_prompt}\n\nAnswer: {answer}"

    def start_new_conversation(self) -> None:
        """Start new session with same document understanding"""
        if not self.current_session:
            raise ValueError("No previous session to branch from")
            
        self.current_session = Session.create_new(self.current_session.document_summary)
        self.session_manager.save_session(self.current_session)
        print(f"{COLORS['success']}Started new session: {self.current_session.session_id}{Style.RESET_ALL}")

    def load_session(self, session_id: str) -> None:
        """Load a previous session"""
        session = self.session_manager.load_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        self.current_session = session
        print(f"{COLORS['success']}Loaded session: {session_id}{Style.RESET_ALL}")

    def create_conversation(self, name: str) -> None:
        """Create a new conversation with given name"""
        if self.session_manager.get_session_by_name(name):
            raise ValueError(f"Conversation '{name}' already exists")
            
        print(f"{COLORS['info']}Creating new conversation: {name}{Style.RESET_ALL}")
        
        # Load default documents
        docs = self.load_documents_from_directory(DIRECTORIES['default'])
        
        # Process documents
        summary = self.process_documents(docs, name)
        
        # Create new session
        self.current_session = Session.create_new(name, summary)
        self.session_manager.save_session(self.current_session)
        
        print(f"{COLORS['success']}Created conversation: {name}{Style.RESET_ALL}")

    def switch_conversation(self, name: str) -> None:
        """Switch to a different conversation, creating it if it doesn't exist"""
        # Try to get existing session
        session = self.session_manager.get_session_by_name(name)
        
        if not session:
            # Check if we have processed documents even if no session
            processed_dir = os.path.join(DIRECTORIES['processed'], name)
            understanding_path = os.path.join(processed_dir, 'understanding.md')
            
            if os.path.exists(understanding_path) and LOAD_PROCESSED_DOCS:
                print(f"{COLORS['info']}Loading existing conversation: {name}{Style.RESET_ALL}")
                # Load documents to maintain document models
                docs = self.load_documents_from_directory(DIRECTORIES['default'])
                conv_dir = os.path.join(DIRECTORIES['input'], name)
                if os.path.exists(conv_dir):
                    conv_docs = self.load_documents_from_directory(conv_dir)
                    docs.update(conv_docs)
                
                # Process will load from cache since understanding exists
                summary = self.process_documents(docs, name)
            else:
                # If session doesn't exist and no cache, create it
                print(f"{COLORS['info']}Creating new conversation: {name}{Style.RESET_ALL}")
                # Load documents
                docs = self.load_documents_from_directory(DIRECTORIES['default'])
                conv_dir = os.path.join(DIRECTORIES['input'], name)
                if os.path.exists(conv_dir):
                    conv_docs = self.load_documents_from_directory(conv_dir)
                    docs.update(conv_docs)
                
                # Process documents and create session
                summary = self.process_documents(docs, name)
            
            # Create new session if needed
            if not self.current_session:
                self.current_session = Session.create_new(name, summary)
                self.session_manager.save_session(self.current_session)
        else:
            # Switch to existing session
            self.current_session = session
            print(f"{COLORS['success']}Switched to conversation: {name}{Style.RESET_ALL}")

    def reload_documents(self, context_window: Optional[int] = None) -> None:
        """Reload documents and update context"""
        if not self.current_session:
            raise ValueError("No active conversation")
            
        window = context_window or DEFAULT_CONTEXT_WINDOW
        
        # Load documents from conversation's input directory
        docs = self.load_documents_from_directory(
            os.path.join(DIRECTORIES['input'], self.current_session.name)
        )
        
        # Update summary
        summary = self.process_documents(docs, self.current_session.name)
        
        # Update session
        self.current_session.document_summary = summary
        self.current_session.message_window = self.current_session.message_window[-window:]
        self.session_manager.save_session(self.current_session)
        
        print(f"{COLORS['success']}Reloaded documents with {window} messages of context{Style.RESET_ALL}")

    def create_branch(self, branch_name: str, include_history: bool = True) -> None:
        """Create new conversation branch"""
        if not self.current_session:
            raise ValueError("No active conversation to branch from")
        
        new_session = self.current_session.create_branch(
            branch_name=branch_name,
            include_history=include_history
        )
        self.session_manager.save_session(new_session)
        self.current_session = new_session
        
        print(f"{COLORS['success']}Created branch '{branch_name}' from '{self.current_session.name}'{Style.RESET_ALL}")

    def list_branches(self) -> None:
        """Show branch structure of current conversation"""
        if not self.current_session:
            raise ValueError("No active conversation")
        
        branches = self.session_manager.get_branches(self.current_session.name)
        print(f"\nBranches for conversation '{self.current_session.name}':")
        self._print_branch_tree(branches)

    def show_document_sources(self) -> None:
        """Show current document sources for active conversation"""
        if not self.current_session:
            print(f"{COLORS['error']}No active conversation{Style.RESET_ALL}")
            return
        
        conv_dir = os.path.join(DIRECTORIES['input'], self.current_session.name)
        print(f"\n{COLORS['system']}Documents for conversation '{self.current_session.name}':{Style.RESET_ALL}")
        
        # Show documents in default directory
        print(f"\n{COLORS['info']}Default documents:{Style.RESET_ALL}")
        for doc in os.listdir(DIRECTORIES['default']):
            if doc.endswith(('.txt', '.md', '.doc', '.docx', '.pdf')):
                print(f"  • {doc}")
            
        # Show conversation-specific documents
        if os.path.exists(conv_dir) and os.listdir(conv_dir):
            print(f"\n{COLORS['info']}Conversation-specific documents:{Style.RESET_ALL}")
            for doc in os.listdir(conv_dir):
                if doc.endswith(('.txt', '.md', '.doc', '.docx', '.pdf')):
                    print(f"  • {doc}")

    def set_system_prompt(self, prompt_type: str) -> str:
        """Switch to a different system prompt"""
        # Convert to lowercase for comparison
        prompt_type = prompt_type.lower()
        if prompt_type not in {k.lower(): k for k in SYSTEM_PROMPTS}:
            available = ", ".join(SYSTEM_PROMPTS.keys())
            return f"Invalid prompt type. Available options: {available}"
        
        # Use original casing from SYSTEM_PROMPTS
        original_case = {k.lower(): k for k in SYSTEM_PROMPTS}[prompt_type]
        self.current_system_prompt = original_case
        return f"Switched to {original_case} system prompt"
        
    def list_system_prompts(self) -> None:
        """Display available system prompts"""
        print(f"\n{COLORS['system']}Available System Prompts:{Style.RESET_ALL}")
        for name, prompt in SYSTEM_PROMPTS.items():
            print(f"\n{COLORS['info']}{name.upper()}:{Style.RESET_ALL}")
            print(f"{prompt}\n")

    def _save_debug_output(self, step: str, content: dict):
        """Save debug information for analysis"""
        if not DEBUG_MODE:
            return
        
        # Add structured context analysis
        context_analysis = {
            "document_sources": {
                "default": [d for d in os.listdir(DIRECTORIES['default']) if d.endswith(('.md', '.txt'))],
                "conversation": (
                    [d for d in os.listdir(os.path.join(DIRECTORIES['input'], self.current_session.name)) 
                     if d.endswith(('.md', '.txt'))] if self.current_session else []
                )
            },
            "context_state": {
                "current_session": self.current_session.name if self.current_session else None,
                "system_prompt_type": self.current_system_prompt,
                "message_window_size": len(self.current_session.message_window) if self.current_session else 0,
                "has_understanding_file": os.path.exists(os.path.join(
                    DIRECTORIES['processed'], 
                    self.current_session.name if self.current_session else '', 
                    'understanding.md'
                ))
            },
            "content_analysis": {
                "technical_terms": self._extract_technical_terms(content),
                "metaphorical_terms": self._extract_metaphorical_terms(content),
                "context_position": {
                    "in_system_prompt": self._check_terms_in_system(content),
                    "in_messages": self._check_terms_in_messages(content)
                }
            }
        }
        
        debug_entry = {
            "timestamp": datetime.now().strftime('%Y%m%d_%H%M%S'),
            "step": step,
            "session_name": self.current_session.name if self.current_session else None,
            "content": content,
            "context_analysis": context_analysis
        }
        
        with open(self.debug_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(debug_entry) + '\n')

    def _extract_technical_terms(self, content: dict) -> list:
        """Extract technical terms from content"""
        technical_patterns = [
            "Network-Mesh", "Spiral", "Holographic", "Temporal", 
            "Adaptive", "Recursive", "Constellation"
        ]
        return self._find_terms(content, technical_patterns)

    def _extract_metaphorical_terms(self, content: dict) -> list:
        """Extract metaphorical terms from content"""
        metaphor_patterns = [
            "wizard", "balding man", "crown", "gems", 
            "facets", "virtual encapsulation"
        ]
        return self._find_terms(content, metaphor_patterns)

    def _find_terms(self, content: dict, patterns: list) -> list:
        """Helper function to find terms in content"""
        found_terms = []
        for pattern in patterns:
            if pattern in content.values():
                found_terms.append(pattern)
        return found_terms

    def _check_terms_in_system(self, content: dict) -> bool:
        """Check if any terms are in the system prompt"""
        system_prompt = self.system_prompts[self.current_system_prompt]
        return any(
            str(term) in system_prompt 
            for term in content.values() 
            if term is not None
        )

    def _check_terms_in_messages(self, content: dict) -> bool:
        """Check if any terms are in the messages"""
        return any(
            str(term) in str(msg) 
            for term in content.values() 
            if term is not None
            for msg in content.values() 
            if msg is not None
        )

    def _track_usage(self, response):
        """Track token usage and costs from API response"""
        usage = response.usage
        
        # Update session usage totals
        self.current_session.total_input_tokens += usage.input_tokens
        self.current_session.total_output_tokens += usage.output_tokens
        
        # Calculate costs (per 1K tokens)
        input_cost = (usage.input_tokens / 1000.0) * self.input_token_price
        output_cost = (usage.output_tokens / 1000.0) * self.output_token_price
        self.current_session.total_cost += input_cost + output_cost
        
        # Save updated session
        self.session_manager.save_session(self.current_session)
        
        print(f"\nAPI Usage for this call:")
        print(f"Input tokens: {usage.input_tokens:,}")
        print(f"Output tokens: {usage.output_tokens:,}") 
        print(f"Cost: ${(input_cost + output_cost):.4f}")
        print(f"\nTotal usage for conversation '{self.current_session.name}':")
        print(f"Total input tokens: {self.current_session.total_input_tokens:,}")
        print(f"Total output tokens: {self.current_session.total_output_tokens:,}")
        print(f"Total cost: ${self.current_session.total_cost:.4f}") 