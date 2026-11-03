"""Offline preparation for the supplied board. No hardware or Typhoon API calls."""
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import math
import re

from .cases import read_json
from .utils import PROJECT, sha256

DEFAULT_PROFILE = PROJECT/'configs/tle9877_sample.json'
FRAME_ALIASES = {'control':'ControlLIN','status':'StatusLIN','version':'VARIANTLIN'}


def pid(frame_id):
    if type(frame_id) is not int or not 0 <= frame_id <= 63:
        raise ValueError('LIN ID must be an integer in 0..63')
    b = [(frame_id >> i) & 1 for i in range(6)]
    return frame_id | ((b[0]^b[1]^b[2]^b[4]) << 6) | ((1^b[1]^b[3]^b[4]^b[5]) << 7)


def byte_values(data):
    if isinstance(data, str):
        tokens = re.split(r'[\s,]+', data.strip())
        if any(not re.fullmatch(r'(?:0x)?[0-9a-fA-F]{2}', t) for t in tokens):
            raise ValueError('data must contain two-digit hexadecimal bytes, e.g. "64 00"')
        data = [int(t,16) for t in tokens]
    if not isinstance(data,(list,tuple,bytes,bytearray)) or not data:
        raise ValueError('a nonempty byte sequence is required')
    if any(type(v) is not int or not 0 <= v <= 255 for v in data):
        raise ValueError('each byte must be an integer in 0..255')
    return list(data)


def checksum(frame_id, data):
    """LIN enhanced checksum; diagnostic IDs 0x3C/0x3D use classic checksum."""
    protected_id = pid(frame_id)
    total = 0 if frame_id in (60,61) else protected_id
    for value in byte_values(data):
        total += value
        total = (total & 255)+(total >> 8)
    return (~total) & 255


def load_profile(path=DEFAULT_PROFILE):
    profile = read_json(path)
    if type(profile.get('schema_version')) is not int or profile['schema_version'] != 1:
        raise ValueError('sample profile schema_version must be 1')
    if profile.get('sample_id') != 'tle9877_received_board':
        raise ValueError('this tool is scoped to tle9877_received_board')
    reference = profile['sources']['ldf']
    source = (PROJECT/reference['project_copy']).resolve()
    if not source.is_relative_to(PROJECT/'data/tle9877') or sha256(source) != reference['sha256']:
        raise ValueError('LDF snapshot is missing, changed or outside data/tle9877')
    # Included in THCC's bundled Python; no Typhoon session or online dependency.
    import ldfparser
    ldf = ldfparser.parse_ldf_to_dict(str(source))
    if ldf['protocol_version'] != '2.1' or ldf['speed'] != 19200:
        raise ValueError('unexpected supplied LDF protocol or bitrate')
    signals = {s['name']:s for s in ldf['signals']}
    frames = {f['name']:f for f in ldf['frames']}
    if set(frames) != set(FRAME_ALIASES.values()):
        raise ValueError('expected the three supplied business frames')
    for name, frame_id, length in [('ControlLIN',38,2),('StatusLIN',37,8),('VARIANTLIN',39,2)]:
        f=frames[name]
        if (f['frame_id'],f['length']) != (frame_id,length):
            raise ValueError('frame identity differs from supplied board contract')
        used=set()
        for item in f['signals']:
            s=signals[item['signal']]
            bits=set(range(item['offset'],item['offset']+s['width']))
            if min(bits)<0 or max(bits)>=length*8 or used & bits or s['publisher']!=f['publisher']:
                raise ValueError('invalid LDF signal layout or publisher')
            used |= bits
    return profile, ldf


def _encodings(ldf):
    types={t['name']:t['values'] for t in ldf['signal_encoding_types']}
    return {s:types[r['encoding']] for r in ldf['signal_representations'] for s in r['signals']}


def decode_frame(frame, data, *, identifier=None, identifier_kind='id', received_checksum=None,
                 profile_path=DEFAULT_PROFILE):
    profile,ldf=load_profile(profile_path)
    frame=FRAME_ALIASES.get(frame,frame)
    frames={f['name']:f for f in ldf['frames']}
    if frame not in frames:
        raise ValueError('frame must be control, status or version')
    f=frames[frame]; data=byte_values(data)
    if len(data)!=f['length']:
        raise ValueError(f"{frame} requires exactly {f['length']} data bytes")
    if identifier_kind not in ('id','pid'):
        raise ValueError('identifier_kind must be id or pid')
    expected_id=f['frame_id'] if identifier_kind=='id' else pid(f['frame_id'])
    if identifier is not None and (type(identifier) is not int or identifier!=expected_id):
        raise ValueError('identifier/PID parity does not match selected frame')
    expected_checksum=checksum(f['frame_id'],data)
    if received_checksum is not None and (type(received_checksum) is not int or received_checksum!=expected_checksum):
        raise ValueError(f'checksum mismatch: expected 0x{expected_checksum:02X}')
    word=int.from_bytes(bytes(data),'little')
    signals={s['name']:s for s in ldf['signals']}; enc=_encodings(ldf)
    decoded={}; used=0
    for field in f['signals']:
        name=field['signal']; width=signals[name]['width']; offset=field['offset']
        mask=(1<<width)-1; raw=(word>>offset)&mask; used|=mask<<offset
        item={'raw':raw,'validity':'unencoded','value':None,'unit':None,'label':None}
        for rule in enc.get(name,[]):
            if rule['type']=='physical' and rule['min']<=raw<=rule['max']:
                value=Decimal(raw)*Decimal(str(rule['scale']))+Decimal(str(rule['offset']))
                item.update(validity='valid',value=float(value),unit=rule['unit']);break
            if rule['type']=='logical' and raw==rule['value']:
                state='invalid' if rule['text']=='Signal invalid' else ('initial' if rule['text']=='initial' else 'valid')
                item.update(validity=state,label=rule['text']);break
        else:
            if name in enc:
                item['validity']='invalid' if raw==255 and width==8 else 'undefined'
        if 'Reserved' in name:
            item['validity']='reserved'
        decoded[name]=item
    unassigned=word & (((1<<(8*len(data)))-1)^used)
    return {'status':'passed','scope':'offline_decode','frame':frame,'id':f['frame_id'],
        'pid':pid(f['frame_id']),'publisher':f['publisher'],'data':data,'data_hex':' '.join(f'{b:02X}' for b in data),
        'checksum':expected_checksum,'checksum_verified':received_checksum is not None,
        'checksum_policy':profile['lin']['checksum_policy'],'signals':decoded,
        'unassigned_bits_raw':unassigned,'warnings':['nonzero unassigned control bits'] if unassigned else []}


