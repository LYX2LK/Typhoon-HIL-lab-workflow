"""Reports use only saved motor records, without importing Typhoon."""
import html
import json
import numpy as np
from .analysis import load_waveforms
from .reporting import _json, _write, _table, _md_table, _image, _fmt, _metadata
from .motor_analysis import COLUMNS


def write_motor_report(path, manifest):
    c = _json(path/'config.json');m = _json(path/'metrics.json')
    if c.get('events'):
        return write_motor_step_report(path, manifest, c, m)
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


def write_motor_step_report(path, manifest, config, metrics):
    status = manifest.get('status', 'error')
    hp, mp, outputs = [], [], []
    if manifest.get('error'):
        message = manifest['error']
        hp.append('<h2>执行异常</h2><pre>'+html.escape(message)+'</pre>')
        mp.append('## 执行异常\n\n'+message)
    if metrics:
        event = metrics['events'][0]
        speed = metrics['speed']
        rows = [
            ('参考转速变化 (rpm)', f"{speed['initial_reference_rpm']:g} → {speed['final_reference_rpm']:g}"),
            ('请求／实际生效时刻 (s)', f"{event['requested_at_s']:g} / {_fmt(event['observed_at_s'])}"),
            ('事件状态', event['status']),
            ('事件前最大相对误差', _fmt(speed['pre_event_max_relative_error'], True)),
            ('事件后最大相对误差', _fmt(speed['post_event_max_relative_error'], True)),
            ('±1% 带内调节时间 (s)', _fmt(speed['settling_time_s'])),
            ('沿阶跃方向超出量／阶跃幅值', _fmt(speed['directional_overshoot_fraction_of_step'], True)),
            ('事件后超限采样点', speed['post_event_exceeded_sample_count']),
        ]
        hp.append('<h2>转速阶跃结果</h2>'+_table(('指标', '值'), rows))
        mp.append('## 转速阶跃结果\n\n'+_md_table(('指标', '值'), rows))
        if (path/'waveforms.csv').exists():
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            d = load_waveforms(path/'waveforms.csv', COLUMNS)
            t = np.asarray(d['t_simulation_s'])
            y = np.asarray(d['Speed_rpm'])
            ref = np.asarray(d['SpeedReference_rpm'])
            torque = np.asarray(d['ElectromagneticTorque_Nm'])
            load = np.asarray(d['LoadCommand_Nm'])
            requested = event['requested_at_s']
            observed = event['observed_at_s']
            for detail, name in ((False, 'waveforms.png'), (True, 'response_detail.png')):
                with plt.rc_context({'font.family': 'DejaVu Sans', 'axes.grid': True, 'grid.alpha': .2,
                                     'path.simplify': False}):
                    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(10, 8), layout='constrained')
                    axes[0].plot(t, y, color='#0072B2', linewidth=1, label='Measured speed')
                    axes[0].plot(t, ref, color='#D55E00', linestyle='--', label='Applied reference')
                    axes[0].set_ylabel('Speed (rpm)')
                    axes[1].plot(t, torque, color='#0072B2', linewidth=1, label='Electromagnetic torque')
                    axes[1].plot(t, load, color='#D55E00', linestyle='--', label='Load command')
                    axes[1].set_ylabel('Torque (N m)')
                    active_error = np.full_like(y, np.nan, dtype=float)
                    np.divide(np.abs(y-ref)*100, np.abs(ref), out=active_error, where=np.abs(ref)>1e-9)
                    axes[2].plot(t, active_error, color='#0072B2', linewidth=1,
                                 label='Error from applied reference')
                    axes[2].axhline(config['acceptance']['max_relative_speed_error']*100,
                                    color='#D55E00', linestyle='--', label='Final tolerance')
                    axes[2].set_ylabel('Tracking error (%)')
                    axes[2].set_xlabel('Simulation time (s)')
                    for ax in axes:
                        ax.axvline(requested, color='#009E73', linestyle=':', label='Requested step')
                        if observed is not None:
                            ax.axvline(observed, color='#CC79A7', linestyle='-.', label='Observed step')
                        post = metrics['analysis']['post_event_window_s']
                        if post:
                            ax.axvspan(post[0], post[1], color='#009E73', alpha=.1, label='Final evaluation')
                        ax.legend(loc='upper right', fontsize=8)
                    if detail:
                        axes[0].set_xlim(max(0, requested-.5), min(config['capture']['duration_s'], requested+2.5))
                    fig.suptitle('Induction motor speed reference step - '+('response detail' if detail else 'full raw capture'))
                    target_path = path/name
                    fig.savefig(target_path, dpi=150, facecolor='white',
                                metadata={'Description': 'Unfiltered raw samples; requested and observed event times marked.'})
                    plt.close(fig)
                outputs.append(target_path)
            caption = '完整原始波形与阶跃局部视图；事件由实际参考探针核验，电磁转矩与负载指令分别显示。'
            hp.append('<h2>波形</h2>'+_image(path/'waveforms.png', caption)+_image(path/'response_detail.png', caption))
            mp.append('## 波形\n\n![完整原始波形](waveforms.png)\n\n![阶跃局部视图](response_detail.png)\n\n'+caption)
        for title, value in (('事件证据', event), ('检查项', metrics['checks']),
                             ('分析方法', metrics['analysis']), ('实际配置', config)):
            data = json.dumps(value, ensure_ascii=False, indent=2)
            hp.append('<h2>'+title+'</h2><pre>'+html.escape(data)+'</pre>')
            mp.append('## '+title+'\n\n```json\n'+data+'\n```')
    hp.append('<h2>来源</h2>'+_table(('字段', '记录'), _metadata(manifest)))
    mp.append('## 来源\n\n'+_md_table(('字段', '记录'), _metadata(manifest)))
    hp.append('<p><a href="waveforms.csv">原始 CSV</a> · <a href="events.json">事件记录</a> · <a href="metrics.json">指标</a> · <a href="manifest.json">清单</a></p>')
    outputs.extend(_write(path, '感应电机转速阶跃动态实验', status, hp, mp,
                          scope='Virtual HIL 项目教学工况。改速后 2 s 起的 ±1% 判据参考安装附带 Typhoon 电机测试；调节时间和超出量仅描述本次模型响应。IEC/GB/T 产品符合性、实体设备与真实电机性能未验证。'))
    return outputs
