import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../services/integration_service.dart';

class AuditScreen extends StatefulWidget {
  const AuditScreen({super.key});

  @override
  State<AuditScreen> createState() => _AuditScreenState();
}

class _AuditScreenState extends State<AuditScreen> {
  List<Map<String, dynamic>> _log = [];
  bool _loading = true;
  String _filter = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final log = await IntegrationService.instance.fetchAuditLog(limit: 200);
      if (mounted) setState(() { _log = log; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<Map<String, dynamic>> get _filtered {
    if (_filter.isEmpty) return _log;
    final q = _filter.toLowerCase();
    return _log.where((e) =>
      e['action']?.toString().toLowerCase().contains(q) == true ||
      e['who']?.toString().toLowerCase().contains(q) == true ||
      e['detail']?.toString().toLowerCase().contains(q) == true,
    ).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('Audit Log', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
            OutlinedButton.icon(onPressed: _load, icon: const Icon(Icons.refresh, size: 16), label: const Text('Refresh')),
          ]),
          const SizedBox(height: 20),

          TextField(
            decoration: const InputDecoration(hintText: 'Filter by action, user or detail...', prefixIcon: Icon(Icons.search, size: 18)),
            onChanged: (v) => setState(() => _filter = v),
          ),
          const SizedBox(height: 16),

          if (_loading)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else
            Expanded(
              child: Card(
                child: _filtered.isEmpty
                  ? const Center(child: Text('No log entries', style: TextStyle(color: Colors.grey)))
                  : ListView.separated(
                      itemCount: _filtered.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (ctx, i) {
                        final e = _filtered[i];
                        final ts = e['ts'] as int? ?? 0;
                        final dt = DateTime.fromMillisecondsSinceEpoch(ts * 1000);
                        final action = e['action']?.toString() ?? '';
                        return ListTile(
                          dense: true,
                          leading: _ActionIcon(action: action),
                          title: Text(action, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                          subtitle: Text(e['detail']?.toString() ?? '', style: const TextStyle(fontSize: 12)),
                          trailing: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(DateFormat('dd MMM yyyy').format(dt), style: const TextStyle(fontSize: 11)),
                              Text(DateFormat('HH:mm:ss').format(dt), style: TextStyle(fontSize: 10, color: Colors.grey.shade500)),
                              Text(e['who']?.toString() ?? '', style: TextStyle(fontSize: 10, color: Colors.grey.shade500)),
                            ],
                          ),
                        );
                      },
                    ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ActionIcon extends StatelessWidget {
  final String action;
  const _ActionIcon({required this.action});

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch (action.toUpperCase()) {
      String a when a.contains('LOGIN') => (Icons.login, Colors.blue),
      String a when a.contains('LOGOUT') => (Icons.logout, Colors.orange),
      String a when a.contains('SIGNUP') => (Icons.person_add, Colors.green),
      String a when a.contains('SEND') || a.contains('EMAIL') => (Icons.email, Colors.teal),
      String a when a.contains('GENERATE') || a.contains('PDF') => (Icons.picture_as_pdf, Colors.red),
      String a when a.contains('SETTINGS') || a.contains('CHANGE') => (Icons.settings, Colors.purple),
      String a when a.contains('UPLOAD') => (Icons.upload, Colors.indigo),
      String a when a.contains('FAIL') || a.contains('ERROR') => (Icons.error_outline, Colors.red),
      _ => (Icons.history, Colors.grey),
    };
    return CircleAvatar(
      radius: 16,
      backgroundColor: color.withOpacity(0.1),
      child: Icon(icon, color: color, size: 15),
    );
  }
}