def encode_control(rpm, post_set=0, *, profile_path=DEFAULT_PROFILE):
    _,ldf=load_profile(profile_path)
    if isinstance(rpm,bool) or not isinstance(rpm,(int,float)) or not math.isfinite(rpm):
        raise ValueError('rpm must be a finite number')
    rule=_encodings(ldf)['ControlSetspeed'][0]
    scale=Decimal(str(rule['scale'])); value=Decimal(str(rpm))
    if not 0<=value<=Decimal(rule['max'])*scale:
        raise ValueError('requested rpm is outside LDF encoding range 0..5689.6; no clipping')
    if type(post_set) is not int or post_set not in range(6):
        raise ValueError('post_set command must be 0..5; 6 undefined, 7 initial')
    raw=int((value/scale).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    result=decode_frame('control',[raw,post_set<<4],profile_path=profile_path)
    result.update(scope='offline_encode',requested_rpm=float(rpm),encoded_rpm=float(Decimal(raw)*scale),
                  rounding='nearest_code_half_up',firmware_target_rpm=None,
                  sent_to_hardware=False)
    return result


def check_sample(profile_path=DEFAULT_PROFILE, current_a=None):
    p,ldf=load_profile(profile_path)
    source_checks={}
    for name,source in p['sources'].items():
        path=(PROJECT/source['workspace_path']).resolve()
        source_checks[name]='matches' if path.is_file() and sha256(path)==source['sha256'] else ('missing' if not path.is_file() else 'changed')
    errors=[]
    if any(v=='changed' for v in source_checks.values()): errors.append('supplied source hash changed')
    board=p['board']; motor=p['motor']
    for name,value in [('recommended_supply_v',board['recommended_supply_v']),('maximum_supply_v',board['maximum_supply_v']),
                       ('shunt_resistance_ohm',board['shunt_resistance_ohm']),
                       ('phase_resistance_ohm',motor['phase_resistance_ohm']['value']),
                       ('phase_inductance_h',motor['phase_inductance_h']['value'])]:
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            errors.append(f'{name} must be finite and positive')
    if not errors and board['recommended_supply_v']>board['maximum_supply_v']: errors.append('supply recommendation exceeds board maximum')
    if motor['pole_pairs']['value']*2!=motor['poles']: errors.append('pole count and pole pairs differ')
    if len(p['interfaces'])!=18 or len({x['row'] for x in p['interfaces']})!=18: errors.append('18 distinct interface rows required')
    schedules=[]
    for table in ldf['schedule_tables']:
        cycle=sum(x['delay'] for x in table['schedule'])
        schedules.append({'name':table['name'],'cycle_s':cycle,'slots':table['schedule']})
    missing=[k for k,v in motor.items() if isinstance(v,dict) and v.get('value') is None]
    difference=None
    if current_a is not None:
        if isinstance(current_a,bool) or not isinstance(current_a,(int,float)) or not math.isfinite(current_a):
            raise ValueError('current_a must be finite')
        if errors: raise ValueError('; '.join(errors))
        difference=current_a*board['shunt_resistance_ohm']
    # Readiness must be earned by future hardware/model-specific validation.
    return {'status':'failed' if errors else 'passed','scope':'offline_source_and_preparation_checks',
            'errors':errors,'sources':source_checks,'interfaces':len(p['interfaces']),
            'ldf':{'bitrate':ldf['speed'],'signal_count':len(ldf['signals']),'frames':ldf['frames'],'schedules':schedules},
            'sample_model_ready':False,'hardware_ready':False,'missing_motor_parameters':missing,
            'pending':p['pending'],'shunt_relation':{'current_a':current_a,'differential_v':difference,
                'equation':'V_SHP_minus_SHN = I * Rshunt; polarity and injection node require confirmation',
                'output_voltage_command':None},'performance_status':'not_evaluated'}
