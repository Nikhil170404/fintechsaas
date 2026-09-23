enum IntegrationStatus { connected, disconnected, error }

class IntegrationModel {
  final String id;
  final String name;
  final String description;
  final String iconAsset;
  final IntegrationStatus status;
  final Map<String, dynamic> config;

  const IntegrationModel({
    required this.id,
    required this.name,
    required this.description,
    required this.iconAsset,
    required this.status,
    required this.config,
  });

  bool get isConnected => status == IntegrationStatus.connected;

  static const List<Map<String, dynamic>> availableIntegrations = [
    {
      'id': 'zoho',
      'name': 'Zoho Suite',
      'description': 'Zoho CRM, Books, and Mail integration',
      'category': 'CRM & Business',
      'features': ['Sync contacts', 'Create invoices', 'Send via Zoho Mail', 'Track leads'],
    },
    {
      'id': 'gmail',
      'name': 'Gmail / Google Workspace',
      'description': 'Send emails via Gmail or Google Workspace',
      'category': 'Email',
      'features': ['OAuth 2.0', 'Bulk send', 'Attachment support', 'Send as alias'],
    },
    {
      'id': 'microsoft',
      'name': 'Microsoft 365 / Outlook',
      'description': 'Outlook email and Microsoft 365 integration',
      'category': 'Email',
      'features': ['OAuth 2.0', 'Outlook email', 'Teams notifications', 'Contact sync'],
    },
    {
      'id': 'whatsapp',
      'name': 'WhatsApp Business',
      'description': 'Send statements and documents via WhatsApp',
      'category': 'Messaging',
      'features': ['Document delivery', 'Template messages', 'Bulk send', 'Media upload'],
    },
    {
      'id': 'twilio',
      'name': 'Twilio SMS / WhatsApp',
      'description': 'SMS and WhatsApp delivery via Twilio',
      'category': 'Messaging',
      'features': ['SMS alerts', 'WhatsApp messages', 'Bulk SMS', 'Delivery reports'],
    },
    {
      'id': 'razorpay',
      'name': 'Razorpay',
      'description': 'Generate payment links for invoices',
      'category': 'Payments',
      'features': ['Payment links', 'Order tracking', 'Webhook verification'],
    },
    {
      'id': 'stripe',
      'name': 'Stripe',
      'description': 'International payment processing via Stripe',
      'category': 'Payments',
      'features': ['Payment links', 'Invoice creation', 'Subscription management'],
    },
    {
      'id': 'telegram',
      'name': 'Telegram Bot',
      'description': 'Send documents and notifications via Telegram',
      'category': 'Messaging',
      'features': ['Document delivery', 'Bot notifications', 'Group/channel delivery'],
    },
    {
      'id': 'slack',
      'name': 'Slack',
      'description': 'Internal team notifications via Slack',
      'category': 'Collaboration',
      'features': ['Webhook notifications', 'Send summaries', 'Job status alerts'],
    },
  ];
}
