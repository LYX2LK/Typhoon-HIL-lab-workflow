"""Low-voltage PMSM software rehearsal, derived from the installed SVPWM example."""
from copy import deepcopy
import html
import json
import math
from pathlib import Path

from .config import number

PERIOD = 50e-6
SCOPE = ('PMSM 软件预演：使用模型内部角度反馈与示例控制器，电机采用假设的等效星形参数。'
         '用于验证模型、事件与采集流程；样机固件、无感启动、Δ 绕组参数对应、单分流反馈和实体 I/O 待接入。')

# The installed example's MTPA block only accepts positive current commands.
# Preserve its optimum-id relation, rationalized to avoid subtractive cancellation,
# and give iq the requested torque sign for the zero-speed rehearsal.
SIGNED_MTPA = '''if (fabsf(is) > 1e-4f) {
    float delta = Lq - Ld;
    float root = sqrtf(psi_pm*psi_pm + 8.0f*delta*delta*is*is);
    id_ref = -2.0f*delta*is*is/(psi_pm + root);
    iq_ref = (is >= 0.0f ? 1.0f : -1.0f)*sqrtf(fmaxf(0.0f, is*is-id_ref*id_ref));
} else {
    id_ref = 0.0f;
    iq_ref = 0.0f;
}'''


class PMSMPreviewAdapter:
    model_id = 'pmsm_software_preview'
    schema_version = 1
    has_events = True
    capture_before_start = True
    sources = ('V_dc',)
    signals = ('w','Ia','Ib','Ic','LabTorque','LabReference','LabLoad')
    columns = ('MechanicalSpeed_rad_s','Ia_A','Ib_A','Ic_A','ElectromagneticTorque_Nm',
               'Reference_rad_s','Load_Nm')
    units = dict(zip(columns,('rad/s','A','A','A','Nm','rad/s','Nm')))
    changes = ['Low-voltage equivalent-star parameter hypothesis and internal angle feedback.',
               'Model Step sources for speed/load events with directly captured command probes.',
               'Disable inherited converter loss tables and turn-off delay.',
               'Rationalized signed MTPA current command for positive/negative torque rehearsal.']
    numeric_rules = {
        'parameters': {'dc_bus_v':(1,10),'phase_resistance_ohm':(.001,.1),
            'ld_h':(1e-6,.001),'lq_h':(1e-6,.001),'pm_flux_wb':(.0001,.02),
            'inertia_kgm2':(1e-6,.001),'pole_pairs':(1,20),
            'reference_speed_rpm':(100,3000),'load_torque_nm':(0,.1)},
        'capture': {'start_s':(0,0),'duration_s':(.1,2),'sample_rate_hz':(20000,200000),
                    'wall_timeout_s':(30,600)},
        'acceptance': {'settle_after_change_s':(.02,.3),'max_speed_error_rpm':(1,200),
            'max_phase_current_sum_a':(.0001,.1),'min_samples':(2000,100000),
            'min_window_samples':(10,10000)},
    }
    setting_stages = {'parameters':'model_copy_before_compile','capture':'capture_setup','acceptance':'analysis_only'}
    event_capabilities = {'max_per_run':3,'targets':{
        'reference_speed_rpm':{'value_minimum':0,'value_maximum':3000,'setting_stage':'model_copy_before_compile'},
        'load_torque_nm':{'value_minimum':0,'value_maximum':.1,'setting_stage':'model_copy_before_compile'}},
        'time_unit':'s','time_quantum_s':PERIOD,'time_minimum_s':.02,'time_maximum_ref':'capture.duration_s'}
    conditional_constraints = ['software_preview_scope_and_assumptions_required','validated_salient_hypothesis_lq_gt_ld',
        'events_sorted_unique_and_on_control_grid','complete_settled_window_after_each_event','full_capture_at_most_100000_samples']

    def validate(self, raw, sweep=False):
        if sweep: raise ValueError('PMSM preview uses run or run-case, not RLC sweep')
        keys={'schema_version','model','backend','scope','assumptions','parameters','events','capture','acceptance'}
        if not isinstance(raw,dict) or set(raw)!=keys: raise ValueError(f'preview keys must be exactly {sorted(keys)}')
        c=deepcopy(raw)
        if type(c['schema_version']) is not int or c['schema_version']!=1 or c['model']!=self.model_id or c['backend']!='virtual_hil':
            raise ValueError('preview requires schema_version 1, registered model and virtual_hil')
        if c['scope']!='software_preview' or not isinstance(c['assumptions'],dict):
            raise ValueError('software_preview scope and explicit assumptions required')
        assumptions=c['assumptions']
        if set(assumptions)!={'winding_connection','angle_feedback','parameter_basis','sample_parameter_confirmation'} or \
                assumptions['winding_connection']!='star_equivalent_hypothesis' or \
                assumptions['angle_feedback']!='ideal_model_angle' or assumptions['sample_parameter_confirmation'] is not False or \
                not isinstance(assumptions['parameter_basis'],str) or not assumptions['parameter_basis'].strip():
            raise ValueError('preview assumptions must retain the explicit unconfirmed sample boundary')
        for group,rules in self.numeric_rules.items():
            if not isinstance(c[group],dict) or set(c[group])!=set(rules): raise ValueError(f'invalid {group} fields')
            for name,bounds in rules.items(): c[group][name]=number(c[group][name],f'{group}.{name}',*bounds)
        for group,key in [('parameters','pole_pairs'),('acceptance','min_samples'),('acceptance','min_window_samples')]:
            if not c[group][key].is_integer(): raise ValueError(f'{key} must be integer')
            c[group][key]=int(c[group][key])
        if c['parameters']['lq_h']<=c['parameters']['ld_h']:
            raise ValueError('current preview scope requires Lq > Ld; equal-inductance cases are not validated')
        if not isinstance(c['events'],list) or not 1<=len(c['events'])<=3:
            raise ValueError('preview requires 1..3 events')
        previous=0
        last_values={k:c['parameters'][k] for k in self.event_capabilities['targets']}
        for event in c['events']:
            if not isinstance(event,dict) or set(event)!={'at_s','target','value'} or event['target'] not in last_values:
                raise ValueError('invalid PMSM event')
            event['at_s']=number(event['at_s'],'at_s',.02,c['capture']['duration_s'])
            if event['at_s']<=previous or abs(event['at_s']/PERIOD-round(event['at_s']/PERIOD))>1e-7:
                raise ValueError('event times must be strictly increasing and on the control grid')
            previous=event['at_s']; spec=self.event_capabilities['targets'][event['target']]
            event['value']=number(event['value'],'event.value',spec['value_minimum'],spec['value_maximum'])
            if event['value']==last_values[event['target']]: raise ValueError('event must change its target')
            last_values[event['target']]=event['value']
        boundaries=[0]+[e['at_s'] for e in c['events']]+[c['capture']['duration_s']]
        for a,b in zip(boundaries,boundaries[1:]):
            available=b-a-c['acceptance']['settle_after_change_s']
            if available*c['capture']['sample_rate_hz']<c['acceptance']['min_window_samples']:
                raise ValueError('each segment must contain a complete settled evaluation window')
        n=c['capture']['duration_s']*c['capture']['sample_rate_hz']
        if not c['acceptance']['min_samples']<=n<=100000: raise ValueError('capture sample count outside bounds')
        return c

    def inspect_parameters(self,api):
        m=api.get_property_values(api.get_item('pmsm1'))
        return {'machine':{k:m[k] for k in ('model_type','Rs','Ld','Lq','Psi_pm','pms','star_delta','Jm','load_src','ext_mdl_load_type')},
                'scope':SCOPE}

    def prepare(self,api,c):
        return self.prepare_model(api,c['parameters'],c['events'],c['assumptions'])

    def prepare_model(self,api,p,events,assumptions):
        init=f'''import math
Ts = {PERIOD!r}
Tss = Ts
fsw = 20000.0
dt = 1e-6
Pn = 300.0
Vn = {p['dc_bus_v']!r}
In = 40.0
Rs = {p['phase_resistance_ohm']!r}
Ld = {p['ld_h']!r}
Lq = {p['lq_h']!r}
J = {p['inertia_kgm2']!r}
n_n = 3000.0
p = {p['pole_pairs']!r}
f = n_n*p/60
psi_pm = {p['pm_flux_wb']!r}
Back_emf = psi_pm*np.pi*1000/30*p
n_back_emf = 1000
V_dc = Vn
fcc = fsw/25.0
wcc = 2.0*np.pi*fcc
Kpid = Ld*wcc
Kiid = Rs*wcc
Kpiq = Lq*wcc
Kiiq = Rs*wcc
wsc = wcc/20.0
wpi = wsc/5.0
Kpw = J*wsc/(1.5*p*psi_pm)
Kiw = Kpw*wpi
'''
        api.set_model_init_code(init)
        machine=api.get_item('pmsm1')
        applied={'Rs':p['phase_resistance_ohm'],'Ld':p['ld_h'],'Lq':p['lq_h'],
                 'Psi_pm':p['pm_flux_wb'],'pms':p['pole_pairs'],'Jm':p['inertia_kgm2'],
                 'star_delta':'star','friction_coeff':0,'Rsnb_stator':1000.0,'Psi_d_init':p['pm_flux_wb']}
        api.set_property_values(machine,applied)
        actual=api.get_property_values(machine)
        for key,value in applied.items():
            if isinstance(value,str): valid=actual[key]==value
            else: valid=math.isclose(float(actual[key]),value,rel_tol=1e-10,abs_tol=1e-12)
            if not valid: raise ValueError(f'PMSM parameter readback mismatch: {key}')
        inverter=api.get_item('Three Phase Inverter1')
        api.set_property_values(inverter,{'delay_enabled':False,'losses_estimation':False,'fvd':False})
        command=api.get_item('MTPA',parent=api.get_item('current_command_generator'))
        api.set_property_values(command,{'output_fnc':SIGNED_MTPA})
        if api.get_property_value(api.prop(command,'output_fnc'))!=SIGNED_MTPA:
            raise ValueError('signed current-command code readback mismatch')
        mappings=[('w_ref','speed_regulation','w_ref','reference_speed_rpm','LabReference',math.pi/30),
                  ('load_torque','pmsm1','load_in','load_torque_nm','LabLoad',1)]
        for source_name,dest_name,port,target,probe_name,scale in mappings:
            source=api.get_item(source_name); destination=api.term(api.get_item(dest_name),port)
            conns=api.find_connections(api.term(source,'out'),destination)
            if len(conns)!=1: raise ValueError(f'unexpected {source_name} wiring')
            api.delete_item(conns[0])
            output=api.term(source,'out')
            initial=p[target]*scale
            api.set_property_values(source,{'def_value':str(initial),'execution_rate':'Ts'})
            for i,e in enumerate(events):
                if e['target']!=target: continue
                step=api.create_component('core/Step',name=f'LabStep{i}',position=(6500+i*120,7900))
                adder=api.create_component('core/Sum',name=f'LabSum{i}',position=(6580+i*120,8000))
                next_value=e['value']*scale
                api.set_property_values(step,{'step_time':str(e['at_s']),'initial_value':'0',
                    'final_value':str(next_value-initial),'execution_rate':'Ts'})
                api.set_property_values(adder,{'signs':'++','execution_rate':'Ts'})
                api.create_connection(output,api.term(adder,'in'))
                api.create_connection(api.term(step,'out'),api.term(adder,'in1'))
                output=api.term(adder,'out');initial=next_value
            api.create_connection(output,destination)
            probe=api.create_component('core/Probe',name=probe_name,position=(7000,8000))
            api.create_connection(output,api.term(probe,'in'))
        probe=api.create_component('core/Probe',name='LabTorque',position=(8100,6900))
        api.create_connection(api.term(api.get_item('PMSM JMAG_sp_outputs'),'T'),api.term(probe,'in'))
        return {'machine_readback':{k:actual[k] for k in applied},'initialization_code':init,
                'current_command_function':SIGNED_MTPA,
                'assumptions':assumptions,'scope':SCOPE,'control_period_s':PERIOD}

    def initialize(self,hil,c):
        from .runtime import require
        p=c['parameters']
        require(hil.set_source_constant_value('V_dc',value=p['dc_bus_v']),'set model DC bus')
        settings=hil.get_source_settings('V_dc')
        if not settings or not math.isclose(float(settings['value']),p['dc_bus_v'],abs_tol=1e-8):
            raise ValueError('model DC bus readback mismatch')
        requested={'w_ref':p['reference_speed_rpm']*math.pi/30,'load_torque':p['load_torque_nm']}
        for key,value in requested.items():
            require(hil.set_scada_input_value(key,value),f'set {key}')
        actual={key:hil.get_scada_input_settings(key) for key in requested}
        if any(not actual[k] or not math.isclose(float(actual[k]['input_value']),v,abs_tol=1e-8) for k,v in requested.items()):
            raise ValueError('preview initial command readback mismatch')
        return {'actual_source_settings':settings,'actual_scada_settings':actual,'scope':SCOPE}

    def describe_schedule(self,c):
        return [{**e,'scheduled_at_s':e['at_s'],'mechanism':'model_step','pipeline_compensation_s':0} for e in c['events']]

    def schedule(self,hil,c): return self.describe_schedule(c)

    def check_sampling(self,rate,count,c):
        cap=c['capture']
        if abs(rate/cap['sample_rate_hz']-1)>.01 or abs(count/rate-cap['duration_s'])>1/rate+1e-10:
            raise ValueError('actual capture differs from preview sampling/window')

    def analyze(self,path,c): return analyze_preview(path,c)
    def report(self,path,manifest): return write_preview_report(path,manifest)


