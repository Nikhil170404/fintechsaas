import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/api_client.dart';

class AiChatScreen extends StatefulWidget {
  const AiChatScreen({super.key});

  @override
  State<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends State<AiChatScreen> {
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _api = ApiClient.instance;

  final List<_Message> _messages = [];
  final List<Map<String, String>> _history = [];

  bool _loading = false;
  bool _indexing = false;
  Map<String, dynamic>? _status;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadStatus() async {
    try {
      final data = await _api.get('/api/v1/ai/status');
      setState(() => _status = data);
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _pullModels() async {
    setState(() => _loading = true);
    try {
      await _api.post('/api/v1/ai/pull', {'model': 'nomic-embed-text'});
      await _api.post('/api/v1/ai/pull', {'model': 'llama3.2'});
      await _loadStatus();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Models downloaded successfully')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _indexData() async {
    setState(() => _indexing = true);
    try {
      final res = await _api.post('/api/v1/ai/index', {});
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(res['message'] ?? 'Indexed successfully')),
        );
      }
      await _loadStatus();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Indexing failed: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      setState(() => _indexing = false);
    }
  }

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _loading) return;
    _inputCtrl.clear();

    final userMsg = _Message(role: 'user', text: text);
    setState(() {
      _messages.add(userMsg);
      _loading = true;
    });
    _scrollToBottom();

    try {
      final res = await _api.post('/api/v1/ai/chat', {
        'message': text,
        'history': _history,
      });
      final answer = res['answer'] as String? ?? '';
      _history.add({'role': 'user', 'content': text});
      _history.add({'role': 'assistant', 'content': answer});

      setState(() {
        _messages.add(_Message(role: 'assistant', text: answer));
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _messages.add(_Message(role: 'error', text: e.toString()));
        _loading = false;
      });
    }
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _clearChat() {
    setState(() {
      _messages.clear();
      _history.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Assistant'),
        actions: [
          if (_status != null && (_status!['running'] as bool? ?? false))
            IconButton(
              tooltip: 'Re-index client data',
              onPressed: _indexing ? null : _indexData,
              icon: _indexing
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.sync),
            ),
          IconButton(
            tooltip: 'Clear conversation',
            onPressed: _messages.isEmpty ? null : _clearChat,
            icon: const Icon(Icons.delete_sweep_outlined),
          ),
          IconButton(
            tooltip: 'Refresh status',
            onPressed: _loadStatus,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _status == null
          ? const Center(child: CircularProgressIndicator())
          : _buildBody(cs),
    );
  }

  Widget _buildBody(ColorScheme cs) {
    final running = _status!['running'] as bool? ?? false;

    if (!running) {
      return _buildSetupCard(cs);
    }

    final hasLlm = _status!['has_llm'] as bool? ?? false;
    final hasEmbed = _status!['has_embed'] as bool? ?? false;

    if (!hasLlm || !hasEmbed) {
      return _buildDownloadCard(cs, hasLlm: hasLlm, hasEmbed: hasEmbed);
    }

    return Column(
      children: [
        _buildStatusBar(cs),
        Expanded(child: _buildMessageList(cs)),
        _buildInput(cs),
      ],
    );
  }

  Widget _buildSetupCard(ColorScheme cs) {
    final cmds = _status!['install_cmd'] as Map? ?? {};
    return Center(
      child: Card(
        margin: const EdgeInsets.all(32),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.smart_toy_outlined, size: 64, color: cs.primary),
              const SizedBox(height: 16),
              Text('Ollama Not Running', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text(
                'Install Ollama to run AI locally — no internet or API key needed.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              if (cmds.isNotEmpty)
                ...cmds.entries.map((e) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _InstallRow(label: e.key, command: e.value.toString()),
                )),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: _loadStatus,
                icon: const Icon(Icons.refresh),
                label: const Text('Check Again'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDownloadCard(ColorScheme cs, {required bool hasLlm, required bool hasEmbed}) {
    return Center(
      child: Card(
        margin: const EdgeInsets.all(32),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.download_outlined, size: 64, color: cs.primary),
              const SizedBox(height: 16),
              Text('Download AI Models', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text('Required models need to be downloaded once (~2 GB total).'),
              const SizedBox(height: 16),
              _ModelRow(name: 'llama3.2', label: 'Language model (chat)', ready: hasLlm),
              const SizedBox(height: 8),
              _ModelRow(name: 'nomic-embed-text', label: 'Embedding model (RAG)', ready: hasEmbed),
              const SizedBox(height: 24),
              _loading
                  ? const CircularProgressIndicator()
                  : FilledButton.icon(
                      onPressed: _pullModels,
                      icon: const Icon(Icons.download),
                      label: const Text('Download Models'),
                    ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatusBar(ColorScheme cs) {
    final chunks = (_status!['total_chunks'] as int?) ?? 0;
    final model = _status!['default_llm'] as String? ?? 'llama3.2';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      color: cs.surfaceVariant.withOpacity(0.4),
      child: Row(
        children: [
          Icon(Icons.circle, size: 10, color: Colors.green.shade400),
          const SizedBox(width: 6),
          Text('$model  •  ', style: const TextStyle(fontSize: 12)),
          Text(
            chunks > 0 ? '$chunks chunks indexed' : 'No data indexed yet — tap Sync to index clients',
            style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
          ),
          const Spacer(),
          if (chunks == 0)
            TextButton.icon(
              onPressed: _indexing ? null : _indexData,
              icon: const Icon(Icons.sync, size: 14),
              label: const Text('Index Now', style: TextStyle(fontSize: 12)),
              style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
            ),
        ],
      ),
    );
  }

  Widget _buildMessageList(ColorScheme cs) {
    if (_messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.chat_bubble_outline, size: 56, color: cs.outlineVariant),
            const SizedBox(height: 12),
            Text('Ask anything about your clients', style: TextStyle(color: cs.outline)),
            const SizedBox(height: 4),
            Text(
              '"Show overdue loans"  •  "Total portfolio value"  •  "Clients from Mumbai"',
              style: TextStyle(fontSize: 12, color: cs.outlineVariant),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      itemCount: _messages.length + (_loading ? 1 : 0),
      itemBuilder: (ctx, i) {
        if (_loading && i == _messages.length) {
          return const _TypingBubble();
        }
        return _MessageBubble(msg: _messages[i], cs: cs);
      },
    );
  }

  Widget _buildInput(ColorScheme cs) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(top: BorderSide(color: cs.outlineVariant.withOpacity(0.3))),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _inputCtrl,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.newline,
              decoration: InputDecoration(
                hintText: 'Ask about your clients, loans, invoices…',
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                isDense: true,
              ),
              onSubmitted: (_) => _send(),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: _loading ? null : _send,
            style: FilledButton.styleFrom(
              shape: const CircleBorder(),
              padding: const EdgeInsets.all(14),
            ),
            child: const Icon(Icons.send),
          ),
        ],
      ),
    );
  }
}


// ── Data model ────────────────────────────────────────────────────────────────

class _Message {
  final String role; // user | assistant | error
  final String text;
  const _Message({required this.role, required this.text});
}


// ── Widgets ───────────────────────────────────────────────────────────────────

class _MessageBubble extends StatelessWidget {
  final _Message msg;
  final ColorScheme cs;
  const _MessageBubble({required this.msg, required this.cs});

  @override
  Widget build(BuildContext context) {
    final isUser = msg.role == 'user';
    final isError = msg.role == 'error';

    final bg = isError
        ? cs.errorContainer
        : isUser
            ? cs.primaryContainer
            : cs.surfaceVariant;
    final fg = isError
        ? cs.onErrorContainer
        : isUser
            ? cs.onPrimaryContainer
            : cs.onSurfaceVariant;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.72),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(16).copyWith(
            bottomRight: isUser ? const Radius.circular(4) : null,
            bottomLeft: isUser ? null : const Radius.circular(4),
          ),
        ),
        child: SelectableText(msg.text, style: TextStyle(color: fg, height: 1.45)),
      ),
    );
  }
}

