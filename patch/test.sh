curl -X POST -H "Content-Type: application/json" \
  -d '{
    "@type": "MessageCard",
    "@context": "http://schema.org/extensions",
    "summary": "Test Message",
    "themeColor": "0078D7",
    "title": "Oracle Automation",
    "text": "This is a test message from Ansible job",
    "attachments": [
      {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
          "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
          "type": "AdaptiveCard",
          "version": "1.2",
          "body": [
            {
              "type": "TextBlock",
              "text": "This is an adaptive card attachment",
              "wrap": true
            }
          ]
        }
      }
    ]
  }' \
  "https://outlook.office.com/webhook/..."
