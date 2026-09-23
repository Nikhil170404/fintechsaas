class AppConstants {
  static const String appName = 'FinTech Desk';
  static const String appVersion = '1.0.0';

  // Default backend URL (configurable in settings)
  static const String defaultApiBase = 'http://localhost:8000/api/v1';

  // Shared prefs keys
  static const String prefApiBase = 'api_base_url';
  static const String prefToken = 'auth_token';
  static const String prefUserJson = 'user_json';
  static const String prefTenantJson = 'tenant_json';
  static const String prefThemeMode = 'theme_mode';

  // Integration names
  static const String intZoho = 'zoho';
  static const String intGmail = 'gmail';
  static const String intMicrosoft = 'microsoft';
  static const String intWhatsApp = 'whatsapp';
  static const String intTwilio = 'twilio';
  static const String intRazorpay = 'razorpay';
  static const String intStripe = 'stripe';
  static const String intTelegram = 'telegram';
  static const String intSlack = 'slack';

  // Email providers
  static const List<Map<String, String>> emailProviders = [
    {'id': 'smtp', 'name': 'SMTP (Custom)', 'icon': 'email'},
    {'id': 'gmail', 'name': 'Gmail / Google Workspace', 'icon': 'google'},
    {'id': 'microsoft', 'name': 'Outlook / Microsoft 365', 'icon': 'microsoft'},
    {'id': 'zoho', 'name': 'Zoho Mail', 'icon': 'zoho'},
  ];
}
