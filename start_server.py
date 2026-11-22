# -*- coding: utf-8 -*-
"""工厂管理系统启动入口（Waitress）。

由项目根目录的「启动系统.bat」调用，也可手动执行：

    venv\\Scripts\\python.exe start_server.py

支持的环境变量（写入根目录 .env 即可，config.py 在导入时自动加载）：
    SERVER_HOST     监听地址，默认 0.0.0.0（同时允许本机和局域网访问）
    SERVER_PORT     监听端口，默认 5000
    SERVER_THREADS  Waitress 工作线程数，默认 8
    OPEN_BROWSER    是否自动打开浏览器，默认 1；设为 0 则不打开
"""
import os
import socket
import threading
import webbrowser

from app import create_app

# 导入 app 时 config.py 会自动读取根目录 .env，因此这里再读取环境变量即可拿到服务配置。
app = create_app()


def _read_int(name, default):
    """读取整数环境变量，非法值回退到默认值并打印提示。"""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        print('[警告] %s=%r 不是整数，使用默认值 %s' % (name, raw, default))
        return default


def resolve_server_config():
    """返回 (host, port, threads, open_browser)。"""
    host = (os.environ.get('SERVER_HOST') or '0.0.0.0').strip() or '0.0.0.0'

    port = _read_int('SERVER_PORT', 5000)
    if port < 1 or port > 65535:
        print('[警告] SERVER_PORT 超出 1~65535，已使用 5000')
        port = 5000

    threads = _read_int('SERVER_THREADS', 8)
    if threads < 1:
        print('[警告] SERVER_THREADS 必须大于 0，已使用 1')
        threads = 1

    raw_browser = (os.environ.get('OPEN_BROWSER') or '1').strip().lower()
    open_browser = raw_browser not in ('0', 'false', 'no', 'off')
    return host, port, threads, open_browser


def get_lan_ip():
    """获取局域网 IP；无网络时回退到 127.0.0.1。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        sock.close()


def browser_url(host, port):
    """浏览器打开的地址：监听所有网卡时用回环地址，否则用绑定的地址。"""
    target = '127.0.0.1' if host in ('0.0.0.0', '', '::') else host
    return 'http://%s:%d' % (target, port)


def print_banner(host, port, open_browser):
    """在命令行打印访问地址和停止方式。"""
    print('=' * 64)
    print(' 工厂管理系统已启动（Waitress）')
    print(' 本机访问   : %s' % browser_url(host, port))
    if host in ('0.0.0.0', '', '::'):
        print(' 局域网访问 : http://%s:%d' % (get_lan_ip(), port))
    else:
        print(' 监听地址   : http://%s:%d' % (host, port))
    print(' 停止服务   : 按 Ctrl+C，或直接关闭此命令行窗口')
    if open_browser:
        print(' 浏览器     : 将在 1 秒后自动打开本机地址')
    print('=' * 64)
    print('', flush=True)


def main():
    host, port, threads, open_browser = resolve_server_config()
    try:
        from waitress import serve
    except ImportError:
        raise SystemExit(
            '[错误] 缺少 waitress，请先执行：\n'
            '    venv\\Scripts\\python.exe -m pip install -r requirements.txt'
        )

    print_banner(host, port, open_browser)
    if open_browser:
        timer = threading.Timer(1.0, webbrowser.open, args=(browser_url(host, port),))
        timer.daemon = True
        timer.start()

    serve(app, host=host, port=port, threads=threads)


if __name__ == '__main__':
    main()
