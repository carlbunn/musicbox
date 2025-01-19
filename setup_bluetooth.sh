#!/bin/bash

# Check if script is run with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "Please run this script with sudo privileges"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Function to handle errors
handle_error() {
    local exit_code=$?
    local line_number=$1
    echo -e "\nError occurred in script at line ${line_number}"
    exit $exit_code
}

trap 'handle_error ${LINENO}' ERR

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to print status
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} Error: $1 failed"
        exit 1
    fi
}

echo "Starting Bluetooth speaker setup..."

# Install required packages
echo "Installing required packages..."
apt-get update
apt-get install -y build-essential git automake libtool pkg-config \
    libasound2-dev libdbus-1-dev libglib2.0-dev libbluetooth-dev libsbc-dev \
    bluetooth bluez rfkill
print_status "Package installation"

# Build and install bluez-alsa
echo "Building bluez-alsa..."
cd /tmp
rm -rf bluez-alsa
git clone https://github.com/Arkq/bluez-alsa.git
cd bluez-alsa
autoreconf --install --force
mkdir -p build
cd build
../configure --enable-systemd
make
make install
print_status "bluez-alsa build and installation"

# Set up system users
echo "Setting up system users..."
adduser --system --group --no-create-home bluealsa
adduser --system --group --no-create-home bluealsa-aplay
adduser bluealsa-aplay audio
adduser bluealsa bluetooth
print_status "User setup"

# Enable and start services
echo "Configuring services..."
systemctl enable bluealsa.service
systemctl enable bluealsa-aplay.service
systemctl daemon-reload
systemctl start bluetooth
print_status "Service configuration"

# Ensure Bluetooth isn't blocked
rfkill unblock bluetooth
sleep 2  # Give Bluetooth time to initialize

# Function to discover and pair Bluetooth device
discover_and_pair_device() {
    local MAX_ATTEMPTS=3
    local attempt=1
    local device_selected=false
    local mac_address=""
    
    while [ $attempt -le $MAX_ATTEMPTS ] && [ "$device_selected" = false ]; do
        echo -e "\nAttempt $attempt of $MAX_ATTEMPTS to discover Bluetooth devices"
        echo "Please ensure your Bluetooth speaker is in pairing mode"
        echo "Scanning for devices..."
        
        # Start scan and collect devices
        devices=$(timeout 10s bluetoothctl scan on & sleep 5 && bluetoothctl devices)
        
        if [ -z "$devices" ]; then
            echo -e "${YELLOW}No devices found. Retrying...${NC}"
            ((attempt++))
            continue
        }
        
        # Display devices with numbers
        echo -e "\nAvailable devices:"
        echo "$devices" | nl
        
        # Ask user to select a device
        echo -e "\nEnter the number of the device you want to connect to (or 'r' to rescan):"
        read selection
        
        if [ "$selection" = "r" ]; then
            ((attempt++))
            continue
        fi
        
        # Get the MAC address of the selected device
        mac_address=$(echo "$devices" | sed -n "${selection}p" | awk '{print $2}')
        
        if [ -n "$mac_address" ]; then
            device_selected=true
        else
            echo -e "${RED}Invalid selection. Please try again.${NC}"
            ((attempt++))
        fi
    done
    
    if [ "$device_selected" = false ]; then
        echo -e "${RED}Failed to select a device after $MAX_ATTEMPTS attempts${NC}"
        exit 1
    fi
    
    # Pair and trust the device
    echo "Attempting to pair with device: $mac_address"
    bluetoothctl pair $mac_address
    
    if [ $? -eq 0 ]; then
        echo "Trusting device..."
        bluetoothctl trust $mac_address
        echo "Connecting to device..."
        bluetoothctl connect $mac_address
        
        # Create udev rule for auto-connect
        echo "Setting up auto-connect..."
        echo "ACTION==\"add\", SUBSYSTEM==\"bluetooth\", ATTR{address}==\"$mac_address\", ATTR{type}==\"1\", ENV{SYSTEMD_WANTS}+=\"bluetooth-auto-connect@%k.service\"" > /etc/udev/rules.d/99-bluetooth-connect.rules
        
        # Reload udev rules
        udevadm control --reload-rules
        
        print_status "Bluetooth device setup"
        
        # Store the MAC address for future reference
        echo "BLUETOOTH_MAC=$mac_address" > /etc/musicbox/bluetooth.conf
        
        return 0
    else
        echo -e "${RED}Failed to pair with device${NC}"
        return 1
    fi
}

# Main setup process
echo "Starting Bluetooth device discovery..."
discover_and_pair_device

# Final status check
echo -e "\nChecking final status..."
systemctl status bluealsa --no-pager
systemctl status bluealsa-aplay --no-pager

echo -e "\n${GREEN}Bluetooth setup complete!${NC}"
echo "Your Bluetooth speaker should now connect automatically on startup"
echo "You can manually connect using: bluetoothctl connect $mac_address"