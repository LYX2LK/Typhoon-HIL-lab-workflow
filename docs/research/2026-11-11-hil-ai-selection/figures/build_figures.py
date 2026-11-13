from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import html, math, json, hashlib

OUT = Path(__file__).resolve().parent
FONT = 'C:/Windows/Fonts/msyh.ttc'
BOLD = 'C:/Windows/Fonts/msyhbd.ttc'
S = 3
INK = '#243449'
BLUE = '#27628C'
GREEN = '#326C62'
GRAY = '#637386'

class Figure:
    def __init__(self, name, w, h, title):
        self.name, self.w, self.h = name, w, h
        self.im = Image.new('RGB', (w*S, h*S), 'white')
        self.d = ImageDraw.Draw(self.im)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">', '<rect width="100%" height="100%" fill="white"/>']
        self.text(w/2, 39, [title], 34, True)
        self.boxes = []

    def text(self, x, y, lines, size=27, bold=False, color=INK, backing=False):
        font=ImageFont.truetype(BOLD if bold else FONT, size*S)
        widths=[self.d.textlength(t, font=font)/S for t in lines]
        lh=size*1.48
        if backing:
            width=max(widths)+20; height=lh*len(lines)+8
            self.d.rectangle(((x-width/2)*S,(y-height/2)*S,(x+width/2)*S,(y+height/2)*S),fill='white')
            self.svg.append(f'<rect x="{x-width/2}" y="{y-height/2}" width="{width}" height="{height}" fill="white"/>')
        for i,t in enumerate(lines):
            cy=y+(i-(len(lines)-1)/2)*lh
            self.d.text((x*S,cy*S),t,font=font,fill=color,anchor='mm')
            self.svg.append(f'<text x="{x}" y="{cy}" text-anchor="middle" dominant-baseline="central" font-family="Microsoft YaHei, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(t)}</text>')
        return widths

    def line(self, pts, color=GRAY, dash=False, width=2.8):
        scaled=[(x*S,y*S) for x,y in pts]
        if not dash:
            self.d.line(scaled,fill=color,width=round(width*S),joint='curve')
        else:
            for (x1,y1),(x2,y2) in zip(scaled,scaled[1:]):
                length=math.hypot(x2-x1,y2-y1)
                for start in range(0,round(length),21*S):
                    end=min(start+12*S,length)
                    self.d.line((x1+(x2-x1)*start/length,y1+(y2-y1)*start/length,x1+(x2-x1)*end/length,y1+(y2-y1)*end/length),fill=color,width=round(width*S))
        x,y=pts[-1]; px,py=pts[-2]
        a=math.atan2(y-py,x-px); n=12
        tri=[(x,y),(x-n*math.cos(a)+n*.46*math.sin(a),y-n*math.sin(a)-n*.46*math.cos(a)),(x-n*math.cos(a)-n*.46*math.sin(a),y-n*math.sin(a)+n*.46*math.cos(a))]
        self.d.polygon([(a*S,b*S) for a,b in tri],fill=color)
        points=' '.join(f'{a},{b}' for a,b in pts)
        self.svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"'+(' stroke-dasharray="12 9"' if dash else '')+'/>')
        self.svg.append('<polygon points="'+' '.join(f'{a},{b}' for a,b in tri)+f'" fill="{color}"/>')

    def box(self,x,y,w,h,title,body=(),kind='normal',size=27):
        colors={'normal':('#F4F7FA','#74869A'),'llm':('#EAF2FA',BLUE),'data':('#EDF6F1',GREEN),'future':('#FAF7F0','#9A8358')}
        fill,stroke=colors[kind]
        self.d.rounded_rectangle((x*S,y*S,(x+w)*S,(y+h)*S),radius=13*S,fill=fill,outline=stroke,width=2*S)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="13" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        if body:
            th=30*1.48+len(body)*size*1.48+10
            ty=y+(h-th)/2+30*1.48/2
            widths=self.text(x+w/2,ty,[title],30,True,color=INK if kind=='normal' else stroke)
            by=ty+30*1.48/2+10+len(body)*size*1.48/2
            widths+=self.text(x+w/2,by,list(body),size)
        else:
            widths=self.text(x+w/2,y+h/2,[title],30,True,color=stroke)
            th=45
        assert max(widths)<=w-30,(self.name,title,max(widths),w)
        assert th<=h-4,(self.name,title,th,h)
        assert x>=0 and x+w<=self.w and y>=0 and y+h<=self.h
        for xx,yy,ww,hh in self.boxes:
            assert x+w<=xx or xx+ww<=x or y+h<=yy or yy+hh<=y,(self.name,'overlapping boxes')
        self.boxes.append((x,y,w,h))

    def save(self):
        self.im.save(OUT/(self.name+'.png'),dpi=(600,600))
        (OUT/(self.name+'.svg')).write_text('\n'.join(self.svg+['</svg>']),encoding='utf-8')
        return self.im

