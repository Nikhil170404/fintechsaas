class UserModel {
  final int id;
  final String username;
  final String email;
  final String role;

  const UserModel({
    required this.id,
    required this.username,
    required this.email,
    required this.role,
  });

  bool get isOwner => role == 'owner';

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
        id: json['id'] as int? ?? 0,
        username: json['username'] as String? ?? '',
        email: json['email'] as String? ?? '',
        role: json['role'] as String? ?? 'staff',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'email': email,
        'role': role,
      };
}

class TenantModel {
  final int id;
  final String name;
  final String slug;
  final String companyName;
  final String brandColor;

  const TenantModel({
    required this.id,
    required this.name,
    required this.slug,
    required this.companyName,
    required this.brandColor,
  });

  factory TenantModel.fromJson(Map<String, dynamic> json) => TenantModel(
        id: json['id'] as int? ?? 0,
        name: json['name'] as String? ?? '',
        slug: json['slug'] as String? ?? '',
        companyName: json['company_name'] as String? ?? '',
        brandColor: json['brand_color'] as String? ?? '#1976D2',
      );
}
