#!/bin/bash

# Exit on error
set -e

echo "Creating new data directory structure..."
mkdir -p data/{input,processed,output,sessions,vectordb,uploads}

echo "Migrating existing data..."

# Function to safely copy directories
safe_copy() {
    local src=$1
    local dest=$2
    if [ -d "$src" ] && [ "$(ls -A $src)" ]; then
        echo "Copying $src to $dest"
        cp -r "$src"/* "$dest/"
    else
        echo "No data to migrate from $src"
    fi
}

# Migrate existing directories
safe_copy "input-docs" "data/input"
safe_copy "processed-docs" "data/processed"
safe_copy "output-docs" "data/output"
safe_copy "sessions" "data/sessions"

echo "Creating .gitignore for data directory..."
cat > data/.gitignore << EOL
# Ignore everything in data directory except .gitignore
*
!.gitignore
EOL

echo "Data migration complete! 🎉"
echo "You can now safely remove the old directories after verifying the migration."
echo "Old directories to review:"
echo "- input-docs/"
echo "- processed-docs/"
echo "- output-docs/"
echo "- sessions/" 