#!/bin/bash

# Check if script is run with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "Please run this script with sudo privileges"
    echo "Usage: sudo ./uninstall.sh"
    exit 1
fi

# Configuration
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

# Function to print status
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}!${NC} $1"
}

echo "Starting MusicBox uninstallation..."

# Ask for confirmation
read -p "This will remove all MusicBox files and configurations. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 1
fi

# Ask about music files
read -p "Would you like to keep the music files? (Y/n) " -n 1 -r
echo
KEEP_MUSIC=true
if [[ $REPLY =~ ^[Nn]$ ]]; then
    KEEP_MUSIC=false
fi

# Stop and remove service
echo "Removing systemd service..."
if systemctl is-active --quiet musicbox.service; then
    systemctl stop musicbox.service 2>/dev/null || print_warning "Service was not running"
fi
systemctl disable musicbox.service 2>/dev/null || print_warning "Service was not enabled"
rm -f /etc/systemd/system/musicbox.service
systemctl daemon-reload
print_status "Service removed"

# Backup music if requested
if [ "$KEEP_MUSIC" = true ] && [ -d "$INSTALL_DIR/music" ]; then
    echo "Backing up music files..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    MUSIC_BACKUP="$HOME/musicbox_music_backup_$TIMESTAMP"
    mkdir -p "$MUSIC_BACKUP"
    cp -r "$INSTALL_DIR/music"/* "$MUSIC_BACKUP"/ 2>/dev/null || print_warning "No music files found"
    print_status "Music files backed up to $MUSIC_BACKUP"
fi

# Remove firewall rules
if command -v ufw >/dev/null; then
    echo "Removing firewall rules..."
    # Remove API rule
    ufw delete allow 8000/tcp >/dev/null 2>&1 || print_warning "Could not remove API firewall rule"
    
    # Remove SMB rules
    ufw delete allow 139/tcp >/dev/null 2>&1 || print_warning "Could not remove SMB TCP firewall rule"
    ufw delete allow 445/tcp >/dev/null 2>&1 || print_warning "Could not remove SMB TCP firewall rule"
    ufw delete allow 137/udp >/dev/null 2>&1 || print_warning "Could not remove SMB UDP firewall rule"
    ufw delete allow 138/udp >/dev/null 2>&1 || print_warning "Could not remove SMB UDP firewall rule"
    
    print_status "Firewall rules cleaned up"
fi

# Remove log rotation configuration
echo "Removing log rotation configuration..."
rm -f /etc/logrotate.d/musicbox
print_status "Log rotation configuration removed"

# Remove Samba configuration
echo "Removing Samba configuration..."
if [ -f /etc/samba/smb.conf.bak ]; then
    mv /etc/samba/smb.conf.bak /etc/samba/smb.conf
    systemctl restart smbd nmbd
    print_status "Samba configuration restored"
else
    # If no backup exists, just remove our section
    sed -i '/# MusicBox Share Configuration/,/force group/d' /etc/samba/smb.conf
    systemctl restart smbd nmbd
    print_status "Samba configuration removed"
fi

# Remove log directory
echo "Removing log directory..."
rm -rf "$LOG_DIR"
print_status "Log directory removed"

# Remove backup directory
echo "Removing backup directory..."
rm -rf "$BACKUP_DIR"
print_status "Backup directory removed"

# Remove installation directory
echo "Removing installation directory..."
rm -rf "$INSTALL_DIR"
print_status "Installation directory removed"

# Remove user and group
echo "Removing service user and group..."
if id "$SERVICE_USER" &>/dev/null; then
    # Remove from hardware groups first
    for group in gpio spi i2c; do
        if getent group $group >/dev/null; then
            gpasswd -d "$SERVICE_USER" $group 2>/dev/null || print_warning "Could not remove $SERVICE_USER from $group group"
        fi
    done
    
    pkill -u "$SERVICE_USER" || print_warning "No processes found for $SERVICE_USER"
    userdel "$SERVICE_USER" || print_warning "Could not remove user $SERVICE_USER"
    print_status "Service user removed"
else
    print_warning "Service user did not exist"
fi

# Remove original user from the service group before removing group
if [ -n "$SUDO_USER" ]; then
    gpasswd -d "$SUDO_USER" "$SERVICE_GROUP" 2>/dev/null || print_warning "Could not remove $SUDO_USER from $SERVICE_GROUP"
    print_status "Removed $SUDO_USER from $SERVICE_GROUP"
fi

if getent group "$SERVICE_GROUP" >/dev/null; then
    groupdel "$SERVICE_GROUP" || print_warning "Could not remove group $SERVICE_GROUP"
    print_status "Service group removed"
else
    print_warning "Service group did not exist"
fi

# Clean up Python packages (optional since we used venv)
echo "Checking for system-wide Python packages..."
pip3 list | grep -E "python-vlc|mfrc522" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    print_warning "Found system-wide Python packages. These can be removed manually with pip if needed."
fi

# Check SPI configuration
echo "Checking SPI configuration..."
if [ $(raspi-config nonint get_spi) -eq 0 ]; then
    echo "SPI is currently enabled"
    echo "Note: SPI might be used by other services. Do you want to disable it?"
    read -p "Disable SPI? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        raspi-config nonint do_spi 1  # 1 means disable
        print_status "SPI disabled"
        echo -e "${YELLOW}Note: A reboot is required for SPI changes to take effect.${NC}"
    else
        print_warning "SPI configuration left unchanged"
    fi
fi

echo -e "\n${GREEN}Uninstallation complete!${NC}"
if [ "$KEEP_MUSIC" = true ] && [ -d "$MUSIC_BACKUP" ]; then
    echo "Your music files have been backed up to: $MUSIC_BACKUP"
fi
echo "You may want to:"
echo "1. Remove system packages if no longer needed:"
echo "   sudo apt remove vlc python3-vlc"
echo "2. Reboot the system if SPI configuration was changed"