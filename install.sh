#!/bin/bash
#
# Argus Install Script
# https://github.com/nickpending/argus
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nickpending/argus/main/install.sh | bash
#
# What this script does:
#   1. Detects your OS (macOS or Linux)
#   2. Installs uv package manager if not present
#   3. Installs argus via uv tool install
#   4. Creates default config (if not exists)
#   5. Optionally sets up auto-start service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin)
            OS="macos"
            SERVICE_FILE="info.voidwire.argus.plist"
            SERVICE_DIR="$HOME/Library/LaunchAgents"
            ;;
        Linux)
            OS="linux"
            SERVICE_FILE="argus.service"
            SERVICE_DIR="$HOME/.config/systemd/user"
            ;;
        *)
            error "Unsupported operating system: $(uname -s)"
            ;;
    esac
    success "Detected OS: $OS"
}

# Check if uv is installed
check_uv() {
    if command -v uv &> /dev/null; then
        success "uv is installed: $(uv --version)"
        return 0
    else
        return 1
    fi
}

# Install uv
install_uv() {
    info "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the environment
    if [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    elif [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi

    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &> /dev/null; then
        success "uv installed successfully"
    else
        error "Failed to install uv. Please install manually: https://github.com/astral-sh/uv"
    fi
}

# Install argus
install_argus() {
    info "Installing argus..."
    uv tool install git+https://github.com/nickpending/argus.git

    # Verify installation
    if command -v argus &> /dev/null; then
        success "argus installed: $(argus --version 2>/dev/null || echo 'version check failed')"
    else
        # Try adding uv tools to PATH
        export PATH="$HOME/.local/bin:$PATH"
        if command -v argus &> /dev/null; then
            success "argus installed (added to PATH)"
        else
            error "argus installation failed. Check output above for errors."
        fi
    fi
}

# Initialize config
init_config() {
    CONFIG_FILE="$HOME/.config/argus/config.toml"

    if [ -f "$CONFIG_FILE" ]; then
        warn "Config already exists: $CONFIG_FILE (skipping)"
    else
        info "Creating default config..."
        argus config init
        success "Config created: $CONFIG_FILE"
        warn "Edit $CONFIG_FILE to set your API key"
    fi
}

# Setup auto-start service
setup_service() {
    echo ""
    read -p "Would you like to set up auto-start on login? [y/N] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Skipping auto-start setup"
        echo ""
        echo "To set up later, see: https://github.com/nickpending/argus#auto-start"
        return
    fi

    # Create data directory (required by service)
    mkdir -p "$HOME/.local/share/argus"

    if [ "$OS" = "macos" ]; then
        setup_launchd
    else
        setup_systemd
    fi
}

# Setup launchd (macOS)
setup_launchd() {
    info "Setting up launchd service..."

    PLIST_URL="https://raw.githubusercontent.com/nickpending/argus/main/install/info.voidwire.argus.plist"
    PLIST_PATH="$SERVICE_DIR/$SERVICE_FILE"

    mkdir -p "$SERVICE_DIR"

    # Download and configure plist
    curl -fsSL "$PLIST_URL" -o "$PLIST_PATH"

    # Replace USERNAME placeholder with actual username
    sed -i '' "s/USERNAME/$USER/g" "$PLIST_PATH"

    # Load the service
    launchctl load "$PLIST_PATH"

    success "launchd service installed and started"
    echo ""
    echo "Manage with:"
    echo "  launchctl start info.voidwire.argus   # Start"
    echo "  launchctl stop info.voidwire.argus    # Stop (restarts due to KeepAlive)"
    echo "  launchctl unload $PLIST_PATH          # Disable"
}

# Setup systemd (Linux)
setup_systemd() {
    info "Setting up systemd user service..."

    SERVICE_URL="https://raw.githubusercontent.com/nickpending/argus/main/install/argus.service"
    SERVICE_PATH="$SERVICE_DIR/$SERVICE_FILE"

    mkdir -p "$SERVICE_DIR"

    # Download service file
    curl -fsSL "$SERVICE_URL" -o "$SERVICE_PATH"

    # Reload and enable
    systemctl --user daemon-reload
    systemctl --user enable argus
    systemctl --user start argus

    success "systemd service installed, enabled, and started"
    echo ""
    echo "Manage with:"
    echo "  systemctl --user status argus    # Check status"
    echo "  systemctl --user stop argus      # Stop"
    echo "  systemctl --user restart argus   # Restart"
    echo "  journalctl --user -u argus -f    # View logs"
}

# Main
main() {
    echo ""
    echo "================================"
    echo "  Argus Installer"
    echo "================================"
    echo ""

    detect_os

    if ! check_uv; then
        install_uv
    fi

    install_argus
    init_config
    setup_service

    echo ""
    echo "================================"
    success "Installation complete!"
    echo "================================"
    echo ""
    echo "Next steps:"
    echo "  1. Edit ~/.config/argus/config.toml to set your API key"
    echo "  2. Start the server: argus serve"
    echo "  3. Open the web UI: http://127.0.0.1:8765"
    echo ""
}

main "$@"
