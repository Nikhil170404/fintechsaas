import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/api_client.dart';
import '../core/constants.dart';
import '../models/user.dart';

class AuthService {
  static final AuthService instance = AuthService._();
  AuthService._();

  UserModel? _user;
  TenantModel? _tenant;

  UserModel? get currentUser => _user;
  TenantModel? get currentTenant => _tenant;
  bool get isLoggedIn => _user != null;

  Future<void> loadFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final userJson = prefs.getString(AppConstants.prefUserJson);
    final tenantJson = prefs.getString(AppConstants.prefTenantJson);
    if (userJson != null) {
      _user = UserModel.fromJson(jsonDecode(userJson) as Map<String, dynamic>);
    }
    if (tenantJson != null) {
      _tenant = TenantModel.fromJson(jsonDecode(tenantJson) as Map<String, dynamic>);
    }
    // Check token still valid
    final token = await ApiClient.instance.getToken();
    if (token == null) {
      _user = null;
      _tenant = null;
    }
  }

  Future<bool> login(String email, String password) async {
    final data = await ApiClient.instance.post('/auth/login', data: {
      'email': email,
      'password': password,
    });
    final token = data['token'] as String?;
    if (token == null) return false;

    await ApiClient.instance.saveToken(token);
    _user = UserModel.fromJson(data['user'] as Map<String, dynamic>);
    _tenant = TenantModel.fromJson(data['tenant'] as Map<String, dynamic>);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppConstants.prefUserJson, jsonEncode(_user!.toJson()));
    await prefs.setString(AppConstants.prefTenantJson, jsonEncode(_tenant!.toJson()));
    return true;
  }

  Future<void> logout() async {
    try {
      await ApiClient.instance.post('/auth/logout');
    } catch (_) {}
    await ApiClient.instance.clearToken();
    _user = null;
    _tenant = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(AppConstants.prefUserJson);
    await prefs.remove(AppConstants.prefTenantJson);
  }

  Future<void> refreshMe() async {
    try {
      final data = await ApiClient.instance.get('/auth/me');
      _user = UserModel.fromJson(data['user'] as Map<String, dynamic>);
      _tenant = TenantModel.fromJson(data['tenant'] as Map<String, dynamic>);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(AppConstants.prefUserJson, jsonEncode(_user!.toJson()));
      await prefs.setString(AppConstants.prefTenantJson, jsonEncode(_tenant!.toJson()));
    } catch (_) {}
  }
}
