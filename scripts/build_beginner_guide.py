"""Build the offline reader from Markdown with the THCC bundled Python.

Run from the project root: <bundled-python> -B -X utf8 scripts/build_beginner_guide.py
Existing source assets and their provenance are preserved.
"""
from pathlib import Path
from hashlib import sha256
from html import escape
from markdown_it import MarkdownIt
import json
import re

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "docs/beginner"
ASSETS = COURSE / "assets"
CHAPTERS = [
    ("README.md", "start", "开始", "学习路线"),
    ("01-electricity-and-system.md", "electricity", "01", "电与整套系统"),
    ("02-chip-board-and-wires.md", "board", "02", "芯片、控制板与引线"),
    ("03-motor-and-control.md", "motor", "03", "电机与控制"),
    ("04-feedback-and-hil.md", "feedback", "04", "反馈与 HIL"),
    ("05-lin-and-pwm.md", "communication", "05", "LIN 与 PWM 练习"),
    ("06-typhoon-walkthrough.md", "practice", "06", "Typhoon 预演导读"),
    ("07-test-preparation.md", "preparation", "07", "样机测试准备"),
    ("08-ti-launchpad-chil.md", "ti-chil", "08", "TI 真实控制器实训"),
    ("09-pmsm-to-tle9877-chil.md", "tle-chil", "09", "走向 TLE9877 实体测试"),
    ("reference.md", "reference", "查阅", "术语、资料与原图"),
]
LESSON_COUNT = sum(number.isdigit() for _, _, number, _ in CHAPTERS)

def diagram(name, title, boxes, arrows, note, height=400):
    colors = {"control": ("#e8f2f0", "#26675f"), "plant": ("#edf1f8", "#355779"),
              "power": ("#fff0df", "#95632c"), "feedback": ("#f2edf9", "#6d558a")}
    bits = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(note)}</desc>',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#48606a"/></marker></defs>',
            '<rect width="100%" height="100%" fill="#fcfcf9"/>',
            '<g font-family="Microsoft YaHei, PingFang SC, sans-serif" fill="#22383d">',
            f'<text x="34" y="40" font-size="25" font-weight="700">{escape(title)}</text>']
    for x, y, w, h, lines, kind in boxes:
        fill, stroke = colors[kind]
        bits.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        top = y + h/2 - (len(lines)-1)*15 + 8
        for i, line in enumerate(lines):
            bits.append(f'<text x="{x+w/2}" y="{top+i*30}" text-anchor="middle" font-size="22">{escape(line)}</text>')
    for path, label, x, y, dashed in arrows:
        dash = 'stroke-dasharray="7 5"' if dashed else ''
        bits.append(f'<path d="{path}" fill="none" stroke="#48606a" stroke-width="2.5" {dash} marker-end="url(#arrow)"/>')
        if label:
            bits.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="18" paint-order="stroke" stroke="#fcfcf9" stroke-width="7">{escape(label)}</text>')
    bits.append(f'<text x="34" y="{height-20}" font-size="17" fill="#5e6f73">{escape(note)}</text></g></svg>')
    path = ASSETS / name
    path.write_text("\n".join(bits)+"\n", encoding="utf-8")
    return {"asset": path.relative_to(ROOT).as_posix(), "source": "author_generated",
            "scope": "conceptual_function_diagram", "sha256": sha256(path.read_bytes()).hexdigest()}

