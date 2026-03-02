#!/bin/bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y poppler-utils python3-venv python3-pip

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

echo "Setup complete! Run: source venv/bin/activate && bash run.sh"
