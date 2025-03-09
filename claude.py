from document_processor import DocumentProcessor
import os
from settings import HELP_TEXT, DIRECTORIES, TOKEN_LENGTHS, COLORS
from colorama import init, Fore, Style
from setup import setup_directories
from dotenv import load_dotenv
from session_manager import Session
import uuid
from datetime import datetime
import shutil
import json
import textwrap
import re
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.filters import Condition
from prompt_toolkit.keys import Keys
from prompt_toolkit.filters.utils import is_true

def expand_file_references(processor, input_text: str) -> tuple[bool, str]:
    """
    Expand @@filename references in the input text.
    Returns (success, expanded_text) where success indicates if all files were found.
    """
    # Find all @@filename patterns
    pattern = r'@@([\w\-\.]+)'
    matches = re.finditer(pattern, input_text)
    
    # Track the last position for building result
    last_pos = 0
    result = ""
    
    # Get conversation output directory
    if not processor.current_session:
        return False, "No active conversation"
    output_dir = os.path.join(DIRECTORIES['output'], processor.current_session.name)
    
    for match in matches:
        filename = match.group(1)
        filepath = os.path.join(output_dir, filename)
        
        # Check if file exists
        if not os.path.exists(filepath):
            print(f"{COLORS['error']}File not found: {filepath}{Style.RESET_ALL}")
            return False, f"File not found: {filepath}"
            
        # Read file contents
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                file_contents = f.read()
        except Exception as e:
            print(f"{COLORS['error']}Error reading file {filepath}: {str(e)}{Style.RESET_ALL}")
            return False, f"Error reading file {filepath}: {str(e)}"
            
        # Add text up to the match and the tagged file contents
        result += input_text[last_pos:match.start()]
        result += f'<file name="{filename}">\n{file_contents}\n</file>'
        last_pos = match.end()
    
    # Add any remaining text
    result += input_text[last_pos:]
    return True, result

class ClaudePrompt:
    def __init__(self, processor):
        self.processor = processor
        self.history = FileHistory(".claude_history")
        self.session = PromptSession(history=self.history)
        
        # Style for the prompt
        self.style = PromptStyle.from_dict({
            'prompt': '#00aa00',       # Green
            'conversation': '#0000aa', # Blue
            'role': '#00aaaa',         # Cyan
            'length': '#aa00aa',       # Magenta
        })
        
        # Key bindings
        self.kb = KeyBindings()
        
        @self.kb.add('c-c')
        def _(event):
            "Ctrl-C clears the current input."
            event.app.current_buffer.text = ""
            
        @self.kb.add('c-d')
        def _(event):
            "Ctrl-D exits the application."
            event.app.exit()
            
        @self.kb.add("enter")
        def handle_enter(event):
            """
            Handle Enter key:
              - If the current line is exactly "..", remove that line from
                the buffer and submit the prompt.
              - Otherwise, insert a newline.
            """
            doc = event.current_buffer.document
            current_line = doc.current_line
            if current_line.strip() == "..":
                # Get the full text from the buffer and split into lines.
                full_text = event.current_buffer.text
                lines = full_text.split("\n")
                # If the last line is exactly ".." (ignoring whitespace), remove it.
                if lines and lines[-1].strip() == "..":
                    lines.pop()
                # Update the buffer without the ".." line.
                event.current_buffer.text = "\n".join(lines)
                event.current_buffer.validate_and_handle()
            else:
                event.current_buffer.insert_text("\n")

        @self.kb.add(Keys.ControlM)  # Ctrl+Enter
        def _(event):
            "Ctrl+Enter submits the input"
            event.current_buffer.validate_and_handle()
        
    def get_conversation_prompt(self) -> FormattedText:
        """Get formatted conversation prompt"""
        if not self.processor.current_session:
            return FormattedText([('class:prompt', 'Q: ')])
            
        name = self.processor.current_session.name
        branch = self.processor.current_session.branch_info
        
        # Get current token length name
        current_length = next(
            (name for name, tokens in TOKEN_LENGTHS.items() 
             if tokens == self.processor.max_tokens),
            "M"
        )
        
        # Get current system prompt type
        current_role = self.processor.current_system_prompt
        
        # Build formatted text segments
        segments = []
        segments.append(('class:prompt', 'Q '))
        
        if branch:
            segments.append(('class:conversation', f'[{name}:{branch.branch_name}] '))
        else:
            segments.append(('class:conversation', f'[{name}] '))
            
        segments.append(('class:role', f'[{current_role.upper()}] '))
        segments.append(('class:length', f'[{current_length}] '))
        segments.append(('class:prompt', ': '))
        
        return FormattedText(segments)
        
    def get_input(self) -> str:
        """Get multi-line input from the user with the formatted prompt"""
        try:
            result = self.session.prompt(
                self.get_conversation_prompt,
                style=self.style,
                multiline=True,  # Enable multi-line editing
                key_bindings=self.kb,
                wrap_lines=True,  # Enable line wrapping
            )
            return result.strip() if result else ""
        except KeyboardInterrupt:
            return ""
        except EOFError:  # Ctrl+D
            return "/q"  # Return quit command directly without stripping

