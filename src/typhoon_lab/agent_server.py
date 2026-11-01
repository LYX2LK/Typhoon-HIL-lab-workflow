"""Loopback HTTP host for the conversational agent (separate from the old demo)."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import urllib.parse
import os
import socket

from .agent import open_session
from .agent_cases import catalog, BOOST
from .boost_agent_render import STYLE


class AgentHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve(port=8767,session_dir=None,default_case=BOOST):
    holder={"session":open_session(session_dir,default_case=default_case)};token=secrets.token_hex(24)
    archives={holder['session'].root.name:holder['session'].root}
    template=Path(__file__).with_name('agent_page.html').read_text(encoding='utf-8')
    page=template.replace('__REPORT_STYLE__',STYLE).replace('__TOKEN__',token).encode('utf-8')
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,value,mime='application/json; charset=utf-8'):
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            session=holder['session']
            if self.path=='/':return self.reply(200,page,'text/html; charset=utf-8')
            if self.path=='/favicon.ico':return self.reply(204,b'','image/x-icon')
            if self.path=='/api/state':return self.reply(200,session.snapshot())
            if self.path=='/api/cases':return self.reply(200,{'cases':catalog()})
            if self.path=='/export':
                session.export()
                content=(session.root/'report.html').read_text(encoding='utf-8').replace('href="runs/','href="/archive-files/'+session.root.name+'/runs/')
                return self.reply(200,content.encode('utf-8'),'text/html; charset=utf-8')
            if self.path.startswith('/archive-files/'):
                parts=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).split('/',3)
                archive=archives.get(parts[2])
                if archive and len(parts)==4:
                    p=(archive/parts[3]).resolve()
                    if p.is_relative_to(archive.resolve()) and p.is_file() and p.suffix.lower() in {'.html','.png','.json','.csv','.md'}:
                        mime=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
                        return self.reply(200,p.read_bytes(),mime+('; charset=utf-8' if mime.startswith('text/') else ''))
            if self.path.startswith('/files/'):
                rel=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path[7:]);p=(session.root/rel).resolve()
                if p.is_relative_to(session.root.resolve()) and p.is_file() and p.suffix.lower() in {'.html','.png','.json','.csv','.md'}:
                    mime=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
                    if mime.startswith('text/') or p.suffix=='.json':mime+='; charset=utf-8'
                    return self.reply(200,p.read_bytes(),mime)
            self.reply(404,{'error':'未找到资源'})
        def do_POST(self):
            if self.headers.get('X-Agent-Token')!=token:return self.reply(403,{'error':'请求标识无效，请刷新页面'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length>20000:return self.reply(413,{'error':'请求过大'})
                data=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(data,dict):raise ValueError('请求必须为对象')
                operation=self.path.removeprefix('/api/')
                if operation=='new':
                    old=holder['session']
                    with old.guard:
                        if old.state['busy']:raise ValueError('当前实验/分析仍在运行')
                        old.export();holder['session']=open_session(default_case=default_case)
                        archives[holder['session'].root.name]=holder['session'].root
                    result={'accepted':True}
                else:result=holder['session'].launch(operation,data)
                self.reply(200,result)
            except Exception as exc:self.reply(400,{'error':str(exc)})
        def log_message(self,*args):pass
    server=AgentHTTPServer(('127.0.0.1',port),Handler)
    print(f'Agent URL: http://127.0.0.1:{port}\nSession: {holder["session"].root}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
