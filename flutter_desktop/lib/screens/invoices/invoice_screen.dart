import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import '../../services/document_service.dart';
import '../../services/integration_service.dart';

class InvoiceScreen extends StatefulWidget {
  const InvoiceScreen({super.key});

  @override
  State<InvoiceScreen> createState() => _InvoiceScreenState();
}

class _InvoiceScreenState extends State<InvoiceScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _generating = false;
  String? _generatedPdf;

  // Form fields
  final _clientName = TextEditingController();
  final _clientEmail = TextEditingController();
  final _clientPhone = TextEditingController();
  final _clientGstin = TextEditingController();
  final _clientAddress = TextEditingController();
  final _invoiceNo = TextEditingController(text: 'INV-001');
  final _invoiceDate = TextEditingController();
  String _supplyType = 'intrastate';

  final List<Map<String, dynamic>> _items = [
    {'description': '', 'hsn': '', 'quantity': 1, 'rate': 0.0, 'gst_rate': 18},
  ];

  @override
  void initState() {
    super.initState();
    _invoiceDate.text = DateTime.now().toIso8601String().split('T').first;
  }

  Future<void> _generate() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _generating = true);
    try {
      final data = {
        'invoice_no': _invoiceNo.text,
        'invoice_date': _invoiceDate.text,
        'supply_type': _supplyType,
        'client': {
          'name': _clientName.text,
          'email': _clientEmail.text,
          'phone': _clientPhone.text,
          'gstin': _clientGstin.text,
          'address': _clientAddress.text,
        },
        'items': _items,
      };
      final result = await DocumentService.instance.generateInvoice(data);
      final pdf = result['pdf'] as String?;
      if (pdf != null && mounted) {
        setState(() => _generatedPdf = pdf);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Invoice generated: $pdf'), action: SnackBarAction(
            label: 'Open', onPressed: () async {
              final path = await DocumentService.instance.downloadFile(pdf);
              OpenFilex.open(path);
            },
          )),
        );
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _createRazorpayLink() async {
    if (_generatedPdf == null || _clientEmail.text.isEmpty) return;
    final total = _items.fold<double>(0, (sum, item) {
      final qty = (item['quantity'] as num).toDouble();
      final rate = (item['rate'] as num).toDouble();
      final gst = (item['gst_rate'] as num).toDouble();
      return sum + qty * rate * (1 + gst / 100);
    });

    try {
      final url = await IntegrationService.instance.createRazorpayLink(
        {'name': _clientName.text, 'email': _clientEmail.text, 'phone': _clientPhone.text},
        total,
        'Invoice ${_invoiceNo.text}',
      );
      if (mounted && url.isNotEmpty) {
        await showDialog(context: context, builder: (ctx) => AlertDialog(
          title: const Text('Payment Link Created'),
          content: SelectableText(url),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
        ));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Razorpay error: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('GST Invoice Generator', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
              Row(children: [
                if (_generatedPdf != null)
                  OutlinedButton.icon(
                    onPressed: _createRazorpayLink,
                    icon: const Icon(Icons.payment, size: 16),
                    label: const Text('Razorpay Link'),
                  ),
                const SizedBox(width: 12),
                ElevatedButton.icon(
                  onPressed: _generating ? null : _generate,
                  icon: _generating
                    ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.picture_as_pdf, size: 16),
                  label: Text(_generating ? 'Generating...' : 'Generate Invoice'),
                ),
              ]),
            ],
          ),
          const SizedBox(height: 24),

          Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Invoice details
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Invoice Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                      const SizedBox(height: 16),
                      Row(children: [
                        Expanded(child: TextFormField(controller: _invoiceNo, decoration: const InputDecoration(labelText: 'Invoice Number'), validator: (v) => v?.isEmpty == true ? 'Required' : null)),
                        const SizedBox(width: 16),
                        Expanded(child: TextFormField(controller: _invoiceDate, decoration: const InputDecoration(labelText: 'Invoice Date'))),
                        const SizedBox(width: 16),
                        Expanded(child: DropdownButtonFormField<String>(
                          value: _supplyType,
                          decoration: const InputDecoration(labelText: 'Supply Type'),
                          items: const [
                            DropdownMenuItem(value: 'intrastate', child: Text('Intrastate (CGST + SGST)')),
                            DropdownMenuItem(value: 'interstate', child: Text('Interstate (IGST)')),
                          ],
                          onChanged: (v) => setState(() => _supplyType = v!),
                        )),
                      ]),
                    ]),
                  ),
                ),
                const SizedBox(height: 16),

                // Client details
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Client Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                      const SizedBox(height: 16),
                      Row(children: [
                        Expanded(child: TextFormField(controller: _clientName, decoration: const InputDecoration(labelText: 'Client Name'), validator: (v) => v?.isEmpty == true ? 'Required' : null)),
                        const SizedBox(width: 16),
                        Expanded(child: TextFormField(controller: _clientEmail, decoration: const InputDecoration(labelText: 'Email'), keyboardType: TextInputType.emailAddress)),
                        const SizedBox(width: 16),
                        Expanded(child: TextFormField(controller: _clientPhone, decoration: const InputDecoration(labelText: 'Phone'))),
                      ]),
                      const SizedBox(height: 12),
                      Row(children: [
                        Expanded(child: TextFormField(controller: _clientGstin, decoration: const InputDecoration(labelText: 'GSTIN'))),
                        const SizedBox(width: 16),
                        Expanded(flex: 3, child: TextFormField(controller: _clientAddress, decoration: const InputDecoration(labelText: 'Address'))),
                      ]),
                    ]),
                  ),
                ),
                const SizedBox(height: 16),

                // Line items
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                        const Text('Line Items', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                        TextButton.icon(
                          onPressed: () => setState(() => _items.add({'description': '', 'hsn': '', 'quantity': 1, 'rate': 0.0, 'gst_rate': 18})),
                          icon: const Icon(Icons.add, size: 16),
                          label: const Text('Add Item'),
                        ),
                      ]),
                      const SizedBox(height: 12),
                      ..._items.asMap().entries.map((entry) {
                        final idx = entry.key;
                        final item = entry.value;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Row(children: [
                            Expanded(flex: 3, child: TextFormField(
                              initialValue: item['description'],
                              decoration: const InputDecoration(labelText: 'Description'),
                              onChanged: (v) => _items[idx]['description'] = v,
                              validator: (v) => v?.isEmpty == true ? 'Required' : null,
                            )),
                            const SizedBox(width: 8),
                            Expanded(child: TextFormField(
                              initialValue: item['hsn'],
                              decoration: const InputDecoration(labelText: 'HSN'),
                              onChanged: (v) => _items[idx]['hsn'] = v,
                            )),
                            const SizedBox(width: 8),
                            Expanded(child: TextFormField(
                              initialValue: item['quantity'].toString(),
                              decoration: const InputDecoration(labelText: 'Qty'),
                              keyboardType: TextInputType.number,
                              onChanged: (v) => _items[idx]['quantity'] = int.tryParse(v) ?? 1,
                            )),
                            const SizedBox(width: 8),
                            Expanded(child: TextFormField(
                              initialValue: item['rate'].toString(),
                              decoration: const InputDecoration(labelText: 'Rate (₹)'),
                              keyboardType: TextInputType.number,
                              onChanged: (v) => _items[idx]['rate'] = double.tryParse(v) ?? 0,
                            )),
                            const SizedBox(width: 8),
                            Expanded(child: DropdownButtonFormField<int>(
                              value: item['gst_rate'] as int,
                              decoration: const InputDecoration(labelText: 'GST %'),
                              items: [0, 5, 12, 18, 28].map((r) => DropdownMenuItem(value: r, child: Text('$r%'))).toList(),
                              onChanged: (v) => setState(() => _items[idx]['gst_rate'] = v!),
                            )),
                            if (_items.length > 1) IconButton(
                              icon: const Icon(Icons.delete_outline, color: Colors.red, size: 18),
                              onPressed: () => setState(() => _items.removeAt(idx)),
                            ),
                          ]),
                        );
                      }),

                      // Total
                      Align(
                        alignment: Alignment.centerRight,
                        child: Text(
                          'Total: ₹${_calculateTotal().toStringAsFixed(2)}',
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18),
                        ),
                      ),
                    ]),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  double _calculateTotal() {
    return _items.fold(0, (sum, item) {
      final qty = (item['quantity'] as num).toDouble();
      final rate = (item['rate'] as num).toDouble();
      final gst = (item['gst_rate'] as num).toDouble();
      return sum + qty * rate * (1 + gst / 100);
    });
  }
}
