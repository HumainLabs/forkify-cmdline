import os
from settings import DIRECTORIES

def setup_directories():
    """Create required directory structure"""
    # Create base directories
    for dir_path in DIRECTORIES.values():
        os.makedirs(dir_path, exist_ok=True)
        # Create .gitkeep to maintain directory structure
        gitkeep_path = os.path.join(dir_path, '.gitkeep')
        if not os.path.exists(gitkeep_path):
            open(gitkeep_path, 'a').close()
    
    # Create sessions directory
    os.makedirs('sessions', exist_ok=True)
    open(os.path.join('sessions', '.gitkeep'), 'a').close()
    
    # Ensure input-docs/default and input-docs/main exist
    input_docs = DIRECTORIES['input']
    required_subdirs = ['default', 'main']
    for subdir in required_subdirs:
        subdir_path = os.path.join(input_docs, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        # Create .gitkeep in each required subdirectory
        gitkeep_path = os.path.join(subdir_path, '.gitkeep')
        if not os.path.exists(gitkeep_path):
            open(gitkeep_path, 'a').close()

if __name__ == "__main__":
    setup_directories() 