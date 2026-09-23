import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import '../../services/document_service.dart';

class LoansScreen extends StatefulWidget {
  const LoansScreen({super.key});

  @override
  State<LoansScreen> createState() => _LoansScreenState();
}

class _LoansScreenState extends State<LoansScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _generating = false;

  final _borrowerName = TextEditingController();
  final _borrowerEmail = TextEditingController();
  final _principalCtrl = TextEditingController();
  final _rateCtrl = TextEditingController();
  final _tenureCtrl = TextEditingController();
  final _startDateCtrl = TextEditingController();
  String _tenureType = 'months';

  @override
  void initState() {
    super.initState();
    _startDateCtrl.text = DateTime.now().toIso8601String().split('T').first;
  }

  double get _emi {
    final p = double.tryParse(_principalCtrl.text) ?? 0;
    final r = (double.tryParse(_rateCtrl.text) ?? 0) / 1200;
    final n = int.tryParse(_tenureCtrl.text) ?? 0;
    final months = _tenureType == 'years' ? n * 12 : n;
    if (r == 0 || months == 0) return p / (months == 0 ? 1 : months);
    return p * r * (1 + r).pow(months) / ((1 + r).pow(months) - 1);
  }

  Future<void> _generate() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _generating = true);
    try {
      final n = int.tryParse(_tenureCtrl.text) ?? 0;
      final result = await DocumentService.instance.generateLoan({
        'borrower_name': _borrowerName.text,
        'borrower_email': _borrowerEmail.text,
        'principal': double.tryParse(_principalCtrl.text) ?? 0,
        'annual_rate': double.tryParse(_rateCtrl.text) ?? 0,
        'tenure_months': _tenureType == 'years' ? n * 12 : n,
        'start_date': _startDateCtrl.text,
      });
      final pdf = result['pdf'] as String?;
      if (pdf != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Loan schedule generated: $pdf'),
          action: SnackBarAction(label: 'Open', onPressed: () async {
            final path = await DocumentService.instance.downloadFile(pdf);
            OpenFilex.open(path);
          }),
        ));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final emi = _emi;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('Loan / EMI Schedule', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
          ElevatedButton.icon(
            onPressed: _generating ? null : _generate,
            icon: _generating ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.picture_as_pdf, size: 16),
            label: Text(_generating ? 'Generating...' : 'Generate Schedule'),
          ),
        ]),
        const SizedBox(height: 24),

        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            flex: 3,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Form(
                  key: _formKey,
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Loan Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    const SizedBox(height: 16),
                    Row(children: [
                      Expanded(child: TextFormField(controller: _borrowerName, decoration: const InputDecoration(labelText: 'Borrower Name'), validator: (v) => v?.isEmpty == true ? 'Required' : null)),
                      const SizedBox(width: 16),
                      Expanded(child: TextFormField(controller: _borrowerEmail, decoration: const InputDecoration(labelText: 'Email'), keyboardType: TextInputType.emailAddress)),
                    ]),
                    const SizedBox(height: 16),
                    Row(children: [
                      Expanded(child: TextFormField(controller: _principalCtrl, decoration: const InputDecoration(labelText: 'Principal Amount (₹)', prefixText: '₹ '), keyboardType: TextInputType.number, onChanged: (_) => setState(() {}), validator: (v) => (double.tryParse(v ?? '') ?? 0) > 0 ? null : 'Enter valid amount')),
                      const SizedBox(width: 16),
                      Expanded(child: TextFormField(controller: _rateCtrl, decoration: const InputDecoration(labelText: 'Annual Interest Rate (%)', suffixText: '%'), keyboardType: TextInputType.number, onChanged: (_) => setState(() {}), validator: (v) => (double.tryParse(v ?? '') ?? 0) > 0 ? null : 'Enter valid rate')),
                    ]),
                    const SizedBox(height: 16),
                    Row(children: [
                      Expanded(child: TextFormField(controller: _tenureCtrl, decoration: const InputDecoration(labelText: 'Tenure'), keyboardType: TextInputType.number, onChanged: (_) => setState(() {}), validator: (v) => (int.tryParse(v ?? '') ?? 0) > 0 ? null : 'Enter valid tenure')),
                      const SizedBox(width: 16),
                      Expanded(child: DropdownButtonFormField<String>(
                        value: _tenureType,
                        decoration: const InputDecoration(labelText: 'Unit'),
                        items: const [
                          DropdownMenuItem(value: 'months', child: Text('Months')),
                          DropdownMenuItem(value: 'years', child: Text('Years')),
                        ],
                        onChanged: (v) => setState(() { _tenureType = v!; }),
                      )),
                      const SizedBox(width: 16),
                      Expanded(child: TextFormField(controller: _startDateCtrl, decoration: const InputDecoration(labelText: 'Start Date'))),
                    ]),
                  ]),
                ),
              ),
            ),
          ),

          const SizedBox(width: 16),

          // EMI preview
          SizedBox(
            width: 260,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('EMI Preview', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                  const SizedBox(height: 20),
                  _PreviewRow(label: 'Monthly EMI', value: emi > 0 ? '₹${emi.toStringAsFixed(2)}' : '—', highlight: true),
                  const Divider(height: 24),
                  _PreviewRow(label: 'Principal', value: _principalCtrl.text.isNotEmpty ? '₹${_principalCtrl.text}' : '—'),
                  const SizedBox(height: 8),
                  _PreviewRow(label: 'Rate (p.a.)', value: _rateCtrl.text.isNotEmpty ? '${_rateCtrl.text}%' : '—'),
                  const SizedBox(height: 8),
                  _PreviewRow(
                    label: 'Tenure',
                    value: _tenureCtrl.text.isNotEmpty
                      ? '${_tenureCtrl.text} ${_tenureType} (${_tenureType == 'years' ? (int.tryParse(_tenureCtrl.text) ?? 0) * 12 : _tenureCtrl.text} EMIs)'
                      : '—',
                  ),
                  const SizedBox(height: 8),
                  _PreviewRow(
                    label: 'Total Interest',
                    value: emi > 0 && (_tenureCtrl.text.isNotEmpty) ? () {
                      final n = int.tryParse(_tenureCtrl.text) ?? 0;
                      final months = _tenureType == 'years' ? n * 12 : n;
                      final principal = double.tryParse(_principalCtrl.text) ?? 0;
                      return '₹${(emi * months - principal).toStringAsFixed(2)}';
                    }() : '—',
                  ),
                  const SizedBox(height: 8),
                  _PreviewRow(
                    label: 'Total Payable',
                    value: emi > 0 && (_tenureCtrl.text.isNotEmpty) ? () {
                      final n = int.tryParse(_tenureCtrl.text) ?? 0;
                      final months = _tenureType == 'years' ? n * 12 : n;
                      return '₹${(emi * months).toStringAsFixed(2)}';
                    }() : '—',
                  ),
                ]),
              ),
            ),
          ),
        ]),
      ]),
    );
  }
}

class _PreviewRow extends StatelessWidget {
  final String label;
  final String value;
  final bool highlight;
  const _PreviewRow({required this.label, required this.value, this.highlight = false});

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
      Text(label, style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
      Text(value, style: TextStyle(fontSize: highlight ? 20 : 13, fontWeight: highlight ? FontWeight.w800 : FontWeight.w600, color: highlight ? const Color(0xFF1565C0) : null)),
    ]);
  }
}

extension NumPow on double {
  double pow(int n) {
    double result = 1;
    for (int i = 0; i < n; i++) result *= this;
    return result;
  }
}
