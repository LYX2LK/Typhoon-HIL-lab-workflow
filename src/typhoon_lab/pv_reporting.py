"""Saved-data-only reports for generic PV HzWatt experiments."""
import json,html
import numpy as np
from .analysis import load_waveforms
from .reporting import _image,_write,_table,_md_table,_metadata
from .adapters.pv import PVAdapter

def write_pv_report(path,manifest):
    status=manifest.get('status','error');hp=[];mp=[]
    outputs=[]
    if manifest.get('error'):
        hp.append('<p>'+html.escape(manifest['error'])+'</p>');mp.append(manifest['error'])
    if (path/'metrics.json').exists():
        metrics=json.loads((path/'metrics.json').read_text(encoding='utf-8'))
        config=json.loads((path/'config.json').read_text(encoding='utf-8'))
        p=metrics['power'];c=metrics['control_evidence'];limit=config['acceptance']['max_relative_power_error']
        rows=[('电网频率目标 / Hz',c['frequency_target_hz']),('频率平均 / Hz',c['frequency_mean_hz']),
              ('参考有功 / kW',p['expected_kw']),('有功平均 / kW',p['mean_kw']),('限额参考平均 / kW',c['reference_mean_kw']),('限额参考目标 / kW',c['reference_expected_kw']),
              ('最大相对误差 / %',p['max_relative_error']*100),('限值 / %',limit*100),('越限点数',p['exceeded_sample_count'])]
        hp.append(_table(('项目','值'),rows));mp.append(_md_table(('项目','值'),rows))
        data=load_waveforms(path/'waveforms.csv',('t_relative_s','t_simulation_s',*PVAdapter.columns))
        t=np.asarray(data['t_simulation_s'])
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        with plt.rc_context({'axes.grid':True,'grid.alpha':.2,'path.simplify':False}):
            fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True,layout='constrained')
            axes[0].plot(t,data['ActivePower_kW'],label='Measured active power',color='#0072B2')
            axes[0].plot(t,data['PowerReference_kW'],label='Curtailment reference before HzWatt',color='#A34400',ls='--')
            axes[0].axhspan(p['expected_kw']*(1-limit),p['expected_kw']*(1+limit),alpha=.12,color='#009E73',label='Declared tolerance')
            axes[0].axhline(p['expected_kw'],color='#333333',ls=':',label='Independent tabulated reference')
            axes[0].set_ylabel('Active power (kW)')
            axes[1].plot(t,data['Frequency_Hz'],color='#0072B2',label='Measured frequency')
            axes[1].axhline(c['frequency_target_hz'],color='#A34400',ls='--',label='Requested frequency')
            axes[1].set_ylabel('Frequency (Hz)')
            axes[2].plot(t,data['Enable'],label='Enable feedback',color='#0072B2')
            axes[2].plot(t,data['AlarmCode'],label='Alarm code',ls='--',color='#A34400')
            axes[2].set(ylabel='State / code',xlabel='Simulation time (s)')
            for ax in axes:ax.legend(loc='best',fontsize=8);ax.ticklabel_format(axis='y',style='plain',useOffset=False)
            fig.suptitle('Generic PV plant - HzWatt steady-state point')
            fig.savefig(path/'waveforms.png',dpi=150,facecolor='white');plt.close(fig)
        outputs.append(path/'waveforms.png')
        caption='全部稳态采样；独立启动后等待规定时间。参考来自安装附带的官方测试表，图中同时显示实际频率、功率参考和状态。'
        hp.append(_image(path/'waveforms.png',caption));mp.append('![稳态波形](waveforms.png)\n\n'+caption)
        for title,value in [('检查项',metrics['checks']),('方法',metrics['analysis']),('配置',config)]:
            text=json.dumps(value,ensure_ascii=False,indent=2)
            hp.append('<h2>'+title+'</h2><pre>'+html.escape(text)+'</pre>')
            mp.append('## '+title+'\n\n'+chr(96)*3+'json\n'+text+'\n'+chr(96)*3)
    hp.append('<h2>运行来源</h2>'+_table(('字段','记录'),_metadata(manifest)))
    mp.append('## 运行来源\n\n'+_md_table(('字段','记录'),_metadata(manifest)))
    hp.append('<p><a href="waveforms.csv">原始 CSV</a> · <a href="metrics.json">指标</a> · <a href="manifest.json">清单</a></p>')
    mp.append('[原始 CSV](waveforms.csv) · [指标](metrics.json) · [清单](manifest.json)')
    hp.append('<p>软件教学实验；记录一致性见 verification.json，实验性能状态见 metrics.json。</p>')
    mp.append('软件教学实验；记录一致性见 verification.json，实验性能状态见 metrics.json。')
    outputs.extend(_write(path,'光伏电站 HzWatt 稳态实验',status,hp,mp,scope='Generic PV plant 的 Virtual HIL 稳态教学实验；结论适用于声明频率点和固定判据，不代表实体控制器或微电网系统验收。'))
    return outputs
