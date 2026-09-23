import '../core/api_client.dart';

class IntegrationService {
  static final IntegrationService instance = IntegrationService._();
  IntegrationService._();

  Future<Map<String, dynamic>> fetchIntegrations() async {
    return ApiClient.instance.get('/integrations');
  }

  Future<void> saveIntegration(String name, Map<String, dynamic> config) async {
    await ApiClient.instance.put('/integrations/$name', data: config);
  }

  Future<void> removeIntegration(String name) async {
    await ApiClient.instance.delete('/integrations/$name');
  }

  // Zoho
  Future<String> getZohoAuthUrl(String clientId, String clientSecret, String redirectUri) async {
    await saveIntegration('zoho', {
      'client_id': clientId,
      'client_secret': clientSecret,
      'redirect_uri': redirectUri,
    });
    // Return auth URL for browser opening
    final scope = 'ZohoCRM.modules.ALL,ZohoBooks.invoices.ALL,ZohoMail.accounts.ALL';
    return 'https://accounts.zoho.com/oauth/v2/auth?response_type=code'
        '&client_id=$clientId&scope=$scope&redirect_uri=$redirectUri&access_type=offline';
  }

  Future<List<Map<String, dynamic>>> syncZohoContacts() async {
    final data = await ApiClient.instance.post('/integrations/zoho/sync-contacts');
    return (data['contacts'] as List<dynamic>? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  Future<Map<String, dynamic>> pushClientToZoho(Map<String, dynamic> client) async {
    return ApiClient.instance.post('/integrations/zoho/push-contact', data: client);
  }

  // Gmail
  Future<String> getGmailAuthUrl(String clientId, String clientSecret, String redirectUri) async {
    await saveIntegration('gmail', {
      'client_id': clientId,
      'client_secret': clientSecret,
      'redirect_uri': redirectUri,
    });
    final scope = Uri.encodeComponent(
        'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email');
    return 'https://accounts.google.com/o/oauth2/v2/auth?response_type=code'
        '&client_id=$clientId&redirect_uri=${Uri.encodeComponent(redirectUri)}'
        '&scope=$scope&access_type=offline&prompt=consent';
  }

  // Microsoft
  Future<String> getMicrosoftAuthUrl(String clientId, String clientSecret, String redirectUri) async {
    await saveIntegration('microsoft', {
      'client_id': clientId,
      'client_secret': clientSecret,
      'redirect_uri': redirectUri,
    });
    final scope = Uri.encodeComponent('offline_access Mail.Send Mail.Read User.Read Contacts.Read');
    return 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?response_type=code'
        '&client_id=$clientId&redirect_uri=${Uri.encodeComponent(redirectUri)}'
        '&scope=$scope&response_mode=query';
  }

  // Payment links
  Future<String> createRazorpayLink(Map<String, dynamic> client, double amount, String description) async {
    final data = await ApiClient.instance.post('/payments/razorpay/link', data: {
      'client': client,
      'amount': amount,
      'description': description,
    });
    return data['url'] as String? ?? '';
  }

  // Settings
  Future<Map<String, dynamic>> fetchSettings() async {
    return ApiClient.instance.get('/settings');
  }

  Future<void> updateSettings(Map<String, dynamic> settings) async {
    await ApiClient.instance.put('/settings', data: settings);
  }

  Future<void> updateSmtp(Map<String, dynamic> smtpConfig) async {
    await ApiClient.instance.put('/settings/smtp', data: smtpConfig);
  }

  // Team
  Future<List<Map<String, dynamic>>> fetchTeam() async {
    final data = await ApiClient.instance.get('/team');
    return (data['team'] as List<dynamic>? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  Future<void> addTeamMember(String username, String email, String password, String role) async {
    await ApiClient.instance.post('/team', data: {
      'username': username,
      'email': email,
      'password': password,
      'role': role,
    });
  }

  Future<void> removeTeamMember(int userId) async {
    await ApiClient.instance.delete('/team/$userId');
  }

  // Audit log
  Future<List<Map<String, dynamic>>> fetchAuditLog({int limit = 100}) async {
    final data = await ApiClient.instance.get('/audit-log', params: {'limit': limit});
    return (data['log'] as List<dynamic>? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }
}
