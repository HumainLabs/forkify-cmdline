#!/bin/bash

# Exit on error
set -e

# Install command-line dependencies first
echo "Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "Creating directory structure..."
mkdir -p data/{vectordb,uploads,input,processed,output,sessions}
python setup.py

# Copy environment variables
echo "Setting up environment variables..."
if [ ! -f .env ]; then
    cp .env.template .env
    echo "Created .env file from template. Please update with your settings."
fi

echo "Setup complete! 🚀"
echo "Next steps:"
echo "1. Update .env with your API keys"
echo "2. Run 'python claude.py' or './scripts/dev.sh' to start the command-line interface" 