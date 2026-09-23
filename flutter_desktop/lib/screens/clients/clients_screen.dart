import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../models/client.dart';
import '../../services/document_service.dart';
import '../../services/integration_service.dart';

class ClientsScreen extends StatefulWidget {
  const ClientsScreen({super.key});

  @override
  State<ClientsScreen> createState() => _ClientsScreenState();
}

class _ClientsScreenState extends State<ClientsScreen> {
  List<ClientModel> _clients = [];
  List<ClientModel> _filtered = [];
  final _searchCtrl = TextEditingController();
  bool _loading = true;
  String? _error;
  final Set<String> _selected = {};

  @override
  void initState() {
    super.initState();
    _load();
    _searchCtrl.addListener(_filter);
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final clients = await DocumentService.instance.fetchClients();
      if (mounted) {
        setState(() {
          _clients = clients;
          _filtered = clients;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  void _filter() {
    final q = _searchCtrl.text.toLowerCase();
    setState(() {
      _filtered = q.isEmpty ? _clients : _clients.where((c) =>
        c.name.toLowerCase().contains(q) ||
        c.email.toLowerCase().contains(q) ||
        c.accountNo.toLowerCase().contains(q),
      ).toList();
    });
  }

  Future<void> _pushToZoho() async {
    if (_selected.isEmpty) return;
    final selected = _clients.where((c) => _selected.contains(c.accountNo)).toList();
    int ok = 0; int err = 0;
    for (final client in selected) {
      try {
        await IntegrationService.instance.pushClientToZoho(client.toJson());
        ok++;
      } catch (_) { err++; }
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Pushed $ok clients to Zoho CRM${err > 0 ? " ($err failed)" : ""}')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Clients', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
              Row(children: [
                if (_selected.isNotEmpty) ...[
                  OutlinedButton.icon(
                    onPressed: _pushToZoho,
                    icon: const Icon(Icons.business, size: 16),
                    label: Text('Push ${_selected.length} to Zoho'),
                  ),
                  const SizedBox(width: 12),
                ],
                OutlinedButton.icon(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Refresh'),
                ),
              ]),
            ],
          ),
          const SizedBox(height: 8),
          Text('${_clients.length} clients loaded', style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
          const SizedBox(height: 20),

          TextField(
            controller: _searchCtrl,
            decoration: InputDecoration(
              hintText: 'Search by name, email or account number...',
              prefixIcon: const Icon(Icons.search, size: 18),
              suffixIcon: _searchCtrl.text.isNotEmpty
                ? IconButton(icon: const Icon(Icons.clear, size: 16), onPressed: () { _searchCtrl.clear(); _filter(); })
                : null,
            ),
          ),
          const SizedBox(height: 20),

          if (_loading)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else if (_error != null)
            Expanded(child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.error_outline, color: Colors.red.shade400, size: 48),
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Colors.red.shade700)),
              const SizedBox(height: 16),
              ElevatedButton(onPressed: _load, child: const Text('Retry')),
            ])))
          else if (_filtered.isEmpty)
            const Expanded(child: Center(child: Text('No clients found', style: TextStyle(color: Colors.grey))))
          else
            Expanded(
              child: Card(
                child: SingleChildScrollView(
                  child: DataTable(
                    showCheckboxColumn: true,
                    columns: const [
                      DataColumn(label: Text('Account No', style: TextStyle(fontWeight: FontWeight.w600))),
                      DataColumn(label: Text('Name', style: TextStyle(fontWeight: FontWeight.w600))),
                      DataColumn(label: Text('Email', style: TextStyle(fontWeight: FontWeight.w600))),
                      DataColumn(label: Text('Phone', style: TextStyle(fontWeight: FontWeight.w600))),
                      DataColumn(label: Text('Closing Balance', style: TextStyle(fontWeight: FontWeight.w600))),
                    ],
                    rows: _filtered.map((c) => DataRow(
                      selected: _selected.contains(c.accountNo),
                      onSelectChanged: (v) => setState(() {
                        if (v == true) _selected.add(c.accountNo);
                        else _selected.remove(c.accountNo);
                      }),
                      cells: [
                        DataCell(Text(c.accountNo, style: const TextStyle(fontFamily: 'monospace', fontSize: 12))),
                        DataCell(Text(c.name)),
                        DataCell(Text(c.email)),
                        DataCell(Text(c.phone)),
                        DataCell(Text(c.closingBalance != null ? '₹${c.closingBalance!.toStringAsFixed(2)}' : '—')),
                      ],
                    )).toList(),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
