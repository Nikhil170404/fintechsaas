import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import '../core/api_client.dart';
import '../models/client.dart';

class DocumentService {
  static final DocumentService instance = DocumentService._();
  DocumentService._();

  Future<List<ClientModel>> fetchClients({String? search, int page = 1}) async {
    final data = await ApiClient.instance.get('/clients', params: {
      if (search != null && search.isNotEmpty) 'q': search,
      'page': page,
      'per_page': 100,
    });
    final list = data['clients'] as List<dynamic>? ?? [];
    return list.map((e) => ClientModel.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Map<String, dynamic>>> fetchFiles() async {
    final data = await ApiClient.instance.get('/files');
    return (data['files'] as List<dynamic>? ?? [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  Future<String> downloadFile(String filename) async {
    final dir = await getDownloadsDirectory() ?? await getApplicationDocumentsDirectory();
    final savePath = p.join(dir.path, filename);
    await ApiClient.instance.downloadFile('/files/$filename', savePath);
    return savePath;
  }

  Future<Map<String, dynamic>> generateStatements(List<String> accountNos) async {
    return ApiClient.instance.post('/generate/statements', data: {
      'account_nos': accountNos,
    });
  }

  Future<Map<String, dynamic>> generateInvoice(Map<String, dynamic> invoiceData) async {
    return ApiClient.instance.post('/generate/invoice', data: invoiceData);
  }

  Future<Map<String, dynamic>> generateLoan(Map<String, dynamic> loanData) async {
    return ApiClient.instance.post('/generate/loan', data: loanData);
  }

  Future<Map<String, dynamic>> generatePortfolio(Map<String, dynamic> data) async {
    return ApiClient.instance.post('/generate/portfolio', data: data);
  }

  Future<Map<String, dynamic>> sendEmail({
    required List<String> to,
    required String subject,
    required String body,
    List<String> attachments = const [],
    String provider = 'smtp',
    List<String>? cc,
  }) async {
    return ApiClient.instance.post('/send/email', data: {
      'to': to,
      'subject': subject,
      'body': body,
      'attachments': attachments,
      'provider': provider,
      if (cc != null) 'cc': cc,
    });
  }

  Future<Map<String, dynamic>> sendWhatsApp({
    required List<String> accountNos,
    required String message,
    String? pdfFilename,
  }) async {
    return ApiClient.instance.post('/send/whatsapp', data: {
      'account_nos': accountNos,
      'message': message,
      if (pdfFilename != null) 'pdf': pdfFilename,
    });
  }
}
