#!/bin/bash
# Waybar LED Control Module
# This script provides status output for Waybar and handles mouse clicks

LED_SCRIPT="$(dirname "$(readlink -f "$0")")/../led_control.py"
CACHE_FILE="$HOME/.local/share/ledble_state"

# Function to get status
get_status() {
    if [ -f "$CACHE_FILE" ]; then
        cat "$CACHE_FILE"
    else
        echo "off"
    fi
}

# Function to get icon based on state
get_icon() {
    local state=$(get_status)
    if [ "$state" = "off" ]; then
        echo "󰛩"  # Lightbulb off icon
    else
        echo "󰛨"  # Lightbulb on icon
    fi
}

# Function to get CSS class
get_class() {
    local state=$(get_status)
    if [ "$state" = "off" ]; then
        echo "off"
    else
        echo "on"
    fi
}

# Function to get tooltip
generate_tooltip() {
    local state=$(get_status)
    if [ "$state" = "off" ]; then
        echo "LED OFF - Click to turn on"
    else
        echo "LED ON ($state) - Left: Toggle | Right: Menu"
    fi
}

# Handle different arguments
case "$1" in
    status)
        # Output JSON for Waybar
        icon=$(get_icon)
        tooltip=$(generate_tooltip)
        class=$(get_class)
        echo "{\"text\":\"$icon\",\"tooltip\":\"$tooltip\",\"class\":\"$class\"}"
        ;;
    
    left-click)
        # Toggle on/off
        python3 "$LED_SCRIPT" toggle > /dev/null 2>&1
        ;;
    
    right-click)
        # Show color menu using wofi (Wayland) or rofi (X11)
        if command -v wofi &> /dev/null; then
            MENU_CMD="wofi --dmenu --prompt 'LED Color'"
        elif command -v rofi &> /dev/null; then
            MENU_CMD="rofi -dmenu -p 'LED Color'"
        else
            notify-send "LED Control" "Please install wofi or rofi for color menu"
            exit 1
        fi
        
        # Define color options
        choice=$(printf "Red\nGreen\nBlue\nWhite\nYellow\nPurple\nCyan\nOrange\nPink\nCustom RGB..." | eval "$MENU_CMD")
        
        case "$choice" in
            "Red")
                python3 "$LED_SCRIPT" on red > /dev/null 2>&1
                ;;
            "Green")
                python3 "$LED_SCRIPT" on green > /dev/null 2>&1
                ;;
            "Blue")
                python3 "$LED_SCRIPT" on blue > /dev/null 2>&1
                ;;
            "White")
                python3 "$LED_SCRIPT" on white > /dev/null 2>&1
                ;;
            "Yellow")
                python3 "$LED_SCRIPT" on yellow > /dev/null 2>&1
                ;;
            "Purple")
                python3 "$LED_SCRIPT" on purple > /dev/null 2>&1
                ;;
            "Cyan")
                python3 "$LED_SCRIPT" on cyan > /dev/null 2>&1
                ;;
            "Orange")
                python3 "$LED_SCRIPT" on orange > /dev/null 2>&1
                ;;
            "Pink")
                python3 "$LED_SCRIPT" on pink > /dev/null 2>&1
                ;;
            "Custom RGB...")
                # Get custom RGB values
                if command -v wofi &> /dev/null; then
                    rgb=$(printf "" | wofi --dmenu --prompt "Enter R G B (e.g., 255 128 0)")
                else
                    rgb=$(printf "" | rofi -dmenu -p "Enter R G B (e.g., 255 128 0)")
                fi
                
                if [ -n "$rgb" ]; then
                    python3 "$LED_SCRIPT" on $rgb > /dev/null 2>&1
                fi
                ;;
        esac
        ;;
    
    middle-click)
        # Turn off
        python3 "$LED_SCRIPT" off > /dev/null 2>&1
        ;;
    
    *)
        # Default: show status
        icon=$(get_icon)
        tooltip=$(generate_tooltip)
        class=$(get_class)
        echo "{\"text\":\"$icon\",\"tooltip\":\"$tooltip\",\"class\":\"$class\"}"
        ;;
esac
