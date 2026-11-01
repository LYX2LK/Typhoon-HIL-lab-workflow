"""Render model-authored semantic blocks using verified data and fixed components."""
import base64
import html
from pathlib import Path
import re

from .analysis import load_waveforms
from .boost_agent_tools import COLUMNS
from .utils import write_json,sha256,now
from .boost_ai import read

STYLE='''.assessment{border:1px solid #cedfe1;background:#f8fbfb;border-radius:14px;padding:18px 22px;margin:24px 0}.assessment-decision{color:#216b77;margin-top:0}.claim{border-top:1px solid #e0e8ea;padding:14px 0}.claim p{margin:6px 0}.claim summary{cursor:pointer;color:#48646e}body{font:17px/1.8 "Microsoft YaHei","Segoe UI",sans-serif;color:#1d2935;background:#fff;margin:0}main{max-width:980px;margin:40px auto;padding:0 28px}h1{font-size:32px}h2{font-size:25px;line-height:1.4;margin:28px 0 14px}h3{font-size:21px;margin:24px 0 10px}p{margin:12px 0}a{color:#216b77}img{max-width:100%;height:auto}figure{margin:24px 0}figcaption,.muted,.evidence{font-size:16px;color:#65727b;line-height:1.6}.table-wrap{overflow:auto;margin:20px 0}table{border-collapse:collapse;min-width:720px;width:100%;font-size:16px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #e0e6e9;white-space:nowrap}th{background:#f4f7f8;font-weight:600}.callout{border-left:3px solid #216b77;background:#f4f8f8;padding:12px 20px;margin:22px 0}.callout.warning{border-color:#a86c30;background:#fcf8f1}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f7;padding:16px;font:16px/1.6 Consolas,monospace}code{font:16px Consolas,monospace;background:#f2f4f5;padding:2px 4px}article{margin:28px 0 40px}.user-message{margin-left:auto;max-width:85%;background:#f1f4f5;border-radius:18px;padding:12px 20px;white-space:pre-wrap}.tool-line{color:#6b7780;font-size:16px;margin:10px 0}.speaker{font-size:16px;color:#718087;margin-bottom:10px}.question{border:1px solid #d7e0e3;border-radius:14px;padding:20px;margin:26px 0}.option{display:block;border:1px solid #d7e0e3;border-radius:10px;padding:14px;margin:10px 0}.option strong{font-size:18px}.option p{font-size:16px;color:#5a6973;margin:5px 0}.error{border-left:3px solid #b25126;padding:12px 18px;background:#fff5ef}'''


def inline(text):
    text=html.escape(text)
    text=re.sub(r'`([^`\n]+)`',r'<code>\1</code>',text)
    text=re.sub(r'\*\*([^*\n]+)\*\*',r'<strong>\1</strong>',text)
    def link(m):
        url=html.unescape(m.group(2))
        if not re.match(r'^https?://',url,re.I):return m.group(0)
        return '<a target="_blank" rel="noopener" href="'+html.escape(url,quote=True)+'">'+m.group(1)+'</a>'
    return re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)',link,text)


def markdown(text):
    out=[];listing=None;code=False;buffer=[]
    for line in text.splitlines():
        if line.strip().startswith('```'):
            if listing:out.append('</'+listing+'>');listing=None
            if code:out.append('<pre>'+html.escape('\n'.join(buffer))+'</pre>');buffer=[]
            code=not code;continue
        if code:buffer.append(line);continue
        item=re.match(r'^\s*(?:[-*]|(\d+)\.)\s+(.+)$',line)
        kind='ol' if item and item.group(1) else 'ul'
        if item:
            if listing!=kind:
                if listing:out.append('</'+listing+'>')
                out.append('<'+kind+'>');listing=kind
            out.append('<li>'+inline(item.group(2))+'</li>');continue
        if listing:out.append('</'+listing+'>');listing=None
        head=re.match(r'^#{1,4}\s+(.+)',line)
        if head:out.append('<h3>'+inline(head.group(1))+'</h3>')
        elif line.strip():out.append('<p>'+inline(line)+'</p>')
    if listing:out.append('</'+listing+'>')
    if code:out.append('<pre>'+html.escape('\n'.join(buffer))+'</pre>')
    return ''.join(out)