def overview():
    f=Figure('01-overall-workflow',1200,1210,'总体流程与任务衔接')
    f.line([(600,220),(600,305)])
    f.line([(600,425),(600,520)])
    f.line([(600,640),(600,780)])
    f.line([(600,925),(600,1020)])
    f.line([(320,160),(75,160),(75,852),(320,852)])
    f.line([(320,580),(225,580),(225,365),(320,365)],BLUE)
    f.line([(880,852),(905,852),(905,1080),(940,1080)])
    f.line([(1170,1080),(1185,1080),(1185,580),(880,580)],'#9A8358',True)
    f.box(320,100,560,120,'工程输入',['性能需求、接口说明与机理知识'])
    f.box(320,305,560,120,'任务一：生成工况并搜索失效',['根据需求与历史反馈选择下一工况'],'llm')
    f.box(320,520,560,120,'Typhoon 电机控制闭环测试',['执行测试并采集波形与实际事件'],'data')
    f.box(320,780,560,145,'任务二：数据分析与故障诊断',['分析动态行为、检测异常','识别故障并分析原因'],'llm')
    f.box(320,1020,560,150,'分析与诊断结果',['动态特征、异常与故障类别','候选原因及支持与冲突证据'],'data')
    f.box(940,1020,230,120,'复验建议',kind='future')
    f.text(600,472,['测试提案'],25,backing=True)
    f.text(600,710,['波形、工况与实际事件'],26,backing=True)
    f.text(225,475,['性能指标与判定结果','响应特征'],24,color=BLUE,backing=True)
    f.text(123,705,['机理知识','与接口说明'],24,backing=True)
    f.text(1040,710,['后续扩展','执行复验'],25,color='#8B724C',backing=True)
    return f.save()

def search():
    f=Figure('02-test-search-feedback',1000,1110,'任务一：测试生成与反馈搜索')
    f.line([(595,245),(595,330)])
    f.line([(595,470),(595,565)])
    f.line([(595,715),(595,815)])
    f.line([(270,900),(100,900),(100,175),(270,175)],BLUE)
    f.box(270,105,650,140,'测试决策输入',['性能要求、允许操作与参数范围','变量含义、机理知识及历史测试结果'])
    f.box(270,330,650,140,'LLM 测试决策',['提出测试假设与预期响应','选择初始工况或下一轮候选'],'llm')
    f.box(270,565,650,150,'提案校验与测试执行',['工具校验参数、时序与评价窗口','Typhoon 执行测试并采集数据'],'data')
    f.box(270,815,650,170,'工具评分与响应分析',['计算性能指标及其与限值的差值','提取恢复、振荡及电流响应特征'],'data')
    f.text(595,518,['测试提案'],26,backing=True)
    f.text(595,765,['波形与实际事件'],26,backing=True)
    f.text(115,530,['将本轮结果','加入测试历史'],25,color=BLUE,backing=True)
    f.text(500,1055,['以真实反馈调整下一轮测试工况'],26,color=GRAY)
    return f.save()

