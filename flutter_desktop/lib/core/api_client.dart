import 'dart:convert';
import 'dart:io';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/constants.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  const ApiException(this.message, {this.statusCode});
  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient {
  static ApiClient? _instance;
  late Dio _dio;
  final _secure = const FlutterSecureStorage();
  String _baseUrl = AppConstants.defaultApiBase;

  ApiClient._();

  static ApiClient get instance {
    _instance ??= ApiClient._();
    return _instance!;
  }

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(AppConstants.prefApiBase) ?? AppConstants.defaultApiBase;
    _dio = Dio(BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 60),
      sendTimeout: const Duration(seconds: 60),
      headers: {'Content-Type': 'application/json'},
    ));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await _secure.read(key: AppConstants.prefToken);
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (error, handler) {
        final msg = _extractError(error);
        return handler.reject(DioException(
          requestOptions: error.requestOptions,
          response: error.response,
          message: msg,
          type: error.type,
        ));
      },
    ));
  }

  String _extractError(DioException e) {
    try {
      final data = e.response?.data;
      if (data is Map) return data['error'] ?? data['message'] ?? e.message ?? 'Unknown error';
    } catch (_) {}
    return e.message ?? 'Network error';
  }

  void setBaseUrl(String url) {
    _baseUrl = url.trimRight().replaceAll(RegExp(r'/$'), '');
    _dio.options.baseUrl = _baseUrl;
  }

  Future<void> saveToken(String token) async {
    await _secure.write(key: AppConstants.prefToken, value: token);
  }

  Future<void> clearToken() async {
    await _secure.delete(key: AppConstants.prefToken);
  }

  Future<String?> getToken() async {
    return await _secure.read(key: AppConstants.prefToken);
  }

  Future<Map<String, dynamic>> get(String path, {Map<String, dynamic>? params}) async {
    try {
      final r = await _dio.get(path, queryParameters: params);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Request failed', statusCode: e.response?.statusCode);
    }
  }

  Future<Map<String, dynamic>> post(String path, {dynamic data}) async {
    try {
      final r = await _dio.post(path, data: data);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Request failed', statusCode: e.response?.statusCode);
    }
  }

  Future<Map<String, dynamic>> put(String path, {dynamic data}) async {
    try {
      final r = await _dio.put(path, data: data);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Request failed', statusCode: e.response?.statusCode);
    }
  }

  Future<Map<String, dynamic>> delete(String path) async {
    try {
      final r = await _dio.delete(path);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Request failed', statusCode: e.response?.statusCode);
    }
  }

  Future<void> downloadFile(String path, String savePath) async {
    try {
      await _dio.download(path, savePath);
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Download failed', statusCode: e.response?.statusCode);
    }
  }

  Future<Map<String, dynamic>> uploadFile(String path, String filePath, {Map<String, dynamic>? extra}) async {
    try {
      final formData = FormData.fromMap({
        ...?extra,
        'file': await MultipartFile.fromFile(filePath, filename: filePath.split('/').last),
      });
      final r = await _dio.post(path, data: formData,
        options: Options(headers: {'Content-Type': 'multipart/form-data'}));
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw ApiException(e.message ?? 'Upload failed', statusCode: e.response?.statusCode);
    }
  }
}
