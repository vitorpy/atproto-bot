#!/bin/bash
# Initial setup script for atproto-bot on remote server
# Run this once on the server before first deployment

set -e

echo "Setting up atproto-bot deployment directories..."

# Create directories
sudo mkdir -p /var/www/atproto-bot
sudo mkdir -p /var/lib/atproto-bot

# Set ownership
sudo chown -R vitorpy:http /var/www/atproto-bot
sudo chown -R vitorpy:http /var/lib/atproto-bot

# Set permissions
sudo chmod 755 /var/www/atproto-bot
sudo chmod 755 /var/lib/atproto-bot

echo "Setup complete!"
echo "Directories created:"
echo "  - /var/www/atproto-bot (application)"
echo "  - /var/lib/atproto-bot (database)"
echo ""
echo "Next steps:"
echo "1. Verify uv is installed: uv --version"
echo "2. Configure GitHub secrets"
echo "3. Push to main to trigger deployment"
