#!/bin/bash

# Check if script is run with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "Please run this script with sudo privileges"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Configuration
REPO_URL="https://github.com/carlbunn/musicbox.git"
SERVICE_USER="musicbox"
SERVICE_GROUP="musicbox"
INSTALL_DIR="/opt/musicbox"
LOG_DIR="/var/log/musicbox"
BACKUP_DIR="/opt/musicbox_backup"

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
        systemctl stop musicbox.service 2>/dev/null || true
        systemctl disable musicbox.service 2>/dev/null || true
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

# Function to print a warning
print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

# Function to run commands as service user
run_as_service_user() {
    su - "$SERVICE_USER" -s /bin/bash -c "$1"
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

# Add network interface check
echo "Checking network interfaces..."
if ip link show | grep -q "wlan0"; then
    print_status "Wireless interface found (wlan0)"
else
    print_warning "No wireless interface found - please ensure network connectivity"
fi

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

# Add service user to required hardware groups
echo "Setting up hardware access permissions..."
for group in gpio spi i2c; do
    if getent group $group >/dev/null; then
        usermod -a -G $group "$SERVICE_USER"
    fi
done
print_status "Hardware group permissions"

# Create necessary directories
echo "Setting up directories..."
mkdir -p "$LOG_DIR" "$BACKUP_DIR"
chown "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR" "$BACKUP_DIR"
chmod 755 "$LOG_DIR" "$BACKUP_DIR"
print_status "Directory setup"

# Set up log rotation
echo "Configuring log rotation..."
setup_logrotate

# Enable SPI interface
echo "Checking SPI configuration..."
if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "Enabling SPI interface..."
    echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
    print_status "SPI configuration"
    needs_reboot=true
else
    echo -e "${GREEN}SPI already enabled${NC}"
fi

# Stop existing service if running
if systemctl is-active --quiet musicbox.service; then
    echo "Stopping existing MusicBox service..."
    systemctl stop musicbox.service || true
    print_status "Service stop"
fi

# Install required packages
echo "Installing system packages..."
apt-get update
apt-get install -y \
    git \
    vlc \
    logrotate \
    python3-vlc \
    python3-rpi.gpio \
    python3-pip \
    python3-venv \
    expect
print_status "System packages"

# Handle existing installation
if [ -d "$INSTALL_DIR" ]; then
    echo "Existing installation found..."
    # Backup existing music files
    if [ -d "$INSTALL_DIR/music" ]; then
        echo "Backing up music directory..."
        cp -r "$INSTALL_DIR/music" "$BACKUP_DIR/"
        print_status "Music backup"
    fi
    
    # Remove old installation but keep .git if it exists
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "Updating existing repository..."
        cd "$INSTALL_DIR"
        # Add the safe directory configuration
        git config --global --add safe.directory "$INSTALL_DIR"
        git fetch
        git reset --hard origin/main
        git clean -fd
        needs_restart=true
        print_status "Repository update"
    else
        echo "Performing fresh clone..."
        rm -rf "$INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
        # Add the safe directory configuration before cloning
        git config --global --add safe.directory "$INSTALL_DIR"
        run_as_service_user "git clone $REPO_URL $INSTALL_DIR"
        needs_restart=true
        print_status "Repository clone"
    fi
    
    # Restore music files
    if [ -d "$BACKUP_DIR/music" ]; then
        echo "Restoring music directory..."
        rm -rf "$INSTALL_DIR/music"
        cp -r "$BACKUP_DIR/music" "$INSTALL_DIR/"
        print_status "Music restore"
    fi
else
    # Fresh installation
    echo "Creating installation directory..."
    mkdir -p "$INSTALL_DIR"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    run_as_service_user "git clone $REPO_URL $INSTALL_DIR"
    print_status "Repository clone"
    needs_restart=true
fi

# Create and ensure proper permissions for music directory
echo "Setting up music directory..."
mkdir -p "$INSTALL_DIR/music"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/music"
chmod 775 "$INSTALL_DIR/music"  # Group writable for music directory
print_status "Music directory setup"

echo "Setting up Python environment..."
if [ -d "$INSTALL_DIR/venv" ]; then
    # Check if the venv is functional by trying to run python
    if run_as_service_user "cd $INSTALL_DIR && ./venv/bin/python3 -c 'import sys; sys.exit(0)'"; then
        print_status "Using existing virtual environment"
    else
        echo "Existing virtual environment appears broken, recreating..."
        rm -rf "$INSTALL_DIR/venv"
        run_as_service_user "cd $INSTALL_DIR && python3 -m venv venv"
        print_status "Virtual environment setup"
    fi
else
    run_as_service_user "cd $INSTALL_DIR && python3 -m venv venv"
    print_status "Virtual environment setup"
fi

# Install Python packages
echo "Installing project dependencies..."
run_as_service_user "cd $INSTALL_DIR && source venv/bin/activate && pip install -r requirements.txt"
print_status "Python packages"

# Create necessary directories with appropriate permissions
echo "Setting up project directories..."
mkdir -p "$INSTALL_DIR"/{music,config,logs}
chmod 755 "$INSTALL_DIR"/config "$INSTALL_DIR"/logs
chmod 775 "$INSTALL_DIR"/music  # Group writable for music directory
print_status "Project directories"

# Configure Samba
echo "Configuring Samba share..."
# Backup existing config
cp /etc/samba/smb.conf /etc/samba/smb.conf.bak

# Create new smb.conf with only our share
cat > /etc/samba/smb.conf << EOL
[global]
   workgroup = WORKGROUP
   server string = %h server (Samba, MusicBox)
   log file = /var/log/samba/log.%m
   max log size = 1000
   logging = file
   panic action = /usr/share/samba/panic-action %d
   server role = standalone server
   obey pam restrictions = yes
   unix password sync = yes
   passwd program = /usr/bin/passwd %u
   passwd chat = *Enter\snew\s*\spassword:* %n\n *Retype\snew\s*\spassword:* %n\n *password\supdated\ssuccessfully* .
   pam password change = yes
   map to guest = bad user
   usershare allow guests = yes

# MusicBox Share Configuration
[musicbox]
   path = $INSTALL_DIR/music
   browseable = yes
   read only = no
   guest ok = yes
   public = yes
   create mode = 0666
   directory mode = 0777
   force user = $SERVICE_USER
   force group = $SERVICE_GROUP
EOL

# Restart Samba services
systemctl restart smbd nmbd
print_status "Samba configuration"

# Copy default config if it doesn't exist
if [ ! -f "$INSTALL_DIR/config/config.json" ] && [ -f "$INSTALL_DIR/config.json" ]; then
    echo "Creating default configuration..."
    cp "$INSTALL_DIR/config.json" "$INSTALL_DIR/config/config.json"
    chmod 644 "$INSTALL_DIR/config/config.json"
    print_status "Default configuration"
else
    echo -e "${YELLOW}Configuration file already exists${NC}"
fi

# Configure firewall rules
echo "Configuring firewall..."
if command -v ufw >/dev/null; then
    # API port
    ufw allow 8000/tcp comment 'MusicBox API'
    
    # SMB ports
    ufw allow 139/tcp comment 'SMB NetBIOS'
    ufw allow 445/tcp comment 'SMB Direct'
    
    # Optional: Allow SMB discovery
    ufw allow 137/udp comment 'SMB NetBIOS Name'
    ufw allow 138/udp comment 'SMB NetBIOS Datagram'
    
    print_status "Firewall configured for MusicBox ports"
else
    print_warning "UFW not installed, please ensure the following ports are accessible:
    - TCP 8000 (API)
    - TCP 139, 445 (SMB)
    - UDP 137, 138 (SMB Discovery)"
fi

# Set up permissions
echo "Setting permissions..."
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
if [ -n "$SUDO_USER" ]; then
    usermod -a -G "$SERVICE_GROUP" "$SUDO_USER"
    print_status "Permissions (user $SUDO_USER added to $SERVICE_GROUP)"
else
    print_warning "Could not determine original user, you may need to manually add your user to the $SERVICE_GROUP group"
fi

# Update systemd service
echo "Updating systemd service..."
cat > /etc/systemd/system/musicbox.service << EOL
[Unit]
Description=MusicBox Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/src/main.py
WorkingDirectory=$INSTALL_DIR
StandardOutput=append:$LOG_DIR/musicbox.log
StandardError=append:$LOG_DIR/musicbox.log

# Restart configuration
Restart=on-failure
RestartSec=10s
StartLimitInterval=5min
StartLimitBurst=10

# Environment
Environment=PYTHONUNBUFFERED=1
Environment=MUSICBOX_ENV=production

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

# Reload systemd
systemctl daemon-reload

# Enable and restart service
systemctl enable musicbox.service
if [ "$needs_restart" = true ]; then
    echo "Restarting MusicBox service..."
    systemctl restart musicbox.service
    sleep 2  # Give the service a moment to start
    print_status "Service restart"
else
    echo "Starting MusicBox service..."
    systemctl start musicbox.service
    sleep 2  # Give the service a moment to start
    print_status "Service start"
fi

# Verify service is running and provide diagnostic information
echo "Verifying service status..."
sleep 2  # Give the service a moment to start

# Check service status more comprehensively
SERVICE_STATUS=$(systemctl is-active musicbox.service)
if [ "$SERVICE_STATUS" = "active" ] || [ "$SERVICE_STATUS" = "activating" ]; then
    print_status "Service verification"
    echo -e "${GREEN}Service is running normally. Available at:${NC}"
    echo "- Status: sudo systemctl status musicbox"
    echo "- Logs: sudo tail -f $LOG_DIR/musicbox.log"
else
    echo -e "${RED}Warning: Service status check returned: $SERVICE_STATUS${NC}"
    echo "Checking logs for errors..."
    tail -n 20 "$LOG_DIR/musicbox.log"
    
    # Check if we see the control messages that indicate successful startup
    if grep -q "Available mappings:" "$LOG_DIR/musicbox.log"; then
        echo -e "${GREEN}Service appears to be functioning despite status check${NC}"
        print_status "Service verification"
    else
        echo -e "${RED}Service may not be running correctly. Please check logs for details.${NC}"
        exit 1
    fi
fi

# Ask user if they want to setup Bluetooth
read -p "Would you like to set up a Bluetooth speaker? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Setting up Bluetooth..."
    ./setup_bluetooth.sh
    print_status "Bluetooth setup"
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