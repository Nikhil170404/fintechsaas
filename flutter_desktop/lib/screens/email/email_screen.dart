import 'package:flutter/material.dart';
import '../../core/constants.dart';
import '../../models/client.dart';
import '../../services/document_service.dart';

class EmailScreen extends StatefulWidget {
  const EmailScreen({super.key});

  @override
  State<EmailScreen> createState() => _EmailScreenState();
}

class _EmailScreenState extends State<EmailScreen> {
  final _subjectCtrl = TextEditingController(text: 'Your Account Statement');
  final _bodyCtrl = TextEditingController(text: 'Dear {{name}},\n\nPlease find your account statement attached.\n\nThank you.');
  String _provider = 'smtp';
  List<ClientModel> _clients = [];
  List<Map<String, dynamic>> _files = [];
  final Set<String> _selectedClients = {};
  final Set<String> _selectedFiles = {};
  bool _loading = true;
  bool _sending = false;
  String? _sendResult;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final clients = await DocumentService.instance.fetchClients();
      final files = await DocumentService.instance.fetchFiles();
      if (mounted) {
        setState(() {
          _clients = clients;
          _files = files.where((f) => f['name'].toString().endsWith('.pdf')).toList();
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _send() async {
    if (_selectedClients.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Select recipients first')));
      return;
    }
    setState(() { _sending = true; _sendResult = null; });

    final selected = _clients.where((c) => _selectedClients.contains(c.accountNo)).toList();

    try {
      int ok = 0;
      for (final client in selected) {
        final body = _bodyCtrl.text
          .replaceAll('{{name}}', client.name)
          .replaceAll('{{account_no}}', client.accountNo)
          .replaceAll('{{email}}', client.email);

        await DocumentService.instance.sendEmail(
          to: [client.email],
          subject: _subjectCtrl.text,
          body: body,
          attachments: _selectedFiles.toList(),
          provider: _provider,
        );
        ok++;
      }

      if (mounted) setState(() => _sendResult = 'Sent to $ok recipients');
    } catch (e) {
      if (mounted) setState(() => _sendResult = 'Error: $e');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _sendWhatsApp() async {
    if (_selectedClients.isEmpty) return;
    setState(() => _sending = true);
    try {
      final result = await DocumentService.instance.sendWhatsApp(
        accountNos: _selectedClients.toList(),
        message: _bodyCtrl.text,
        pdfFilename: _selectedFiles.firstOrNull,
      );
      final sent = (result['results'] as List? ?? []).where((r) => r['status'] == 'sent').length;
      if (mounted) setState(() => _sendResult = 'WhatsApp: sent to $sent clients');
    } catch (e) {
      if (mounted) setState(() => _sendResult = 'WhatsApp error: $e');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('Email & Document Delivery', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
            Row(children: [
              OutlinedButton.icon(
                onPressed: _sending ? null : _sendWhatsApp,
                icon: const Icon(Icons.chat, size: 16, color: Color(0xFF25D366)),
                label: const Text('Send WhatsApp'),
              ),
              const SizedBox(width: 12),
              ElevatedButton.icon(
                onPressed: _sending ? null : _send,
                icon: _sending
                  ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.send, size: 16),
                label: Text(_sending ? 'Sending...' : 'Send Email'),
              ),
            ]),
          ]),

          if (_sendResult != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _sendResult!.startsWith('Error') ? Colors.red.shade50 : Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(_sendResult!, style: TextStyle(color: _sendResult!.startsWith('Error') ? Colors.red.shade700 : Colors.green.shade700)),
            ),
          ],

          const SizedBox(height: 24),

          Expanded(
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Compose panel
              Expanded(
                flex: 3,
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Compose', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                      const SizedBox(height: 16),

                      // Provider picker
                      DropdownButtonFormField<String>(
                        value: _provider,
                        decoration: const InputDecoration(labelText: 'Send via', prefixIcon: Icon(Icons.email_outlined, size: 18)),
                        items: AppConstants.emailProviders.map((p) => DropdownMenuItem(
                          value: p['id'],
                          child: Text(p['name']!),
                        )).toList(),
                        onChanged: (v) => setState(() => _provider = v!),
                      ),
                      const SizedBox(height: 16),

                      TextField(
                        controller: _subjectCtrl,
                        decoration: const InputDecoration(labelText: 'Subject'),
                      ),
                      const SizedBox(height: 16),
                      Expanded(
                        child: TextField(
                          controller: _bodyCtrl,
                          maxLines: null,
                          expands: true,
                          textAlignVertical: TextAlignVertical.top,
                          decoration: const InputDecoration(
                            labelText: 'Email Body (use {{name}}, {{account_no}})',
                            alignLabelWithHint: true,
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text('Tip: {{name}} and {{account_no}} are replaced per client',
                        style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
                    ]),
                  ),
                ),
              ),

              const SizedBox(width: 16),

              // Recipients & attachments
              SizedBox(
                width: 320,
                child: Column(children: [
                  // Recipients
                  Expanded(
                    child: Card(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                          child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                            Text('Recipients (${_selectedClients.length}/${_clients.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                            TextButton(
                              onPressed: () => setState(() {
                                if (_selectedClients.length == _clients.length) _selectedClients.clear();
                                else { _selectedClients.clear(); for (final c in _clients) _selectedClients.add(c.accountNo); }
                              }),
                              child: Text(_selectedClients.length == _clients.length ? 'Deselect All' : 'Select All'),
                            ),
                          ]),
                        ),
                        const Divider(height: 1),
                        if (_loading)
                          const Expanded(child: Center(child: CircularProgressIndicator()))
                        else
                          Expanded(
                            child: ListView.builder(
                              itemCount: _clients.length,
                              itemBuilder: (ctx, i) {
                                final c = _clients[i];
                                return CheckboxListTile(
                                  dense: true,
                                  value: _selectedClients.contains(c.accountNo),
                                  onChanged: (v) => setState(() {
                                    if (v == true) _selectedClients.add(c.accountNo);
                                    else _selectedClients.remove(c.accountNo);
                                  }),
                                  title: Text(c.name, style: const TextStyle(fontSize: 13)),
                                  subtitle: Text(c.email, style: const TextStyle(fontSize: 11)),
                                );
                              },
                            ),
                          ),
                      ]),
                    ),
                  ),

                  const SizedBox(height: 12),

                  // Attachments
                  SizedBox(
                    height: 200,
                    child: Card(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                          child: Text('Attachments (${_selectedFiles.length})', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                        ),
                        const Divider(height: 1),
                        Expanded(
                          child: _files.isEmpty
                            ? const Center(child: Text('No PDFs — generate statements first', style: TextStyle(color: Colors.grey, fontSize: 12)))
                            : ListView.builder(
                                itemCount: _files.length,
                                itemBuilder: (ctx, i) {
                                  final f = _files[i];
                                  final name = f['name'].toString();
                                  return CheckboxListTile(
                                    dense: true,
                                    value: _selectedFiles.contains(name),
                                    onChanged: (v) => setState(() {
                                      if (v == true) _selectedFiles.add(name);
                                      else _selectedFiles.remove(name);
                                    }),
                                    title: Text(name, style: const TextStyle(fontSize: 12)),
                                    secondary: const Icon(Icons.picture_as_pdf, color: Colors.red, size: 18),
                                  );
                                },
                              ),
                        ),
                      ]),
                    ),
                  ),
                ]),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}