generated = []
generated.append(diagram("system-loop.svg", "要求怎样变成动作，又怎样取得反馈", [
    (35,140,165,80,["转速要求"],"control"),
    (270,140,170,80,["控制程序"],"control"),
    (510,140,220,80,["驱动与功率开关"],"power"),
    (800,140,250,80,["电机与负载"],"plant"),
    (545,285,220,70,["测量与状态估计"],"feedback"),
    (545,65,150,50,["电源"],"power"),
], [
    ("M200 180 H270","",0,0,False), ("M440 180 H510","",0,0,False),
    ("M730 180 H800","电能",765,166,False), ("M620 115 V140","",0,0,False),
    ("M925 220 V320 H765","运行信息",903,299,True),
    ("M545 320 H355 V220","反馈",380,302,True),
], "功能关系示意；箭头表示作用与信息传递，电源另向功率通路提供能量。", 420))
generated.append(diagram("control-loops.svg", "常见的转速外环与电流内环", [
    (30,105,145,80,["参考转速"],"control"),
    (225,105,170,80,["转速控制"],"control"),
    (445,105,200,80,["电流／转矩要求"],"control"),
    (695,105,170,80,["电流控制","与调制"],"control"),
    (915,105,155,80,["三相桥","与电机"],"plant"),
    (735,245,180,65,["电流反馈"],"feedback"),
    (420,350,250,65,["转速测量或估计"],"feedback"),
], [
    ("M175 145 H225","",0,0,False), ("M395 145 H445","",0,0,False),
    ("M645 145 H695","",0,0,False), ("M865 145 H915","",0,0,False),
    ("M990 185 V278 H915","",0,0,True), ("M735 278 H710 V185","",0,0,True),
    ("M1035 185 V382 H670","",0,0,True), ("M420 382 H310 V185","",0,0,True),
], "具体算法、周期、限幅和反馈来源由当前控制器实现决定。", 470))
generated.append(diagram("hil-loop.svg", "真实控制板与实时仿真对象的拟接入关系", [
    (35,100,230,80,["LIN 主节点","或已确认命令源"],"control"),
    (410,100,240,80,["真实控制板","与固件"],"control"),
    (790,100,260,80,["驱动信号","调理与捕获"],"power"),
    (790,285,260,80,["实时逆变器","与电机模型"],"plant"),
    (410,285,240,80,["反馈输出","调理与注入"],"feedback"),
], [
    ("M265 125 H410","命令",335,110,False),
    ("M410 160 H265","LIN 状态",337,185,True),
    ("M650 140 H790","六路驱动",720,121,False),
    ("M920 180 V285","开关状态",977,241,False),
    ("M790 325 H650","所需反馈",720,305,True),
    ("M530 285 V180","电气反馈",578,241,True),
], "功能方案示意；实际保留电路、注入节点、量程和时序按确认的改装与调理方案落实。", 430))

generated.append(diagram("ti-chil-loop.svg", "TI C-HIL：把命令、驱动与反馈分开看", [
    (30,115,230,100,["电脑与 SCADA","安排命令、采集与记录"],"control"),
    (410,115,245,100,["真实 TI F28379D","执行 FOC 与 PWM"],"control"),
    (800,115,270,100,["实体 HIL 实时仿真","逆变器、PMSM 与负载"],"plant"),
], [
    ("M260 165 H410","USB 串口命令",335,145,False),
    ("M655 165 H800","六路驱动 → DI",727,145,False),
    ("M880 215 V290 H615 V215","AO：电流反馈",740,273,True),
    ("M1000 215 V355 H455 V215","DO：编码器 A / B / Z",740,337,True),
], "本教程绘制的功能示意；通道、电平和供电选择按匹配版本的 TI 接口板资料核对。", 420))

generated.append(diagram("tle9877-shunt-path.svg", "单分流反馈：支路、比例与采样时刻一起对应", [
    (30,105,250,85,["六路开关状态","调理后捕获"],"control"),
    (415,105,250,85,["逆变器与电机模型","计算电路响应"],"plant"),
    (800,105,270,85,["对应分流支路电流","i_shunt(t)"],"feedback"),
    (800,285,270,85,["分流关系与反馈调理","差分、共模与动态响应"],"feedback"),
    (415,285,250,85,["已确认的注入节点","对应实际保留电路"],"feedback"),
    (30,285,250,85,["真实 ADC 与固件","在有效窗口内采样"],"control"),
], [
    ("M280 147 H415","开关动作",348,128,False),
    ("M665 147 H800","支路测量",732,128,False),
    ("M935 190 V285","",0,0,True),
    ("M800 327 H665","电气反馈",732,308,True),
    ("M415 327 H280","输入采样链",348,308,True),
    ("M155 285 V190","",0,0,False),
], "功能关系示意；支路方向、注入位置、增益、偏置、延迟和采样窗口由本板方案确认。", 430))

manifest_path = ASSETS / "sources.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["conceptual_diagrams"] = generated
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

