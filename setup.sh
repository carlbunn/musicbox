#!/bin/bash

# Check if script is run with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "Please run this script with sudo privileges"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Configuration
REPO_URL="https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git"
SERVICE_USER="musicbox"
SERVICE_GROUP="musicbox"
INSTALL_DIR="/opt/musicbox"
LOG_DIR="/var/log/musicbox"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Error handling
handle_error() {
    local exit_code=$?
    local line_number=$1
    echo -e "\n${RED}Error occurred in script at line ${line_number}${NC}"
    cleanup
    exit $exit_code
}

trap 'handle_error ${LINENO}' ERR

# Cleanup function for failed installations
cleanup() {
    echo "Cleaning up installation..."
    
    # Stop and disable service if it exists
    if systemctl list-unit-files | grep -q musicbox.service; then
        systemctl stop musicbox.service 2>/dev/null
        systemctl disable musicbox.service 2>/dev/null
        rm -f /etc/systemd/system/musicbox.service
        systemctl daemon-reload
    fi
    
    # Only remove installation directory if it doesn't contain user music
    if [ -d "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/music" ]; then
        rm -rf "$INSTALL_DIR"
    fi
    
    echo "Cleanup completed"
}

# Function to print status
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} Error: $1 failed"
        exit 1
    fi
}

# Function to set up log rotation
setup_logrotate() {
    cat > /etc/logrotate.d/musicbox << EOL
$LOG_DIR/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 $SERVICE_USER $SERVICE_GROUP
    postrotate
        systemctl kill -s USR1 musicbox.service
    endscript
}
EOL
    chmod 644 /etc/logrotate.d/musicbox
    print_status "Log rotation configuration"
}

# Function to check if service needs restart
needs_restart=false
needs_reboot=false

echo "Starting MusicBox installation..."

# Create service user and group if they don't exist
if ! getent group "$SERVICE_GROUP" > /dev/null; then
    echo "Creating service group..."
    groupadd "$SERVICE_GROUP"
    print_status "Group creation"
fi

if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user..."
    useradd -r -g "$SERVICE_GROUP" -d "$INSTALL_DIR" -s /bin/false "$SERVICE_USER"
    print_status "User creation"
fi

# Create log directory
echo "Setting up log directory..."
mkdir -p "$LOG_DIR"
chown "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 755 "$LOG_DIR"
print_status "Log directory setup"

# Set up log rotation
echo "Configuring log rotation..."
setup_logrotate

# Stop existing service if running
if systemctl is-active --quiet musicbox.service; then
    echo "Stopping existing MusicBox service..."
    sudo systemctl stop musicbox.service
    print_status "Service stop"
fi

# Enable SPI interface
echo "Checking SPI configuration..."
if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "Enabling SPI interface..."
    echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
    print_status "SPI configuration"
    echo -e "${YELLOW}Note: SPI has been enabled. A reboot will be required after installation.${NC}"
    needs_reboot=true
else
    echo -e "${GREEN}SPI already enabled${NC}"
fi

# Install required packages
echo "Installing system dependencies..."
sudo apt-get update
if ! dpkg -l | grep -qw python3-pip; then
    sudo apt-get install -y git python3-pip python3-venv vlc logrotate
    print_status "System packages"
else
    echo -e "${YELLOW}System packages already installed${NC}"
fi

# Handle existing installation
if [ -d "$INSTALL_DIR" ]; then
    echo "Existing installation found..."
    cd "$INSTALL_DIR"
    
    # Check if it's a git repository
    if [ -d ".git" ]; then
        echo "Updating existing repository..."
        sudo -u "$SERVICE_USER" git fetch
        if [ "$(git rev-parse HEAD)" != "$(git rev-parse @{u})" ]; then
            sudo -u "$SERVICE_USER" git pull
            needs_restart=true
            print_status "Repository update"
        else
            echo -e "${YELLOW}Repository already up to date${NC}"
        fi
    else
        echo "Backing up existing music directory..."
        mv music music_backup
        echo "Removing old installation..."
        cd ..
        rm -rf "$INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        sudo -u "$SERVICE_USER" git clone "$REPO_URL" .
        print_status "Repository clone"
        
        echo "Restoring music directory..."
        rm -rf music
        mv ../musicbox/music_backup music
        print_status "Music directory restore"
        needs_restart=true
    fi
else
    # Fresh installation
    echo "Creating installation directory..."
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" git clone "$REPO_URL" .
    print_status "Repository clone"
    needs_restart=true
fi

# Set up virtual environment if needed
if [ ! -d "venv" ]; then
    echo "Setting up Python virtual environment..."
    sudo -u "$SERVICE_USER" python3 -m venv venv
    print_status "Virtual environment"
    needs_restart=true
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
fi

# Activate virtual environment and update requirements
source venv/bin/activate
echo "Updating Python requirements..."
sudo -u "$SERVICE_USER" pip install -r requirements.txt
print_status "Python packages"

# Create necessary directories with appropriate permissions
echo "Creating project directories..."
mkdir -p music config logs
chmod 755 config logs
chmod 775 music  # Group writable for music directory
print_status "Project directories"

# Copy default config if it doesn't exist
if [ ! -f config/config.json ]; then
    echo "Creating default configuration..."
    cp config.json config/config.json
    chmod 644 config/config.json
    print_status "Default configuration"
else
    echo -e "${YELLOW}Configuration file already exists${NC}"
fi

# Set up permissions
echo "Setting permissions..."
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
# Add pi user to musicbox group for music file management
usermod -a -G "$SERVICE_GROUP" pi
print_status "Permissions"

# Update systemd service
echo "Updating systemd service..."
sudo bash -c "cat > /etc/systemd/system/musicbox.service" << EOL
[Unit]
Description=MusicBox Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/src/main.py
WorkingDirectory=$INSTALL_DIR
StandardOutput=append:$LOG_DIR/musicbox.log
StandardError=append:$LOG_DIR/musicbox.log
Restart=always

# Security enhancements
ProtectSystem=full
PrivateTmp=true
NoNewPrivileges=true
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictNamespaces=true

# Resource limits
LimitNOFILE=65535
MemoryMax=512M
TasksMax=100

[Install]
WantedBy=multi-user.target
EOL
print_status "Service configuration"

# Reload systemd if service file changed
sudo systemctl daemon-reload

# Enable and restart service if needed
sudo systemctl enable musicbox.service
if [ "$needs_restart" = true ]; then
    echo "Restarting MusicBox service..."
    sudo systemctl restart musicbox.service
    print_status "Service restart"
else
    echo "Starting MusicBox service..."
    sudo systemctl start musicbox.service
    print_status "Service start"
fi

echo -e "\n${GREEN}Installation complete!${NC}"
echo "Service is running as user: $SERVICE_USER"
echo "You can check the service status with: sudo systemctl status musicbox"
echo "View logs with: sudo tail -f $LOG_DIR/musicbox.log"
echo "Add music files to: $INSTALL_DIR/music"
echo -e "${YELLOW}Note: The 'pi' user has been added to the '$SERVICE_GROUP' group."
echo "You may need to log out and log back in for this change to take effect."
if [ "$needs_reboot" = true ]; then
    echo -e "\n${RED}Important: A reboot is required for SPI changes to take effect."
    echo -e "Please reboot your Raspberry Pi with: sudo reboot${NC}"
fi