def main():
    init()  # Initialize colorama
    try:
        # Load environment variables
        load_dotenv()
        
        # Ensure directory structure exists
        setup_directories()
        
        # Get API key from environment
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")
            
        processor = DocumentProcessor(api_key=api_key)
        
        # Create directory structure if it doesn't exist
        for dir_path in DIRECTORIES.values():
            os.makedirs(dir_path, exist_ok=True)
            
        # Check if default directory has documents
        default_dir = DIRECTORIES['default']
        if not os.path.exists(default_dir) or not os.listdir(default_dir):
            print(f"{Fore.YELLOW}No documents found in {default_dir}{Style.RESET_ALL}")
            print(f"Please place your default documents in this directory and run the script again")
            return
        
        # Load documents from default directory
        docs = processor.load_documents_from_directory(default_dir)
        
        # Process the documents with main conversation
        initial_analysis = processor.process_documents(
            docs=docs,
            name="main"  # Default conversation name
        )
        print(f"{Fore.CYAN}Initial Analysis:{Style.RESET_ALL}", initial_analysis)
        
        # Interactive question loop
        print("\nEnter your questions or commands:")
        print(HELP_TEXT)
        
        # Get terminal width for text wrapping
        terminal_width = shutil.get_terminal_size().columns
        wrapper = textwrap.TextWrapper(
            width=terminal_width-2,  # Leave some margin
            break_long_words=False,
            replace_whitespace=False,
            expand_tabs=False,
            drop_whitespace=True
        )
        
        # Initialize prompt interface
        prompt = ClaudePrompt(processor)
        
        while True:
            user_input = prompt.get_input()
            
            if user_input.lower() in ['/q', '/quit']:
                print(f"{Fore.CYAN}Exiting...{Style.RESET_ALL}")
                break
                
            elif user_input == '/n':
                processor.start_new_conversation()
                print(f"\n{Fore.GREEN}Started new conversation{Style.RESET_ALL}")
                continue
                
            elif user_input.startswith('/load '):
                session_id = user_input[6:].strip()
                processor.load_session(session_id)
                continue
                
            elif user_input == '/sessions':
                sessions = processor.session_manager.list_sessions()
                print("\nAvailable sessions:")
                for s in sessions:
                    print(f"  • {s['session_id']} (Last accessed: {s['last_accessed']})")
                continue
                
            elif user_input == '/xxs':
                print(processor.set_response_length("XXS"))
                continue
                
            elif user_input == '/xs':
                print(processor.set_response_length("XS"))
                continue
                
            elif user_input == '/s':
                print(processor.set_response_length("S"))
                continue
                
            elif user_input == '/m':
                print(processor.set_response_length("M"))
                continue
                
            elif user_input == '/l':
                print(processor.set_response_length("L"))
                continue
                
            elif user_input == '/xl':
                print(processor.set_response_length("XL"))
                continue
                
            elif user_input == '/xxl':
                print(processor.set_response_length("XXL"))
                continue
                
            elif user_input == '/':
                print(HELP_TEXT)
                continue
                
            elif user_input == '/ls':
                sessions = processor.session_manager.list_sessions()
                print("\nAvailable conversations:")
                for s in sessions:
                    print(f"  • {s['name']} ({s['message_count']} messages)")
                continue
                
            elif user_input.startswith('/n '):
                name = user_input[3:].strip()
                processor.create_conversation(name)
                continue
                
            elif user_input.startswith('/sw'):
                if len(user_input) <= 4:  # Just "/sw" or "/sw "
                    sessions = processor.session_manager.list_sessions()
                    print("\nAvailable conversations:")
                    for s in sessions:
                        print(f"  • {s['name']} ({s['message_count']} messages)")
                else:
                    try:
                        name = user_input[4:].strip()
                        processor.switch_conversation(name)  # This will create if doesn't exist
                    except Exception as e:
                        print(f"{COLORS['error']}Error: {str(e)}{Style.RESET_ALL}")
                continue
                
            elif user_input.startswith('/p'):
                if len(user_input) <= 3:  # Just "/p" or "/p "
                    processor.list_system_prompts()
                else:
                    prompt_type = user_input[3:].strip()
                    print(processor.set_system_prompt(prompt_type))
                continue
                
            elif user_input.startswith('/ld'):
                parts = user_input.split()
                window = int(parts[1]) if len(parts) > 1 else DEFAULT_CONTEXT_WINDOW
                
                # Update window size in current session - multiply by 2 for pairs
                processor.current_session.window_size = window * 2
                processor.session_manager.save_session(processor.current_session)
                print(f"{COLORS['success']}Context window size set to {window} message pairs{Style.RESET_ALL}")
                continue
                
            elif user_input == '/docs':
                processor.show_document_sources()
                continue
                
            elif user_input == '/clear':
                response = input(f"{COLORS['info']}Clear current session? [y/N]: {Style.RESET_ALL}")
                if response.lower() == 'y':
                    session_id = processor.current_session.session_id
                    session_path = os.path.join('sessions', f"{session_id}.json")
                    if os.path.exists(session_path):
                        os.remove(session_path)
                    print(f"{COLORS['success']}Session cleared{Style.RESET_ALL}")
                continue
                
            elif user_input == '/clearall':
                response = input(f"{COLORS['info']}Clear ALL session and conversation files? [y/N]: {Style.RESET_ALL}")
                if response.lower() == 'y':
                    # Clear session files
                    for f in os.listdir('sessions'):
                        if f.endswith('.json'):
                            os.remove(os.path.join('sessions', f))
                    # Clear conversation files
                    for conv_dir in os.listdir('output-docs'):
                        conv_path = os.path.join('output-docs', conv_dir)
                        if os.path.isdir(conv_path):
                            for f in os.listdir(conv_path):
                                if f.endswith('.md'):
                                    os.remove(os.path.join(conv_path, f))
                    
                    # Create completely fresh session
                    processor.current_session = Session(
                        name=processor.current_session.name,
                        session_id=str(uuid.uuid4()),
                        document_summary=processor.current_session.document_summary,
                        message_window=[],
                        created_at=datetime.now(),
                        last_accessed=datetime.now(),
                        last_prompt_id=0  # Reset ID counter
                    )
                    processor.session_manager.save_session(processor.current_session)
                    
                    print(f"{COLORS['success']}All sessions and conversations cleared{Style.RESET_ALL}")
                continue
                
            elif user_input == '/reload':
                response = input(f"{COLORS['info']}Reprocess all documents for current conversation? [y/N]: {Style.RESET_ALL}")
                if response.lower() == 'y':
                    name = processor.current_session.name
                    
                    # Load both default and conversation-specific docs
                    docs = processor.load_documents_from_directory(DIRECTORIES['default'])
                    conv_dir = os.path.join(DIRECTORIES['input'], name)
                    if os.path.exists(conv_dir):
                        conv_docs = processor.load_documents_from_directory(conv_dir)
                        docs.update(conv_docs)
                    
                    # Remove existing processed docs
                    processed_dir = os.path.join(DIRECTORIES['processed'], name)
                    if os.path.exists(processed_dir):
                        for f in os.listdir(processed_dir):
                            os.remove(os.path.join(processed_dir, f))
                    
                    # Reprocess documents
                    print(f"\n{COLORS['info']}Reprocessing documents...{Style.RESET_ALL}")
                    summary = processor.process_documents(docs, name)
                    print(f"{COLORS['success']}Documents reprocessed{Style.RESET_ALL}")
                continue
                
            elif user_input == '/clearconv':
                response = input(f"{COLORS['info']}Clear ALL conversations and related files/folders? [y/N]: {Style.RESET_ALL}")
                if response.lower() == 'y':
                    # Clear conversation files
                    for conv_dir in os.listdir('output-docs'):
                        conv_path = os.path.join('output-docs', conv_dir)
                        if os.path.isdir(conv_path):
                            shutil.rmtree(conv_path)
                            
                    # Clear processed documents
                    for conv_dir in os.listdir('processed-docs'):
                        conv_path = os.path.join('processed-docs', conv_dir)
                        if os.path.isdir(conv_path):
                            shutil.rmtree(conv_path)
                            
                    # Clear session files
                    for f in os.listdir('sessions'):
                        if f.endswith('.json'):
                            os.remove(os.path.join('sessions', f))
                            
                    # Create fresh session
                    processor.current_session = Session(
                        name=processor.current_session.name,
                        session_id=str(uuid.uuid4()),
                        document_summary=processor.current_session.document_summary,
                        message_window=[],
                        created_at=datetime.now(),
                        last_accessed=datetime.now(),
                        last_prompt_id=0  # Reset ID counter
                    )
                    processor.session_manager.save_session(processor.current_session)
                    
                    print(f"{COLORS['success']}All conversations and related files cleared{Style.RESET_ALL}")
                continue
                
            elif user_input == '/usage':
                print(f"\n{COLORS['info']}Token Usage for conversation '{processor.current_session.name}':{Style.RESET_ALL}")
                print(f"Input tokens: {processor.current_session.total_input_tokens:,}")
                print(f"Output tokens: {processor.current_session.total_output_tokens:,}")
                print(f"Total tokens: {(processor.current_session.total_input_tokens + processor.current_session.total_output_tokens):,}")
                print(f"\n{COLORS['info']}Total Cost:{Style.RESET_ALL}")
                input_cost = (processor.current_session.total_input_tokens / 1000.0) * processor.input_token_price
                output_cost = (processor.current_session.total_output_tokens / 1000.0) * processor.output_token_price
                print(f"Input cost: ${input_cost:.4f} (${processor.input_token_price:.3f}/1K tokens)")
                print(f"Output cost: ${output_cost:.4f} (${processor.output_token_price:.3f}/1K tokens)")
                print(f"Total cost: ${processor.current_session.total_cost:.4f}")
                continue
                
            elif user_input.startswith('/rmrf'):
                if len(user_input) <= 6:  # Just "/rmrf" or "/rmrf "
                    print(f"{COLORS['error']}Please specify a conversation name to remove{Style.RESET_ALL}")
                    continue
                    
                name = user_input[6:].strip()
                if name == processor.current_session.name:
                    print(f"{COLORS['error']}Cannot remove active conversation. Switch to a different conversation first.{Style.RESET_ALL}")
                    continue
                
                response = input(f"{COLORS['info']}Remove conversation '{name}' and ALL associated files/folders? [y/N]: {Style.RESET_ALL}")
                if response.lower() == 'y':
                    # Remove conversation output directory
                    conv_path = os.path.join('output-docs', name)
                    if os.path.exists(conv_path):
                        shutil.rmtree(conv_path)
                        
                    # Remove processed documents
                    proc_path = os.path.join('processed-docs', name)
                    if os.path.exists(proc_path):
                        shutil.rmtree(proc_path)
                        
                    # Remove session file
                    for f in os.listdir('sessions'):
                        if f.endswith('.json'):
                            session_path = os.path.join('sessions', f)
                            try:
                                with open(session_path, 'r') as sf:
                                    session_data = json.load(sf)
                                    if session_data.get('name') == name:
                                        os.remove(session_path)
                            except (json.JSONDecodeError, KeyError):
                                continue
                    
                    print(f"{COLORS['success']}Removed conversation '{name}' and all associated files{Style.RESET_ALL}")
                continue
                
            elif not user_input:
                continue
                
            # Handle regular questions
            # Move cursor home and clear from cursor to end of screen
            print("\033[H\033[J", end="")  # Move cursor home and clear from cursor down
            formatted_prompt = prompt.get_conversation_prompt()
            
            # Expand any @@filename references
            success, expanded_input = expand_file_references(processor, user_input)
            if not success:
                continue
                
            # Wrap and display user input
            wrapped_input = wrapper.fill(expanded_input)
            print(f"{formatted_prompt}{wrapped_input}")  # Show prompt and wrapped question
            
            # Process question
            answer, prompt_id = processor.ask_question(expanded_input)
            
            # Wrap and display response
            wrapped_answer = wrapper.fill(answer)
            print(f"{Fore.YELLOW}A: {wrapped_answer}{Style.RESET_ALL}")
            print(f"\n{COLORS['info']}Created Prompt {prompt_id}{Style.RESET_ALL}")
            
    except ValueError as e:
        print(f"{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")
        if "ANTHROPIC_API_KEY" in str(e):
            print(f"{Fore.RED}Please set your ANTHROPIC_API_KEY environment variable{Style.RESET_ALL}")

if __name__ == "__main__":
    main() 