md = MarkdownIt("commonmark", {"html": True}).enable("table")
by_file = {f: sid for f, sid, _, _ in CHAPTERS}
diagrams = {"electricity": "system-loop.svg", "motor": "control-loops.svg", "feedback": "hil-loop.svg"}
navigation = []
articles = []
for filename, sid, number, label in CHAPTERS:
    text = (COURSE / filename).read_text(encoding="utf-8")
    tokens = md.parse(text)
    used = set()
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            slug = re.sub(r"[^\w\s-]", "", tokens[i+1].content.lower()).strip()
            slug = re.sub(r"\s+", "-", slug)
            anchor = f"{sid}--{slug}"
            while anchor in used:
                anchor += "-2"
            used.add(anchor)
            token.attrSet("id", anchor)
        if token.type == "fence" and token.info.strip() == "mermaid":
            token.type = "html_block"
            token.tag = ""
            token.content = (f'<figure class="concept-diagram"><img src="assets/{diagrams[sid]}" '
                             f'alt="{escape(label)}功能关系示意图"><figcaption>本教程绘制的功能关系示意图</figcaption></figure>')
    html = md.renderer.render(tokens, md.options, {})
    def relink(match):
        href = match.group(1)
        name, sep, fragment = href.partition("#")
        if name in by_file:
            target = by_file[name]
            return f'href="#{target}"' if not sep else f'href="#{target}--{fragment}"'
        return match.group(0)
    html = re.sub(r'href="([^"]+)"', relink, html)
    navigation.append(f'<a href="#{sid}" data-chapter="{sid}"><span>{number}</span>{label}</a>')
    articles.append(f'<article id="{sid}" data-chapter-title="{escape(label)}">{html}</article>')

