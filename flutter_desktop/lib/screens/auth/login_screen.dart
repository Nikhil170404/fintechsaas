import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/api_client.dart';
import '../../core/constants.dart';
import '../../core/theme.dart';
import '../../services/auth_service.dart';

class LoginScreen extends StatefulWidget {
  final VoidCallback onLogin;
  const LoginScreen({super.key, required this.onLogin});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  final _urlCtrl = TextEditingController();
  bool _obscurePass = true;
  bool _loading = false;
  bool _showServerConfig = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSavedUrl();
  }

  Future<void> _loadSavedUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final url = prefs.getString(AppConstants.prefApiBase) ?? AppConstants.defaultApiBase;
    _urlCtrl.text = url;
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _loading = true; _error = null; });

    // Apply server URL
    final url = _urlCtrl.text.trim();
    ApiClient.instance.setBaseUrl(url);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.prefApiBase, url);

    try {
      final ok = await AuthService.instance.login(
        _emailCtrl.text.trim(),
        _passCtrl.text,
      );
      if (ok && mounted) {
        widget.onLogin();
      } else if (mounted) {
        setState(() => _error = 'Invalid credentials');
      }
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      body: Row(
        children: [
          // Left panel
          Expanded(
            flex: 5,
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [AppTheme.primaryDark, AppTheme.primary, AppTheme.accent.withOpacity(0.8)],
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(48),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 40),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Icon(Icons.account_balance, color: Colors.white, size: 40),
                    ),
                    const SizedBox(height: 32),
                    const Text(
                      'FinTech Desk',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 36,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Professional financial document management\nfor Indian financial services',
                      style: TextStyle(color: Colors.white.withOpacity(0.8), fontSize: 16, height: 1.5),
                    ),
                    const SizedBox(height: 48),
                    ...[
                      _Feature(icon: Icons.description, text: 'Account Statements & Reports'),
                      _Feature(icon: Icons.receipt_long, text: 'GST Invoices with CGST/IGST'),
                      _Feature(icon: Icons.account_balance, text: 'EMI & Loan Schedules'),
                      _Feature(icon: Icons.pie_chart, text: 'Portfolio Reports'),
                      _Feature(icon: Icons.hub, text: 'Zoho, Gmail, WhatsApp & More'),
                      _Feature(icon: Icons.payment, text: 'Razorpay / Stripe Payment Links'),
                    ],
                  ],
                ),
              ),
            ),
          ),

          // Right panel (login form)
          Expanded(
            flex: 4,
            child: Container(
              color: isDark ? AppTheme.surfaceDark : Colors.white,
              child: Center(
                child: Container(
                  constraints: const BoxConstraints(maxWidth: 400),
                  padding: const EdgeInsets.all(40),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Welcome back',
                        style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Sign in to your account',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.grey,
                        ),
                      ),
                      const SizedBox(height: 32),

                      if (_error != null)
                        Container(
                          margin: const EdgeInsets.only(bottom: 16),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: Colors.red.shade50,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: Colors.red.shade200),
                          ),
                          child: Row(
                            children: [
                              Icon(Icons.error_outline, color: Colors.red.shade700, size: 16),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(_error!, style: TextStyle(color: Colors.red.shade700, fontSize: 13)),
                              ),
                            ],
                          ),
                        ),

                      Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            TextFormField(
                              controller: _emailCtrl,
                              keyboardType: TextInputType.emailAddress,
                              decoration: const InputDecoration(
                                labelText: 'Email address',
                                prefixIcon: Icon(Icons.email_outlined, size: 18),
                              ),
                              validator: (v) => (v?.contains('@') == true) ? null : 'Enter a valid email',
                              textInputAction: TextInputAction.next,
                            ),
                            const SizedBox(height: 16),
                            TextFormField(
                              controller: _passCtrl,
                              obscureText: _obscurePass,
                              decoration: InputDecoration(
                                labelText: 'Password',
                                prefixIcon: const Icon(Icons.lock_outline, size: 18),
                                suffixIcon: IconButton(
                                  icon: Icon(
                                    _obscurePass ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                                    size: 18,
                                  ),
                                  onPressed: () => setState(() => _obscurePass = !_obscurePass),
                                ),
                              ),
                              validator: (v) => (v?.length ?? 0) >= 4 ? null : 'Password required',
                              onFieldSubmitted: (_) => _submit(),
                            ),
                            const SizedBox(height: 24),
                            SizedBox(
                              height: 48,
                              child: ElevatedButton(
                                onPressed: _loading ? null : _submit,
                                child: _loading
                                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                                    : const Text('Sign In'),
                              ),
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: 24),

                      // Server config toggle
                      GestureDetector(
                        onTap: () => setState(() => _showServerConfig = !_showServerConfig),
                        child: Row(
                          children: [
                            Icon(Icons.settings_outlined, size: 14, color: Colors.grey.shade500),
                            const SizedBox(width: 6),
                            Text(
                              'Server configuration',
                              style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                            ),
                            Icon(
                              _showServerConfig ? Icons.expand_less : Icons.expand_more,
                              size: 14,
                              color: Colors.grey.shade500,
                            ),
                          ],
                        ),
                      ),

                      if (_showServerConfig) ...[
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _urlCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Backend URL',
                            hintText: 'http://localhost:8000/api/v1',
                            prefixIcon: Icon(Icons.dns_outlined, size: 18),
                          ),
                          style: const TextStyle(fontSize: 13),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Feature extends StatelessWidget {
  final IconData icon;
  final String text;
  const _Feature({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, color: Colors.white.withOpacity(0.9), size: 16),
          const SizedBox(width: 12),
          Text(text, style: TextStyle(color: Colors.white.withOpacity(0.9), fontSize: 14)),
        ],
      ),
    );
  }
}
