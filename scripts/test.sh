#!/bin/bash

# Exit on error
set -e

# Run backend tests
echo "Running backend tests..."
cd backend
pytest
cd ..

# Run frontend tests (when we have them)
echo "Running frontend tests..."
cd frontend
npm test
cd ..

echo "All tests completed! 🎉" 