style = """
:root{--paper:#fbfaf6;--ink:#253b42;--muted:#60757b;--accent:#276a62;--line:#dbe4df;--reader-size:18px}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:34px}body{margin:0;background:var(--paper);color:var(--ink);font:var(--reader-size)/1.85 'Segoe UI','Microsoft YaHei','PingFang SC',sans-serif}
a{color:#21665f;text-underline-offset:4px}a:hover{color:#954b28}button,input{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #ba7b43;outline-offset:4px}
.skip{position:absolute;top:-100px}.skip:focus{top:12px;left:20px;background:white;padding:12px;z-index:20}
aside{position:fixed;inset:0 auto 0 0;width:280px;padding:34px 25px;background:#eff3ef;border-right:1px solid var(--line);overflow:auto;font-size:15px}
.eyebrow{font-size:12px;letter-spacing:2px;color:#57786b}.brand{font-weight:750;font-size:25px;line-height:1.4;margin:12px 0}.intro-note{color:var(--muted);font-size:14px;margin:12px 0 22px}
nav a{display:flex;align-items:center;gap:12px;padding:10px 9px;margin:3px -9px;text-decoration:none;border-radius:7px;color:#3e5958}nav a span{font-size:12px;font-weight:700;min-width:34px;color:#668074}nav a.active{background:white;box-shadow:inset 3px 0 var(--accent);font-weight:700;color:#20564f}
.searchbox{margin:22px 0 12px}.searchbox label{display:block;color:var(--muted);font-size:13px;margin-bottom:5px}.searchbox input{width:100%;border:1px solid #b8c9c1;border-radius:7px;background:#fff;padding:8px 10px;font-size:14px}
#search-results{display:grid;gap:7px;font-size:13px;margin-top:8px}#search-results a{line-height:1.5}#search-status{font-size:12px;color:var(--muted)}
.tools{display:flex;gap:8px;margin-top:18px}.tools button{border:1px solid #bdcec5;border-radius:6px;background:transparent;color:#355b50;padding:4px 10px;font-size:14px}.image-note{font-size:12px;color:var(--muted);margin-top:15px}
main{margin-left:280px;max-width:1320px;padding:58px 76px 100px}.course-label{font-size:13px;letter-spacing:1px;text-transform:uppercase;color:#8f5d35;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:26px}
article{margin-bottom:90px;padding-bottom:65px;border-bottom:1px solid var(--line);scroll-margin-top:30px;overflow-wrap:anywhere}h1{font-size:34px;line-height:1.4;letter-spacing:-.6px;margin:16px 0 20px}h2{font-size:25px;line-height:1.5;margin:48px 0 17px}h3{font-size:20px;line-height:1.5;margin:32px 0 12px}p{margin:16px 0}strong{font-weight:700;color:#1d524c}li{padding-left:3px;margin:7px 0}ul,ol{padding-left:27px}
.table-wrap{overflow:auto;margin:24px 0;border:1px solid var(--line);border-radius:9px;background:#fff}table{border-collapse:collapse;width:100%;font-size:.88em;line-height:1.7}th,td{padding:12px 14px;text-align:left;vertical-align:top;border-bottom:1px solid #e4ebe6;min-width:110px}th{background:#ecf1ed;font-weight:650;color:#36584d}tr:last-child td{border-bottom:0}tbody tr:nth-child(even){background:#fbfcfa}
pre{background:#22373e;color:#edf6f4;overflow:auto;border-radius:9px;padding:22px 24px;font-size:14px;line-height:1.8;margin:24px 0;tab-size:4}code{font-family:Consolas,'Cascadia Code',monospace}p code,td code,li code{background:#e8eee9;border-radius:4px;padding:2px 5px;color:#234b43;font-size:.9em}
img{display:block;max-width:100%;height:auto;margin:0 auto}.image-button{display:block;width:100%;padding:18px;border:1px solid #dbe3df;border-radius:10px;background:white;margin:26px 0 10px;text-align:center;cursor:zoom-in}.image-button img{max-height:540px;object-fit:contain}.image-button::after{content:'点击放大原图';display:block;color:#677c75;font-size:12px;margin-top:9px}.concept-diagram{margin:28px 0}.concept-diagram .image-button{padding:5px}.concept-diagram img{width:100%;max-height:none}figcaption{font-size:13px;color:var(--muted);text-align:center;margin-top:8px}
details{background:#eff4ef;border:1px solid #d4e1d8;border-radius:9px;padding:15px 20px;margin:24px 0}summary{cursor:pointer;color:#296154;font-weight:650}details[open] summary{margin-bottom:13px}
dialog{width:min(1280px,96vw);max-height:94vh;border:0;border-radius:12px;padding:24px;background:#fff;color:var(--ink);overflow:auto}dialog::backdrop{background:#14272cbd}.dialog-header{display:flex;position:sticky;top:-24px;align-items:center;justify-content:space-between;gap:20px;background:#fff;padding:10px 0 14px;border-bottom:1px solid var(--line);z-index:2}.dialog-header p{margin:0;font-size:15px}.dialog-header button{padding:7px 16px;border:1px solid #b5c7bd;background:#f2f5f1;border-radius:6px;font-size:14px}#zoom-image{width:100%;max-height:none;margin-top:22px}
footer{font-size:14px;color:var(--muted)}
@media(max-width:1150px){main{padding:40px 36px}aside{width:245px;padding:28px 20px}main{margin-left:245px}h1{font-size:30px}}
@media(max-width:780px){aside{position:relative;width:auto;border-right:0;border-bottom:1px solid var(--line);padding:24px}main{margin:0;padding:28px 22px}nav{display:grid;grid-template-columns:1fr 1fr;gap:2px 12px}nav a{font-size:13px;padding:8px}.brand{font-size:25px}.intro-note{margin-bottom:10px}.searchbox{margin-top:14px}h1{font-size:29px}h2{font-size:23px}.image-button{padding:8px}th,td{padding:10px;font-size:14px}pre{padding:16px;font-size:13px}article{margin-bottom:55px;padding-bottom:40px}}
@media print{aside,.course-label,.skip{display:none}main{margin:0;padding:0;max-width:none}body{font-size:11pt;background:white}article{page-break-before:always;margin:0;border:0;padding:0}article:first-of-type{page-break-before:auto}h1,h2,h3{break-after:avoid}pre,figure,.image-button{break-inside:avoid}.image-button{border:0;cursor:default}.image-button::after{display:none}a{color:inherit}details{background:white}pre{white-space:pre-wrap;background:#f2f3f2;color:#222}}
"""

