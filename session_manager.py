from dataclasses import dataclass
from datetime import datetime
import json
import os
from typing import List, Dict, Optional
import uuid
from settings import DEFAULT_CONTEXT_WINDOW, DIRECTORIES
import string
import random

@dataclass
class BranchInfo:
    branch_name: str
    parent_id: str
    created_at: datetime
    document_hash: str

def generate_conversation_id() -> str:
    """Generate a random 6 character conversation ID"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

@dataclass
class Session:
    session_id: str
    conversation_id: str  # 6-char random ID for conversation caching
    name: str
    document_summary: str
    message_window: List[Dict]
    created_at: datetime
    last_accessed: datetime
    window_size: int = DEFAULT_CONTEXT_WINDOW
    branch_info: Optional[BranchInfo] = None
    last_prompt_id: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    
    @classmethod
    def create_new(cls, name: str, document_summary: str, last_prompt_id: int = 0) -> 'Session':
        # First check if a session exists with this name
        session_dir = "sessions"
        for filename in os.listdir(session_dir):
            if filename.endswith('.json'):
                with open(os.path.join(session_dir, filename), 'r') as f:
                    try:
                        data = json.load(f)
                        if data.get('name') == name:
                            # Return existing session
                            session = cls.from_dict(data)
                            # Set last_prompt_id based on message history
                            if session.message_window:
                                max_id = max(
                                    int(msg['prompt_id']) 
                                    for msg in session.message_window 
                                    if msg['role'] == 'user'
                                )
                                session.last_prompt_id = max_id
                            return session
                    except json.JSONDecodeError:
                        continue

        # If no existing session, create new one
        session_id = str(uuid.uuid4())
        conversation_id = generate_conversation_id()
        
        # Initialize message window
        message_window = []
        
        # Check for existing conversation file and update last_prompt_id if needed
        output_dir = os.path.join("output-docs", name)
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename.startswith("conversation_") and filename.endswith(".md"):
                    filepath = os.path.join(output_dir, filename)
                    with open(filepath, 'r') as f:
                        current_prompt = None
                        for line in f:
                            if line.startswith("## ID: "):
                                try:
                                    # Format ID consistently with leading zeros
                                    prompt_id = int(line[7:12])  # Extract "00001" format
                                    last_prompt_id = max(last_prompt_id, prompt_id)
                                    current_prompt = f"{prompt_id:05d}"  # Format as 00001
                                except ValueError:
                                    continue
                            elif line.startswith("**Q:** "):
                                if current_prompt:
                                    message_window.append({
                                        "role": "user",
                                        "content": line[6:].strip(),
                                        "prompt_id": current_prompt
                                    })
                            elif line.startswith("**A:** "):
                                if current_prompt:
                                    message_window.append({
                                        "role": "assistant",
                                        "content": line[6:].strip(),
                                        "prompt_id": current_prompt
                                    })
        
        # Create directories
        for dir_type, base_dir in DIRECTORIES.items():
            if dir_type != 'default':
                os.makedirs(os.path.join(base_dir, name), exist_ok=True)
        
        return cls(
            session_id=session_id,
            conversation_id=conversation_id,
            name=name,
            document_summary=document_summary,
            message_window=message_window,
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            last_prompt_id=last_prompt_id  # Use the passed or computed last_prompt_id
        )
    
    def to_dict(self) -> Dict:
        return {
            'session_id': self.session_id,
            'conversation_id': self.conversation_id,
            'name': self.name,
            'document_summary': self.document_summary,
            'message_window': self.message_window,
            'created_at': self.created_at.isoformat(),
            'last_accessed': self.last_accessed.isoformat(),
            'window_size': self.window_size,
            'branch_info': self.branch_info.__dict__ if self.branch_info else None,
            'last_prompt_id': self.last_prompt_id,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_cost': self.total_cost
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Session':
        session = cls(
            session_id=data['session_id'],
            conversation_id=data.get('conversation_id', generate_conversation_id()),  # Generate new if missing
            name=data['name'],
            document_summary=data['document_summary'],
            message_window=data['message_window'],
            created_at=datetime.fromisoformat(data['created_at']),
            last_accessed=datetime.fromisoformat(data['last_accessed']),
            window_size=data.get('window_size', DEFAULT_CONTEXT_WINDOW),
            last_prompt_id=data.get('last_prompt_id', 0),
            total_input_tokens=data.get('total_input_tokens', 0),
            total_output_tokens=data.get('total_output_tokens', 0),
            total_cost=data.get('total_cost', 0.0)
        )
        if data.get('branch_info'):
            session.branch_info = BranchInfo(**data['branch_info'])
            
        # If last_prompt_id wasn't saved, compute it from message history
        if not session.last_prompt_id and session.message_window:
            try:
                session.last_prompt_id = max(
                    int(msg['prompt_id']) 
                    for msg in session.message_window 
                    if msg['role'] == 'user'
                )
            except (ValueError, KeyError):
                session.last_prompt_id = 0
                
        return session

    def create_branch(self, branch_name: str, include_history: bool = True) -> 'Session':
        """Create a new branch from this session"""
        # Validate branch name
        if '/' in branch_name:
            raise ValueError("Branch name cannot contain '/'")
            
        # Create new session
        new_name = f"{self.name}/{branch_name}"
        new_session = Session.create_new(
            name=new_name,
            document_summary=self.document_summary
        )
        
        # Set up branch info
        new_session.branch_info = BranchInfo(
            branch_name=branch_name,
            parent_id=self.session_id,
            created_at=datetime.now(),
            document_hash=self._hash_documents()
        )
        
        # Copy history if requested
        if include_history:
            new_session.message_window = self.message_window.copy()
            
        return new_session

    def _hash_documents(self) -> str:
        """Create hash of current document state"""
        # Implementation depends on how we store documents
        pass

    def get_next_prompt_id(self) -> str:
        """Get next sequential prompt ID"""
        self.last_prompt_id += 1
        return f"{self.last_prompt_id:05d}"  # Format as 00001, 00002, etc.

class SessionManager:
    def __init__(self):
        self.sessions_dir = "sessions"
        # Create all base directories
        for dir_path in DIRECTORIES.values():
            os.makedirs(dir_path, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)
            
    def get_session_by_name(self, name: str) -> Optional[Session]:
        """Find session by name instead of ID"""
        for filename in os.listdir(self.sessions_dir):
            if filename.endswith('.json'):
                session = self.load_session(filename[:-5])  # Remove .json
                if session and session.name == name:
                    return session
        return None
    
    def save_session(self, session: Session) -> None:
        session.last_accessed = datetime.now()
        path = os.path.join(self.sessions_dir, f"{session.session_id}.json")
        with open(path, 'w') as f:
            json.dump(session.to_dict(), f, indent=2)
    
    def load_session(self, session_id: str) -> Optional[Session]:
        path = os.path.join(self.sessions_dir, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, 'r') as f:
            return Session.from_dict(json.load(f))
    
    def list_sessions(self) -> List[Dict]:
        """List all valid sessions"""
        sessions = []
        seen_names = set()  # Track unique names
        
        for filename in os.listdir(self.sessions_dir):
            if filename.endswith('.json'):
                try:
                    path = os.path.join(self.sessions_dir, filename)
                    with open(path, 'r') as f:
                        data = json.load(f)
                        if 'name' in data and data['name'] not in seen_names:
                            name = data['name']
                            
                            # Count user messages from message_window
                            message_count = len([
                                msg for msg in data.get('message_window', [])
                                if msg['role'] == 'user'
                            ])
                            
                            sessions.append({
                                'name': name,
                                'message_count': message_count
                            })
                            seen_names.add(name)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Warning: Skipping invalid session file {filename}")
                    continue
        
        return sorted(sessions, key=lambda x: x['name']) 