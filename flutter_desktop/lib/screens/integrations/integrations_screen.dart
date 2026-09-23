import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../core/theme.dart';
import '../../models/integration.dart';
import '../../services/integration_service.dart';

class IntegrationsScreen extends StatefulWidget {
  const IntegrationsScreen({super.key});

  @override
  State<IntegrationsScreen> createState() => _IntegrationsScreenState();
}

class _IntegrationsScreenState extends State<IntegrationsScreen> {
  Map<String, dynamic> _configs = {};
  String? _selectedCategory;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await IntegrationService.instance.fetchIntegrations();
      if (mounted) setState(() { _configs = data['integrations'] as Map<String, dynamic>? ?? {}; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<String> get _categories {
    final cats = IntegrationModel.availableIntegrations.map((i) => i['category'] as String).toSet().toList();
    return ['All', ...cats];
  }

  List<Map<String, dynamic>> get _filtered {
    final all = IntegrationModel.availableIntegrations;
    if (_selectedCategory == null || _selectedCategory == 'All') return all;
    return all.where((i) => i['category'] == _selectedCategory).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Integrations Hub', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text('Connect FinTech Desk with your business tools', style: TextStyle(color: Colors.grey.shade600)),
          const SizedBox(height: 24),

          // Category filter
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: _categories.map((cat) => Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FilterChip(
                  label: Text(cat),
                  selected: (_selectedCategory ?? 'All') == cat,
                  onSelected: (v) => setState(() => _selectedCategory = v ? cat : 'All'),
                  selectedColor: AppTheme.primary.withOpacity(0.15),
                ),
              )).toList(),
            ),
          ),
          const SizedBox(height: 24),

          if (_loading)
            const Center(child: CircularProgressIndicator())
          else
            Expanded(
              child: GridView.builder(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 360,
                  crossAxisSpacing: 16,
                  mainAxisSpacing: 16,
                  childAspectRatio: 1.4,
                ),
                itemCount: _filtered.length,
                itemBuilder: (ctx, i) {
                  final int_data = _filtered[i];
                  final id = int_data['id'] as String;
                  final configured = _configs.containsKey(id) && (_configs[id] as Map).isNotEmpty;
                  return _IntegrationCard(
                    data: int_data,
                    configured: configured,
                    onConfigure: () => _showConfigDialog(int_data),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }

  void _showConfigDialog(Map<String, dynamic> intData) {
    final id = intData['id'] as String;
    final existing = Map<String, dynamic>.from((_configs[id] as Map<dynamic, dynamic>?) ?? {});

    showDialog(
      context: context,
      builder: (ctx) => _IntegrationConfigDialog(
        integrationId: id,
        integrationName: intData['name'] as String,
        existingConfig: existing,
        onSave: (config) async {
          try {
            await IntegrationService.instance.saveIntegration(id, config);
            await _load();
            if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('${intData['name']} configured')));
          } catch (e) {
            if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
          }
        },
        onOAuth: id == 'zoho'
          ? () async {
              final cfg = existing;
              if (cfg['client_id']?.toString().isNotEmpty == true) {
                final url = await IntegrationService.instance.getZohoAuthUrl(
                  cfg['client_id'].toString(),
                  cfg['client_secret'].toString(),
                  cfg['redirect_uri']?.toString() ?? 'http://localhost:8000/api/v1/oauth/zoho/callback',
                );
                await launchUrl(Uri.parse(url));
              }
            }
          : id == 'gmail'
            ? () async {
                final cfg = existing;
                if (cfg['client_id']?.toString().isNotEmpty == true) {
                  final url = await IntegrationService.instance.getGmailAuthUrl(
                    cfg['client_id'].toString(),
                    cfg['client_secret'].toString(),
                    cfg['redirect_uri']?.toString() ?? 'http://localhost:8000/api/v1/oauth/google/callback',
                  );
                  await launchUrl(Uri.parse(url));
                }
              }
            : id == 'microsoft'
              ? () async {
                  final cfg = existing;
                  if (cfg['client_id']?.toString().isNotEmpty == true) {
                    final url = await IntegrationService.instance.getMicrosoftAuthUrl(
                      cfg['client_id'].toString(),
                      cfg['client_secret'].toString(),
                      cfg['redirect_uri']?.toString() ?? 'http://localhost:8000/api/v1/oauth/microsoft/callback',
                    );
                    await launchUrl(Uri.parse(url));
                  }
                }
              : null,
        onRemove: () async {
          await IntegrationService.instance.removeIntegration(id);
          await _load();
        },
      ),
    );
  }
}

