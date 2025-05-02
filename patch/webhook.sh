#!/bin/bash

# Teams webhook URL - replace with your actual webhook URL
WEBHOOK_URL="YOUR_WEBHOOK_URL_HERE"

# Function to send a message with HTML-style color formatting
send_html_color_message() {
    # Create the JSON payload with HTML-like color formatting
    payload=$(cat <<EOF
{
    "@type": "MessageCard",
    "@context": "http://schema.org/extensions",
    "title": "Status Report",
    "text": "<span style='color: green;'>✅ All systems operational</span><br><span style='color: red;'>❌ Database connection failed</span>"
}
EOF
)

    # Send the request using curl
    curl -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL"
    echo -e "\nSent message with HTML-style colors"
}

# Function to send a message with container-based color styling (more reliable)
send_container_color_message() {
    # Create the JSON payload with container styling
    payload=$(cat <<EOF
{
    "type": "AdaptiveCard",
    "\$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
    "version": "1.4",
    "body": [
        {
            "type": "TextBlock",
            "text": "Status Report",
            "weight": "bolder",
            "size": "medium"
        },
        {
            "type": "Container",
            "style": "good",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "✅ All systems operational",
                    "wrap": true
                }
            ]
        },
        {
            "type": "Container",
            "style": "attention",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "❌ Database connection failed",
                    "wrap": true
                }
            ]
        }
    ]
}
EOF
)

    # Send the request using curl
    curl -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL"
    echo -e "\nSent message with container-based colors"
}

# Function to send a custom message with a specified color
send_custom_message() {
    local message=$1
    local color=$2
    local style="default"

    # Map color to container style
    if [ "$color" == "green" ]; then
        style="good"
    elif [ "$color" == "red" ]; then
        style="attention"
    elif [ "$color" == "blue" ]; then
        style="accent"
    elif [ "$color" == "yellow" ]; then
        style="warning"
    fi

    # Create the JSON payload with the provided message and color
    payload=$(cat <<EOF
{
    "type": "AdaptiveCard",
    "\$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
    "version": "1.4",
    "body": [
        {
            "type": "Container",
            "style": "$style",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "$message",
                    "wrap": true
                }
            ]
        }
    ]
}
EOF
)

    # Send the request using curl
    curl -H "Content-Type: application/json" -d "$payload" "$WEBHOOK_URL"
    echo -e "\nSent custom message with $color color"
}

# Display menu
echo "Microsoft Teams Webhook Color Message Sender"
echo "-------------------------------------------"
echo "1. Send message with HTML-style colors"
echo "2. Send message with container-based colors"
echo "3. Send custom green message"
echo "4. Send custom red message"
echo "5. Exit"
echo

read -p "Choose an option (1-5): " option

case $option in
    1)
        send_html_color_message
        ;;
    2)
        send_container_color_message
        ;;
    3)
        read -p "Enter your message: " message
        send_custom_message "$message" "green"
        ;;
    4)
        read -p "Enter your message: " message
        send_custom_message "$message" "red"
        ;;
    5)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid option. Exiting..."
        exit 1
        ;;
esac

echo "Done!"