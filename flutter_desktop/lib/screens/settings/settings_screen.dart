import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/api_client.dart';
import '../../services/integration_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabs;
  bool _loading = true;
  bool _saving = false;

  final _companyName = TextEditingController();
  final _brandColor = TextEditingController(text: '#1565C0');
  final _smtpHost = TextEditingController();
  final _smtpPort = TextEditingController(text: '587');
  final _smtpUser = TextEditingController();
  final _smtpPass = TextEditingController();
  bool _smtpTls = true;
  final _backendUrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _loadSettings();
    _loadBackendUrl();
  }

  @override
  void dispose() {
    _tabs.dispose();
    _companyName.dispose();
    _brandColor.dispose();
    _smtpHost.dispose();
    _smtpPort.dispose();
    _smtpUser.dispose();
    _smtpPass.dispose();
    _backendUrl.dispose();
    super.dispose();
  }

  Future<void> _loadSettings() async {
    try {
      final s = await IntegrationService.instance.fetchSettings();
      if (mounted) {
        setState(() {
          _companyName.text = s['company_name']?.toString() ?? '';
          _brandColor.text = s['brand_color']?.toString() ?? '#1565C0';
          _smtpHost.text = s['smtp_host']?.toString() ?? '';
          _smtpPort.text = s['smtp_port']?.toString() ?? '587';
          _smtpUser.text = s['smtp_user']?.toString() ?? '';
          _smtpTls = s['smtp_use_tls'] as bool? ?? true;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadBackendUrl() async {
    final prefs = await SharedPreferences.getInstance();
    _backendUrl.text = prefs.getString('api_base_url') ?? 'http://localhost:8000/api/v1';
  }

  Future<void> _saveCompany() async {
    setState(() => _saving = true);
    try {
      await IntegrationService.instance.updateSettings({
        'company_name': _companyName.text,
        'brand_color': _brandColor.text,
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Company settings saved')));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _saveSmtp() async {
    if (_smtpHost.text.isEmpty || _smtpUser.text.isEmpty || _smtpPass.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Fill all SMTP fields')));
      return;
    }
    setState(() => _saving = true);
    try {
      await IntegrationService.instance.updateSmtp({
        'smtp_host': _smtpHost.text,
        'smtp_port': int.tryParse(_smtpPort.text) ?? 587,
        'smtp_user': _smtpUser.text,
        'smtp_password': _smtpPass.text,
        'smtp_use_tls': _smtpTls,
      });
      if (mounted) {
        _smtpPass.clear();
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('SMTP settings saved')));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _saveBackendUrl() async {
    final url = _backendUrl.text.trim();
    ApiClient.instance.setBaseUrl(url);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('api_base_url', url);
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Backend URL saved — restart the app to reconnect')));
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Settings', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 24),

          TabBar(
            controller: _tabs,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            tabs: const [
              Tab(text: 'Company'),
              Tab(text: 'SMTP Email'),
              Tab(text: 'App / Backend'),
            ],
          ),
          const SizedBox(height: 24),

          if (_loading)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else
            Expanded(
              child: TabBarView(
                controller: _tabs,
                children: [
                  // Company tab
                  _SettingsCard(
                    title: 'Company Details',
                    onSave: _saveCompany,
                    saving: _saving,
                    child: Column(children: [
                      TextField(controller: _companyName, decoration: const InputDecoration(labelText: 'Company Name')),
                      const SizedBox(height: 16),
                      TextField(controller: _brandColor, decoration: const InputDecoration(labelText: 'Brand Color (hex)', hintText: '#1565C0')),
                    ]),
                  ),

                  // SMTP tab
                  _SettingsCard(
                    title: 'SMTP Configuration',
                    subtitle: 'Used for sending emails via the default SMTP provider. Works with Gmail, Outlook, and any custom SMTP server.',
                    onSave: _saveSmtp,
                    saving: _saving,
                    child: Column(children: [
                      Row(children: [
                        Expanded(flex: 3, child: TextField(controller: _smtpHost, decoration: const InputDecoration(labelText: 'SMTP Host', hintText: 'smtp.gmail.com'))),
                        const SizedBox(width: 16),
                        Expanded(child: TextField(controller: _smtpPort, decoration: const InputDecoration(labelText: 'Port'), keyboardType: TextInputType.number)),
                      ]),
                      const SizedBox(height: 16),
                      TextField(controller: _smtpUser, decoration: const InputDecoration(labelText: 'Username / Email')),
                      const SizedBox(height: 16),
                      TextField(
                        controller: _smtpPass,
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Password / App Password',
                          helperText: 'Leave blank to keep existing password',
                          suffixIcon: Icon(Icons.lock_outline, size: 16),
                        ),
                      ),
                      const SizedBox(height: 16),
                      SwitchListTile(
                        title: const Text('Use STARTTLS / TLS'),
                        subtitle: const Text('Enable for Gmail (port 587), Outlook, and most providers'),
                        value: _smtpTls,
                        onChanged: (v) => setState(() => _smtpTls = v),
                        contentPadding: EdgeInsets.zero,
                      ),
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.blue.shade50,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          const Text('Common SMTP Settings:', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                          const SizedBox(height: 6),
                          _SmtpTip('Gmail', 'smtp.gmail.com', '587', 'Use App Password (2FA required)'),
                          _SmtpTip('Outlook/Office365', 'smtp.office365.com', '587', 'Use your Microsoft password'),
                          _SmtpTip('Yahoo', 'smtp.mail.yahoo.com', '587', 'Use App Password'),
                          _SmtpTip('Custom', 'your.smtp.host', '587 or 465', 'Contact your email provider'),
                        ]),
                      ),
                    ]),
                  ),

                  // App tab
                  _SettingsCard(
                    title: 'Backend Connection',
                    subtitle: 'Configure the FinTech SaaS backend server this desktop app connects to.',
                    onSave: _saveBackendUrl,
                    saving: _saving,
                    child: Column(children: [
                      TextField(
                        controller: _backendUrl,
                        decoration: const InputDecoration(
                          labelText: 'Backend API URL',
                          hintText: 'http://localhost:8000/api/v1',
                          prefixIcon: Icon(Icons.dns_outlined, size: 18),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'For local install: http://localhost:8000/api/v1\n'
                        'For remote server: https://yourserver.com/api/v1',
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                      ),
                    ]),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _SmtpTip extends StatelessWidget {
  final String provider;
  final String host;
  final String port;
  final String note;

  const _SmtpTip(this.provider, this.host, this.port, this.note);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: RichText(
        text: TextSpan(
          style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
          children: [
            TextSpan(text: '$provider: ', style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.black87)),
            TextSpan(text: '$host:$port — $note'),
          ],
        ),
      ),
    );
  }
}

class _SettingsCard extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget child;
  final VoidCallback onSave;
  final bool saving;

  const _SettingsCard({required this.title, this.subtitle, required this.child, required this.onSave, required this.saving});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              if (subtitle != null) ...[
                const SizedBox(height: 4),
                Text(subtitle!, style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
              ],
              const SizedBox(height: 20),
              child,
              const SizedBox(height: 24),
              Align(
                alignment: Alignment.centerRight,
                child: ElevatedButton(
                  onPressed: saving ? null : onSave,
                  child: Text(saving ? 'Saving...' : 'Save Changes'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