script = """
document.querySelectorAll('table').forEach(table=>{const wrap=document.createElement('div');wrap.className='table-wrap';table.replaceWith(wrap);wrap.append(table)});
const dialog=document.getElementById('image-dialog'),zoom=document.getElementById('zoom-image'),caption=document.getElementById('zoom-caption');
document.querySelectorAll('article img').forEach(img=>{const button=document.createElement('button');button.className='image-button';button.type='button';button.setAttribute('aria-label','放大图片：'+img.alt);img.replaceWith(button);button.append(img);button.addEventListener('click',()=>{zoom.src=img.src;zoom.alt=img.alt;caption.textContent=img.alt;dialog.showModal()})});
document.getElementById('close-image').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close()}});
let size=18;document.querySelectorAll('[data-size]').forEach(button=>button.addEventListener('click',()=>{size=Math.max(15,Math.min(24,size+Number(button.dataset.size)));document.documentElement.style.setProperty('--reader-size',size+'px')}));
document.getElementById('print-reader').addEventListener('click',()=>window.print());
const navLinks=[...document.querySelectorAll('nav a')];function select(id){navLinks.forEach(a=>a.classList.toggle('active',a.dataset.chapter===id))}
const observer=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);if(visible.length)select(visible[0].target.id)},{rootMargin:'-5% 0px -65% 0px'});document.querySelectorAll('article').forEach(article=>observer.observe(article));select(location.hash.slice(1)||'start');
const sections=[...document.querySelectorAll('article h2,article h3')].map(h=>{const lines=[];let n=h.nextElementSibling;while(n&&!/^H[123]$/.test(n.tagName)){lines.push(n.textContent);n=n.nextElementSibling}return{title:h.textContent,chapter:h.closest('article').dataset.chapterTitle,body:lines.join(' '),id:h.id}});
const search=document.getElementById('course-search'),results=document.getElementById('search-results'),status=document.getElementById('search-status');search.addEventListener('input',()=>{results.replaceChildren();const q=search.value.trim().toLocaleLowerCase();if(!q){status.textContent='';return}const found=sections.filter(s=>(s.title+' '+s.body).toLocaleLowerCase().includes(q));status.textContent=found.length?'找到 '+found.length+' 处，显示前 8 处':'未找到，请换一个词';found.slice(0,8).forEach(s=>{const a=document.createElement('a');a.href='#'+s.id;a.textContent=s.chapter+' · '+s.title;results.append(a)})});
document.documentElement.dataset.readerReady='true';
"""

html = ('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>从零理解样机测试 · Typhoon 图文教程</title><meta name="description" content="面向初学者的样机测试教程：电路、芯片、电机控制、LIN/PWM、PMSM 软件预演、TI LaunchPad 中文实训与 TLE9877 实体 C-HIL 准备。"><style>'''+style+'''</style></head><body>
<a class="skip" href="#content">跳到正文</a>
<aside><div class="eyebrow">TYPHOON · LEARNING NOTES</div><div class="brand">从零理解<br>样机测试</div><p class="intro-note">从电压与电流开始，读懂这块板、这套模型和一次测试。</p><nav aria-label="章节导航">'''+"".join(navigation)+'''</nav>
<div class="searchbox"><label for="course-search">查一个术语或问题</label><input id="course-search" type="search" placeholder="例如：分流、2240、无感" autocomplete="off"><div id="search-status" role="status"></div><div id="search-results"></div></div>
<div class="tools" aria-label="阅读工具"><button type="button" data-size="-1" aria-label="缩小正文字号">A−</button><button type="button" data-size="1" aria-label="放大正文字号">A＋</button><button type="button" id="print-reader">打印</button></div><p class="image-note">图片可点击放大，按 Esc 返回。<br>本页可离线阅读；官方外链需联网。</p></aside>
<main id="content"><div class="course-label">零基础图文教程 · '''+str(LESSON_COUNT)+''' 章学习与动手练习</div>'''+"".join(articles)+'''<footer>正文以同目录 Markdown 为可维护版本。板级事实、参数与实际结果沿正文链接查阅。</footer></main>
<dialog id="image-dialog" aria-label="图片放大"><div class="dialog-header"><p id="zoom-caption"></p><button type="button" id="close-image">关闭图片</button></div><img id="zoom-image" alt=""></dialog><script>'''+script+'''</script></body></html>''')
html = html.replace("<head>", '<head><link rel="icon" href="data:,">', 1)
(COURSE / "index.html").write_text(html, encoding="utf-8")
print(json.dumps({"chapters": LESSON_COUNT, "markdown_pages": len(CHAPTERS), "source_images": len(manifest["assets"]),
                  "conceptual_diagrams": len(generated), "html_bytes": len(html.encode("utf-8"))}, ensure_ascii=False))
