"""Reports use only saved motor records, without importing Typhoon."""
import html
import json
import numpy as np
from .analysis import load_waveforms
from .reporting import _json, _write, _table, _md_table, _image, _fmt, _metadata
from .motor_analysis import COLUMNS


def write_motor_report(path, manifest):
    c = _json(path/'config.json');m = _json(path/'metrics.json')
    status = manifest.get('status', 'error'); hp=[];mp=[];outputs=[]
    if manifest.get('error'):
        text = manifest['error'];hp.append('<h2>执行异常</h2><pre>'+html.escape(text)+'</pre>');mp.append('## 执行异常\n\n'+text)
    if m:
        speed=m['speed'];a=c['acceptance']
        rows=[('目标转速 (rpm)',_fmt(speed['reference_rpm'])),('窗口平均转速 (rpm)',_fmt(speed['mean_rpm'])),
              ('最大绝对误差 (rpm)',_fmt(speed['max_absolute_error_rpm'])),('最大相对误差',_fmt(speed['max_relative_error'],True)),
              ('阈值',_fmt(a['max_relative_speed_error'],True)),('超限采样点',speed['exceeded_sample_count']),
              ('最差误差时刻 (s)',_fmt(speed['worst_error_time_s']))]
        hp.append('<h2>转速判定</h2>'+_table(('指标','值'),rows));mp.append('## 转速判定\n\n'+_md_table(('指标','值'),rows))
        if (path/'waveforms.csv').exists():
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            d=load_waveforms(path/'waveforms.csv',COLUMNS);t=np.asarray(d['t_simulation_s'])
            with plt.rc_context({'font.family':'DejaVu Sans','axes.grid':True,'grid.alpha':.2,'path.simplify':False}):
                fig,axes=plt.subplots(3,1,sharex=True,figsize=(10,8),layout='constrained')
                axes[0].plot(t,d['Speed_rpm'],color='#0072B2',label='Measured speed',linewidth=1)
                axes[0].plot(t,d['SpeedReference_rpm'],color='#D55E00',linestyle='--',label='Applied reference')
                axes[0].set_ylabel('Speed (rpm)')
                axes[1].plot(t,d['ElectromagneticTorque_Nm'],color='#0072B2',label='Electromagnetic torque',linewidth=1)
                axes[1].plot(t,d['LoadCommand_Nm'],color='#D55E00',linestyle='--',label='Applied torque load')
                axes[1].set_ylabel('Torque (N m)')
                error=np.abs(np.asarray(d['Speed_rpm'])-speed['reference_rpm'])/abs(speed['reference_rpm'])*100
                axes[2].plot(t,error,color='#0072B2',label='Absolute relative speed error',linewidth=1)
                axes[2].axhline(a['max_relative_speed_error']*100,color='#D55E00',linestyle='--',label='Criterion')
                axes[2].set_ylabel('Error (%)');axes[2].set_xlabel('Simulation time (s)')
                for ax in axes:
                    ax.axvspan(a['window_start_s'],a['window_end_s'],color='#009E73',alpha=.1,label='Evaluation window')
                    ax.legend(loc='upper right',fontsize=8)
                fig.suptitle('Induction motor startup tracking - full raw capture')
                plot=path/'waveforms.png';fig.savefig(plot,dpi=150,facecolor='white',metadata={'Description':'Full raw capture; no filtering or interpolation. Shaded evaluation window.'});plt.close(fig)
            caption='完整启动原始波形；阴影为实际仿真时间评价窗口。速度参考与负载指令均直接观测。'
            hp.append('<h2>原始波形</h2>'+_image(plot,caption));mp.append('## 原始波形\n\n![电机原始波形](waveforms.png)\n\n'+caption);outputs.append(plot)
        for title,value in (('采集与判据',m['analysis']),('实际控制证据',{'API回读':manifest.get('actual_scada_settings'),'波形':m['control_evidence']}),('超限采样时刻 (s)',speed['exceeded_times_s']),('实际配置',c)):
            text=json.dumps(value,ensure_ascii=False,indent=2);hp.append('<h2>'+title+'</h2><pre>'+html.escape(text)+'</pre>');mp.append('## '+title+'\n\n```json\n'+text+'\n```')
    hp.append('<h2>来源</h2>'+_table(('字段','记录'),_metadata(manifest)));mp.append('## 来源\n\n'+_md_table(('字段','记录'),_metadata(manifest)))
    hp.append('<p><a href="waveforms.csv">原始 CSV</a> · <a href="metrics.json">指标与全部超限时刻</a> · <a href="manifest.json">清单</a></p>')
    outputs.extend(_write(path,'感应电机闭环转速跟踪',status,hp,mp,scope='Virtual HIL 项目教学工况：独立启动；判据参考安装附带官方测试并调整采样与时间基准。电磁转矩与施加负载指令分别记录。实体设备与真实电机性能尚未验证。'))
    return outputs
