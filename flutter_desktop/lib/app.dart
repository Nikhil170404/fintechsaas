import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'core/constants.dart';
import 'core/theme.dart';
import 'services/auth_service.dart';
import 'screens/auth/login_screen.dart';
import 'screens/dashboard/dashboard_screen.dart';

class FinTechDeskApp extends StatefulWidget {
  const FinTechDeskApp({super.key});

  @override
  State<FinTechDeskApp> createState() => _FinTechDeskAppState();
}

class _FinTechDeskAppState extends State<FinTechDeskApp> {
  ThemeMode _themeMode = ThemeMode.light;

  @override
  void initState() {
    super.initState();
    _loadTheme();
  }

  Future<void> _loadTheme() async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString(AppConstants.prefThemeMode) ?? 'light';
    setState(() {
      _themeMode = mode == 'dark' ? ThemeMode.dark : ThemeMode.light;
    });
  }

  void toggleTheme() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _themeMode = _themeMode == ThemeMode.light ? ThemeMode.dark : ThemeMode.light;
    });
    await prefs.setString(
      AppConstants.prefThemeMode,
      _themeMode == ThemeMode.dark ? 'dark' : 'light',
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: _themeMode,
      home: AuthService.instance.isLoggedIn
          ? MainShell(onToggleTheme: toggleTheme, themeMode: _themeMode)
          : LoginScreen(onLogin: () => setState(() {})),
    );
  }
}

class MainShell extends StatefulWidget {
  final VoidCallback onToggleTheme;
  final ThemeMode themeMode;
  const MainShell({super.key, required this.onToggleTheme, required this.themeMode});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    return DashboardScreen(
      selectedIndex: _selectedIndex,
      onSelectIndex: (i) => setState(() => _selectedIndex = i),
      onToggleTheme: widget.onToggleTheme,
      themeMode: widget.themeMode,
    );
  }
}
