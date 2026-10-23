"""Official generic PV plant: independently initialized HzWatt points."""
from copy import deepcopy
import math
from ..config import number

REFERENCE_POINTS = {0.985: 1.2, 0.996: 1.0, 1.0: 1.0, 1.02: .68}
PLANT = 'PV Power Plant (Generic)1'
UI = 'PV Power Plant (Generic) UI1.'

class PVAdapter:
    model_id = 'generic_pv_plant'
    schema_version = 1
    has_events = False
    capture_before_start = False
    sources = ()
    signals = tuple(UI+n for n in ('Pmeas_kW','Pref_fb_kW','Fmeas_Hz','Enable_fb','alarm_msg','Qmeas_kVAr'))
    columns = ('ActivePower_kW','PowerReference_kW','Frequency_Hz','Enable','AlarmCode','ReactivePower_kVAr')
    units = dict(zip(columns,('kW','kW','Hz','1','code','kVAr')))
    changes = ['Configure grid_code_fcn=HzWatt, opc_pu=0.3 and Pnom=250000 W in the per-run model copy.']
    numeric_rules = {
        'parameters': {'frequency_pu':(.985,1.02)},
        'capture': {'settle_s':(10,30),'duration_s':(1,5),'sample_rate_hz':(2000,10000),'wall_timeout_s':(60,600)},
        'acceptance': {'max_relative_power_error':(.0001,.01),'max_frequency_error_hz':(.001,.01),'min_samples':(2000,100000)}
    }
    setting_stages = {'parameters':'after_load_before_start','capture':'capture_setup','acceptance':'analysis_only'}
    event_capabilities = {'max_per_run':0,'targets':{}}
    conditional_constraints = ['frequency_in_official_reference_points_0.985_0.996_1.0_1.02',
                              'capture_samples_between_minimum_and_100000',
                              'fixed_nominal_250kW_50Hz_headroom_0.3']
    def validate(self,raw,sweep=False):
        if sweep: raise ValueError('PV uses independent configurations and run-case; sweep is RLC-only')
        if not isinstance(raw,dict) or set(raw)!={'schema_version','model','backend','parameters','capture','acceptance'}:
            raise ValueError('PV configuration requires schema_version/model/backend/parameters/capture/acceptance')
        c=deepcopy(raw)
        if type(c['schema_version']) is not int or c['schema_version']!=1: raise ValueError('PV schema_version must be integer 1')
        if c['model']!=self.model_id or c['backend']!='virtual_hil': raise ValueError('PV requires generic_pv_plant on virtual_hil')
        for group,rules in self.numeric_rules.items():
            if not isinstance(c[group],dict) or set(c[group])!=set(rules): raise ValueError(f'invalid {group} fields')
            for key,(lo,hi) in rules.items(): c[group][key]=number(c[group][key],group+'.'+key,lo,hi)
        if c['parameters']['frequency_pu'] not in REFERENCE_POINTS: raise ValueError('frequency has no declared official reference point')
        n=c['acceptance']['min_samples']
        if not n.is_integer(): raise ValueError('min_samples must be integer')
        c['acceptance']['min_samples']=int(n)
        total=c['capture']['duration_s']*c['capture']['sample_rate_hz']
        if total<n or total>100000: raise ValueError('capture sample count outside declared limits')
        return c
    def inspect_parameters(self,api):
        item=api.get_item(PLANT)
        if item is None: raise ValueError('PV component missing')
        return {k:api.get_property_value(api.prop(item,k)) for k in ('grid_code_fcn','opc_pu','Pnom')}
    def prepare(self,api,config):
        item=api.get_item(PLANT)
        if item is None: raise ValueError('PV component missing')
        for k,v in {'grid_code_fcn':'HzWatt','opc_pu':'0.3','Pnom':'250000'}.items():
            api.set_property_value(api.prop(item,k),v)
        actual=self.inspect_parameters(api)
        if actual['grid_code_fcn']!='HzWatt' or not math.isclose(float(actual['opc_pu']),.3,abs_tol=1e-12) or not math.isclose(float(actual['Pnom']),250000,abs_tol=1e-8):
            raise ValueError('PV model parameter readback mismatch')
        return actual
    def initialize(self,hil,config):
        from ..runtime import require
        values={'Grid UI1.Connect':1.,'Grid UI1.Grid_Vrms_cmd':1.,
                'Grid UI1.Grid_freq_cmd':config['parameters']['frequency_pu'],
                UI+'Enable':1.,UI+'Pcurtailment':1.,UI+'HzWatt enable':1.,
                UI+'Pcurtailment rate of change':1.,UI+'MPPT rate of change':1.}
        readback={}
        for name,value in values.items():
            require(hil.set_scada_input_value(name,value),f'set {name}')
            readback[name]=hil.get_scada_input_settings(name)
            if not readback[name] or not math.isclose(float(readback[name]['input_value']),value,abs_tol=1e-9):
                raise ValueError(f'PV SCADA readback mismatch: {name}')
        return {'requested_scada_settings':values,'actual_scada_settings':readback,
                'nominal_power_w':250000.,'nominal_frequency_hz':50.}
    def schedule(self,hil,config): return []
    def check_sampling(self,rate,count,config):
        if rate<2000 or count<config['acceptance']['min_samples']: raise ValueError('PV capture is too short or slow')
        if not math.isclose(rate,config['capture']['sample_rate_hz'],rel_tol=.001): raise ValueError('PV sample rate quantization exceeds allowance')
    def analyze(self,path,config):
        from ..pv_analysis import analyze_pv
        return analyze_pv(path,config)
    def report(self,path,manifest):
        from ..pv_reporting import write_pv_report
        return write_pv_report(path,manifest)