def plot(path,view,run_ids,evidence,runs,root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=['#0072B2','#D55E00','#009E73','#CC79A7','#666666','#E69F00','#56B4E9','#000000']
    styles=['-','--','-.',':']
    with plt.rc_context({'font.size':11,'axes.spines.top':False,'axes.spines.right':False}):
        fig,ax=plt.subplots(figsize=(9,4.7),layout='constrained')
        if view!='full':ax.axhspan(49,51,color='#777777',alpha=.08)
        for j,rid in enumerate(run_ids):
            e=evidence[rid];d=load_waveforms(Path(root)/runs[rid]['path']/'waveforms.csv',columns=COLUMNS)
            t,y=d['t_simulation_s'],d['Vout_V'];anchor=e['anchor_s']
            if view=='full':xx=t;yy=y
            else:
                left,right=(-.1,0) if view=='pre_event' else (-.1,.9)
                selected=[i for i,x in enumerate(t) if left-1e-9<=x-anchor<right-1e-9]
                xx=[t[i]-anchor for i in selected];yy=[y[i] for i in selected]
            suffix='event' if e['anchor_kind']=='observed_event' else 'baseline reference'
            ax.plot(xx,yy,color=colors[j],linestyle=styles[j%4],linewidth=1.6,label=f'{rid}: {suffix} {e["nominal_anchor_s"]:g} s')
        ax.axhline(50,color='#333333',linewidth=.7)
        if view=='aligned':ax.axvline(0,color='#555555',linewidth=.7)
        ax.set_xlabel('Simulation time (s)' if view=='full' else 'Time relative to event / baseline reference (s)')
        ax.set_ylabel('Output voltage (V)');ax.grid(alpha=.2);ax.legend(loc='best',fontsize=9)
        fig.savefig(path,dpi=150);plt.close(fig)


def prepare_assets(turn_dir,answer,evidence,runs,root):
    p=Path(turn_dir);assets={}
    for i,block in enumerate(answer['blocks']):
        if block['type']=='waveform':
            name=f'waveform-{i+1:02d}.png';plot(p/name,block['view'],block['run_ids'],evidence,runs,root)
            assets[str(i)]=name
    return assets


def metrics_table(evidence,run_ids):
    headings=['记录','施扰 / 参考时刻','比较窗峰偏差','恢复 / s','最终误差','施扰前趋势 / V/s','记录 / 原性能']
    rows=[]
    for rid in run_ids:
        e=evidence[rid];a=e['aligned_response'];m=e['metrics'];recovery=a['recovery_s']
        rows.append([rid,f'{e["nominal_anchor_s"]:g} s'+('（无扰动参考）' if e['anchor_kind']!='observed_event' else ''),
            f'{100*a["peak_deviation_relative"]:.4f}%',f'{recovery:.4f}' if recovery is not None else '未恢复',
            f'{100*m["signals"]["Vout_V"]["relative_steady_error"]:.5f}%',f'{e["pre_event_trend"]["slope_v_per_s"]:.5f}',
            e['record_status']+' / '+e['experiment_status']])
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in headings)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div><p class="muted">比较窗为锚点后[0,0.9) s，各9,000点，相对50 V计算；无扰动行描述背景变化，不作为输入扰动合格判定。原判据：峰偏差≤10%，恢复≤0.5 s，最终误差≤2%。原性能按完整记录评价。</p>'


def render_assessment(value, narrative=''):
    decisions={'continue':'下一步继续验证','ready_to_conclude':'可以总结本阶段结果','needs_capability':'下一步需要补充观测或实验能力','complete':'本阶段结果'}
    statuses={'established':'已有证据支持这一判断','supported':'目前的证据支持这一解释','weakened':'这一解释的支持减弱了','refuted':'在本次验证范围内可以排除','unresolved':'还需要进一步验证'}
    goal={'characterize_response':'确认异常并评估启动残余解释','identify_mechanism':'定位具体机理'}.get(value['goal'],value['goal'])
    out=['<section class="assessment">']
    seen=[]
    def prose(text):
        if not text or text in narrative or text in seen:return ''
        seen.append(text)
        return markdown(text)
    if not narrative:
        out.append('<p class="assessment-decision"><strong>'+decisions[value['decision']]+'</strong></p>'+prose(value['summary']))
    out.append('<p class="muted">本轮问题：'+html.escape(goal)+'</p><ul>')
    for c in value['claims']:
        heading='数据中可以确认' if c['kind']=='observation' else statuses[c['status']]
        out.append('<li class="claim"><strong>'+heading+'</strong>'+prose(c['claim'])+prose(c['scope'])+prose(c['reason'])+
                   prose(c.get('criterion',''))+prose(c.get('test_basis',''))+'<p class="evidence">证据：'+html.escape(' · '.join(c['evidence']))+'</p></li>')
    out.append('</ul>'+prose(value['next_requirement'])+'</section>');return ''.join(out)


