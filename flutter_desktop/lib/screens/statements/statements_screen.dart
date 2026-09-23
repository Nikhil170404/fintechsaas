import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:open_filex/open_filex.dart';
import '../../core/theme.dart';
import '../../models/client.dart';
import '../../services/document_service.dart';

class StatementsScreen extends StatefulWidget {
  const StatementsScreen({super.key});

  @override
  State<StatementsScreen> createState() => _StatementsScreenState();
}

class _StatementsScreenState extends State<StatementsScreen> {
  List<ClientModel> _clients = [];
  List<Map<String, dynamic>> _files = [];
  final Set<String> _selected = {};
  bool _loadingClients = true;
  bool _loadingFiles = false;
  bool _generating = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    setState(() { _loadingClients = true; _error = null; });
    try {
      final clients = await DocumentService.instance.fetchClients();
      final files = await DocumentService.instance.fetchFiles();
      if (mounted) {
        setState(() {
          _clients = clients;
          _files = files.where((f) => f['name'].toString().endsWith('.pdf')).toList();
          _loadingClients = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loadingClients = false; });
    }
  }

  Future<void> _generateSelected() async {
    if (_selected.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Select clients first')));
      return;
    }
    setState(() => _generating = true);
    try {
      final result = await DocumentService.instance.generateStatements(_selected.toList());
      final results = (result['results'] as List? ?? []).cast<Map<String, dynamic>>();
      final ok = results.where((r) => r['status'] == 'ok').length;
      final failed = results.length - ok;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Generated $ok statements${failed > 0 ? " ($failed failed)" : ""}')),
        );
        _loadAll();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _generateAll() async {
    setState(() {
      _selected.clear();
      for (final c in _clients) _selected.add(c.accountNo);
    });
    await _generateSelected();
  }

  Future<void> _downloadFile(String filename) async {
    try {
      final path = await DocumentService.instance.downloadFile(filename);
      OpenFilex.open(path);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Download error: $e')));
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
              Text('Account Statements', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
              Row(children: [
                OutlinedButton.icon(
                  onPressed: _loadingClients ? null : _loadAll,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Refresh'),
                ),
                const SizedBox(width: 12),
                if (_selected.isNotEmpty)
                  ElevatedButton.icon(
                    onPressed: _generating ? null : _generateSelected,
                    icon: _generating ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.picture_as_pdf, size: 16),
                    label: Text(_generating ? 'Generating...' : 'Generate ${_selected.length} Selected'),
                  )
                else
                  ElevatedButton.icon(
                    onPressed: _generating || _loadingClients ? null : _generateAll,
                    icon: const Icon(Icons.picture_as_pdf, size: 16),
                    label: const Text('Generate All'),
                  ),
              ]),
            ],
          ),
          const SizedBox(height: 24),

          if (_error != null)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: Colors.red.shade50, borderRadius: BorderRadius.circular(8)),
              child: Text(_error!, style: TextStyle(color: Colors.red.shade700)),
            ),

          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Client list
                Expanded(
                  flex: 3,
                  child: Card(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.all(16),
                          child: Row(
                            children: [
                              const Text('Clients', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                              const Spacer(),
                              if (_selected.isNotEmpty)
                                TextButton(
                                  onPressed: () => setState(() => _selected.clear()),
                                  child: Text('Clear (${_selected.length})'),
                                ),
                              TextButton(
                                onPressed: () => setState(() {
                                  if (_selected.length == _clients.length) _selected.clear();
                                  else { _selected.clear(); for (final c in _clients) _selected.add(c.accountNo); }
                                }),
                                child: Text(_selected.length == _clients.length ? 'Deselect All' : 'Select All'),
                              ),
                            ],
                          ),
                        ),
                        const Divider(height: 1),
                        if (_loadingClients)
                          const Expanded(child: Center(child: CircularProgressIndicator()))
                        else
                          Expanded(
                            child: ListView.builder(
                              itemCount: _clients.length,
                              itemBuilder: (ctx, i) {
                                final c = _clients[i];
                                final sel = _selected.contains(c.accountNo);
                                return CheckboxListTile(
                                  value: sel,
                                  onChanged: (v) => setState(() {
                                    if (v == true) _selected.add(c.accountNo);
                                    else _selected.remove(c.accountNo);
                                  }),
                                  title: Text(c.name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                                  subtitle: Text(c.accountNo, style: const TextStyle(fontSize: 11)),
                                  secondary: CircleAvatar(radius: 16, backgroundColor: AppTheme.primary.withOpacity(0.1),
                                    child: Text(c.name.isNotEmpty ? c.name.substring(0, 1).toUpperCase() : '?', style: const TextStyle(color: AppTheme.primary, fontSize: 12, fontWeight: FontWeight.bold))),
                                );
                              },
                            ),
                          ),
                      ],
                    ),
                  ),
                ),

                const SizedBox(width: 16),

                // Generated files
                Expanded(
                  flex: 2,
                  child: Card(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.all(16),
                          child: Row(
                            children: [
                              const Text('Generated PDFs', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                              const Spacer(),
                              if (_loadingFiles) const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                            ],
                          ),
                        ),
                        const Divider(height: 1),
                        Expanded(
                          child: _files.isEmpty
                            ? const Center(child: Text('No PDFs yet', style: TextStyle(color: Colors.grey)))
                            : ListView.builder(
                                itemCount: _files.length,
                                itemBuilder: (ctx, i) {
                                  final f = _files[i];
                                  return ListTile(
                                    leading: const Icon(Icons.picture_as_pdf, color: Colors.red),
                                    title: Text(f['name'].toString(), style: const TextStyle(fontSize: 12)),
                                    subtitle: Text(_formatSize(f['size'] as int? ?? 0), style: const TextStyle(fontSize: 11)),
                                    trailing: IconButton(
                                      icon: const Icon(Icons.download_outlined, size: 18),
                                      onPressed: () => _downloadFile(f['name'].toString()),
                                    ),
                                  );
                                },
                              ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
