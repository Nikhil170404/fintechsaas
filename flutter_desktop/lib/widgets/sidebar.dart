import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../services/auth_service.dart';

class SidebarItem {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  final int index;
  final bool requiresOwner;

  const SidebarItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
    required this.index,
    this.requiresOwner = false,
  });
}

const _items = [
  SidebarItem(icon: Icons.dashboard_outlined, activeIcon: Icons.dashboard, label: 'Dashboard', index: 0),
  SidebarItem(icon: Icons.people_outline, activeIcon: Icons.people, label: 'Clients', index: 1),
  SidebarItem(icon: Icons.description_outlined, activeIcon: Icons.description, label: 'Statements', index: 2),
  SidebarItem(icon: Icons.receipt_long_outlined, activeIcon: Icons.receipt_long, label: 'GST Invoices', index: 3),
  SidebarItem(icon: Icons.account_balance_outlined, activeIcon: Icons.account_balance, label: 'Loan Schedules', index: 4),
  SidebarItem(icon: Icons.pie_chart_outline, activeIcon: Icons.pie_chart, label: 'Portfolio', index: 5),
  SidebarItem(icon: Icons.email_outlined, activeIcon: Icons.email, label: 'Email & Send', index: 6),
  SidebarItem(icon: Icons.hub_outlined, activeIcon: Icons.hub, label: 'Integrations', index: 7),
  SidebarItem(icon: Icons.settings_outlined, activeIcon: Icons.settings, label: 'Settings', index: 8, requiresOwner: true),
  SidebarItem(icon: Icons.manage_accounts_outlined, activeIcon: Icons.manage_accounts, label: 'Team', index: 9, requiresOwner: true),
  SidebarItem(icon: Icons.history_outlined, activeIcon: Icons.history, label: 'Audit Log', index: 10, requiresOwner: true),
  SidebarItem(icon: Icons.smart_toy_outlined, activeIcon: Icons.smart_toy, label: 'AI Assistant', index: 11),
];

class AppSidebar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final VoidCallback onToggleTheme;
  final ThemeMode themeMode;
  final VoidCallback onLogout;

  const AppSidebar({
    super.key,
    required this.selectedIndex,
    required this.onSelect,
    required this.onToggleTheme,
    required this.themeMode,
    required this.onLogout,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final sidebarBg = isDark ? AppTheme.sidebarDark : const Color(0xFF1565C0);
    final user = AuthService.instance.currentUser;
    final tenant = AuthService.instance.currentTenant;

    return Container(
      width: 220,
      decoration: BoxDecoration(
        color: sidebarBg,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.15),
            blurRadius: 8,
            offset: const Offset(2, 0),
          ),
        ],
      ),
      child: Column(
        children: [
          // Logo & company name
          Container(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.account_balance, color: Colors.white, size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    tenant?.companyName.isNotEmpty == true ? tenant!.companyName : 'FinTech Desk',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),

          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 8),

          // Nav items
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              itemCount: _items.length,
              itemBuilder: (ctx, i) {
                final item = _items[i];
                if (item.requiresOwner && user?.isOwner != true) {
                  return const SizedBox.shrink();
                }
                final selected = selectedIndex == item.index;
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 1),
                  child: Material(
                    color: selected
                        ? Colors.white.withOpacity(0.15)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(8),
                      onTap: () => onSelect(item.index),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        child: Row(
                          children: [
                            Icon(
                              selected ? item.activeIcon : item.icon,
                              color: selected ? Colors.white : Colors.white60,
                              size: 18,
                            ),
                            const SizedBox(width: 12),
                            Text(
                              item.label,
                              style: TextStyle(
                                color: selected ? Colors.white : Colors.white70,
                                fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                                fontSize: 13.5,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),

          const Divider(color: Colors.white12, height: 1),

          // Bottom actions
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                _BottomAction(
                  icon: themeMode == ThemeMode.dark ? Icons.light_mode_outlined : Icons.dark_mode_outlined,
                  label: themeMode == ThemeMode.dark ? 'Light Mode' : 'Dark Mode',
                  onTap: onToggleTheme,
                ),
                const SizedBox(height: 4),
                _BottomAction(
                  icon: Icons.logout_outlined,
                  label: 'Sign Out',
                  onTap: onLogout,
                  danger: true,
                ),
              ],
            ),
          ),

          // User info
          Container(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: Colors.white.withOpacity(0.2),
                  child: Text(
                    (user?.username ?? 'U').substring(0, 1).toUpperCase(),
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        user?.username ?? '',
                        style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        user?.role.toUpperCase() ?? '',
                        style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 10),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BottomAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool danger;

  const _BottomAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.danger = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = danger ? Colors.redAccent.shade100 : Colors.white70;
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(6),
      child: InkWell(
        borderRadius: BorderRadius.circular(6),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            children: [
              Icon(icon, color: color, size: 16),
              const SizedBox(width: 10),
              Text(label, style: TextStyle(color: color, fontSize: 13)),
            ],
          ),
        ),
      ),
    );
  }
}