class _IntegrationCard extends StatelessWidget {
  final Map<String, dynamic> data;
  final bool configured;
  final VoidCallback onConfigure;

  const _IntegrationCard({required this.data, required this.configured, required this.onConfigure});

  Color get _color {
    return switch (data['id'] as String) {
      'zoho' => const Color(0xFFE8541C),
      'gmail' => const Color(0xFFD93025),
      'microsoft' => const Color(0xFF0078D4),
      'whatsapp' => const Color(0xFF25D366),
      'twilio' => const Color(0xFFF22F46),
      'razorpay' => const Color(0xFF2D81FE),
      'stripe' => const Color(0xFF635BFF),
      'telegram' => const Color(0xFF0088CC),
      'slack' => const Color(0xFF4A154B),
      _ => AppTheme.primary,
    };
  }

  @override
  Widget build(BuildContext context) {
    final color = _color;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onConfigure,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(8)),
                  child: Icon(_categoryIcon(data['id'] as String), color: color, size: 22),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: configured ? Colors.green.shade50 : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: configured ? Colors.green.shade200 : Colors.grey.shade300),
                  ),
                  child: Text(
                    configured ? 'Configured' : 'Not Set',
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: configured ? Colors.green.shade700 : Colors.grey.shade600),
                  ),
                ),
              ]),
              const SizedBox(height: 12),
              Text(data['name'] as String, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
              const SizedBox(height: 4),
              Text(data['description'] as String, style: TextStyle(fontSize: 12, color: Colors.grey.shade600), maxLines: 2, overflow: TextOverflow.ellipsis),
              const Spacer(),
              Text(
                (data['features'] as List).take(2).join(' • '),
                style: TextStyle(fontSize: 11, color: color),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData _categoryIcon(String id) {
    return switch (id) {
      'zoho' => Icons.business,
      'gmail' => Icons.mail,
      'microsoft' => Icons.window,
      'whatsapp' => Icons.chat,
      'twilio' => Icons.sms,
      'razorpay' || 'stripe' => Icons.payment,
      'telegram' => Icons.send,
      'slack' => Icons.forum,
      _ => Icons.extension,
    };
  }
}

// Config dialog for each integration
class _IntegrationConfigDialog extends StatefulWidget {
  final String integrationId;
  final String integrationName;
  final Map<String, dynamic> existingConfig;
  final Function(Map<String, dynamic>) onSave;
  final VoidCallback? onOAuth;
  final VoidCallback? onRemove;

  const _IntegrationConfigDialog({
    required this.integrationId,
    required this.integrationName,
    required this.existingConfig,
    required this.onSave,
    this.onOAuth,
    this.onRemove,
  });

  @override
  State<_IntegrationConfigDialog> createState() => _IntegrationConfigDialogState();
}

class _IntegrationConfigDialogState extends State<_IntegrationConfigDialog> {
  late Map<String, TextEditingController> _controllers;
  bool _saving = false;

  List<_Field> get _fields => switch (widget.integrationId) {
    'zoho' => [
        _Field('client_id', 'Client ID', false),
        _Field('client_secret', 'Client Secret', true),
        _Field('redirect_uri', 'Redirect URI', false, hint: 'http://localhost:8000/api/v1/oauth/zoho/callback'),
        _Field('organization_id', 'Zoho Books Org ID (optional)', false),
        _Field('mail_account_id', 'Zoho Mail Account ID (optional)', false),
      ],
    'gmail' => [
        _Field('client_id', 'Google Client ID', false),
        _Field('client_secret', 'Google Client Secret', true),
        _Field('redirect_uri', 'Redirect URI', false, hint: 'http://localhost:8000/api/v1/oauth/google/callback'),
      ],
    'microsoft' => [
        _Field('client_id', 'Azure App Client ID', false),
        _Field('client_secret', 'Azure Client Secret', true),
        _Field('redirect_uri', 'Redirect URI', false, hint: 'http://localhost:8000/api/v1/oauth/microsoft/callback'),
        _Field('tenant', 'Tenant (common or your tenant ID)', false),
      ],
    'whatsapp' => [
        _Field('phone_number_id', 'Phone Number ID', false),
        _Field('access_token', 'Permanent Access Token', true),
        _Field('waba_id', 'WhatsApp Business Account ID', false),
      ],
    'twilio' => [
        _Field('account_sid', 'Account SID', false),
        _Field('auth_token', 'Auth Token', true),
        _Field('from_number', 'From Number (+91...)', false),
      ],
    'razorpay' => [
        _Field('key_id', 'Key ID', false),
        _Field('key_secret', 'Key Secret', true),
        _Field('webhook_secret', 'Webhook Secret (optional)', true),
      ],
    'stripe' => [
        _Field('publishable_key', 'Publishable Key', false),
        _Field('secret_key', 'Secret Key', true),
        _Field('webhook_secret', 'Webhook Secret (optional)', true),
      ],
    'telegram' => [
        _Field('bot_token', 'Bot Token', true),
        _Field('chat_id', 'Default Chat ID / Channel', false),
      ],
    'slack' => [
        _Field('webhook_url', 'Incoming Webhook URL', false),
        _Field('bot_token', 'Bot Token (optional)', true),
        _Field('channel', 'Default Channel', false),
      ],
    _ => <_Field>[],
  };

  @override
  void initState() {
    super.initState();
    _controllers = { for (final f in _fields) f.key: TextEditingController(text: widget.existingConfig[f.key]?.toString() ?? '') };
  }

  @override
  void dispose() {
    for (final c in _controllers.values) c.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final config = { for (final f in _fields) f.key: _controllers[f.key]!.text };
    await widget.onSave(config);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 540),
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text('Configure ${widget.integrationName}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
              IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
            ]),
            const SizedBox(height: 20),

            ..._fields.map((f) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: TextField(
                controller: _controllers[f.key],
                obscureText: f.secret,
                decoration: InputDecoration(
                  labelText: f.label,
                  hintText: f.hint,
                  suffixIcon: f.secret ? const Icon(Icons.lock_outline, size: 16) : null,
                ),
              ),
            )),

            const SizedBox(height: 20),
            Row(children: [
              if (widget.onRemove != null)
                TextButton(
                  onPressed: () { widget.onRemove!(); Navigator.pop(context); },
                  style: TextButton.styleFrom(foregroundColor: Colors.red),
                  child: const Text('Remove'),
                ),
              const Spacer(),
              if (widget.onOAuth != null) ...[
                OutlinedButton.icon(
                  onPressed: () { _save().then((_) => widget.onOAuth!()); },
                  icon: const Icon(Icons.open_in_browser, size: 16),
                  label: const Text('Save & Authorize'),
                ),
                const SizedBox(width: 12),
              ],
              ElevatedButton(
                onPressed: _saving ? null : _save,
                child: Text(_saving ? 'Saving...' : 'Save'),
              ),
            ]),
          ],
        ),
      ),
    );
  }
}

class _Field {
  final String key;
  final String label;
  final bool secret;
  final String? hint;
  const _Field(this.key, this.label, this.secret, {this.hint});
}
