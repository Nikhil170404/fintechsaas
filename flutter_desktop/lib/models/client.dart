class ClientModel {
  final String accountNo;
  final String name;
  final String email;
  final String phone;
  final String? address;
  final double? openingBalance;
  final double? closingBalance;
  final List<Map<String, dynamic>> transactions;
  final String? zohoId;

  const ClientModel({
    required this.accountNo,
    required this.name,
    required this.email,
    required this.phone,
    this.address,
    this.openingBalance,
    this.closingBalance,
    this.transactions = const [],
    this.zohoId,
  });

  factory ClientModel.fromJson(Map<String, dynamic> json) => ClientModel(
        accountNo: json['account_no']?.toString() ?? '',
        name: json['name']?.toString() ?? '',
        email: json['email']?.toString() ?? '',
        phone: json['phone']?.toString() ?? '',
        address: json['address']?.toString(),
        openingBalance: (json['opening_balance'] as num?)?.toDouble(),
        closingBalance: (json['closing_balance'] as num?)?.toDouble(),
        transactions: (json['transactions'] as List<dynamic>?)
                ?.map((e) => Map<String, dynamic>.from(e as Map))
                .toList() ??
            [],
        zohoId: json['zoho_id']?.toString(),
      );

  Map<String, dynamic> toJson() => {
        'account_no': accountNo,
        'name': name,
        'email': email,
        'phone': phone,
        if (address != null) 'address': address,
        if (openingBalance != null) 'opening_balance': openingBalance,
        if (closingBalance != null) 'closing_balance': closingBalance,
        'transactions': transactions,
        if (zohoId != null) 'zoho_id': zohoId,
      };
}
