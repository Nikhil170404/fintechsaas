import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../services/auth_service.dart';
import '../../services/document_service.dart';
import '../../widgets/sidebar.dart';
import '../clients/clients_screen.dart';
import '../statements/statements_screen.dart';
import '../invoices/invoice_screen.dart';
import '../loans/loans_screen.dart';
import '../portfolio/portfolio_screen.dart';
import '../email/email_screen.dart';
import '../integrations/integrations_screen.dart';
import '../settings/settings_screen.dart';
import '../audit/audit_screen.dart';
import '../ai/ai_chat_screen.dart';

class DashboardScreen extends StatefulWidget {
  final int selectedIndex;
  final ValueChanged<int> onSelectIndex;
  final VoidCallback onToggleTheme;
  final ThemeMode themeMode;

  const DashboardScreen({
    super.key,
    required this.selectedIndex,
    required this.onSelectIndex,
    required this.onToggleTheme,
    required this.themeMode,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _clientCount = 0;
  int _fileCount = 0;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadStats();
  }

  Future<void> _loadStats() async {
    try {
      final clients = await DocumentService.instance.fetchClients();
      final files = await DocumentService.instance.fetchFiles();
      if (mounted) {
        setState(() {
          _clientCount = clients.length;
          _fileCount = files.length;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          AppSidebar(
            selectedIndex: widget.selectedIndex,
            onSelect: widget.onSelectIndex,
            onToggleTheme: widget.onToggleTheme,
            themeMode: widget.themeMode,
            onLogout: _logout,
          ),
          Expanded(
            child: _buildContent(widget.selectedIndex),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(int index) {
    switch (index) {
      case 0:
        return _DashboardHome(
          clientCount: _clientCount,
          fileCount: _fileCount,
          loading: _loading,
          onRefresh: _loadStats,
          onNavigate: widget.onSelectIndex,
        );
      case 1:  return const ClientsScreen();
      case 2:  return const StatementsScreen();
      case 3:  return const InvoiceScreen();
      case 4:  return const LoansScreen();
      case 5:  return const PortfolioScreen();
      case 6:  return const EmailScreen();
      case 7:  return const IntegrationsScreen();
      case 8:  return const SettingsScreen();
      case 9:  return const TeamScreen();
      case 10: return const AuditScreen();
      case 11: return const AiChatScreen();
      default:
        return _DashboardHome(
          clientCount: _clientCount,
          fileCount: _fileCount,
          loading: _loading,
          onRefresh: _loadStats,
          onNavigate: widget.onSelectIndex,
        );
    }
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text('Are you sure you want to sign out?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Sign Out')),
        ],
      ),
    );
    if (ok == true && mounted) {
      await AuthService.instance.logout();
      // Force app restart via Navigator
      Navigator.of(context).popUntil((r) => r.isFirst);
      // Rebuild app root
      (context as Element).markNeedsBuild();
    }
  }
}

class _DashboardHome extends StatelessWidget {
  final int clientCount;
  final int fileCount;
  final bool loading;
  final VoidCallback? onRefresh;
  final ValueChanged<int>? onNavigate;

  const _DashboardHome({
    required this.clientCount,
    required this.fileCount,
    required this.loading,
    required this.onRefresh,
    required this.onNavigate,
  });

  @override
  Widget build(BuildContext context) {
    final user = AuthService.instance.currentUser;
    final tenant = AuthService.instance.currentTenant;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Good ${_timeGreeting()}, ${user?.username ?? 'there'}',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    tenant?.companyName ?? 'FinTech Dashboard',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.grey),
                  ),
                ],
              ),
              if (onRefresh != null)
                OutlinedButton.icon(
                  onPressed: onRefresh,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Refresh'),
                ),
            ],
          ),
          const SizedBox(height: 32),

          Row(
            children: [
              _StatCard(label: 'Total Clients', value: loading ? '—' : clientCount.toString(), icon: Icons.people, color: AppTheme.primary, onTap: () => onNavigate?.call(1)),
              const SizedBox(width: 16),
              _StatCard(label: 'Generated PDFs', value: loading ? '—' : fileCount.toString(), icon: Icons.description, color: AppTheme.accent, onTap: () => onNavigate?.call(2)),
              const SizedBox(width: 16),
              _StatCard(label: 'Statements Ready', value: loading ? '—' : fileCount.toString(), icon: Icons.task_alt, color: AppTheme.success),
              const SizedBox(width: 16),
              _StatCard(label: 'Integrations', value: 'Manage', icon: Icons.hub, color: const Color(0xFF7B1FA2), onTap: () => onNavigate?.call(7)),
            ],
          ),

          const SizedBox(height: 32),
          Text('Quick Actions', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 16),

          Wrap(
            spacing: 16,
            runSpacing: 16,
            children: [
              _QuickAction(icon: Icons.upload_file, label: 'Upload\nClients', subtitle: 'Excel import', color: AppTheme.primary, onTap: () => onNavigate?.call(2)),
              _QuickAction(icon: Icons.receipt_long, label: 'New\nInvoice', subtitle: 'GST invoice', color: const Color(0xFF388E3C), onTap: () => onNavigate?.call(3)),
              _QuickAction(icon: Icons.account_balance, label: 'Loan\nSchedule', subtitle: 'EMI amortisation', color: const Color(0xFF0288D1), onTap: () => onNavigate?.call(4)),
              _QuickAction(icon: Icons.pie_chart, label: 'Portfolio\nReport', subtitle: 'Investment report', color: const Color(0xFF7B1FA2), onTap: () => onNavigate?.call(5)),
              _QuickAction(icon: Icons.email, label: 'Send\nEmails', subtitle: 'Bulk delivery', color: AppTheme.warning, onTap: () => onNavigate?.call(6)),
              _QuickAction(icon: Icons.hub, label: 'Connect\nApps', subtitle: 'Zoho, Gmail...', color: const Color(0xFFD32F2F), onTap: () => onNavigate?.call(7)),
              _QuickAction(icon: Icons.smart_toy, label: 'AI\nAssistant', subtitle: 'Local AI (Ollama)', color: const Color(0xFF00897B), onTap: () => onNavigate?.call(11)),
            ],
          ),

          const SizedBox(height: 32),
          Text('Connected Services', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 16),
          const _IntegrationStatusRow(),
        ],
      ),
    );
  }

  String _timeGreeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'morning';
    if (h < 17) return 'afternoon';
    return 'evening';
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final VoidCallback? onTap;

  const _StatCard({required this.label, required this.value, required this.icon, required this.color, this.onTap});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(10)),
                  child: Icon(icon, color: color, size: 24),
                ),
                const SizedBox(width: 16),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(value, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: color)),
                    Text(label, style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final String subtitle;
  final Color color;
  final VoidCallback? onTap;

  const _QuickAction({required this.icon, required this.label, required this.subtitle, required this.color, this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 140,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Theme.of(context).cardTheme.color,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.2)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(8)),
              child: Icon(icon, color: color, size: 22),
            ),
            const SizedBox(height: 12),
            Text(label, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, height: 1.4)),
            const SizedBox(height: 4),
            Text(subtitle, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
          ],
        ),
      ),
    );
  }
}

