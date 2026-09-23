import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import '../../services/document_service.dart';

class PortfolioScreen extends StatefulWidget {
  const PortfolioScreen({super.key});

  @override
  State<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends State<PortfolioScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _generating = false;

  final _investorName = TextEditingController();
  final _investorEmail = TextEditingController();
  final _reportDate = TextEditingController();
  final _asOfDate = TextEditingController();

  final List<Map<String, dynamic>> _holdings = [
    {'scheme': '', 'category': 'Equity', 'units': 0.0, 'nav': 0.0, 'invested': 0.0},
  ];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now().toIso8601String().split('T').first;
    _reportDate.text = now;
    _asOfDate.text = now;
  }

  Future<void> _generate() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _generating = true);
    try {
      final result = await DocumentService.instance.generatePortfolio({
        'investor_name': _investorName.text,
        'investor_email': _investorEmail.text,
        'report_date': _reportDate.text,
        'as_of_date': _asOfDate.text,
        'holdings': _holdings,
      });
      final pdf = result['pdf'] as String?;
      if (pdf != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Portfolio report generated: $pdf'),
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
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('Portfolio Report', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700)),
          ElevatedButton.icon(
            onPressed: _generating ? null : _generate,
            icon: _generating ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Icon(Icons.picture_as_pdf, size: 16),
            label: Text(_generating ? 'Generating...' : 'Generate Report'),
          ),
        ]),
        const SizedBox(height: 24),

        Form(
          key: _formKey,
          child: Column(children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('Investor Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                  const SizedBox(height: 16),
                  Row(children: [
                    Expanded(child: TextFormField(controller: _investorName, decoration: const InputDecoration(labelText: 'Investor Name'), validator: (v) => v?.isEmpty == true ? 'Required' : null)),
                    const SizedBox(width: 16),
                    Expanded(child: TextFormField(controller: _investorEmail, decoration: const InputDecoration(labelText: 'Email'), keyboardType: TextInputType.emailAddress)),
                    const SizedBox(width: 16),
                    Expanded(child: TextFormField(controller: _reportDate, decoration: const InputDecoration(labelText: 'Report Date'))),
                    const SizedBox(width: 16),
                    Expanded(child: TextFormField(controller: _asOfDate, decoration: const InputDecoration(labelText: 'As of Date'))),
                  ]),
                ]),
              ),
            ),
            const SizedBox(height: 16),

            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                    const Text('Holdings', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    TextButton.icon(
                      onPressed: () => setState(() => _holdings.add({'scheme': '', 'category': 'Equity', 'units': 0.0, 'nav': 0.0, 'invested': 0.0})),
                      icon: const Icon(Icons.add, size: 16),
                      label: const Text('Add Holding'),
                    ),
                  ]),
                  const SizedBox(height: 12),
                  ..._holdings.asMap().entries.map((entry) {
                    final idx = entry.key;
                    final h = entry.value;
                    final currentValue = (h['units'] as num).toDouble() * (h['nav'] as num).toDouble();
                    final invested = (h['invested'] as num).toDouble();
                    final returns = invested > 0 ? ((currentValue - invested) / invested * 100) : 0.0;
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(color: Theme.of(context).scaffoldBackgroundColor, borderRadius: BorderRadius.circular(8)),
                        child: Column(children: [
                          Row(children: [
                            Expanded(flex: 3, child: TextFormField(initialValue: h['scheme'], decoration: const InputDecoration(labelText: 'Scheme Name'), onChanged: (v) => _holdings[idx]['scheme'] = v, validator: (v) => v?.isEmpty == true ? 'Required' : null)),
                            const SizedBox(width: 8),
                            Expanded(child: DropdownButtonFormField<String>(
                              value: h['category'],
                              decoration: const InputDecoration(labelText: 'Category'),
                              items: ['Equity', 'Debt', 'Hybrid', 'Liquid', 'Gold', 'Other'].map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
                              onChanged: (v) => setState(() => _holdings[idx]['category'] = v!),
                            )),
                            const SizedBox(width: 8),
                            Expanded(child: TextFormField(initialValue: h['units'].toString(), decoration: const InputDecoration(labelText: 'Units'), keyboardType: TextInputType.number, onChanged: (v) => setState(() => _holdings[idx]['units'] = double.tryParse(v) ?? 0))),
                            const SizedBox(width: 8),
                            Expanded(child: TextFormField(initialValue: h['nav'].toString(), decoration: const InputDecoration(labelText: 'Current NAV'), keyboardType: TextInputType.number, onChanged: (v) => setState(() => _holdings[idx]['nav'] = double.tryParse(v) ?? 0))),
                            const SizedBox(width: 8),
                            Expanded(child: TextFormField(initialValue: h['invested'].toString(), decoration: const InputDecoration(labelText: 'Invested (₹)'), keyboardType: TextInputType.number, onChanged: (v) => setState(() => _holdings[idx]['invested'] = double.tryParse(v) ?? 0))),
                            const SizedBox(width: 8),
                            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                              Text('₹${currentValue.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
                              Text('${returns.toStringAsFixed(1)}%', style: TextStyle(fontSize: 11, color: returns >= 0 ? Colors.green : Colors.red, fontWeight: FontWeight.w600)),
                            ]),
                            if (_holdings.length > 1) IconButton(icon: const Icon(Icons.delete_outline, color: Colors.red, size: 18), onPressed: () => setState(() => _holdings.removeAt(idx))),
                          ]),
                        ]),
                      ),
                    );
                  }),

                  // Summary
                  Align(
                    alignment: Alignment.centerRight,
                    child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Text('Current Value: ₹${_holdings.fold<double>(0, (s, h) => s + (h['units'] as num).toDouble() * (h['nav'] as num).toDouble()).toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                      Text('Invested: ₹${_holdings.fold<double>(0, (s, h) => s + (h['invested'] as num).toDouble()).toStringAsFixed(2)}', style: const TextStyle(fontSize: 13, color: Colors.grey)),
                    ]),
                  ),
                ]),
              ),
            ),
          ]),
        ),
      ]),
    );
  }
}