def diagnosis():
    f=Figure('03-analysis-and-diagnosis',1400,1600,'任务二：动态分析、异常检测与故障诊断')
    f.line([(700,265),(700,340)])
    f.line([(430,425),(370,425)])
    f.line([(700,510),(700,595)])
    f.line([(970,665),(1030,665)])
    f.line([(700,735),(700,890)])
    f.line([(1195,755),(930,755),(930,890)],BLUE,True)
    f.line([(370,985),(430,985)])
    f.line([(970,945),(1005,945),(1005,850),(1195,850),(1195,890)],BLUE)
    f.line([(1195,1080),(1195,1190),(900,1190),(900,1080)],GREEN)
    f.line([(700,1080),(700,1320)])
    f.box(430,90,540,175,'输入：多通道波形',['机械速度与给定、三相电流','电磁转矩与负载转矩','工况、实际事件及采样时间'],size=26)
    f.box(430,340,540,170,'数值分析',['提取动态特征','计算相对同工况正常参照的偏差','计算可用物理残差'],'data',25)
    f.box(40,340,330,170,'行为分析结果',['恢复与振荡特征','跨工况规律'],'data',26)
    f.box(430,595,540,140,'异常检测',['定位异常区间与涉及通道','计算异常分数'],'data',26)
    f.box(1030,595,330,160,'专用故障分类',['预测类别或候选类别','作为对照或辅助'],size=25)
    f.box(40,890,330,190,'工程知识',['控制关系与故障机制','已核验案例','适用条件与资料来源'],size=25)
    f.box(430,890,540,190,'LLM 诊断决策',['提出原因假设与响应预测','选择能区分原因的分析工具','根据检验结果修订判断'],'llm',26)
    f.box(1030,890,330,190,'波形分析工具',['查询已采集的数据','计算特征、频谱','或物理残差'],'data',26)
    f.box(430,1320,540,205,'诊断结果',['故障类别、候选原因','支持与冲突证据','缺失信息及复验建议'],'data',28)
    f.text(700,552,['动态特征、正常参照对比结果','与物理残差'],23,backing=True)
    f.text(700,808,['异常区间与特征摘要','工况、单位及正常参照偏差'],25,backing=True)
    f.text(1125,775,['可选：预测类别'],24,color=BLUE,backing=True)
    f.text(1210,845,['分析请求：通道','窗口与计算内容'],24,color=BLUE,backing=True)
    f.text(1110,1140,['实际数值与预测比较','适用条件及数据来源'],25,color=GREEN,backing=True)
    f.text(700,1240,['汇总诊断结论与证据'],25,backing=True)
    f.text(700,1570,['实线：主要处理与数据流    虚线：可选辅助输入'],23,color=GRAY)
    return f.save()

if __name__=='__main__':
    imgs=[overview(),search(),diagnosis()]
    thumbs=[]
    for im in imgs:
        t=im.copy(); t.thumbnail((560,760),Image.Resampling.LANCZOS); thumbs.append(t)
    sheet=Image.new('RGB',(1740,810),'#E9EDF1')
    for i,t in enumerate(thumbs): sheet.paste(t,(10+i*580+(560-t.width)//2,20))
    sheet.save(OUT/'preview.png')
    source=OUT.parent/'discussion-brief.md'
    meta={'source':'../discussion-brief.md','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'date':'2026-11-13','raster_scale':S,'dpi':600,'figures':[]}
    for stem,im in zip(('01-overall-workflow','02-test-search-feedback','03-analysis-and-diagnosis'),imgs):
        meta['figures'].append({'name':stem,'pixels':list(im.size)})
    (OUT/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'README.md').write_text('''# 讨论稿流程图：Word 插图

来源：2026-11-13 当前 discussion-brief.md 的三张流程图及相邻正文。

1. 01-overall-workflow：总体流程与任务衔接。
2. 02-test-search-feedback：任务一的测试生成与真实反馈循环。
3. 03-analysis-and-diagnosis：任务二的数据分析、故障识别及工具辅助诊断。

术语与正文一致：反馈包括性能指标、判定结果及响应特征；评分计算指标与限值的差值，恢复时间示例使用正文定义的余量。图中的“闭环”专指电机控制闭环。

PNG 为白底、600 dpi，适合直接插入 Word。建议插入后锁定纵横比，宽度设置为 15—16 cm；第三张建议独占一页。SVG 为可缩放矢量源图，使用 Microsoft YaHei 字体，需在有相应字体的系统中查看或插入。

文字按语义显式分行，并按实际字体测量宽度；框与连线均手动定位。实线表示当前主要数据/处理流程；图一虚线表示后续执行复验，图三虚线表示可选分类器辅助输入。图二将相邻正文的工程知识与反馈特征展开为输入说明。其余措辞为适应图示做了等义简化。

build_figures.py 可重新生成所有图片，manifest.json 记录来源文件摘要及图片尺寸。来源按脚本所在目录相对定位，输出保存在本 figures 目录，不生成压缩包。

在项目根目录运行：

```powershell
& 'D:\\Typhoon\\Typhoon HIL Control Center 2026.3\\python3_portable\\python.exe' -B -X utf8 'docs/research/2026-11-11-hil-ai-selection/figures/build_figures.py'
```

图片采用手动排版，脚本不会自动读取并转换 Mermaid。后续正文或流程变化时，需同步更新图中文字与布局，再重新生成图片。
''',encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))