class _IntegrationStatusRow extends StatelessWidget {
  const _IntegrationStatusRow();

  @override
  Widget build(BuildContext context) {
    final items = [
      {'name': 'Zoho', 'icon': Icons.business, 'color': const Color(0xFFE8541C)},
      {'name': 'Gmail', 'icon': Icons.mail, 'color': const Color(0xFFD93025)},
      {'name': 'Microsoft 365', 'icon': Icons.window, 'color': const Color(0xFF0078D4)},
      {'name': 'WhatsApp', 'icon': Icons.chat, 'color': const Color(0xFF25D366)},
      {'name': 'Razorpay', 'icon': Icons.payment, 'color': const Color(0xFF2D81FE)},
      {'name': 'Twilio SMS', 'icon': Icons.sms, 'color': const Color(0xFFF22F46)},
      {'name': 'Stripe', 'icon': Icons.credit_card, 'color': const Color(0xFF635BFF)},
      {'name': 'Telegram', 'icon': Icons.send, 'color': const Color(0xFF0088CC)},
    ];

    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: items.map((item) => _IntegrationChip(
        name: item['name'] as String,
        icon: item['icon'] as IconData,
        color: item['color'] as Color,
      )).toList(),
    );
  }
}

class _IntegrationChip extends StatelessWidget {
  final String name;
  final IconData icon;
  final Color color;

  const _IntegrationChip({required this.name, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 6),
          Text(name, style: TextStyle(fontSize: 13, color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

// Team screen
class TeamScreen extends StatefulWidget {
  const TeamScreen({super.key});

  @override
  State<TeamScreen> createState() => _TeamScreenState();
}

class _TeamScreenState extends State<TeamScreen> {
  List<Map<String, dynamic>> _team = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await ApiClient.instance.get('/team');
      if (mounted) {
        setState(() {
          _team = (data['team'] as List).cast<Map<String, dynamic>>();
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Team Members', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 24),
          if (_loading)
            const CircularProgressIndicator()
          else
            ..._team.map((m) => Card(
              child: ListTile(
                leading: CircleAvatar(child: Text((m['username'] ?? 'U').toString().substring(0, 1).toUpperCase())),
                title: Text(m['username']?.toString() ?? ''),
                subtitle: Text(m['email']?.toString() ?? ''),
                trailing: Chip(label: Text((m['role']?.toString() ?? '').toUpperCase())),
              ),
            )),
        ],
      ),
    );
  }
}