class _TypingBubble extends StatelessWidget {
  const _TypingBubble();
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: cs.surfaceVariant,
          borderRadius: BorderRadius.circular(16).copyWith(bottomLeft: const Radius.circular(4)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) => _Dot(delay: i * 200)),
        ),
      ),
    );
  }
}

class _Dot extends StatefulWidget {
  final int delay;
  const _Dot({required this.delay});
  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600))
      ..repeat(reverse: true);
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut);
    Future.delayed(Duration(milliseconds: widget.delay), () {
      if (mounted) _ctrl.forward();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => Container(
        width: 8,
        height: 8,
        margin: const EdgeInsets.symmetric(horizontal: 2),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primary.withOpacity(0.4 + 0.6 * _anim.value),
          shape: BoxShape.circle,
        ),
      ),
    );
  }
}

class _ModelRow extends StatelessWidget {
  final String name;
  final String label;
  final bool ready;
  const _ModelRow({required this.name, required this.label, required this.ready});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(ready ? Icons.check_circle : Icons.radio_button_unchecked,
            size: 18, color: ready ? Colors.green : Colors.grey),
        const SizedBox(width: 8),
        Expanded(child: Text('$label  ($name)')),
      ],
    );
  }
}

class _InstallRow extends StatelessWidget {
  final String label;
  final String command;
  const _InstallRow({required this.label, required this.command});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(width: 80, child: Text(label, style: const TextStyle(fontWeight: FontWeight.bold))),
        Expanded(
          child: GestureDetector(
            onTap: () {
              Clipboard.setData(ClipboardData(text: command));
              ScaffoldMessenger.of(context)
                  .showSnackBar(const SnackBar(content: Text('Copied to clipboard')));
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceVariant,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(command, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
            ),
          ),
        ),
        const SizedBox(width: 4),
        Icon(Icons.copy, size: 14, color: Theme.of(context).colorScheme.outline),
      ],
    );
  }
}