def analyze_preview(path,c):
    import numpy as np
    from .analysis import load_waveforms
    d=load_waveforms(Path(path),('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
    t=np.asarray(d['t_simulation_s']); rate=1/float(np.median(np.diff(t)))
    if abs(rate/c['capture']['sample_rate_hz']-1)>.01 or len(t)<c['acceptance']['min_samples'] or \
            t[0]>2/rate or t[-1]<c['capture']['duration_s']-2/rate:
        raise ValueError('capture is incomplete or has an unexpected sample rate/start')
    speed=np.asarray(d['MechanicalSpeed_rad_s'])*30/math.pi
    ref=np.asarray(d['Reference_rad_s'])*30/math.pi
    load=np.asarray(d['Load_Nm'])
    events=[]; by_target={k:[] for k in ('reference_speed_rpm','load_torque_nm')}
    for e in c['events']: by_target[e['target']].append(e)
    checks={}
    for target,signal in [('reference_speed_rpm',ref),('load_torque_nm',load)]:
        es=by_target[target]; previous=c['parameters'][target]
        # Runtime waveforms are quantized to simulator float precision.
        tolerance=1e-3 if target=='reference_speed_rpm' else 1e-7
        for i,e in enumerate(es):
            end=es[i+1]['at_s'] if i+1<len(es) else c['capture']['duration_s']
            search=(t>=e['at_s']-1/rate)&(t<end)
            hits=np.flatnonzero(search & (np.abs(signal-previous)>tolerance))
            observed=float(t[hits[0]]) if len(hits) else None
            timing=observed is not None and e['at_s']-1/rate<=observed<=e['at_s']+4*PERIOD+1/rate
            settled=(t>=e['at_s']+4*PERIOD)&(t<end)
            level=bool(np.any(settled)) and bool(np.all(np.abs(signal[settled]-e['value'])<=tolerance))
            events.append({**e,'observed_at_s':observed,'timing_tolerance_s':4*PERIOD+1/rate,
                           'status':'passed' if timing and level else 'failed'})
            previous=e['value']
        expected=np.full(len(t),c['parameters'][target],dtype=float)
        # A small model pipeline interval is excluded only for command-level comparison.
        stable=t>=4*PERIOD+1/rate
        for e in es:
            expected[t>=e['at_s']]=e['value']
            stable &= ~((t>=e['at_s']-1/rate)&(t<e['at_s']+4*PERIOD+1/rate))
        checks[target+'_command_levels']=bool(np.any(stable)) and bool(np.all(np.abs(signal[stable]-expected[stable])<=tolerance))
    events.sort(key=lambda e:e['at_s'])
    checks['events_applied']=all(e['status']=='passed' for e in events)
    windows=[]; boundaries=[0]+[e['at_s'] for e in c['events']]+[c['capture']['duration_s']]
    for left,right in zip(boundaries,boundaries[1:]):
        start=left+c['acceptance']['settle_after_change_s']
        mask=(t>=start)&(t<right-1/rate)
        if np.count_nonzero(mask)<c['acceptance']['min_window_samples']:
            raise ValueError('insufficient complete settled-window samples')
        error=float(np.max(np.abs(speed[mask]-ref[mask])))
        windows.append({'start_s':start,'end_s':right,'sample_count':int(np.count_nonzero(mask)),
                        'mean_speed_rpm':float(np.mean(speed[mask])),'max_speed_error_rpm':error,
                        'passed':error<=c['acceptance']['max_speed_error_rpm']})
    checks['settled_speed_tracking']=all(w['passed'] for w in windows)
    balance=np.asarray(d['Ia_A'])+np.asarray(d['Ib_A'])+np.asarray(d['Ic_A'])
    maximum=float(np.max(np.abs(balance)))
    checks['three_phase_kcl']=maximum<=c['acceptance']['max_phase_current_sum_a']
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'events':events,
        'windows':windows,'capture':{'sample_count':len(t),'sample_rate_hz':rate,'start_s':float(t[0]),'end_s':float(t[-1])},
        'max_phase_current_sum_a':maximum,'max_abs_phase_current_a':max(float(np.max(np.abs(d[k]))) for k in ('Ia_A','Ib_A','Ic_A')),
        'scope':SCOPE,'sample_performance_status':'not_evaluated','analysis':{
            'filtering':'none','speed_conversion':'mechanical_rad_s * 30/pi',
            'speed_test':'maximum absolute speed-reference error in every settled segment',
            'current_test':'maximum absolute Ia+Ib+Ic; software circuit consistency only',
            'event_test':'captured command change and stable levels (0.001rpm / 1e-7Nm); up to four control periods plus one sample',
            'assumptions':c['assumptions']}}


def write_preview_report(path,manifest):
    from .reporting import _write, _image
    path=Path(path);hp=[];mp=[];outputs=[]
    if manifest.get('error'):
        hp.append('<pre>'+html.escape(manifest['error'])+'</pre>');mp.append(manifest['error'])
    if (path/'metrics.json').exists():
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from .analysis import load_waveforms
        metrics=json.loads((path/'metrics.json').read_text(encoding='utf-8'))
        d=load_waveforms(path/'waveforms.csv',('t_relative_s','t_simulation_s',*PMSMPreviewAdapter.columns))
        t=np.asarray(d['t_simulation_s'])
        with plt.rc_context({'font.family':'DejaVu Sans','axes.grid':True,'grid.alpha':.2,'path.simplify':False}):
            fig,axes=plt.subplots(3,1,sharex=True,figsize=(11,9),layout='constrained')
            axes[0].plot(t,np.asarray(d['MechanicalSpeed_rad_s'])*30/math.pi,label='Model speed',color='#0072B2')
            axes[0].plot(t,np.asarray(d['Reference_rad_s'])*30/math.pi,label='Applied reference',color='#D55E00',linestyle='--')
            axes[0].set_ylabel('Speed (rpm)')
            for key,color,style in [('Ia_A','#0072B2','-'),('Ib_A','#D55E00','--'),('Ic_A','#009E73',':')]:
                axes[1].plot(t,d[key],label=key,color=color,linestyle=style,linewidth=.65)
            axes[1].set_ylabel('Phase current (A)')
            axes[2].plot(t,d['ElectromagneticTorque_Nm'],label='Electromagnetic torque',color='#0072B2')
            axes[2].plot(t,d['Load_Nm'],label='Applied load',color='#D55E00',linestyle='--')
            axes[2].set_ylabel('Torque (N m)');axes[2].set_xlabel('Simulation time (s)')
            for ax in axes:
                for e in metrics['events']: ax.axvline(e['at_s'],color='#555',linestyle=':',linewidth=.8)
                ax.legend(loc='upper right',fontsize=8)
            fig.suptitle('PMSM software rehearsal - equivalent-star hypothesis, ideal angle feedback')
            output=path/'waveforms.png';fig.savefig(output,dpi=130,facecolor='white');plt.close(fig);outputs.append(output)
        caption='完整原始采样；虚线标出请求事件，实际生效时刻由命令波形复算。电流图为此采样率下的记录。'
        hp.append(_image(output,caption));mp.append('![PMSM 软件预演](waveforms.png)\n\n'+caption)
        for title,value in [('软件检查与分段结果',metrics),('实际参数与假设',manifest.get('actual_model_parameters'))]:
            text=json.dumps(value,ensure_ascii=False,indent=2)
            hp.append('<h2>'+title+'</h2><pre>'+html.escape(text)+'</pre>');mp.append('## '+title+'\n\n```json\n'+text+'\n```')
    outputs.extend(_write(path,'低压 PMSM 软件预演',manifest.get('status','error'),hp,mp,scope=SCOPE))
    return outputs