def render_answer(answer,evidence,assets,url):
    narrative='\n\n'.join(b['text'] for b in answer['blocks'] if b['type']=='markdown')
    out=[]
    if 'assessment' in answer and not narrative:out.append(render_assessment(answer['assessment']))
    seen=set()
    for i,b in enumerate(answer['blocks']):
        title='<h2>'+inline(b['title'])+'</h2>'
        if b['type']=='markdown':
            if b['text'] in seen:continue
            seen.add(b['text']);out.append(markdown(b['text']))
        elif b['type']=='callout':
            if b['text'] in narrative.split('\n\n') or b['text'] in seen:continue
            seen.add(b['text'])
            # Never interpolate model-supplied CSS; missing/unknown hints use the default.
            tone='warning' if b.get('tone')=='warning' else 'info'
            out.append('<aside class="callout '+tone+'"><h3>'+html.escape(b['title'])+'</h3>'+markdown(b['text'])+'</aside>')
        elif b['type']=='metrics':out.append(title+metrics_table(evidence,b['run_ids']))
        elif b['type']=='waveform':
            scopes={'full':'完整启动与施扰过程','aligned':'实际事件 / 明确基准参考对齐，−0.1至0.9 s','pre_event':'施扰前 / 基准参考前0.1 s'}
            out.append(title+'<figure><img loading="lazy" alt="'+html.escape(b['title'],quote=True)+'" src="'+html.escape(url(assets[str(i)]),quote=True)+'"><figcaption>'+html.escape(', '.join(b['run_ids'])+' · '+scopes[b['view']]+' · 原始10 kHz采样，未平滑或重采样；原始数据与工况见证据。')+'</figcaption></figure>')
        if b.get('evidence') and 'assessment' not in answer:out.append('<p class="evidence">证据：'+html.escape(' · '.join(b['evidence']))+'</p>')
    if 'assessment' in answer and narrative:
        out.append('<details class="evidence-details"><summary>查看判断依据与适用范围</summary>'+render_assessment(answer['assessment'],narrative)+'</details>')
    return ''.join(out)


def message_html(root, message):
    """Refresh presentation from saved artifacts without rewriting a model answer."""
    p=Path(root)/'turns'/message['turn_id']
    return render_answer(message['answer'],read(p/'evidence.json'),read(p/'render_assets.json'),
                         lambda name:'/files/'+(p/name).relative_to(root).as_posix())


def export_session(root,state):
    root=Path(root);body=['<h1>Typhoon 实验分析与验证</h1><p>面向控制器测试，验证从波形采集、大模型分析到对照复验的协同流程，为后续水泵控制器测试接入提供基础。</p><p><strong>当前案例：Boost 输入跌落下的输出电压响应。</strong>检验输出偏差是否超限，结合证据评估启动残余解释，并选择后续验证。</p><p class="muted">Virtual HIL · PC软件证据 · 本报告由会话真实工具结果与模型回答生成。实验结论与流程完成范围分别说明；建议的实验须另行确认执行。</p>']
    for m in state['messages']:
        if m['role']=='user':body.append('<article class="user-message">'+html.escape(m['text'])+'</article>')
        elif m['role']=='tool':body.append('<p class="tool-line">'+html.escape(m['text']+' · '+m.get('status',''))+'</p>')
        elif m['role']=='draft':body.append('<article><p class="muted">分析正文已保存；结论状态与实验选项尚未校验，当前不可执行实验。</p>'+m['html']+'</article>')
        elif m['role']=='error':body.append('<p class="error">'+html.escape(m['text'])+'</p>')
        elif m['role']=='assistant':
            value=message_html(root,m)
            for key,label in (('characterize_response','确认异常并评估启动残余解释'),('identify_mechanism','定位具体机理')):
                value=value.replace('目标：'+key,'目标：'+label,1)
            def embed(match):
                rel=match.group(1);p=(root/rel).resolve()
                if not p.is_relative_to(root.resolve()):raise ValueError('export image leaves session')
                return 'src="data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode('ascii')+'"'
            value=re.sub(r'src="/files/([^"]+)"',embed,value)
            body.append('<article><p class="speaker">Agent · '+html.escape(m['at'])+'</p>'+value)
            question=m['answer'].get('question')
            if question:
                body.append('<section class="question"><h3>'+html.escape(question['title'] if len(question['title'])<=60 else '接下来怎么做？')+'</h3>')
                for option in question['options']:
                    description='<p>'+html.escape(option['description'])+'</p>'
                    if len(option['description'])>120:description='<details><summary>查看原建议说明</summary>'+description+'</details>'
                    body.append('<div class="option"><strong>'+html.escape(option['label'])+(' · 推荐' if option['recommended'] else '')+'</strong>'+description+'</div>')
                body.append('</section>')
            body.append('</article>')
    body.append('<h2>实验与原始证据</h2><ul>')
    for rid,run in state['runs'].items():
        base=html.escape(run['path'],quote=True)
        body.append('<li>'+html.escape(rid+' · '+run['record_status']+' / '+run['experiment_status'])+' · <a href="'+base+'/report.html">原实验报告</a> · <a href="'+base+'/waveforms.csv">原始CSV</a> · <a href="'+base+'/manifest.json">清单</a></li>')
    body.append('</ul><p class="muted">模型回答中的候选机理需进一步验证；当前未采集实际占空比、PI积分或限幅状态。不作为独立故障识别准确率或实体HIL验收。</p>')
    output=root/'report.html'
    output.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Typhoon Agent 分析报告</title><style>'+STYLE+'</style><main>'+''.join(body)+'</main></html>',encoding='utf-8')
    write_json(root/'export_manifest.json',{'created_at':now(),'report_sha256':sha256(output),'inline_images':True,'runs':list(state['runs']),'model_turns':len(state['turns'])})
